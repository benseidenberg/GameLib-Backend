from fastapi import APIRouter, HTTPException
from src.recommender.recommender import get_game_clusters
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


async def get_game_from_db(app_id: int):
    """
    Fetch game details from games_db table first
    
    Args:
        app_id: Steam app ID
    
    Returns:
        Game info dict if found, None otherwise
    """
    try:
        result = supabase.table('games_db').select('*').eq('game_id', app_id).execute()
        
        if result.data and len(result.data) > 0:
            db_game = result.data[0]
            
            # Format database result to match Steam API structure
            return {
                "app_id": db_game.get('game_id'),
                "title": db_game.get('name', 'Unknown Game'),
                "description": db_game.get('short_desc', ''),
                "detailed_description": db_game.get('detailed_desc', ''),
                "image": db_game.get('image', ''),
                "price": db_game.get('price', 'Free'),
                "price_usd": db_game.get('price_usd'),
                "is_free": db_game.get('is_free', False),
                "genres": db_game.get('genres', []),
                "categories": db_game.get('categories', []),
                "platforms": db_game.get('platforms', {}),
                "metacritic": db_game.get('metacritic', {}),
                "content_descriptors": db_game.get('content', {}),
                "developers": db_game.get('developers', []),
                "publishers": db_game.get('publishers', []),
                "release_date": str(db_game.get('release_date', '')),
                "steam_url": db_game.get('steam_url', f"https://store.steampowered.com/app/{app_id}/")
            }
        
        return None
        
    except Exception as e:
        print(f"DEBUG: Error fetching game from database for {app_id}: {str(e)}")
        return None


async def get_steam_app_details(app_id: int, skip_content_filter: bool = False):
    """
    Fetch detailed game information - checks database first, then Steam API as fallback
    
    Args:
        app_id: Steam app ID
        skip_content_filter: If True, skips content appropriateness check (for database population)
    """
    # Try database first
    db_game = await get_game_from_db(app_id)
    if db_game:
        return db_game
    
    # Fallback to Steam API
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&format=json"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Steam API returns data with app_id as key
                app_data = data.get(str(app_id))
                if app_data and app_data.get('success') and 'data' in app_data:
                    game_data = app_data['data']
                    
                    # Check if content is appropriate (unless skipped)
                    if not skip_content_filter and not is_content_appropriate(game_data):
                        return None
                    
                    # Extract price information
                    is_free = game_data.get('is_free', False)
                    price_usd = None
                    price_formatted = 'Free'
                    
                    if not is_free and 'price_overview' in game_data:
                        price_info = game_data['price_overview']
                        price_usd = price_info.get('final', 0) / 100.0  # Convert cents to dollars
                        price_formatted = price_info.get('final_formatted', 'N/A')
                    
                    # Extract relevant information
                    game_info = {
                        "app_id": app_id,
                        "title": game_data.get('name', 'Unknown Game'),
                        "description": game_data.get('short_description', ''),
                        "detailed_description": game_data.get('detailed_description', ''),
                        "image": game_data.get('header_image', ''),
                        "price": price_formatted,
                        "price_usd": price_usd,
                        "is_free": is_free,
                        "genres": [genre.get('description', '') for genre in game_data.get('genres', [])],
                        "categories": [cat.get('description', '') for cat in game_data.get('categories', [])],
                        "platforms": game_data.get('platforms', {}),
                        "metacritic": game_data.get('metacritic', {}),
                        "content_descriptors": game_data.get('content_descriptors', {}),
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
        game_name = game_data.get('name', 'Unknown')
        
        # Check content descriptors for adult content
        content_descriptors = game_data.get('content_descriptors', {})
        if not content_descriptors:
            # Also check 'content' field (used in database format)
            content_descriptors = game_data.get('content', {})
        
        if content_descriptors:
            descriptor_ids = content_descriptors.get('ids', [])
            descriptor_notes = content_descriptors.get('notes', '')
                        
            # Ensure descriptor_notes is a string
            if descriptor_notes is None:
                descriptor_notes = ''
            
            # Steam's adult content descriptor IDs
            # 1: Violence, 2: Gore, 3: Nudity/Sexual Content, 4: Adult Only Sexual Content, 5: Frequent Violence/Gore
            adult_descriptor_ids = [3, 4]  # 3: Nudity/Sexual Content, 4: Adult Only Sexual Content
            
            if any(desc_id in adult_descriptor_ids for desc_id in descriptor_ids):
                print(f"DEBUG is_content_appropriate: FILTERING {game_name} - Adult content descriptor IDs: {descriptor_ids}")
                return False
            
            # Check descriptor notes for sexual content keywords
            descriptor_notes_lower = descriptor_notes.lower()
            sexual_keywords = [
                'sexual content', 'nudity', 'mature content', 'adult', 'erotic', 
                'hentai', 'nsfw', 'xxx', 'porn', '18+', 'adults only'
            ]
            for keyword in sexual_keywords:
                if keyword in descriptor_notes_lower:
                    print(f"DEBUG: Filtered game due to keyword '{keyword}' in content notes")
                    return False
        
        # Check age ratings
        required_age = game_data.get('required_age', 0)
        if required_age >= 18:
            print(f"DEBUG: Filtered game due to required_age >= 18: {required_age}")
            return False
        
        # Check game name and description for inappropriate content
        game_name = (game_data.get('name') or '').lower()
        game_desc = (game_data.get('short_description') or '').lower()
        detailed_desc = (game_data.get('detailed_description') or '').lower()
        
        # List of inappropriate keywords
        inappropriate_keywords = [
            'hentai', 'porn', 'erotic', 'xxx', 'adult only', 'sexual',
            'strip', 'mature content', 'adult content', 'nsfw', '18+',
            'ecchi', 'lewd', 'nudity', 'sexy', 'adults only'
        ]
        
        # Check if any inappropriate keywords are in the title or description
        for keyword in inappropriate_keywords:
            if keyword in game_name:
                return False
            if keyword in game_desc or keyword in detailed_desc:
                return False
        
        # Check tags for adult content
        tags = game_data.get('tags', [])
        if tags:
            tags_lower = [tag.lower() if isinstance(tag, str) else str(tag).lower() for tag in tags]
            adult_tags = [
                'hentai', 'sexual content', 'nudity', 'adult', 'erotic', 'nsfw',
                'mature', 'xxx', 'porn', '18+', 'adults only', 'ecchi', 'lewd'
            ]
            for tag in tags_lower:
                for adult_tag in adult_tags:
                    if adult_tag in tag:
                        return False
        
        # Check genres for adult content
        genres = game_data.get('genres', [])
        for genre in genres:
            if isinstance(genre, dict):
                genre_desc = (genre.get('description') or '').lower()
            else:
                genre_desc = str(genre).lower()
            
            adult_genre_keywords = ['adult', 'sexual', 'mature', 'hentai', 'erotic']
            for keyword in adult_genre_keywords:
                if keyword in genre_desc:
                    return False
        
        # Check categories for adult content
        categories = game_data.get('categories', [])
        for category in categories:
            if isinstance(category, dict):
                cat_desc = (category.get('description') or '').lower()
            else:
                cat_desc = str(category).lower()
            
            if 'adult only' in cat_desc or 'mature content' in cat_desc:
                return False
        
        return True
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        # If there's an error in filtering, err on the side of caution and filter it out
        return False


async def get_steam_app_details_basic(app_id: int):
    """
    Fetch basic game details (title and app_id) - checks database first, then Steam API as fallback
    """
    # Try database first
    db_game = await get_game_from_db(app_id)
    if db_game:
        return {
            "app_id": db_game.get('app_id'),
            "title": db_game.get('title')
        }

    # Fallback to Steam API
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


@router.get("/clusters/{steam_id}")
async def get_clusters(steam_id: int):
    """
    Get game recommendations/clusters for a user by Steam ID
    """
    try:
        clusters = await get_game_clusters(steam_id)
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
        url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json&include_appinfo=1&include_played_free_games=1"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                
                if "response" in data and "games" in data["response"]:
                    # Process the games data
                    games = data["response"]["games"]
                    
                    # Create a simplified version for the API response
                    processed_games = []
                    for game in games:
                        if game.get("playtime_forever", 0) > 0:  # Only include played games
                            processed_games.append({
                                "appid": game.get("appid"),
                                "name": game.get("name", "Unknown Game"),
                                "playtime_forever": game.get("playtime_forever", 0),
                                "playtime_2weeks": game.get("playtime_2weeks", 0),
                                "img_icon_url": game.get("img_icon_url", ""),
                                "rtime_last_played": game.get("rtime_last_played")
                            })
                    
                    return {
                        "steam_id": steam_id,
                        "total_games": len(processed_games),
                        "games": processed_games
                    }
                else:
                    return {"steam_id": steam_id, "total_games": 0, "games": []}
            else:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch Steam profile")
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Steam profile: {str(e)}")


@router.get("/steam/player/{steam_id}")
async def get_steam_player_summary(steam_id: int):
    """
    Get Steam user's profile information (name, avatar, etc.)
    """
    try:
        url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        params = {
            'key': STEAM_API_KEY,
            'steamids': str(steam_id)
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if "response" in data and "players" in data["response"] and len(data["response"]["players"]) > 0:
                player = data["response"]["players"][0]
                return {
                    "steamid": player.get("steamid"),
                    "personaname": player.get("personaname"),
                    "profileurl": player.get("profileurl"),
                    "avatar": player.get("avatar"),
                    "avatarmedium": player.get("avatarmedium"),
                    "avatarfull": player.get("avatarfull"),
                    "personastate": player.get("personastate"),
                    "communityvisibilitystate": player.get("communityvisibilitystate"),
                    "profilestate": player.get("profilestate"),
                    "lastlogoff": player.get("lastlogoff"),
                    "commentpermission": player.get("commentpermission")
                }
            else:
                raise HTTPException(status_code=404, detail="Player not found")
                
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Steam API error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Steam player summary: {str(e)}")


@router.get("/steam/game-details/{app_id}")
async def get_steam_game_details_endpoint(app_id: int):
    """
    Get detailed information about a specific Steam game
    """
    try:
        game_info = await get_steam_app_details(app_id)
        
        if not game_info:
            raise HTTPException(status_code=404, detail=f"Game with app_id {app_id} not found or filtered out")
        
        return game_info
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        print(f"DEBUG: Error in get_steam_game_details for app_id {app_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching game details: {str(e)}")


@router.get("/recommendations/test/{steam_id}")
async def test_recommendations(steam_id: int):
    """
    Test endpoint that returns 3 games with their details from Steam API
    Uses the provided Steam ID to get clusters, then returns first 3 games with full details
    """
    try:
        # Get game clusters for the provided Steam ID
        clusters_data = await get_game_clusters(steam_id)
        
        # Extract app IDs from clusters with their source games
        app_ids_with_source = []  # Will store tuples of (app_id, source_game_info)
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
                    if len(app_ids_with_source) >= 5:
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
                        source_app_id = played_apps_list[0]
                        
                        # Fetch source game details
                        source_game_info = await get_steam_app_details_basic(source_app_id)
                        
                        if source_game_info:
                            # Add ONE similar game from this cluster for variety
                            for app_id in similar_apps:
                                # Check if we already have this app_id
                                existing_app_ids = [item[0] for item in app_ids_with_source]
                                if app_id not in existing_app_ids:
                                    app_ids_with_source.append((app_id, source_game_info))
                                    break  # Only take ONE game per cluster
                
        # If we don't have enough games from clusters, add some popular games as fallback
        if len(app_ids_with_source) < 5:
            fallback_games = [570, 440, 730]  # Dota 2, TF2, CS:GO
            
            for app_id in fallback_games:
                if len(app_ids_with_source) >= 5:
                    break
                # Add fallback games without a specific source
                existing_app_ids = [item[0] for item in app_ids_with_source]
                if app_id not in existing_app_ids:
                    app_ids_with_source.append((app_id, {"title": "Popular games", "app_id": None}))
        
        # Limit to 5 games
        app_ids_with_source = app_ids_with_source[:5]
        
        # Fetch game details for each app ID with content filtering
        games_data = []
        
        for app_id, source_info in app_ids_with_source:
            game_info = await get_steam_app_details(app_id)
            if game_info:  # Only add if not filtered out
                # Add the source information to the game data
                game_info["based_on"] = {
                    "title": source_info["title"],
                    "app_id": source_info.get("app_id")
                }
                games_data.append(game_info)
        
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
                    source_app_id = played_apps_list[0]
                    source_game_info = await get_steam_app_details_basic(source_app_id)
                    
                    if source_game_info:
                        for app_id in similar_apps[:5]:  # Try more games per cluster
                            if len(games_data) >= 5:
                                break
                            
                            # Check if we already have this game
                            existing_app_ids = [game['app_id'] for game in games_data]
                            if app_id not in existing_app_ids:
                                game_info = await get_steam_app_details(app_id)
                                if game_info:
                                    game_info["based_on"] = {
                                        "title": source_game_info["title"],
                                        "app_id": source_game_info.get("app_id")
                                    }
                                    games_data.append(game_info)
        
        # Final fallback to safe, popular games if still not enough
        if len(games_data) < 5:
            safe_fallback_games = [570, 440, 730, 359550, 271590]  # Dota 2, TF2, CS:GO, Rainbow Six, GTA V
            for app_id in safe_fallback_games:
                if len(games_data) >= 5:
                    break
                
                existing_app_ids = [game['app_id'] for game in games_data]
                if app_id not in existing_app_ids:  # Avoid duplicates
                    game_info = await get_steam_app_details(app_id)
                    if game_info:
                        game_info["based_on"] = {
                            "title": "Popular games",
                            "app_id": None
                        }
                        games_data.append(game_info)
        
        return {
            "message": "Test recommendations successful",
            "steam_id": steam_id,
            "total_games": len(games_data),
            "games": games_data
        }
        
    except Exception as e:
        print(f"DEBUG: Error in test_recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting test recommendations: {str(e)}")