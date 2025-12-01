"""
Collaborative filtering recommendations service
Business logic for generating game recommendations based on similar users
"""
from collections import Counter
from typing import List, Dict, Optional
from src.db.repositories.users_db import UsersRepository
from src.services.filtering import FilteringService


class CollaborativeRecommendationService:
    """Service for collaborative filtering recommendations"""
    
    def __init__(self):
        self.users_repo = UsersRepository()
        self.filtering_service = FilteringService()
    
    async def get_recommendations(
        self,
        steam_id: int,
        top_n_games: int = 5,
        min_playtime: int = 60,
        max_total_users: int = 1000,
        max_recommendations: int = 20,
        batch_size: int = 750,
        max_batches: int = 50
    ) -> Dict:
        """
        Get game recommendations based on similar users' libraries
        
        Args:
            steam_id: Current user's Steam ID
            top_n_games: Number of top games to use for finding similar users
            min_playtime: Minimum playtime (minutes) to consider a game
            max_similar_users: Maximum number of similar users to analyze
            max_recommendations: Maximum recommendations to return
            batch_size: Users per batch for pagination
            max_batches: Maximum batches to fetch
            
        Returns:
            Dictionary with recommendations, similar users, and metadata
        """
        try:
            # 1. Get current user's data
            current_user = self.users_repo.find_by_steam_id(steam_id)
            
            if not current_user:
                return self._error_response("User not found in database")
            
            user_games = current_user.games or {}
            user_games_array = current_user.games_array or []
            
            if not user_games or not user_games_array:
                return self._error_response("No games data found for user")
            
            # 2. Get user's top N games (already sorted by playtime)
            user_top_games = user_games_array[:top_n_games]
            user_owned_games = set(int(game_id) for game_id in user_games.keys())
            
            if not user_top_games:
                return self._error_response("User has no games")
            
            print(f"User's top {len(user_top_games)} games: {user_top_games}")
            
            # 3. Find similar users in batches
            all_similar_users, total_users_pulled = await self._find_similar_users_batched(
                steam_id=steam_id,
                user_top_games=user_top_games,
                batch_size=batch_size,
                max_batches=max_batches,
                target_users=max_total_users
            )
            
            if not all_similar_users:
                return self._error_response(
                    "No similar users found with overlapping games",
                    user_top_games=user_top_games
                )
            
            print(f"Total users collected: {len(all_similar_users)}")
            
            # 4. Calculate similarity scores
            similar_users = self._calculate_similarity_scores(
                user_top_games=user_top_games,
                user_owned_games=user_owned_games,
                potential_users=all_similar_users
            )
            
            if not similar_users:
                return self._error_response(
                    "No similar users found",
                    user_top_games=user_top_games
                )
            
            print(f"Found {len(similar_users)} similar users")
            
            # 5. Aggregate game recommendations
            recommendations = self._aggregate_recommendations(
                similar_users=similar_users,
                user_owned_games=user_owned_games,
                min_playtime=min_playtime,
                max_recommendations=max_recommendations
            )
            
            # 6. Build response
            similar_users_summary = [
                {
                    "steam_id": user["steam_id"],
                    "persona_name": user["persona_name"],
                    "similarity_score": user["similarity_score"],
                    "top_games_overlap": user["top_games_overlap"],
                    "total_games_overlap": user["total_games_overlap"]
                }
                for user in similar_users
            ]
            
            return {
                "recommendations": recommendations,
                "similar_users": similar_users_summary,
                "user_top_games": user_top_games,
                "total_users_analyzed": total_users_pulled
            }
            
        except Exception as e:
            print(f"Error in get_recommendations: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._error_response(str(e))
    
    async def _find_similar_users_batched(
        self,
        steam_id: int,
        user_top_games: List[str],
        batch_size: int,
        max_batches: int,
        target_users: int
    ) -> tuple[List[Dict], int]:
        """Find similar users using batched queries with top-game prioritization
        
        Returns:
            Tuple of (list of user dicts, total count of users pulled from database)
        """
        all_similar_users = []
        seen_steam_ids = set()  # Track unique steam_ids
        last_steam_id = None
        total_users_pulled = 0
        
        print(f"Querying database for users with overlapping TOP games (prioritized matching)...")
        print(f"  User's top {len(user_top_games)} games for matching: {user_top_games[:5]}...")
        print(f"  Target: {target_users} users to analyze")
        
        try:
            for batch_num in range(max_batches):
                print(f"  Fetching batch {batch_num + 1} (up to {batch_size} users)...")
                
                batch_users = self.users_repo.find_similar_users_batch(
                    games_array=user_top_games,
                    batch_size=batch_size,
                    last_steam_id=last_steam_id,
                    exclude_steam_id=steam_id,
                    top_n_priority=len(user_top_games)  # Use all top games for priority
                )
                
                if not batch_users:
                    print(f"  No more users found, stopping...")
                    break
                
                # Deduplicate: only add users we haven't seen before
                unique_batch_users = []
                for user in batch_users:
                    user_steam_id = user.get('steam_id')
                    if user_steam_id not in seen_steam_ids:
                        seen_steam_ids.add(user_steam_id)
                        unique_batch_users.append(user)
                
                total_users_pulled += batch_size # Count actual users pulled (not batch_size)
                print(f"  Pulled {len(batch_users)} users from database ({len(unique_batch_users)} unique, Total unique so far: {len(all_similar_users) + len(unique_batch_users)})")
                
                # If no unique users in this batch, skip ahead in pagination to find new users
                if len(unique_batch_users) == 0 and len(batch_users) > 0:
                    print(f"  All users in batch were duplicates, skipping ahead...")
                    # Jump ahead by using the last steam_id from this batch
                    last_steam_id = batch_users[-1]['steam_id']
                    continue
                
                all_similar_users.extend(unique_batch_users)
                
                # Update pagination cursor
                if batch_users:
                    last_steam_id = batch_users[-1]['steam_id']
                
                # Stop when we've collected enough unique users
                if total_users_pulled >= target_users:
                    print(f"  Reached target of {target_users} unique users, stopping...")
                    # Trim to exact target if we went over
                    all_similar_users = all_similar_users[:target_users]
                    break
            
            print(f"Total users pulled from database: {total_users_pulled}")
            print(f"Total unique users collected: {len(all_similar_users)}")
            return all_similar_users, total_users_pulled
            
        except Exception as e:
            print(f"Error finding similar users: {e}")
            import traceback
            traceback.print_exc()
            return [], 0
    
    def _calculate_similarity_scores(
        self,
        user_top_games: List[str],
        user_owned_games: set,
        potential_users: List[Dict],
    ) -> List[Dict]:
        """Calculate similarity scores for potential users with position-aware weighting"""
        similar_users = []
        user_top_games_set = set(user_top_games)
        top_n = len(user_top_games)
        
        for other_user in potential_users:
            other_steam_id = other_user.get('steam_id')
            other_games_array = other_user.get('games_array', [])
            other_games = other_user.get('games', {})
            other_data = other_user.get('data', {})
            
            if not other_games_array or not other_games:
                continue
            
            # Calculate overlap metrics
            other_top_games = set(other_games_array[:top_n])
            
            # Top N overlap (most important)
            top_overlap = len(user_top_games_set & other_top_games)
            
            if top_overlap == 0:
                continue
            
            # Total overlap - convert other_games_array strings to ints for comparison
            other_games_int_set = set(int(game_id) for game_id in other_games_array)
            total_overlap = len(user_owned_games & other_games_int_set)
            
            # Position-aware similarity score
            # Games at the top of both lists should count much more
            position_weighted_score = 0
            base_overlap_score = 0
            
            for i, game in enumerate(user_top_games):
                if game in other_games_array:
                    try:
                        other_pos = other_games_array.index(game)
                        
                        # Both in top N = very high weight
                        if other_pos < top_n:
                            # Weight decreases with position in both arrays
                            weight = (top_n - i) * (top_n - other_pos)
                            position_weighted_score += weight
                        else:
                            # User's top game, but not in other's top = moderate weight
                            position_weighted_score += (top_n - i)
                        
                        base_overlap_score += 1
                    except ValueError:
                        pass
            
            # Combine scores: position weight is primary, top overlap is secondary
            similarity_score = (position_weighted_score * 1.5) + (top_overlap * 5) + (base_overlap_score * 2)
            
            similar_users.append({
                "steam_id": other_steam_id,
                "persona_name": other_data.get('personaname', 'Unknown User'),
                "similarity_score": similarity_score,
                "top_games_overlap": top_overlap,
                "total_games_overlap": total_overlap,
                "games": other_games
            })
        
        # Sort by similarity score (higher = more similar)
        similar_users.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        # Debug: Show top matches
        if similar_users:
            print(f"Top 5 most similar users:")
            for user in similar_users[:5]:
                print(f"  - {user['persona_name']}: score={user['similarity_score']:.1f}, top_overlap={user['top_games_overlap']}, total_overlap={user['total_games_overlap']}")
        
        return similar_users
    
    def _aggregate_recommendations(
        self,
        similar_users: List[Dict],
        user_owned_games: set,
        min_playtime: int,
        max_recommendations: int
    ) -> List[Dict]:
        """Aggregate game recommendations from similar users"""
        game_recommendations = Counter()
        game_sources = {}
        
        for similar_user in similar_users:
            other_games = similar_user["games"]
            
            for game_id_str, game_data in other_games.items():
                try:
                    game_id = int(game_id_str)
                except (ValueError, TypeError):
                    continue
                
                if game_id in user_owned_games:
                    continue
                
                playtime = game_data.get("playtime_forever", 0)
                if playtime < min_playtime:
                    continue
                
                weight = similar_user["similarity_score"]
                game_recommendations[game_id] += weight
                
                if game_id not in game_sources:
                    game_sources[game_id] = []
                game_sources[game_id].append(similar_user["steam_id"])
        
        # Get top recommendations
        top_recommendations = game_recommendations.most_common(max_recommendations)
        
        return [
            {
                "game_id": game_id,
                "recommendation_score": score,
                "recommended_by_users": game_sources[game_id],
                "recommended_by_count": len(game_sources[game_id])
            }
            for game_id, score in top_recommendations
        ]
    
    @staticmethod
    def _error_response(error: str, user_top_games: Optional[List[str]] = None) -> Dict:
        """Build error response"""
        return {
            "error": error,
            "recommendations": [],
            "similar_users": [],
            "user_top_games": user_top_games or []
        }


# Backward compatibility function
async def get_collaborative_recommendations(
    steam_id: int,
    top_n_games: int = 5,
    min_playtime: int = 60,
    max_similar_users: int = 1000,
    max_recommendations: int = 20
) -> Dict:
    """
    Legacy function for backward compatibility
    Delegates to CollaborativeRecommendationService
    """
    service = CollaborativeRecommendationService()
    return await service.get_recommendations(
        steam_id=steam_id,
        top_n_games=top_n_games,
        min_playtime=min_playtime,
        max_recommendations=max_recommendations
    )



