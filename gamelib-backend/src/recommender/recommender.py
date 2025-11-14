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
    min_playtime: int = 600,
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
        
        # Convert to set once for faster lookups
        user_top_games_set = set(user_top_games)
        
        # Use max_similar_users as the early stop threshold (with some buffer for better results)
        early_stop_threshold = max_similar_users * 10  # 10x buffer to ensure quality
        
        # 3. Find similar users who own any of the top games using pagination
        # Process users in batches to avoid timeout
        similar_users = []
        batch_size = 500  # Reduced batch size for faster individual queries
        offset = 0
        total_users_processed = 0
        max_users_to_process = 10000  # Reduced - we'll use early stopping instead
        
        print(f"Starting batch processing of users (early stop at {early_stop_threshold} similar users)...")
        
        while offset < max_users_to_process:
            # Early stopping: if we have enough highly similar users, stop fetching
            if len(similar_users) >= early_stop_threshold:
                print(f"Early stopping: found {len(similar_users)} similar users (threshold: {early_stop_threshold})")
                break
            
            # Fetch a batch of users - only select steam_id and games to reduce data transfer
            batch_response = supabase.table('users').select('steam_id, games').neq('steam_id', steam_id).range(offset, offset + batch_size - 1).limit(batch_size).execute()
            
            batch_count = len(batch_response.data) if batch_response.data else 0
            
            if batch_count == 0:
                print(f"No more users found at offset {offset}")
                break
            
            print(f"Processing batch at offset {offset}: {batch_count} users")
            
            # 4. Calculate similarity scores for users in this batch
            for other_user in batch_response.data:
                other_steam_id = other_user.get('steam_id')
                other_games = other_user.get('games', {})
                
                if not other_games:
                    continue
                
                # Quick check: convert keys to set of ints (do this once per user)
                try:
                    other_game_ids = set(int(appid) for appid in other_games.keys())
                except (ValueError, TypeError):
                    continue
                
                # Fast intersection using set operations
                overlap_count = len(user_top_games_set & other_game_ids)
                
                # Skip users with no overlap (most common case)
                if overlap_count == 0:
                    continue
                
                # Calculate total overlap only if top games match (lazy evaluation)
                total_overlap = len(user_owned_games & other_game_ids)
                similarity_score = overlap_count * 10 + total_overlap  # Weight top games higher
                
                similar_users.append({
                    "steam_id": other_steam_id,
                    "similarity_score": similarity_score,
                    "top_games_overlap": overlap_count,
                    "total_games_overlap": total_overlap,
                    "games": other_game_ids
                })
            
            total_users_processed += batch_count
            
            # If we got fewer users than batch_size, we've reached the end of the table
            if batch_count < batch_size:
                print(f"Reached end of user table (got {batch_count} users, expected {batch_size})")
                break
            
            # Move to next batch
            offset += batch_size
        
        print(f"Finished processing {total_users_processed} users, found {len(similar_users)} similar users")
        
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
            "total_users_analyzed": total_users_processed,
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



