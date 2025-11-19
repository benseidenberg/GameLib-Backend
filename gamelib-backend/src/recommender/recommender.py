# Placeholder for game recommendation ML logic
import pandas as pd
import json
import datetime
import asyncio
from collections import Counter
from typing import List, Dict, Set, Tuple
from src.db.supabase_client import supabase
from dotenv import load_dotenv
import os
load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")


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
    max_similar_users: int = 999999,
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
        ]
        user_games_list.sort(key=lambda x: x["playtime"], reverse=True)
        
        # Get top N games by playtime (no minimum playtime filter for current user)
        user_top_games = [game["appid"] for game in user_games_list[:top_n_games]]
        
        user_owned_games = set(int(appid) for appid in user_games.keys())
        
        if not user_top_games:
            return {
                "error": "User has no games",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": []
            }
        
        print(f"User's top {len(user_top_games)} games (requested {top_n_games}): {user_top_games}")
        
        # Convert to set once for faster lookups
        user_top_games_set = set(user_top_games)
        
        # Use max_similar_users as the early stop threshold (with some buffer for better results)
        # If max_similar_users is very large (no practical limit), increase max_users_to_process
        early_stop_threshold = max_similar_users
        
        # Adjust processing limits based on requested similar users
        if max_similar_users > 50000:
            # "No limit" case - process all available users
            max_users_to_process = 999999999  # Essentially unlimited
        elif max_similar_users > 10000:
            max_users_to_process = 100000
        else:
            max_users_to_process = max(20000, max_similar_users * 2)
        
        # 3. Find similar users using CONCURRENT PAGINATION for speed
        print(f"Starting concurrent batch processing (early stop at {early_stop_threshold} similar users)...")
        
        similar_users = []
        batch_size = 500
        concurrent_batches = 5  # Number of batches to fetch simultaneously
        
        async def fetch_and_process_batch(offset: int):
            """Fetch and process a single batch of users"""
            try:
                batch_response = supabase.table('users').select('steam_id, games, data').neq('steam_id', steam_id).range(offset, offset + batch_size - 1).limit(batch_size).execute()
                
                batch_users = []
                batch_count = len(batch_response.data) if batch_response.data else 0
                
                if batch_count == 0:
                    return batch_users, batch_count
                
                # Process users in this batch
                for other_user in batch_response.data:
                    other_steam_id = other_user.get('steam_id')
                    other_games = other_user.get('games', {})
                    other_data = other_user.get('data', {})
                    
                    if not other_games:
                        continue
                    
                    # Quick check: convert keys to set of ints
                    try:
                        other_game_ids = set(int(appid) for appid in other_games.keys())
                    except (ValueError, TypeError):
                        continue
                    
                    # Fast intersection using set operations
                    overlap_count = len(user_top_games_set & other_game_ids)
                    
                    # Skip users with no overlap
                    if overlap_count == 0:
                        continue
                    
                    # Calculate total overlap only if top games match
                    total_overlap = len(user_owned_games & other_game_ids)
                    similarity_score = overlap_count * 10 + total_overlap
                    
                    batch_users.append({
                        "steam_id": other_steam_id,
                        "persona_name": other_data.get('personaname', 'Unknown User'),
                        "similarity_score": similarity_score,
                        "top_games_overlap": overlap_count,
                        "total_games_overlap": total_overlap,
                        "games": other_games  # Store full game data with playtime info
                    })
                
                return batch_users, batch_count
            except Exception as e:
                print(f"Error fetching batch at offset {offset}: {e}")
                return [], 0
        
        # Process batches concurrently
        offset = 0
        total_users_processed = 0
        
        while offset < max_users_to_process:
            # Early stopping check
            if len(similar_users) >= early_stop_threshold:
                print(f"Early stopping: found {len(similar_users)} similar users (threshold: {early_stop_threshold})")
                break
            
            # Create tasks for concurrent batch fetching
            batch_offsets = [offset + (i * batch_size) for i in range(concurrent_batches)]
            tasks = [fetch_and_process_batch(batch_offset) for batch_offset in batch_offsets]
            
            # Fetch all batches concurrently
            results = await asyncio.gather(*tasks)
            
            # Aggregate results from all batches
            batches_processed = 0
            for batch_users, batch_count in results:
                if batch_count > 0:
                    similar_users.extend(batch_users)
                    total_users_processed += batch_count
                    batches_processed += 1
            
            print(f"Processed {batches_processed} batches concurrently (offsets {offset}-{offset + concurrent_batches * batch_size}): {total_users_processed} total users, {len(similar_users)} similar users found")
            
            # If we didn't get a full set of batches, we've reached the end
            if batches_processed < concurrent_batches:
                print(f"Reached end of user table")
                break
            
            # Move offset forward by the number of batches processed
            offset += concurrent_batches * batch_size
        
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
        # Apply min_playtime filter HERE - only recommend games that similar users played enough
        game_recommendations = Counter()
        game_sources = {}  # Track which users recommended each game
        
        for similar_user in top_similar_users:
            other_games = similar_user["games"]  # Full game data dict with playtime
            
            # Get games this similar user has played for at least min_playtime
            # that current user doesn't own
            for appid_str, game_data in other_games.items():
                try:
                    appid = int(appid_str)
                except (ValueError, TypeError):
                    continue
                
                # Skip if current user already owns this game
                if appid in user_owned_games:
                    continue
                
                # Apply min_playtime filter: only recommend if similar user played enough
                playtime = game_data.get("playtime_forever", 0)
                if playtime < min_playtime:
                    continue
                
                # Weight recommendations by similarity score
                weight = similar_user["similarity_score"]
                game_recommendations[appid] += weight
                
                if appid not in game_sources:
                    game_sources[appid] = []
                game_sources[appid].append(similar_user["steam_id"])
        
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
                "persona_name": user["persona_name"],
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



