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
    Get game recommendations based on similar users' libraries using SQL-based games_array matching.
    
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
        response = supabase.table('users').select('steam_id, games, games_array').eq('steam_id', steam_id).execute()
        
        if not response.data or len(response.data) == 0:
            return {
                "error": "User not found in database",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": []
            }
        
        current_user = response.data[0]
        user_games = current_user.get('games', {})
        user_games_array = current_user.get('games_array', [])
        
        if not user_games or not user_games_array:
            return {
                "error": "No games data found for user",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": []
            }
        
        # 2. Get user's top N games from games_array (already sorted by playtime)
        user_top_games = user_games_array[:top_n_games]
        user_owned_games = set(int(appid) for appid in user_games.keys())
        
        if not user_top_games:
            return {
                "error": "User has no games",
                "recommendations": [],
                "similar_users": [],
                "user_top_games": []
            }
        
        print(f"User's top {len(user_top_games)} games: {user_top_games}")
        
        # 3. Use PostgreSQL array overlap operator (&&) to find similar users in batches
        # This filters at the database level for users whose games_array overlaps with user's top games
        
        print(f"Querying database for users with overlapping games using batched SQL array operator...")
        
        # Build filter string for array overlap
        games_filter = '{' + ','.join(map(str, user_top_games)) + '}'
        
        # Batch processing settings - fetch filtered users in smaller batches
        batch_size = 500  # Smaller batches of filtered results
        target_users = max_similar_users  # Total users we want to collect
        max_batches = 50  # Maximum number of batches to prevent infinite loops
        
        all_similar_users = []
        last_steam_id = None  # Track last steam_id for pagination
        
        try:
            # Process in batches until we have enough users or run out
            for batch_num in range(max_batches):
                print(f"  Fetching batch {batch_num + 1} ({batch_size} filtered users)...")
                
                try:
                    query = supabase.table('users')\
                        .select('steam_id, games, games_array, data')\
                        .neq('steam_id', steam_id)\
                        .not_.is_('games_array', 'null')\
                        .filter('games_array', 'ov', games_filter)\
                        .order('steam_id')\
                        .limit(batch_size)
                    
                    # Use last_steam_id for pagination to get next batch
                    if last_steam_id:
                        query = query.gt('steam_id', last_steam_id)
                    
                    batch_response = query.execute()
                    
                    if not batch_response.data or len(batch_response.data) == 0:
                        print(f"  No more users found in batch {batch_num + 1}, stopping...")
                        break
                    
                    print(f"  Found {len(batch_response.data)} users in batch {batch_num + 1}")
                    all_similar_users.extend(batch_response.data)
                    
                    # Update last_steam_id for next batch
                    last_steam_id = batch_response.data[-1]['steam_id']
                    
                    # Early exit if we have enough users
                    if len(all_similar_users) >= target_users:
                        print(f"  Collected enough users ({len(all_similar_users)}), stopping early...")
                        break
                    
                except Exception as batch_error:
                    print(f"  Error in batch {batch_num + 1}: {batch_error}")
                    # Continue to next batch on error
                    continue
            
            if not all_similar_users:
                return {
                    "error": "No similar users found with overlapping games",
                    "recommendations": [],
                    "similar_users": [],
                    "user_top_games": user_top_games
                }
            
            print(f"Total users collected from all batches: {len(all_similar_users)}")
            
        except Exception as e:
            print(f"Error with batched array overlap query: {e}")
            print(f"Falling back to simple query without overlap filter...")
            # Fallback: fetch without overlap filter in batches
            try:
                for batch_num in range(5):  # Limit fallback to 5 batches
                    offset = batch_num * batch_size
                    
                    batch_response = supabase.table('users')\
                        .select('steam_id, games, games_array, data')\
                        .neq('steam_id', steam_id)\
                        .not_.is_('games_array', 'null')\
                        .range(offset, offset + batch_size - 1)\
                        .execute()
                    
                    if batch_response.data:
                        all_similar_users.extend(batch_response.data)
                    else:
                        break
                        
            except Exception as fallback_error:
                return {
                    "error": f"Database query failed: {str(fallback_error)}",
                    "recommendations": [],
                    "similar_users": [],
                    "user_top_games": user_top_games
                }
        
        # Use all_similar_users directly instead of wrapping in object
        print(f"Processing {len(all_similar_users)} users...")
        
        # 4. Calculate similarity scores using games_array
        similar_users = []
        user_top_games_set = set(user_top_games)
        
        for other_user in all_similar_users:
            other_steam_id = other_user.get('steam_id')
            other_games_array = other_user.get('games_array', [])
            other_games = other_user.get('games', {})
            other_data = other_user.get('data', {})
            
            if not other_games_array or not other_games:
                continue
            
            # Calculate overlap with user's top games
            other_games_set = set(other_games_array)
            overlap_count = len(user_top_games_set & other_games_set)
            
            # Skip users with no overlap
            if overlap_count == 0:
                continue
            
            # Calculate total overlap
            total_overlap = len(user_owned_games & other_games_set)
            similarity_score = overlap_count * 10 + total_overlap
            
            similar_users.append({
                "steam_id": other_steam_id,
                "persona_name": other_data.get('personaname', 'Unknown User'),
                "similarity_score": similarity_score,
                "top_games_overlap": overlap_count,
                "total_games_overlap": total_overlap,
                "games": other_games
            })
        
        # Sort by similarity and take top N
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
        game_sources = {}
        
        for similar_user in top_similar_users:
            other_games = similar_user["games"]
            
            for appid_str, game_data in other_games.items():
                try:
                    appid = int(appid_str)
                except (ValueError, TypeError):
                    continue
                
                if appid in user_owned_games:
                    continue
                
                playtime = game_data.get("playtime_forever", 0)
                if playtime < min_playtime:
                    continue
                
                weight = similar_user["similarity_score"]
                game_recommendations[appid] += weight
                
                if appid not in game_sources:
                    game_sources[appid] = []
                game_sources[appid].append(similar_user["steam_id"])
        
        # 6. Get top recommendations
        top_recommendations = game_recommendations.most_common(max_recommendations)
        
        recommendations_list = [
            {
                "appid": appid,
                "recommendation_score": score,
                "recommended_by_users": game_sources[appid],
                "recommended_by_count": len(game_sources[appid])
            }
            for appid, score in top_recommendations
        ]
        
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
            "total_users_analyzed": len(all_similar_users),
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



