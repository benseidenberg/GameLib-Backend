from fastapi import APIRouter, HTTPException
from src.services.clusters import ClustersService
from src.services.filtering import FilteringService
from src.db.repositories.games_db import GamesRepository
from src.schemas.user_schema import User
from src.db.supabase_client import supabase
import os
import httpx
import asyncio
import random

# Get Steam API key from environment variables (loaded in main.py)
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
if not STEAM_API_KEY:
    raise ValueError("STEAM_API_KEY environment variable is required")

router = APIRouter()

# Initialize services
clusters_service = ClustersService()
filtering_service = FilteringService()


@router.get("/clusters/{steam_id}")
async def get_clusters(steam_id: int):
    """
    Get game recommendations/clusters for a user by Steam ID
    """
    try:
        # Validate steam_id
        if steam_id <= 0 or steam_id > 999999999999999999:
            raise HTTPException(status_code=400, detail="Invalid Steam ID")
        
        clusters = await clusters_service.get_cluster_recommendations(steam_id)
        if not clusters:
            raise HTTPException(status_code=404, detail="No recommendations found")
        return clusters
    except ValueError as e:
        print(f"DEBUG: ValueError occurred: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"DEBUG: Unexpected error occurred: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/steam/profile/{steam_id}")
async def get_steam_profile(steam_id: int):
    """
    Get Steam user's owned games and play data
    """
    try:
        profile_data = await User.fetch_profile_data(steam_id)
        if not profile_data:
            raise HTTPException(status_code=404, detail="Steam profile not found or private")
        
        return profile_data
                
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Steam profile: {str(e)}")


@router.get("/steam/player/{steam_id}")
async def get_steam_player_summary(steam_id: int):
    """
    Get Steam user's profile information (name, avatar, etc.)
    """
    try:
        player_data = await User.fetch_player_summary(steam_id)
        if not player_data:
            raise HTTPException(status_code=404, detail="Player not found")
        
        return player_data
                
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Steam player summary: {str(e)}")


@router.get("/steam/game-details/{game_id}")
async def get_steam_game_details_endpoint(game_id: int):
    """
    Get detailed information about a specific Steam game
    """
    try:
        # Validate game_id
        if game_id <= 0 or game_id > 999999999:
            raise HTTPException(status_code=400, detail="Invalid Steam app ID")
        
        game = await GamesRepository.fetch_details(game_id)
        
        if not game:
            raise HTTPException(status_code=404, detail=f"Game with game_id {game_id} not found or filtered out")
        
        return game
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"DEBUG: Error in get_steam_game_details for game_id {game_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching game details: {str(e)}")


@router.get("/recommendations/clusters/{steam_id}")
async def get_cluster_recommendations(steam_id: int):
    """
    Get 5 cluster-based game recommendations with full details
    Uses Steam's clustering API to find games based on user's playtime patterns
    """
    try:
        # Get game clusters for the provided Steam ID
        clusters_data = await clusters_service.get_cluster_recommendations(steam_id)
        
        # Extract app IDs from clusters with their source games
        game_ids_with_source = []  # Will store tuples of (game_id, source_game_info)
        if clusters_data and isinstance(clusters_data, dict):
            # Handle the actual structure: clusters_data['response']['clusters']
            response_data = clusters_data.get('response', {})
            clusters_list = response_data.get('clusters', [])
                        
            if clusters_list:
                # Sort clusters by relevance (recent playtime + total playtime + popularity)
                def cluster_score(cluster):
                    recent_playtime = cluster.get('playtime_2weeks', 0)
                    total_playtime = cluster.get('playtime_forever', 0)
                    popularity = cluster.get('similar_item_popularity_score', 0)
                    
                    # Weight recent activity higher, but also consider total time and popularity
                    score = (recent_playtime * 10) + (total_playtime * 0.1) + (popularity * 1000)
                    return score
                
                # Sort clusters by relevance score
                sorted_clusters = sorted(clusters_list, key=cluster_score, reverse=True)
                
                for i, cluster in enumerate(sorted_clusters[:5]):
                    score = cluster_score(cluster)
                    recent = cluster.get('playtime_2weeks', 0)
                    total = cluster.get('playtime_forever', 0)
                
                # Take from the most relevant clusters - ONE game per cluster for variety
                for cluster in sorted_clusters[:10]:  # Check top 10 clusters to ensure we get 5 games
                    if len(game_ids_with_source) >= 5:
                        break
                        
                    cluster_id = cluster.get('cluster_id')
                    
                    # Get played games and similar games
                    similar_apps = cluster.get('similar_items_appids', [])
                    played_apps = cluster.get('played_appids', [])
                    
                    # Shuffle similar games to get variety on each request
                    if similar_apps:
                        similar_apps = list(similar_apps)  # Make a copy
                        random.shuffle(similar_apps)
                    
                    # For each cluster, we'll pick one played game as the "source"
                    # and recommend ONE similar game based on it
                    if played_apps and similar_apps:
                        # Shuffle played apps too to vary which game is used as source
                        played_apps_list = list(played_apps)
                        random.shuffle(played_apps_list)
                        source_game_id = played_apps_list[0]
                        
                        # Fetch source game details
                        source_game_info = await GamesRepository.fetch_basic(source_game_id)
                        
                        if source_game_info:
                            # Add ONE similar game from this cluster for variety
                            for game_id in similar_apps:
                                # Check if we already have this game_id
                                existing_game_ids = [item[0] for item in game_ids_with_source]
                                if game_id not in existing_game_ids:
                                    game_ids_with_source.append((game_id, source_game_info))
                                    break  # Only take ONE game per cluster
                
        # If we don't have enough games from clusters, add some popular games as fallback
        if len(game_ids_with_source) < 5:
            fallback_games = [570, 440, 730]  # Dota 2, TF2, CS:GO
            
            for game_id in fallback_games:
                if len(game_ids_with_source) >= 5:
                    break
                # Add fallback games without a specific source
                existing_game_ids = [item[0] for item in game_ids_with_source]
                if game_id not in existing_game_ids:
                    game_ids_with_source.append((game_id, {"title": "Popular games", "game_id": None}))
        
        # Limit to 5 games
        game_ids_with_source = game_ids_with_source[:5]
        
        # Fetch game details for each app ID with content filtering
        games_data = []
        
        for game_id, source_info in game_ids_with_source:
            game = await GamesRepository.fetch_details(game_id)
            if game:  # Only add if not filtered out
                # Add the source information to the game
                game.based_on = {
                    "title": source_info["title"],
                    "game_id": source_info.get("game_id")
                }
                games_data.append(game)
        
        # If we don't have enough games after filtering, try to get more from additional clusters
        if len(games_data) < 5 and clusters_data:
            response_data = clusters_data.get('response', {})
            clusters_list = response_data.get('clusters', [])
            
            # Sort clusters by relevance (reuse the scoring function)
            def cluster_score(cluster):
                recent_playtime = cluster.get('playtime_2weeks', 0)
                total_playtime = cluster.get('playtime_forever', 0)
                popularity = cluster.get('similar_item_popularity_score', 0)
                score = (recent_playtime * 10) + (total_playtime * 0.1) + (popularity * 1000)
                return score
            
            sorted_clusters = sorted(clusters_list, key=cluster_score, reverse=True)
            
            # Try more clusters if available
            for cluster in sorted_clusters[5:15]:  # Try clusters 6-15
                if len(games_data) >= 5:
                    break
                
                played_apps = cluster.get('played_appids', [])
                similar_apps = cluster.get('similar_items_appids', [])
                
                # Shuffle to get variety
                if similar_apps:
                    similar_apps = list(similar_apps)
                    random.shuffle(similar_apps)
                
                if played_apps:
                    played_apps_list = list(played_apps)
                    random.shuffle(played_apps_list)
                    source_game_id = played_apps_list[0]
                    source_game_info = await GamesRepository.fetch_basic(source_game_id)
                    
                    if source_game_info:
                        for game_id in similar_apps[:5]:  # Try more games per cluster
                            if len(games_data) >= 5:
                                break
                            
                            # Check if we already have this game
                            existing_game_ids = [game.game_id for game in games_data]
                            if game_id not in existing_game_ids:
                                game = await GamesRepository.fetch_details(game_id)
                                if game:
                                    game.based_on = {
                                        "title": source_game_info["title"],
                                        "game_id": source_game_info.get("game_id")
                                    }
                                    games_data.append(game)
        
        # Final fallback to safe, popular games if still not enough
        if len(games_data) < 5:
            safe_fallback_games = [570, 440, 730, 359550, 271590]  # Dota 2, TF2, CS:GO, Rainbow Six, GTA V
            for game_id in safe_fallback_games:
                if len(games_data) >= 5:
                    break
                
                existing_game_ids = [game.game_id for game in games_data]
                if game_id not in existing_game_ids:  # Avoid duplicates
                    game = await GamesRepository.fetch_details(game_id)
                    if game:
                        game.based_on = {
                            "title": "Popular games",
                            "game_id": None
                        }
                        games_data.append(game)
        
        return {
            "message": "Cluster recommendations successful",
            "steam_id": steam_id,
            "total_games": len(games_data),
            "games": games_data
        }
        
    except Exception as e:
        print(f"DEBUG: Error in get_cluster_recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting cluster recommendations: {str(e)}")