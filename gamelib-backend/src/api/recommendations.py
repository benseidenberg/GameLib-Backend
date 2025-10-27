from fastapi import APIRouter, HTTPException
from src.recommender.recommender import get_game_clusters
import httpx
import asyncio
import os

# Get Steam API key from environment variables
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
if not STEAM_API_KEY:
    raise ValueError("STEAM_API_KEY environment variable is required")

router = APIRouter()

@router.get("/recommendations/{steam_id}")
async def get_recommendations(steam_id: int):
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
        if game_info:
            return game_info
        else:
            raise HTTPException(status_code=404, detail="Game not found or filtered out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching game details: {str(e)}")
    
#https://api.steampowered.com/IStoreAppSimilarityService/IdentifyClustersFromPlaytime/v1/?access_token=eyAidHlwIjogIkpXVCIsICJhbGciOiAiRWREU0EiIH0.eyAiaXNzIjogInI6MDAwMl8yNkZDQzNFRl9ENTEyNSIsICJzdWIiOiAiNzY1NjExOTg5ODA2NjA2MjciLCAiYXVkIjogWyAid2ViOmNvbW11bml0eSIgXSwgImV4cCI6IDE3NTkyNjAxMDEsICJuYmYiOiAxNzUwNTMyNjM0LCAiaWF0IjogMTc1OTE3MjYzNCwgImp0aSI6ICIwMDE5XzI2RkNDM0U0XzkxMzVGIiwgIm9hdCI6IDE3NTkxNzI2MzQsICJydF9leHAiOiAxNzc3MTI4MTA2LCAicGVyIjogMCwgImlwX3N1YmplY3QiOiAiMTQwLjIzMi4xNzcuMTQ2IiwgImlwX2NvbmZpcm1lciI6ICIxNDAuMjMyLjE2My4yOCIgfQ.Ob602cgjEiiOESorPFGJg9DPfsdFCI8_7m5-uti9ipT9EYxnMmqyjvVqhIZ5KQPgLVXuzreGdE4ZD-wHkbVuCg&steamid=76561198980660627