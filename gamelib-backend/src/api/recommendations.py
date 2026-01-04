from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from src.services.clusters import ClustersService
from src.services.filtering import FilteringService
from src.services.ai_chatbot import (
    load_steam_dataset,
    get_dataset_status as chatbot_get_dataset_status,
    reload_dataset as chatbot_reload_dataset,
    analyze_prompt_with_ai,
    extract_price_preference,
    find_similar_games,
    generate_recommendation_explanation
)
from src.db.repositories.games_db import GamesRepository
from src.db.repositories.users_db import UsersRepository
from src.schemas.user_schema import User
from src.schemas.game_schema import Game
from src.db.supabase_client import supabase
import os
from typing import Optional, List, Dict, Any
import random

# Get Steam API key from environment variables (loaded in main.py)
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
if not STEAM_API_KEY:
    raise ValueError("STEAM_API_KEY environment variable is required")

# Pydantic model for AI recommendation request
class AIRecommendationRequest(BaseModel):
    prompt: str
    steam_id: Optional[int] = None  # Optional Steam ID to filter out owned games

router = APIRouter()

# Initialize services
clusters_service = ClustersService()
filtering_service = FilteringService()


@router.get("/dataset/status")
async def get_dataset_status():
    """
    Get the status of the dataset cache
    """
    return chatbot_get_dataset_status()


@router.post("/dataset/reload")
async def reload_dataset():
    """
    Force reload the dataset from Hugging Face
    """
    return await chatbot_reload_dataset()


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
async def get_steam_game_details(game_id: int):
    """
    Get detailed information about a specific Steam game from database or Steam API
    """
    try:
        # Validate game_id
        if game_id <= 0 or game_id > 999999999:
            raise HTTPException(status_code=400, detail="Invalid Steam app ID")
        
        # Use GamesRepository to fetch game details (checks DB first, then Steam API)
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
    OUTDATED - This endpoint is deprecated and may be removed in future versions.
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
        print(f"DEBUG: Error in test_recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting test recommendations: {str(e)}")


@router.post("/recommendations/ai")
async def get_ai_recommendations(request: AIRecommendationRequest):
    """
    Get AI-powered game recommendations based on a text prompt.
    Uses OpenAI to analyze the prompt and the Steam games dataset to find similar games.
    """
    try:
        prompt = request.prompt.strip()
        
        # Validate prompt
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        
        print(f"DEBUG: AI recommendations requested with prompt: {prompt[:100]}...")
        
        # Step 0: Get user's owned games if Steam ID is provided
        owned_games = []
        if request.steam_id:
            profile_data = await User.fetch_profile_data(request.steam_id)
            if profile_data and profile_data.get('games'):
                # Extract game IDs from the profile data
                owned_games = [int(game_id) for game_id in profile_data['games'].keys()]
                print(f"DEBUG: User owns {len(owned_games)} games, will filter them out")
        
        # Step 1: Analyze the prompt with OpenAI
        ai_analysis = await analyze_prompt_with_ai(prompt)
        print(f"DEBUG: AI Analysis: {ai_analysis}")
        
        # Step 2: Extract price preferences
        price_info = extract_price_preference(prompt, ai_analysis)
        print(f"DEBUG: Price preferences: {price_info}")
        
        # Step 3: Find similar games using the dataset
        similar_games = await find_similar_games(ai_analysis, price_info, limit=5, owned_games=owned_games, original_prompt=prompt)
        
        # Step 4: Enhance results with game details from database
        enhanced_games = []
        for game in similar_games:
            # Game is already a Game object, convert to dict for response
            enhanced_game = {
                "name": game.name,
                "description": game.short_description,
                "genres": game.genres,
                "tags": game.tags,
                "categories": game.categories,
                "similarity_score": game.recommendation_score,
                "price": game.price,
                "price_usd": game.price_usd,
                "steam_appid": game.game_id,
                "app_id": game.game_id,
                "developers": game.developers,
                "publishers": game.publishers,
                "release_date": game.release_date,
                "required_age": game.required_age,
                "positive_ratings": game.positive,
                "negative_ratings": game.negative,
                "steam_url": game.steam_url,
                "image": game.header_image,
                "platforms": game.platforms,
                "languages": game.languages,
                "content": game.content
            }
            
            # Try to get additional info from database if we have an app_id
            if game.game_id:
                try:
                    # Use GamesRepository to fetch full game details
                    game_details = await GamesRepository.fetch_details(game.game_id)
                    if game_details:
                        # Merge database data with dataset data (database data takes precedence)
                        enhanced_game.update({
                            "steam_title": game_details.name,
                            "steam_description": game_details.short_description,
                            "steam_image": game_details.header_image,
                            "steam_price": game_details.price,
                            "steam_genres": game_details.genres,
                            "steam_url": game_details.steam_url,
                            "developers": game_details.developers,
                            "publishers": game_details.publishers
                        })
                except Exception as e:
                    print(f"DEBUG: Error fetching game details for {game.game_id}: {str(e)}")
            
            enhanced_games.append(enhanced_game)
        
        # Step 5: Generate explanation using AI
        explanation = await generate_recommendation_explanation(prompt, ai_analysis, enhanced_games)
        
        # Construct response with optional redirect message
        response_data = {
            "message": "AI recommendations generated successfully",
            "prompt": prompt,
            "analysis": {
                "preferences": ai_analysis,
                "price_constraints": price_info
            },
            "explanation": explanation,
            "total_games": len(enhanced_games),
            "recommendations": enhanced_games
        }
        
        # Include redirect message if present
        if ai_analysis.get("redirect_message"):
            response_data["redirect_message"] = ai_analysis["redirect_message"]
        
        return response_data
        
    except Exception as e:
        print(f"DEBUG: Error in get_ai_recommendations: {str(e)}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error getting AI recommendations: {str(e)}")
