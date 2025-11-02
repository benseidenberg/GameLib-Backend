from fastapi import APIRouter, HTTPException
from src.recommender.recommender import get_collaborative_recommendations
from typing import Optional

router = APIRouter()

@router.get("/collaborative-recommendations/{steam_id}")
async def get_collaborative_filtering_recommendations(
    steam_id: int,
    top_n_games: Optional[int] = 5,
    min_playtime: Optional[int] = 60,
    max_similar_users: Optional[int] = 10,
    max_recommendations: Optional[int] = 20
):
    """
    Get game recommendations based on collaborative filtering.
    Finds similar users and recommends games they play that the current user doesn't own.
    
    Args:
        steam_id: The Steam ID of the user
        top_n_games: Number of top played games to use for finding similar users (default: 5)
        min_playtime: Minimum playtime in minutes to consider a game as "played" (default: 60)
        max_similar_users: Maximum number of similar users to consider (default: 10)
        max_recommendations: Maximum number of games to recommend (default: 20)
    
    Returns:
        Dictionary containing recommendations, similar users, and metadata
    """
    try:
        result = await get_collaborative_recommendations(
            steam_id=steam_id,
            top_n_games=top_n_games if top_n_games is not None else 5,
            min_playtime=min_playtime if min_playtime is not None else 60,
            max_similar_users=max_similar_users if max_similar_users is not None else 10,
            max_recommendations=max_recommendations if max_recommendations is not None else 20
        )
        
        # Check if there was an error
        if "error" in result and result["error"]:
            # Return partial results with error message
            return {
                "success": False,
                "error": result["error"],
                "recommendations": result.get("recommendations", []),
                "similar_users": result.get("similar_users", []),
                "user_top_games": result.get("user_top_games", [])
            }
        
        # Fetch game details from Steam API for each recommendation
        import httpx
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        STEAM_API_KEY = os.getenv("STEAM_API_KEY")
        
        recommendations_with_details = []
        
        async with httpx.AsyncClient() as client:
            for rec in result.get("recommendations", []):
                appid = rec["appid"]
                
                # Fetch game details from Steam API
                try:
                    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
                    response = await client.get(url, timeout=5.0)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if str(appid) in data and data[str(appid)]["success"]:
                            game_data = data[str(appid)]["data"]
                            
                            recommendations_with_details.append({
                                "appid": appid,
                                "name": game_data.get("name", f"Game {appid}"),
                                "header_image": game_data.get("header_image", ""),
                                "short_description": game_data.get("short_description", ""),
                                "genres": [g["description"] for g in game_data.get("genres", [])],
                                "price": game_data.get("price_overview", {}).get("final_formatted", "Free"),
                                "recommendation_score": rec["recommendation_score"],
                                "recommended_by_count": rec["recommended_by_count"],
                                "steam_url": f"https://store.steampowered.com/app/{appid}"
                            })
                        else:
                            # Fallback if game details not available
                            recommendations_with_details.append({
                                "appid": appid,
                                "name": f"Game {appid}",
                                "header_image": "",
                                "short_description": "",
                                "genres": [],
                                "price": "N/A",
                                "recommendation_score": rec["recommendation_score"],
                                "recommended_by_count": rec["recommended_by_count"],
                                "steam_url": f"https://store.steampowered.com/app/{appid}"
                            })
                except Exception as e:
                    print(f"Error fetching details for game {appid}: {str(e)}")
                    # Add basic info without details
                    recommendations_with_details.append({
                        "appid": appid,
                        "name": f"Game {appid}",
                        "header_image": "",
                        "short_description": "",
                        "genres": [],
                        "price": "N/A",
                        "recommendation_score": rec["recommendation_score"],
                        "recommended_by_count": rec["recommended_by_count"],
                        "steam_url": f"https://store.steampowered.com/app/{appid}"
                    })
        
        return {
            "success": True,
            "recommendations": recommendations_with_details,
            "similar_users": result.get("similar_users", []),
            "user_top_games": result.get("user_top_games", []),
            "total_users_analyzed": result.get("total_users_analyzed", 0),
            "similar_users_found": result.get("similar_users_found", 0)
        }
        
    except Exception as e:
        print(f"Error in get_collaborative_filtering_recommendations: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
