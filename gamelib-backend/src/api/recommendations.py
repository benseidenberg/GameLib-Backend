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
        
        # Extract app IDs from clusters (taking first 3)
        app_ids = []
        if clusters_data and 'clusters' in clusters_data:
            for cluster in clusters_data['clusters'][:1]:  # Take first cluster
                if 'apps' in cluster:
                    for app in cluster['apps'][:3]:  # Take first 3 games
                        if 'appid' in app:
                            app_ids.append(app['appid'])
        
        # If we don't have enough games from clusters, add some popular games as fallback
        if len(app_ids) < 3:
            fallback_games = [570, 440, 730]  # Dota 2, TF2, CS:GO
            app_ids.extend(fallback_games[:3-len(app_ids)])
        
        # Limit to 3 games
        app_ids = app_ids[:3]
        
        # Fetch game details for each app ID
        games_data = []
        for app_id in app_ids:
            game_info = await get_steam_app_details(app_id)
            if game_info:
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


async def get_steam_app_details(app_id: int):
    """
    Fetch game details from Steam Store API
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