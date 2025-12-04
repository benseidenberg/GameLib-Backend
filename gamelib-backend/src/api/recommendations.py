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
from src.schemas.user_schema import User
from src.db.supabase_client import supabase
import os
import httpx
import asyncio
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


async def get_steam_app_details(app_id: int):
    """
    Fetch detailed game information from Steam API with content filtering
    """
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&format=json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Steam API returns data with app_id as key
                app_data = data.get(str(app_id))
                if app_data and app_data.get('success') and 'data' in app_data:
                    game_data = app_data['data']
                    
                    # Check if content is appropriate
                    if not is_content_appropriate(game_data):
                        print(f"DEBUG: Filtered out inappropriate content for app_id: {app_id}")
                        return None
                    
                    # Extract relevant information
                    game_info = {
                        "app_id": app_id,
                        "title": game_data.get('name', 'Unknown Game'),
                        "description": game_data.get('short_description', ''),
                        "image": game_data.get('header_image', ''),
                        "price": game_data.get('price_overview', {}).get('final_formatted', 'Free'),
                        "genres": [genre.get('description', '') for genre in game_data.get('genres', [])],
                        "categories": [cat.get('description', '') for cat in game_data.get('categories', [])],
                        "developers": game_data.get('developers', []),
                        "publishers": game_data.get('publishers', []),
                        "release_date": game_data.get('release_date', {}).get('date', ''),
                        "steam_url": f"https://store.steampowered.com/app/{app_id}/"
                    }
                    
                    return game_info
                else:
                    return None
            else:
                return None
                
    except Exception as e:
        print(f"DEBUG: Error fetching Steam app details for {app_id}: {str(e)}")
        return None


def is_content_appropriate(game_data):
    """
    Check if game content is appropriate (filters out sexual/adult content)
    """
    try:
        # Check content descriptors for adult content
        content_descriptors = game_data.get('content_descriptors', {})
        if content_descriptors:
            descriptor_ids = content_descriptors.get('ids', [])
            descriptor_notes = content_descriptors.get('notes') or ''
            
            # Steam's adult content descriptor IDs
            adult_descriptor_ids = [3, 4]  # 3: Nudity/Sexual Content, 4: Adult Only Sexual Content
            
            if any(desc_id in adult_descriptor_ids for desc_id in descriptor_ids):
                return False
            
            # Check descriptor notes for sexual content keywords
            sexual_keywords = ['sexual', 'mature', 'adult', 'erotic', 'hentai']
            if any(keyword in descriptor_notes.lower() for keyword in sexual_keywords):
                return False
        
        # Check age ratings
        required_age = game_data.get('required_age', 0)
        try:
            # Convert to int if it's a string
            required_age_int = int(required_age) if required_age else 0
            if required_age_int >= 18:
                # Additional check for adult content categories
                categories = game_data.get('categories', [])
                for category in categories:
                    cat_desc = (category.get('description') or '').lower()
                    if 'adult only' in cat_desc or 'mature' in cat_desc:
                        return False
        except (ValueError, TypeError):
            # If conversion fails, skip age-based filtering for this game
            print(f"DEBUG: Could not convert required_age '{required_age}' to int, skipping age check")
            pass
        
        # Check game name and description for inappropriate content
        game_name = (game_data.get('name') or '').lower()
        game_desc = (game_data.get('short_description') or '').lower()
        
        # List of inappropriate keywords
        inappropriate_keywords = [
            'hentai', 'porn', 'erotic', 'xxx', 'adult only', 'sexual',
             'strip', 'mature content', 'adult content'
        ]
        
        # Check if any inappropriate keywords are in the title or description
        for keyword in inappropriate_keywords:
            if keyword in game_name or keyword in game_desc:
                return False
        
        # Check genres for adult content
        genres = game_data.get('genres', [])
        for genre in genres:
            genre_desc = (genre.get('description') or '').lower()
            if any(keyword in genre_desc for keyword in ['adult', 'sexual', 'mature']):
                return False
        
        return True
        
    except Exception as e:
        print(f"DEBUG: Error in content filtering: {str(e)}")
        # If there's an error in filtering, err on the side of caution and allow the content
        return True


async def get_steam_app_details_basic(app_id: int):
    """
    Fetch basic game details (just title and app_id) for source games
    """
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&format=json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Steam API returns data with app_id as key
                app_data = data.get(str(app_id))
                if app_data and app_data.get('success') and 'data' in app_data:
                    game_data = app_data['data']
                    
                    return {
                        "app_id": app_id,
                        "title": game_data.get('name', 'Unknown Game')
                    }
            
            return None
            
    except Exception as e:
        print(f"DEBUG: Error fetching basic Steam app details for {app_id}: {str(e)}")
        return None
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
        print(f"DEBUG: Error in test_recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting test recommendations: {str(e)}")


async def get_user_owned_games(steam_id: int) -> List[int]:
    """
    Get list of app IDs that the user already owns
    """
    try:
        url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json&include_appinfo=1&include_played_free_games=1"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                
                if "response" in data and "games" in data["response"]:
                    games = data["response"]["games"]
                    owned_app_ids = [game.get("appid") for game in games if game.get("appid")]
                    print(f"DEBUG: User {steam_id} owns {len(owned_app_ids)} games")
                    return owned_app_ids
                else:
                    print(f"DEBUG: No games found for user {steam_id}")
                    return []
            else:
                print(f"DEBUG: Error fetching owned games for {steam_id}: {response.status_code}")
                return []
                
    except Exception as e:
        print(f"DEBUG: Error getting owned games for {steam_id}: {str(e)}")
        return []


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
            owned_games = await get_user_owned_games(request.steam_id)
            print(f"DEBUG: User owns {len(owned_games)} games, will filter them out")
        
        # Step 1: Analyze the prompt with OpenAI
        ai_analysis = await analyze_prompt_with_ai(prompt)
        print(f"DEBUG: AI Analysis: {ai_analysis}")
        
        # Step 2: Extract price preferences
        price_info = extract_price_preference(prompt, ai_analysis)
        print(f"DEBUG: Price preferences: {price_info}")
        
        # Step 3: Find similar games using the dataset
        similar_games = await find_similar_games(ai_analysis, price_info, limit=5, owned_games=owned_games, original_prompt=prompt)
        
        # Step 4: Enhance results with Steam API data if possible
        enhanced_games = []
        for game in similar_games:
            enhanced_game = game.copy()
            
            # Ensure steam_appid is always included in the response
            enhanced_game["app_id"] = game.get('steam_appid', None)
            
            # Try to get additional info from Steam API if we have an app_id
            steam_appid = game.get('steam_appid')
            if steam_appid and str(steam_appid).isdigit():
                try:
                    steam_info = await get_steam_app_details(int(steam_appid))
                    if steam_info:
                        # Merge Steam API data with dataset data
                        enhanced_game.update({
                            "steam_title": steam_info.get("title"),
                            "steam_description": steam_info.get("description"),
                            "steam_image": steam_info.get("image"),
                            "steam_price": steam_info.get("price"),
                            "steam_genres": steam_info.get("genres", []),
                            "steam_url": steam_info.get("steam_url"),
                            "developers": steam_info.get("developers", []),
                            "publishers": steam_info.get("publishers", []),
                            "app_id": steam_appid  # Ensure app_id is set from Steam API too
                        })
                except Exception as e:
                    print(f"DEBUG: Error fetching Steam data for {steam_appid}: {str(e)}")
            
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
