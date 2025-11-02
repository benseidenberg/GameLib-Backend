# Placeholder for game recommendation ML logic
STEAM_API_KEY="968317D323A2D4C8ED61E3D9F5E2FAB1"
import pandas as pd
import json
import datetime
from collections import Counter
from typing import List, Dict, Set, Tuple
from src.db.supabase_client import supabase


async def get_game_clusters(steam_id: int):
    import httpx
    url = f"https://api.steampowered.com/IStoreAppSimilarityService/IdentifyClustersFromPlaytime/v1/?key={STEAM_API_KEY}&steamid={steam_id}&format=json&randomize=false"
    async with httpx.AsyncClient() as client:
        response = await client.post(url)
        if response.status_code == 200:
            data = response.json()

            return data
        else:
            raise ValueError(f"Failed to fetch: {response.status_code}")
    return None


async def get_collaborative_recommendations(
    steam_id: int, 
    top_n_games: int = 5,
    min_playtime: int = 60,
    max_similar_users: int = 10,
    max_recommendations: int = 20
) -> Dict:
    """
    Get game recommendations based on similar users' libraries.
    
    Args:
        steam_id: The Steam ID of the current user
        top_n_games: Number of top played games to use for finding similar users
        min_playtime: Minimum playtime (minutes) to consider a game as "played"
        max_similar_users: Maximum number of similar users to consider
        max_recommendations: Maximum number of games to recommend
    
    Returns:
        Dictionary containing:
        - recommendations: List of recommended games with scores
        - similar_users: List of similar users found
        - user_top_games: The current user's top games used for matching
    """
    try:
        # 1. Get current user's data from database
        response = supabase.table('users').select('steam_id, games').eq('steam_id', steam_id).execute()
        
        if not response.data or len(response.data) == 0:
            return {
                "error": "User not found in database",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": []
            }
        
        current_user = response.data[0]
        user_games = current_user.get('games', {})
        
        if not user_games:
            return {
                "error": "No games data found for user",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": []
            }
        
        # 2. Get user's top played games (by playtime)
        # Convert games dict to list and sort by playtime
        user_games_list = [
            {"appid": int(appid), "playtime": game_data.get("playtime_forever", 0)}
            for appid, game_data in user_games.items()
            if game_data.get("playtime_forever", 0) >= min_playtime
        ]
        user_games_list.sort(key=lambda x: x["playtime"], reverse=True)
        user_top_games = [game["appid"] for game in user_games_list[:top_n_games]]
        user_owned_games = set(int(appid) for appid in user_games.keys())
        
        if not user_top_games:
            return {
                "error": "No games with sufficient playtime found",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": []
            }
        
        print(f"User's top {top_n_games} games: {user_top_games}")
        
        # 3. Find similar users who own any of the top games
        # Get all users from database (excluding current user)
        all_users_response = supabase.table('users').select('steam_id, games').neq('steam_id', steam_id).execute()
        
        if not all_users_response.data:
            return {
                "error": "No other users found in database",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": user_top_games
            }
        
        # 4. Calculate similarity scores for each user
        similar_users = []
        for other_user in all_users_response.data:
            other_steam_id = other_user.get('steam_id')
            other_games = other_user.get('games', {})
            
            if not other_games:
                continue
            
            # Get other user's game appids
            other_game_ids = set(int(appid) for appid in other_games.keys())
            
            # Calculate overlap with user's top games
            overlap = len(set(user_top_games) & other_game_ids)
            
            if overlap > 0:
                # Calculate similarity score based on:
                # 1. Number of matching top games
                # 2. Total games in common
                total_overlap = len(user_owned_games & other_game_ids)
                similarity_score = overlap * 10 + total_overlap  # Weight top games higher
                
                similar_users.append({
                    "steam_id": other_steam_id,
                    "similarity_score": similarity_score,
                    "top_games_overlap": overlap,
                    "total_games_overlap": total_overlap,
                    "games": other_game_ids
                })
        
        # Sort by similarity score and take top N
        similar_users.sort(key=lambda x: x["similarity_score"], reverse=True)
        top_similar_users = similar_users[:max_similar_users]
        
        if not top_similar_users:
            return {
                "error": "No similar users found",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": user_top_games
            }
        
        print(f"Found {len(top_similar_users)} similar users")
        
        # 5. Aggregate game recommendations from similar users
        game_recommendations = Counter()
        game_sources = {}  # Track which users recommended each game
        
        for similar_user in top_similar_users:
            # Get games this similar user has that current user doesn't
            recommended_games = similar_user["games"] - user_owned_games
            
            # Weight recommendations by similarity score
            weight = similar_user["similarity_score"]
            
            for game_id in recommended_games:
                game_recommendations[game_id] += weight
                
                if game_id not in game_sources:
                    game_sources[game_id] = []
                game_sources[game_id].append(similar_user["steam_id"])
        
        # 6. Get top recommendations
        top_recommendations = game_recommendations.most_common(max_recommendations)
        
        # Format recommendations
        recommendations_list = [
            {
                "appid": appid,
                "recommendation_score": score,
                "recommended_by_users": game_sources[appid],
                "recommended_by_count": len(game_sources[appid])
            }
            for appid, score in top_recommendations
        ]
        
        # Format similar users for response (remove games data for brevity)
        similar_users_summary = [
            {
                "steam_id": user["steam_id"],
                "similarity_score": user["similarity_score"],
                "top_games_overlap": user["top_games_overlap"],
                "total_games_overlap": user["total_games_overlap"]
            }
            for user in top_similar_users
        ]
        
        return {
            "recommendations": recommendations_list,
            "similar_users": similar_users_summary,
            "user_top_games": user_top_games,
            "total_users_analyzed": len(all_users_response.data),
            "similar_users_found": len(top_similar_users)
        }
        
    except Exception as e:
        print(f"Error in get_collaborative_recommendations: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "recommendations": [],
            "similar_users": [],
            "user_top_games": []
        }


#https://api.steampowered.com/IStoreAppSimilarityService/IdentifyClustersFromPlaytime/v1/?access_token=eyAidHlwIjogIkpXVCIsICJhbGciOiAiRWREU0EiIH0.eyAiaXNzIjogInI6MDAwMl8yNkZDQzNFRl9ENTEyNSIsICJzdWIiOiAiNzY1NjExOTg5ODA2NjA2MjciLCAiYXVkIjogWyAid2ViOmNvbW11bml0eSIgXSwgImV4cCI6IDE3NTkyNjAxMDEsICJuYmYiOiAxNzUwNTMyNjM0LCAiaWF0IjogMTc1OTE3MjYzNCwgImp0aSI6ICIwMDE5XzI2RkNDM0U0XzkxMzVGIiwgIm9hdCI6IDE3NTkxNzI2MzQsICJydF9leHAiOiAxNzc3MTI4MTA2LCAicGVyIjogMCwgImlwX3N1YmplY3QiOiAiMTQwLjIzMi4xNzcuMTQ2IiwgImlwX2NvbmZpcm1lciI6ICIxNDAuMjMyLjE2My4yOCIgfQ.Ob602cgjEiiOESorPFGJg9DPfsdFCI8_7m5-uti9ipT9EYxnMmqyjvVqhIZ5KQPgLVXuzreGdE4ZD-wHkbVuCg&steamid=76561198980660627

