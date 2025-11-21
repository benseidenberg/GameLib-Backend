"""
Games database repository
Data access layer for games_db table
"""
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import json
import httpx
from postgrest.base_request_builder import APIResponse
from src.db.supabase_client import supabase

if TYPE_CHECKING:
    from src.schemas.game_schema import Game


class GamesRepository:
    """Repository for games_db table operations"""
    
    @staticmethod
    async def fetch_from_db(game_id: int) -> Optional['Game']:
        """
        Fetch game data from database as Game object
        
        Args:
            game_id: Steam app ID
        
        Returns:
            Game object or None if not found
        """
        try:
            from src.schemas.game_schema import Game
            
            result = supabase.table("games_db").select("*").eq("game_id", game_id).execute()
            
            if result.data and len(result.data) > 0:
                game_data = result.data[0]
                
                # Use model_validate to handle field aliases properly
                return Game.model_validate(game_data)
            
            return None
            
        except Exception as e:
            print(f"DEBUG: Error fetching game from database for {game_id}: {str(e)}")
            return None
    
    @staticmethod
    async def fetch_from_steam(game_id: int, skip_content_filter: bool = False) -> Optional['Game']:
        """
        Fetch detailed game information from Steam API as Game object
        
        Args:
            game_id: Steam app ID
            skip_content_filter: If True, skips content appropriateness check
        
        Returns:
            Game object or None if not found/inappropriate
        """
        try:
            from src.schemas.game_schema import Game
            
            url = f"https://store.steampowered.com/api/appdetails?appids={game_id}&format=json"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    app_data = data.get(str(game_id))
                    if app_data and app_data.get('success') and 'data' in app_data:
                        game_data = app_data['data']
                        
                        # Check if content is appropriate (unless skipped)
                        if not skip_content_filter:
                            from src.services.filtering import FilteringService
                            filtering_service = FilteringService()
                            if not filtering_service.is_content_appropriate(game_data):
                                return None
                        
                        # Extract price information
                        is_free = game_data.get('is_free', False)
                        price_usd = 0.0
                        price_formatted = 'Free'
                        
                        if not is_free and 'price_overview' in game_data:
                            price_info = game_data['price_overview']
                            price_usd = price_info.get('final', 0) / 100.0
                            price_formatted = price_info.get('final_formatted', 'N/A')
                        
                        # Create dict with database field names (aliases)
                        game_dict = {
                            'game_id': game_id,
                            'name': game_data.get('name', 'Unknown Game'),
                            'image': game_data.get('header_image'),
                            'short_desc': game_data.get('short_description'),
                            'detailed_desc': game_data.get('detailed_description'),
                            'genres': [genre.get('description', '') for genre in game_data.get('genres', [])],
                            'languages': [],
                            'categories': [cat.get('description', '') for cat in game_data.get('categories', [])],
                            'tags': [],
                            'platforms': game_data.get('platforms', {}),
                            'release_date': game_data.get('release_date', {}).get('date'),
                            'developers': game_data.get('developers', []),
                            'publishers': game_data.get('publishers', []),
                            'positive': 0,
                            'negative': 0,
                            'price': price_formatted,
                            'price_usd': price_usd,
                            'steam_url': f"https://store.steampowered.com/app/{game_id}/",
                            'content': game_data.get('content_descriptors'),
                            'required_age': game_data.get('required_age', 0)
                        }
                        
                        return Game.model_validate(game_dict)
                    
                    return None
                else:
                    return None
                    
        except Exception as e:
            import traceback
            print(f"DEBUG: Error fetching Steam app details for {game_id}: {str(e)}")
            print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")
            return None
    
    @staticmethod
    async def fetch_details(game_id: int, skip_content_filter: bool = False) -> Optional['Game']:
        """
        Fetch game details as Game object - checks database first, then Steam API as fallback
        
        Args:
            game_id: Steam app ID
            skip_content_filter: If True, skips content appropriateness check
        
        Returns:
            Game object or None if not found
        """
        # Try database first
        db_game = await GamesRepository.fetch_from_db(game_id)
        if db_game:
            return db_game
        
        # Fallback to Steam API
        return await GamesRepository.fetch_from_steam(game_id, skip_content_filter)
    
    @staticmethod
    async def fetch_basic(game_id: int) -> Optional[Dict]:
        """
        Fetch basic game details (title and game_id)
        Checks database first, then Steam API as fallback
        Returns dict for lightweight operations
        
        Args:
            game_id: Steam app ID
        
        Returns:
            Dictionary with game_id and title, or None if not found
        """
        # Try database first
        db_game = await GamesRepository.fetch_from_db(game_id)
        if db_game:
            return {
                "game_id": db_game.game_id,
                "title": db_game.name
            }
        
        # Fallback to Steam API
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={game_id}&format=json"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    app_data = data.get(str(game_id))
                    if app_data and app_data.get('success') and 'data' in app_data:
                        game_data = app_data['data']
                        
                        return {
                            "game_id": game_id,
                            "title": game_data.get('name', 'Unknown Game')
                        }
                
                return None
                
        except Exception as e:
            print(f"DEBUG: Error fetching basic Steam app details for {game_id}: {str(e)}")
            return None
    
    @staticmethod
    def find_by_id(game_id: int) -> Optional[Dict[str, Any]]:
        """
        Find a single game by game_id
        
        Args:
            game_id: Steam application ID
            
        Returns:
            Game data or None if not found
        """
        try:
            response = supabase.table('games_db').select('*').eq('game_id', game_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error finding game {game_id}: {str(e)}")
            return None
    
    @staticmethod
    def find_by_ids(game_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Find multiple games by their game_ids
        
        Args:
            game_ids: List of Steam application IDs
            
        Returns:
            List of game data dictionaries
        """
        if not game_ids:
            return []
        
        try:
            response = supabase.table('games_db').select('*').in_('game_id', game_ids).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error finding games by IDs: {str(e)}")
            return []
    
    @staticmethod
    def find_all(limit: int = 100, order_by: str = 'positive', ascending: bool = False) -> List[Dict[str, Any]]:
        """
        Get all games with ordering and limit
        
        Args:
            limit: Maximum number of games to return
            order_by: Column to order by (positive, negative, metacritic, etc.)
            ascending: Sort order direction
            
        Returns:
            List of game data dictionaries
        """
        try:
            query = supabase.table('games_db').select('*')
            query = query.order(order_by, desc=not ascending)
            query = query.limit(limit)
            response = query.execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error finding all games: {str(e)}")
            return []
    
    @staticmethod
    def find_by_filters(
        game_ids: Optional[List[int]] = None,
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_positive: Optional[int] = None,
        min_negative: Optional[int] = None,
        limit: int = 100,
        order_by: str = 'positive',
        ascending: bool = False
    ) -> List['Game']:
        """
        Find games matching multiple filters using SQL queries
        
        Args:
            game_ids: Filter by specific game_ids
            genres: Filter by genres (array overlap)
            tags: Filter by tags (array overlap)
            categories: Filter by categories (array overlap)
            languages: Filter by supported languages (array overlap)
            platforms: Filter by platforms (windows, mac, linux)
            min_price: Minimum price
            max_price: Maximum price
            min_positive: Minimum positive reviews
            min_negative: Minimum negative reviews
            limit: Maximum results
            order_by: Column to order by
            ascending: Sort direction
            
        Returns:
            List of Game objects matching filters
        """
        try:
            from src.schemas.game_schema import Game
            
            query = supabase.table('games_db').select('*')
            
            # Filter by game_ids if provided
            if game_ids:
                query = query.in_('game_id', game_ids)
            
            # Array overlap filters using 'ov' operator
            if genres:
                query = query.filter('genres', 'ov', json.dumps(genres))
            if tags:
                query = query.filter('tags', 'ov', json.dumps(tags))
            if categories:
                query = query.filter('categories', 'ov', json.dumps(categories))
            if languages:
                query = query.filter('supported_languages', 'ov', json.dumps(languages))
            
            # Platform filters (boolean columns)
            if platforms:
                for platform in platforms:
                    if platform.lower() == 'windows':
                        query = query.eq('windows', True)
                    elif platform.lower() == 'mac':
                        query = query.eq('mac', True)
                    elif platform.lower() == 'linux':
                        query = query.eq('linux', True)
            
            # Price range filters
            if min_price is not None:
                query = query.gte('price', min_price)
            if max_price is not None:
                query = query.lte('price', max_price)
            
            # Review count filters
            if min_positive is not None:
                query = query.gte('positive', min_positive)
            if min_negative is not None:
                query = query.gte('negative', min_negative)
            
            # Ordering and limit
            query = query.order(order_by, desc=not ascending)
            query = query.limit(limit)
            
            response = query.execute()
            
            # Convert to Game objects
            if response.data:
                return [Game.model_validate(game_data) for game_data in response.data]
            return []
            
        except Exception as e:
            print(f"Error finding games by filters: {str(e)}")
            return []
    
    @staticmethod
    def find_by_filters_batch(
        batch_ids: List[int],
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        order_by: str = 'positive'
    ) -> List['Game']:
        """
        Fetch a batch of games by IDs with filters applied
        Used for batch processing in collaborative filtering
        
        Args:
            batch_ids: List of game_ids to fetch
            genres: Filter by genres
            tags: Filter by tags
            categories: Filter by categories
            languages: Filter by languages
            platforms: Filter by platforms
            min_price: Minimum price
            max_price: Maximum price
            order_by: Column to order by
            
        Returns:
            List of Game objects
        """
        if not batch_ids:
            return []
        
        return GamesRepository.find_by_filters(
            game_ids=batch_ids,
            genres=genres,
            tags=tags,
            categories=categories,
            languages=languages,
            platforms=platforms,
            min_price=min_price,
            max_price=max_price,
            limit=len(batch_ids),
            order_by=order_by
        )
    
    @staticmethod
    def count_by_filters(
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> int:
        """
        Count games matching filters
        
        Args:
            Same as find_by_filters
            
        Returns:
            Number of games matching filters
        """
        try:
            query = supabase.table('games_db').select('game_id')
            
            if genres:
                query = query.filter('genres', 'ov', json.dumps(genres))
            if tags:
                query = query.filter('tags', 'ov', json.dumps(tags))
            if categories:
                query = query.filter('categories', 'ov', json.dumps(categories))
            if languages:
                query = query.filter('supported_languages', 'ov', json.dumps(languages))
            
            if platforms:
                for platform in platforms:
                    if platform.lower() == 'windows':
                        query = query.eq('windows', True)
                    elif platform.lower() == 'mac':
                        query = query.eq('mac', True)
                    elif platform.lower() == 'linux':
                        query = query.eq('linux', True)
            
            if min_price is not None:
                query = query.gte('price', min_price)
            if max_price is not None:
                query = query.lte('price', max_price)
            
            response = query.execute()
            return len(response.data) if response.data else 0
            
        except Exception as e:
            print(f"Error counting games: {str(e)}")
            return 0
    
    @staticmethod
    def get_unique_values(column: str) -> List[str]:
        """
        Get unique values for a text array column (genres, tags, categories)
        
        Args:
            column: Column name (genres, tags, categories, supported_languages)
            
        Returns:
            List of unique values
        """
        # This would require aggregation or post-processing
        # For now, return empty list - unique values should be cached
        return []
