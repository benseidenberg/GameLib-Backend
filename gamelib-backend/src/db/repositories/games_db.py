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
        order_by: str = 'positive',
        ascending: bool = False,
        batch_size: int = 75,
        stop_limit: Optional[int] = None,
        apply_content_filter: bool = True,
    ) -> List['Game']:
        """
        Find games matching multiple filters using SQL queries
        
        NOTE: For optimal performance, ensure these PostgreSQL indexes exist:
        - CREATE INDEX idx_games_genres_gin ON games_db USING GIN (genres);
        - CREATE INDEX idx_games_tags_gin ON games_db USING GIN (tags);
        - CREATE INDEX idx_games_categories_gin ON games_db USING GIN (categories);
        - CREATE INDEX idx_games_languages_gin ON games_db USING GIN (languages);
        - CREATE INDEX idx_games_positive ON games_db (positive);
        - CREATE INDEX idx_games_price ON games_db (price);
        
        Args:
            game_ids: Filter by specific game_ids (NO start_index used when provided)
            genres: Filter by genres (array overlap)
            tags: Filter by tags (array overlap)
            categories: Filter by categories (array overlap)
            languages: Filter by supported languages (array overlap)
            platforms: Filter by platforms (windows, mac, linux)
            min_price: Minimum price
            max_price: Maximum price
            min_positive: Minimum positive reviews
            min_negative: Minimum negative reviews
            order_by: Column to order by
            ascending: Sort direction
            batch_size: Batch size for pagination
            stop_limit: Stop when this many games are found (prevents long searches)
            apply_content_filter: If True, filters out inappropriate content
            
        Returns:
            List of Game objects matching filters
        """
        try:
            print("DEBUG: Starting find_by_filters with parameters: ", {
                "game_ids_count": len(game_ids) if game_ids else None,
                "genres": genres,
                "tags": tags,
                "categories": categories,
                "languages": languages,
                "platforms": platforms,
                "min_price": min_price,
                "max_price": max_price,
                "min_positive": min_positive,
                "min_negative": min_negative,
                "ascending": ascending,
                "batch_size": batch_size,
                "stop_limit": stop_limit,
                "apply_content_filter": apply_content_filter
            })
            
            # If game_ids provided, NO start_index - just query those specific IDs
            if game_ids is not None:
                print(f"DEBUG: Querying specific {len(game_ids)} game_ids (no pagination)")
                batch_games = GamesRepository.find_by_filters_batch(
                    game_ids=game_ids,
                    start_index=None,  # NO start_index when game_ids provided
                    batch_size=len(game_ids),  # Get all of them
                    genres=genres,
                    tags=tags,
                    categories=categories,
                    languages=languages,
                    platforms=platforms,
                    min_price=min_price,
                    max_price=max_price,
                    min_positive=min_positive,
                    min_negative=min_negative,
                    order_by=order_by,
                    ascending=ascending,
                    apply_content_filter=apply_content_filter
                )
                return batch_games
            
            # Regular pagination when no game_ids specified
            filtered_games = []
            start_index = 0
            while True:
                batch_games = GamesRepository.find_by_filters_batch(
                    game_ids=None,
                    start_index=start_index,
                    batch_size=batch_size,
                    genres=genres,
                    tags=tags,
                    categories=categories,
                    languages=languages,
                    platforms=platforms,
                    min_price=min_price,
                    max_price=max_price,
                    min_positive=min_positive,
                    min_negative=min_negative,
                    order_by=order_by,
                    ascending=ascending,
                    apply_content_filter=apply_content_filter
                )
                
                if not batch_games:
                    break
                
                filtered_games.extend(batch_games)
                
                # Stop if we've reached the stop_limit
                if stop_limit and len(filtered_games) >= stop_limit:
                    print(f"DEBUG: Reached stop_limit of {stop_limit}, stopping search")
                    filtered_games = filtered_games[:stop_limit]
                    break
                
                if len(batch_games) < batch_size:
                    break
                
                start_index += batch_size
            
            return filtered_games
        except Exception as e:
            print(f"Error finding games by filters: {str(e)}")
            return []
    
    @staticmethod
    def find_by_filters_batch(
        batch_size: int,
        start_index: Optional[int] = None,
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
        order_by: str = 'positive',
        ascending: bool = False,
        apply_content_filter: bool = True
    ) -> List['Game']:
        """
        Fetch games with filters applied using batch processing (ALWAYS uses batching)
        Used for all filtering operations for consistent performance
        
        When game_ids is provided: NO start_index used, queries only those specific IDs
        When game_ids is None: Uses start_index for pagination
        
        Args:
            batch_size: Number of records to fetch in this batch
            start_index: Starting offset for pagination (IGNORED if game_ids provided)
            game_ids: Specific game IDs to query (NO pagination when provided)
            genres: Filter by genres
            tags: Filter by tags (uses SQL array overlap)
            categories: Filter by categories
            languages: Filter by languages
            platforms: Filter by platforms
            min_price: Minimum price
            max_price: Maximum price
            min_positive: Minimum positive reviews
            min_negative: Minimum negative reviews
            order_by: Column to order by
            ascending: Sort direction
            
        Returns:
            List of Game objects (empty list if no more games)
        """
        try:
            from src.schemas.game_schema import Game
            
            from src.services.filtering import FilteringService
            
            query = supabase.table('games_db').select('*')
            
            # If filtering by specific game_ids, add that filter first (most selective)
            # NO start_index used when game_ids provided
            if game_ids is not None:
                if len(game_ids) == 0:
                    return []
                print(f"DEBUG: Filtering by {len(game_ids)} specific game_ids (no start_index)")
                query = query.in_('game_id', game_ids)
            else:
                print(f"DEBUG: find_by_filters_batch - start_index={start_index}, batch_size={batch_size}, order_by={order_by}")
            
            # 1. Apply numeric filters (fast with indexes)
            if min_positive is not None:
                query = query.gte('positive', min_positive)
            if min_negative is not None:
                query = query.gte('negative', min_negative)
            if min_price is not None:
                query = query.gte('price_usd', min_price)
            if max_price is not None:
                query = query.lte('price_usd', max_price)
            
            # 2. Platform filters (JSONB column)
            # Query platforms JSONB column: {"mac":true, "windows":false, "linux":true}
            if platforms:
                for platform in platforms:
                    platform_key = platform.lower()
                    if platform_key in ['windows', 'mac', 'linux']:
                        # Use JSONB containment operator to check if platform is true
                        query = query.filter('platforms', 'cs', f'{{"{platform_key}":true}}')
                            
            # 3. Array contains filters (AND logic - must contain ALL specified items)
            # Format arrays as PostgreSQL array literals: {item1,item2,item3}
            # Uses 'cs' (contains) operator for AND filtering instead of 'ov' (overlaps) for OR
            if genres:
                array_literal = '{' + ','.join(f'"{g}"' for g in genres) + '}'
                query = query.filter('genres', 'cs', array_literal)
            if tags:
                array_literal = '{' + ','.join(f'"{t}"' for t in tags) + '}'
                query = query.filter('tags', 'cs', array_literal)
            if categories:
                array_literal = '{' + ','.join(f'"{c}"' for c in categories) + '}'
                query = query.filter('categories', 'cs', array_literal)
            if languages:
                array_literal = '{' + ','.join(f'"{l}"' for l in languages) + '}'
                query = query.filter('languages', 'cs', array_literal)
            
            # 4. CRITICAL: Apply ordering BEFORE pagination
            query = query.order(order_by, desc=not ascending)
            
            # 5. Apply pagination (only if NOT filtering by game_ids)
            if game_ids is None and start_index is not None:
                query = query.range(start_index, start_index + batch_size - 1)
            elif game_ids is None:
                # No start_index, just limit
                query = query.limit(batch_size)
            # else: game_ids provided, no pagination needed
            
            print(f"DEBUG: Executing query with filters applied")
            response = query.execute()
            print(f"DEBUG: Query returned {len(response.data) if response.data else 0} games")
            
            if not response.data:
                return []
            
            # Convert to Game objects
            games = [Game.model_validate(game_data) for game_data in response.data]
            
            # Apply content filtering if requested
            if apply_content_filter:
                print(f"DEBUG: Applying content filter to {len(games)} games")
                filtered_games = []
                for game in games:
                    game_data = {
                        'name': game.name,
                        'short_description': game.short_description or '',
                        'content_descriptors': game.content or {},
                        'content': game.content or {},
                        'required_age': game.required_age or 0,
                        'tags': game.tags,
                        'categories': game.categories,
                        'genres': game.genres
                    }
                    if FilteringService.is_content_appropriate(game_data):
                        filtered_games.append(game)
                print(f"DEBUG: After content filtering: {len(filtered_games)} games")
                return filtered_games
            
            return games
            
        except Exception as e:
            print(f"Error finding games by filters batch: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
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
            
            # Array contains filters (AND logic - must contain ALL specified items)
            # Uses 'cs' (contains) operator for AND filtering instead of 'ov' (overlaps) for OR
            if genres:
                array_literal = '{' + ','.join(f'"{g}"' for g in genres) + '}'
                query = query.filter('genres', 'cs', array_literal)
            if tags:
                array_literal = '{' + ','.join(f'"{t}"' for t in tags) + '}'
                query = query.filter('tags', 'cs', array_literal)
            if categories:
                array_literal = '{' + ','.join(f'"{c}"' for c in categories) + '}'
                query = query.filter('categories', 'cs', array_literal)
            if languages:
                array_literal = '{' + ','.join(f'"{l}"' for l in languages) + '}'
                query = query.filter('languages', 'cs', array_literal)
            
            if platforms:
                for platform in platforms:
                    platform_key = platform.lower()
                    if platform_key in ['windows', 'mac', 'linux']:
                        # Use JSONB containment operator to check if platform is true
                        query = query.filter('platforms', 'cs', f'{{"{platform_key}":true}}')
            
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
    
    @staticmethod
    def test_query_limit(
        limit: int = 100,
        order_by: str = 'positive',
        tags: Optional[List[str]] = None,
        use_range: bool = False,
        start_index: int = 0
    ) -> Dict[str, Any]:
        """
        Test function to measure query performance with different limits and filters
        
        Args:
            limit: Number of records to fetch
            order_by: Column to order by
            tags: Optional tags filter to test array overlap performance
            use_range: If True, use range() instead of limit()
            start_index: Starting index for range queries
            
        Returns:
            Dictionary with timing info and result count
        """
        import time
        from src.schemas.game_schema import Game
        
        try:
            start_time = time.time()
            
            query = supabase.table('games_db').select('*')
            
            # Apply tag filter if provided (AND logic)
            if tags:
                array_literal = '{' + ','.join(f'"{t}"' for t in tags) + '}'
                query = query.filter('tags', 'cs', array_literal)
            
            # Apply ordering
            query = query.order(order_by, desc=True)
            
            # Apply limit or range
            if use_range:
                query = query.range(start_index, start_index + limit - 1)
            else:
                query = query.limit(limit)
            
            query_build_time = time.time() - start_time
            
            # Execute query
            execute_start = time.time()
            response = query.execute()
            execute_time = time.time() - execute_start
            
            # Convert to Game objects
            convert_start = time.time()
            games = []
            if response.data:
                games = [Game.model_validate(game_data) for game_data in response.data]
            convert_time = time.time() - convert_start
            
            total_time = time.time() - start_time
            
            result = {
                "success": True,
                "limit": limit,
                "use_range": use_range,
                "start_index": start_index if use_range else None,
                "tags_filter": tags,
                "results_count": len(games),
                "timing": {
                    "query_build_ms": round(query_build_time * 1000, 2),
                    "execute_ms": round(execute_time * 1000, 2),
                    "convert_ms": round(convert_time * 1000, 2),
                    "total_ms": round(total_time * 1000, 2)
                },
                "sample_games": [
                    {"game_id": g.game_id, "name": g.name, "positive": g.positive}
                    for g in games[:5]
                ] if games else []
            }
            
            print(f"TEST RESULTS: {result['timing']}")
            return result
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Error in test_query_limit: {error_msg}")
            traceback.print_exc()
            
            return {
                "success": False,
                "error": error_msg,
                "limit": limit,
                "use_range": use_range,
                "tags_filter": tags
            }
