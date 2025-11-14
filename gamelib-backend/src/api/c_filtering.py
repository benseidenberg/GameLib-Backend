from fastapi import APIRouter, HTTPException, Query
from src.recommender.recommender import get_collaborative_recommendations
from typing import Optional, List
import httpx
import os
from dotenv import load_dotenv
load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

router = APIRouter()

@router.get("/collaborative-recommendations/{steam_id}/")
async def get_collaborative_filtering_recommendations(
    steam_id: int,
    top_n_games: Optional[int] = 5,
    min_playtime: Optional[int] = 600,
    max_similar_users: Optional[int] = 150,
    max_recommendations: Optional[int] = 20,
    genres: Optional[List[str]] = Query(None),
    max_price: Optional[float] = None
):
    """
    Get game recommendations based on collaborative filtering.
    Finds similar users and recommends games they play that the current user doesn't own.
    
    Args:
        steam_id: The Steam ID of the user
        top_n_games: Number of top played games to use for finding similar users (default: 5)
        min_playtime: Minimum playtime in minutes to consider a game as "played" (default: 600)
        max_similar_users: Maximum number of similar users to consider (default: 150)
        max_recommendations: Maximum number of games to recommend (default: 20)
        genres: List of genres to filter by (optional)
        max_price: Maximum price in USD to filter by (optional, None = no limit)
    
    Returns:
        Dictionary containing recommendations, similar users, and metadata
    """
    try:
        # Request more recommendations than needed to account for filtering
        # This ensures we still get enough results after filtering
        buffer_multiplier = 3 if (genres or max_price is not None) else 1
        internal_max_recommendations = max_recommendations * buffer_multiplier if max_recommendations else 60
        
        result = await get_collaborative_recommendations(
            steam_id=steam_id,
            top_n_games=top_n_games if top_n_games is not None else 5,
            min_playtime=min_playtime if min_playtime is not None else 600,
            max_similar_users=max_similar_users if max_similar_users is not None else 10,
            max_recommendations=internal_max_recommendations
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
    
        
        recommendations_with_details = []
        
        async with httpx.AsyncClient() as client:
            for rec in result.get("recommendations", []):
                appid = rec["appid"]
                
                # Fetch game details from Steam API
                try:
                    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=US"
                    response = await client.get(url, timeout=5.0)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if str(appid) in data and data[str(appid)]["success"]:
                            game_data = data[str(appid)]["data"]
                            
                            # Extract game details
                            game_genres = [g["description"] for g in game_data.get("genres", [])]
                            price_data = game_data.get("price_overview", {})
                            
                            # Get price in USD (cents)
                            if price_data:
                                price_cents = price_data.get("final", 0)
                                price_usd = price_cents / 100.0
                                price_formatted = price_data.get("final_formatted", "Free")
                            else:
                                price_usd = 0.0
                                price_formatted = "Free"
                            
                            # Apply genre filter
                            if genres:
                                # Check if game has at least one of the requested genres
                                if not any(genre in game_genres for genre in genres):
                                    continue
                            
                            # Apply price filter
                            if max_price is not None and price_usd > max_price:
                                continue
                            
                            recommendations_with_details.append({
                                "appid": appid,
                                "name": game_data.get("name", f"Game {appid}"),
                                "header_image": game_data.get("header_image", ""),
                                "short_description": game_data.get("short_description", ""),
                                "genres": game_genres,
                                "price": price_formatted,
                                "price_usd": price_usd,
                                "recommendation_score": rec["recommendation_score"],
                                "recommended_by_count": rec["recommended_by_count"],
                                "steam_url": f"https://store.steampowered.com/app/{appid}"
                            })
                            
                            # Stop once we have enough recommendations
                            if len(recommendations_with_details) >= (max_recommendations or 20):
                                break
                        else:
                            # Fallback if game details not available
                            recommendations_with_details.append({
                                "appid": appid,
                                "name": f"Game {appid}",
                                "header_image": "",
                                "short_description": "",
                                "genres": [],
                                "price": "N/A",
                                "price_usd": 0.0,
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
                        "price_usd": 0.0,
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
