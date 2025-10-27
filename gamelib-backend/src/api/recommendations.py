from fastapi import APIRouter, HTTPException
from src.recommender.recommender import get_game_clusters
import httpx
import asyncio

router = APIRouter()

@router.get("/clusters/{steam_id}")
async def get_clusters(steam_id: int):
    """
    Get game recommendations/clusters for a user by Steam ID
    """
    print(f"DEBUG: Starting recommendations for steam_id: {steam_id}")
    try:
        print("DEBUG: About to call get_game_clusters")
        clusters = await get_game_clusters(steam_id)
        print(f"DEBUG: get_game_clusters returned: {type(clusters)} - {clusters}")
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
            
            print(f"DEBUG: Found {len(clusters_list)} clusters")
            
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
                
                print(f"DEBUG: Top clusters by relevance:")
                for i, cluster in enumerate(sorted_clusters[:5]):
                    score = cluster_score(cluster)
                    recent = cluster.get('playtime_2weeks', 0)
                    total = cluster.get('playtime_forever', 0)
                    print(f"  Cluster {cluster.get('cluster_id')}: score={score:.1f}, recent={recent}min, total={total}min")
                
                # Take from the most relevant clusters
                for cluster in sorted_clusters[:5]:  # Check top 5 clusters
                    if len(app_ids_with_source) >= 3:
                        break
                        
                    cluster_id = cluster.get('cluster_id')
                    print(f"DEBUG: Processing cluster {cluster_id}")
                    
                    # Get played games and similar games
                    similar_apps = cluster.get('similar_items_appids', [])
                    played_apps = cluster.get('played_appids', [])
                    
                    print(f"DEBUG: Found {len(played_apps)} played apps and {len(similar_apps)} similar apps")
                    print(f"DEBUG: Played games in this cluster: {played_apps}")
                    print(f"DEBUG: Similar games available: {similar_apps[:8]}")  # Show first 8
                    
                    # For each cluster, we'll pick the most played game as the "source"
                    # and recommend similar games based on it
                    if played_apps:
                        # Choose the first played game as the primary source for this cluster
                        source_app_id = played_apps[0]  # Could be improved to pick by playtime
                        
                        # Fetch source game details
                        source_game_info = await get_steam_app_details_basic(source_app_id)
                        
                        if source_game_info:
                            # Add similar games with this source
                            for app_id in similar_apps[:8]:  # Try more games per cluster
                                if len(app_ids_with_source) < 3:
                                    # Check if we already have this app_id
                                    existing_app_ids = [item[0] for item in app_ids_with_source]
                                    if app_id not in existing_app_ids:
                                        app_ids_with_source.append((app_id, source_game_info))
                                        print(f"DEBUG: Added similar app_id: {app_id} based on {source_game_info['title']}")
                                else:
                                    break
        
        print(f"DEBUG: Final app_ids with sources: {[(item[0], item[1]['title']) for item in app_ids_with_source]}")
        
        # If we don't have enough games from clusters, add some popular games as fallback
        if len(app_ids_with_source) < 3:
            print(f"DEBUG: Only got {len(app_ids_with_source)} games from clusters, adding fallback games")
            fallback_games = [570, 440, 730]  # Dota 2, TF2, CS:GO
            
            for app_id in fallback_games:
                if len(app_ids_with_source) >= 3:
                    break
                # Add fallback games without a specific source
                existing_app_ids = [item[0] for item in app_ids_with_source]
                if app_id not in existing_app_ids:
                    app_ids_with_source.append((app_id, {"title": "Popular games", "app_id": None}))
        
        # Limit to 3 games
        app_ids_with_source = app_ids_with_source[:3]
        print(f"DEBUG: Final app_ids to fetch: {[item[0] for item in app_ids_with_source]}")
        
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
        if len(games_data) < 3 and clusters_data:
            print(f"DEBUG: Only got {len(games_data)} appropriate games, fetching more...")
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
                if len(games_data) >= 3:
                    break
                
                played_apps = cluster.get('played_appids', [])
                similar_apps = cluster.get('similar_items_appids', [])
                
                if played_apps:
                    source_app_id = played_apps[0]
                    source_game_info = await get_steam_app_details_basic(source_app_id)
                    
                    if source_game_info:
                        for app_id in similar_apps[:5]:  # Try more games per cluster
                            if len(games_data) >= 3:
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
        if len(games_data) < 3:
            safe_fallback_games = [570, 440, 730, 359550, 271590]  # Dota 2, TF2, CS:GO, Rainbow Six, GTA V
            for app_id in safe_fallback_games:
                if len(games_data) >= 3:
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


async def get_steam_app_details(app_id: int):
    """
    Fetch game details from Steam Store API with content filtering
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
                    
                    # Filter out inappropriate content
                    if not is_content_appropriate(game_data):
                        print(f"DEBUG: Filtered out inappropriate content for app_id: {app_id}")
                        return None
                    
                    return {
                        "app_id": app_id,
                        "title": game_data.get('name', 'Unknown Title'),
                        "description": game_data.get('short_description', 'No description available'),
                        "image": game_data.get('header_image', ''),
                        "price": game_data.get('price_overview', {}).get('final_formatted', 'Free'),
                        "genres": [genre['description'] for genre in game_data.get('genres', [])],
                        "developers": game_data.get('developers', []),
                        "publishers": game_data.get('publishers', []),
                        "release_date": game_data.get('release_date', {}).get('date', 'Unknown'),
                        "steam_url": f"https://store.steampowered.com/app/{app_id}/"
                    }
            
            return None
            
    except Exception as e:
        print(f"DEBUG: Error fetching Steam app details for {app_id}: {str(e)}")
        return None


def is_content_appropriate(game_data: dict) -> bool:
    """
    Check if game content is appropriate (filters out sexual content)
    """
    # Check content descriptors for adult content
    content_descriptors = game_data.get('content_descriptors', {})
    if content_descriptors:
        descriptor_notes = content_descriptors.get('notes', '')
        descriptor_ids = content_descriptors.get('ids', [])
        
        # Handle None values
        if descriptor_notes:
            descriptor_notes = descriptor_notes.lower()
        else:
            descriptor_notes = ''
        
        # Steam content descriptor IDs for adult content
        # ID 3: Nudity or Sexual Content
        # ID 4: Adult Only Sexual Content
        adult_content_ids = [3, 4]
        
        if any(adult_id in descriptor_ids for adult_id in adult_content_ids):
            return False
        
        # Check descriptor notes for sexual keywords
        sexual_keywords = [
            'sexual content', 'nudity', 'adult', 'mature sexual themes',
            'sexual themes', 'partial nudity', 'sexual violence'
        ]
        
        if any(keyword in descriptor_notes for keyword in sexual_keywords):
            return False
    
    # Check required age (if 18+ it might be adult content)
    required_age = game_data.get('required_age', 0)
    if required_age >= 18:
        # Additional check for adult games
        categories = game_data.get('categories', [])
        for category in categories:
            category_desc = category.get('description', '')
            if category_desc and category_desc.lower() in ['adult only content', 'mature']:
                return False
    
    # Check game name and description for obvious adult content
    game_name = game_data.get('name', '') or ''
    game_description = game_data.get('short_description', '') or ''
    
    game_name = game_name.lower()
    game_description = game_description.lower()
    
    inappropriate_terms = [
        'hentai', 'porn', 'erotic', 'xxx', 'adult only',
        'sexual', 'nudity', '18+', 'mature content'
    ]
    
    for term in inappropriate_terms:
        if term in game_name or term in game_description:
            return False
    
    # Check genres for adult content
    genres = game_data.get('genres', [])
    for genre in genres:
        genre_desc = genre.get('description', '')
        if genre_desc and ('adult' in genre_desc.lower() or 'sexual' in genre_desc.lower()):
            return False
    
    return True