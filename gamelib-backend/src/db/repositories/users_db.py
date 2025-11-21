"""
Users database repository
Data access layer for users table
"""
from typing import List, Optional, Dict, Any
import json
from src.db.supabase_client import supabase
from src.schemas.user_schema import User


class UsersRepository:
    """Repository for users table operations"""
    
    @staticmethod
    def find_by_steam_id(steam_id: int) -> Optional[User]:
        """
        Find a user by their Steam ID
        
        Args:
            steam_id: User's Steam ID
            
        Returns:
            User object or None if not found
        """
        try:
            response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
            if response.data and len(response.data) > 0:
                return User.model_validate(response.data[0])
            return None
        except Exception as e:
            print(f"Error finding user {steam_id}: {str(e)}")
            return None
    
    @staticmethod
    def create(user_data: User) -> Optional[User]:
        """
        Create a new user
        
        Args:
            user_data: User creation data
            
        Returns:
            Created User object or None on error
        """
        try:
            response = supabase.table('users').insert(user_data.model_dump()).execute()
            if response.data and len(response.data) > 0:
                return User.model_validate(response.data[0])
            return None
        except Exception as e:
            print(f"Error creating user: {str(e)}")
            return None
    
    @staticmethod
    def update(steam_id: int, update_data: Dict[str, Any]) -> Optional[User]:
        """
        Update an existing user
        
        Args:
            steam_id: User's Steam ID
            update_data: Fields to update (dict with field names and values)
            
        Returns:
            Updated User object or None on error
        """
        try:
            # Only include non-None fields
            update_dict = {k: v for k, v in update_data.items() if v is not None}
            
            if not update_dict:
                # Nothing to update
                return UsersRepository.find_by_steam_id(steam_id)
            
            response = supabase.table('users').update(update_dict).eq('steam_id', steam_id).execute()
            if response.data and len(response.data) > 0:
                return User.model_validate(response.data[0])
            return None
        except Exception as e:
            print(f"Error updating user {steam_id}: {str(e)}")
            return None
    
    @staticmethod
    def upsert(user_data: User) -> Optional[User]:
        """
        Insert or update user (upsert)
        
        Args:
            user_data: User data to upsert
            
        Returns:
            User object after upsert or None on error
        """
        try:
            response = supabase.table('users').upsert(
                user_data.model_dump(),
                on_conflict='steam_id'
            ).execute()
            if response.data and len(response.data) > 0:
                return User.model_validate(response.data[0])
            return None
        except Exception as e:
            print(f"Error upserting user: {str(e)}")
            return None
    
    @staticmethod
    def increment_login_count(steam_id: int) -> Optional[User]:
        """
        Increment user's login count by 1
        
        Args:
            steam_id: User's Steam ID
            
        Returns:
            Updated User object or None on error
        """
        try:
            user = UsersRepository.find_by_steam_id(steam_id)
            if not user:
                return None
            
            new_count = user.login_count + 1
            return UsersRepository.update(steam_id, {'login_count': new_count})
        except Exception as e:
            print(f"Error incrementing login count for {steam_id}: {str(e)}")
            return None
    
    @staticmethod
    def update_games_array(steam_id: int, games_array: List[str]) -> Optional[User]:
        """
        Update user's sorted games array
        
        Args:
            steam_id: User's Steam ID
            games_array: New games array (sorted by playtime)
            
        Returns:
            Updated User object or None on error
        """
        return UsersRepository.update(steam_id, {'games_array': games_array})
    
    @staticmethod
    def find_similar_users(
        games_array: List[str],
        limit: int = 500,
        exclude_steam_id: Optional[int] = None,
        min_overlap: int = 5,
        top_n_priority: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find users with similar game libraries, prioritizing top game matches
        
        Args:
            games_array: Reference games array to match against (sorted by playtime)
            limit: Maximum number of users to return
            exclude_steam_id: Steam ID to exclude from results
            min_overlap: Minimum number of overlapping games (deprecated, now uses top_n)
            top_n_priority: Number of top games to prioritize in matching
            
        Returns:
            List of similar users with their data, ordered by match quality
        """
        if not games_array:
            return []
        
        try:
            # Focus on top N games for more selective matching
            top_games = games_array[:top_n_priority]
            top_games_set = set(top_games)
            
            # Only select necessary fields for performance
            query = supabase.table('users').select('steam_id,games_array,games,data')
            
            # Find users with overlapping TOP games (more selective)
            top_array_literal = '{"' + '","'.join(top_games) + '"}'
            query = query.filter('games_array', 'ov', top_array_literal)
            
            # Exclude specific user if provided
            if exclude_steam_id:
                query = query.neq('steam_id', exclude_steam_id)
            
            # Limit results - don't fetch too many
            query = query.limit(limit)
            
            response = query.execute()
            users = response.data if response.data else []
            
            if not users:
                return []
            
            # Rank users by top-N overlap and position weighting
            ranked_users = []
            for user in users:
                user_games_array = user.get('games_array', [])
                if not user_games_array or len(user_games_array) < 3:
                    continue
                
                # Calculate overlap in top N games
                other_top_games = set(user_games_array[:top_n_priority])
                top_overlap = len(top_games_set & other_top_games)
                
                # Must have at least some overlap in top games
                if top_overlap < 1:
                    continue
                
                # Position-weighted score: matching early games counts more
                # Optimized: only check top 5 games and their top 20 for speed
                position_score = 0
                for i, game in enumerate(top_games[:min(5, top_n_priority)]):
                    if game in user_games_array[:20]:
                        try:
                            other_pos = user_games_array.index(game)
                            # High weight for both users having game in top positions
                            position_weight = max(0, (top_n_priority - i) * (top_n_priority - other_pos))
                            position_score += position_weight
                        except ValueError:
                            pass
                
                user['_combined_score'] = (top_overlap * 100) + position_score
                ranked_users.append(user)
            
            # Sort by match quality
            ranked_users.sort(key=lambda x: x['_combined_score'], reverse=True)
            
            # Clean up scoring metadata
            for user in ranked_users:
                user.pop('_combined_score', None)
            
            return ranked_users
            
        except Exception as e:
            print(f"Error finding similar users: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def find_similar_users_batch(
        games_array: List[str],
        batch_size: int = 750,
        last_steam_id: Optional[int] = None,
        exclude_steam_id: Optional[int] = None,
        top_n_priority: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar users in batches, prioritizing those with matching top games
        Uses PostgreSQL array operations for efficient top-N overlap calculation
        
        Args:
            games_array: Reference games array to match against (sorted by playtime)
            batch_size: Number of users per batch
            last_steam_id: Last steam_id from previous batch (for pagination)
            exclude_steam_id: Steam ID to exclude from results
            top_n_priority: Number of top games to prioritize in matching (default 10)
            
        Returns:
            List of users in this batch, ordered by top-N game overlap
        """
        if not games_array:
            return []
        
        try:
            # Take the top N games for priority matching
            top_games = games_array[:top_n_priority]
            
            # Use optimized query with minimal data fetch
            # Only select necessary fields to reduce data transfer
            query = supabase.table('users').select('steam_id,games_array,games,data')
            
            # Find users with overlapping top games (more selective)
            top_array_literal = '{"' + '","'.join(top_games) + '"}'
            query = query.filter('games_array', 'ov', top_array_literal)
            
            # Exclude specific user if provided
            if exclude_steam_id:
                query = query.neq('steam_id', exclude_steam_id)
            
            # Pagination using steam_id
            if last_steam_id:
                query = query.gt('steam_id', last_steam_id)
            
            # Fetch only what we need - we'll rank and filter as we go
            query = query.limit(batch_size)
            
            response = query.execute()
            users = response.data if response.data else []
            
            if not users:
                return []
            
            # Quick client-side ranking (already limited set)
            top_games_set = set(top_games)
            
            ranked_users = []
            for user in users:
                user_games_array = user.get('games_array', [])
                if not user_games_array or len(user_games_array) < 3:
                    continue
                
                # Quick top-N overlap check (first N games from each user)
                other_top_games = set(user_games_array[:top_n_priority])
                top_overlap = len(top_games_set & other_top_games)
                
                # Must have at least 1 top game overlap
                if top_overlap < 1:
                    continue
                
                # Calculate position-weighted score for ranking
                position_score = 0
                for i, game in enumerate(top_games[:top_n_priority]):  # Only check top 10 for speed
                    if game in user_games_array: 
                        try:
                            other_pos = user_games_array.index(game)
                            if other_pos < top_n_priority:
                                position_weight = (top_n_priority - i) * (top_n_priority - other_pos)
                                position_score += position_weight
                        except ValueError:
                            pass
                
                user['_combined_score'] = (top_overlap * 50) + position_score
                ranked_users.append(user)
            
            # Sort by match quality
            ranked_users.sort(key=lambda x: x['_combined_score'], reverse=True)
            
            # Clean up scoring metadata
            for user in ranked_users:
                user.pop('_combined_score', None)
            
            return ranked_users
            
        except Exception as e:
            print(f"Error finding similar users batch: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def count_all() -> int:
        """
        Count total users in database
        
        Returns:
            Total number of users
        """
        try:
            response = supabase.table('users').select('steam_id').execute()
            return len(response.data) if response.data else 0
        except Exception as e:
            print(f"Error counting users: {str(e)}")
            return 0
    
    @staticmethod
    def delete(steam_id: int) -> bool:
        """
        Delete a user by steam_id
        
        Args:
            steam_id: User's Steam ID
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            response = supabase.table('users').delete().eq('steam_id', steam_id).execute()
            return response.data is not None
        except Exception as e:
            print(f"Error deleting user {steam_id}: {str(e)}")
            return False
