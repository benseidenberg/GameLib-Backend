from fastapi import APIRouter, HTTPException, Query
from src.recommender.recommender import get_collaborative_recommendations
from src.db.supabase_client import supabase
from src.api.recommendations import is_content_appropriate
from typing import Optional, List
import httpx
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

router = APIRouter()


@router.get("/tags")
async def get_available_tags():
    """
    Get all available tags from tags.txt file
    
    Returns:
        List of available tags
    """
    try:
        # Get the path to tags.txt
        current_dir = Path(__file__).resolve().parent.parent
        tags_file_path = current_dir / 'db' / 'tags.txt'
        
        if not tags_file_path.exists():
            return {"tags": []}
        
        # Read and parse tags
        content = tags_file_path.read_text(encoding='utf-8').strip()
        if not content:
            return {"tags": []}
        
        # Split by comma and strip whitespace from each tag
        tags = [tag.strip() for tag in content.split(',') if tag.strip()]
        tags.sort()  # Sort alphabetically for easier browsing
        
        return {"tags": tags}
        
    except Exception as e:
        print(f"Error reading tags: {e}")
        return {"tags": []}


async def get_all_games_by_filter(
    steam_genres: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    steam_categories: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    min_release_date: Optional[str] = None,
    max_release_date: Optional[str] = None,
    min_positive_reviews: Optional[int] = None,
    min_negative_reviews: Optional[int] = None,
    max_price: Optional[float] = None,
    limit: int = 1000
):
    """
    Fetch all games from database matching various filters at SQL level
    Uses PostgreSQL's JSONB operators for efficient array filtering
    
    Args:
        steam_genres: Optional list of Steam genres to filter by
        languages: Optional list of languages to filter by
        steam_categories: Optional list of Steam categories to filter by
        tags: Optional list of tags to filter by
        platforms: Optional list of platforms (mac, linux, windows)
        min_release_date: Optional minimum release date (YYYY-MM-DD)
        max_release_date: Optional maximum release date (YYYY-MM-DD)
        min_positive_reviews: Optional minimum positive review count
        min_negative_reviews: Optional minimum negative review count
        max_price: Optional maximum price in USD
        limit: Maximum number of games to return
    
    Returns:
        List of game info dicts
    """
    try:
        # Start with base query
        query = supabase.table('games_db').select('*')
        
        # Apply price filter at SQL level
        if max_price is not None:
            query = query.lte('price_usd', max_price)
        
        # IMPORTANT: SQL-level JSONB filtering has compatibility issues with PostgREST
        # Always use Python-side filtering for reliability when filters are present
        if steam_genres or languages or steam_categories or tags or platforms or min_release_date or max_release_date or min_positive_reviews or min_negative_reviews:
            print("DEBUG: Filters detected, using Python-side filtering for reliability")
            return await get_all_games_by_filter_python(
                steam_genres=steam_genres,
                languages=languages,
                steam_categories=steam_categories,
                tags=tags,
                platforms=platforms,
                min_release_date=min_release_date,
                max_release_date=max_release_date,
                min_positive_reviews=min_positive_reviews,
                min_negative_reviews=min_negative_reviews,
                max_price=max_price,
                limit=limit
            )
        
        # No filters - just fetch and return, sorted by positive reviews
        query = query.order('positive', desc=True).limit(limit)
        result = query.execute()
        
        if not result.data:
            print("DEBUG: No games returned from SQL query")
            return []
        
        print(f"DEBUG: SQL query (no filters) returned {len(result.data)} games")
        
        # Format results
        games_list = []
        for db_game in result.data:
            price_usd = db_game.get('price_usd', 0.0) or 0.0
            price_formatted = db_game.get('price', 'Free')
            
            games_list.append({
                "appid": db_game.get('game_id'),
                "name": db_game.get('name', f"Game {db_game.get('game_id')}"),
                "header_image": db_game.get('image', ''),
                "short_description": db_game.get('short_desc', ''),
                "genres": db_game.get('genres', []),
                "price": price_formatted,
                "price_usd": price_usd,
                "steam_url": db_game.get('steam_url', f"https://store.steampowered.com/app/{db_game.get('game_id')}")
            })
        
        return games_list
        
    except Exception as e:
        print(f"DEBUG: Error in SQL JSONB genre filtering: {str(e)}")
        import traceback
        traceback.print_exc()
        # Fall back to Python filtering
        print("DEBUG: Falling back to Python-side filtering")
        return await get_all_games_by_filter_python(
            steam_genres=steam_genres,
            languages=languages,
            steam_categories=steam_categories,
            tags=tags,
            platforms=platforms,
            min_release_date=min_release_date,
            max_release_date=max_release_date,
            min_positive_reviews=min_positive_reviews,
            min_negative_reviews=min_negative_reviews,
            max_price=max_price,
            limit=limit
        )


async def get_all_games_by_filter_python(
    steam_genres: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    steam_categories: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    min_release_date: Optional[str] = None,
    max_release_date: Optional[str] = None,
    min_positive_reviews: Optional[int] = None,
    min_negative_reviews: Optional[int] = None,
    max_price: Optional[float] = None,
    limit: int = 1000
):
    """
    Fallback: Fetch games and filter in Python (slower but more compatible)
    Supports: steam_genres, languages, categories, tags, platforms, release dates, review counts, price
    """
    try:
        # Select only needed columns to reduce data transfer
        query = supabase.table('games_db').select(
            'game_id, name, image, short_desc, genres, languages, categories, tags, platforms, '
            'release_date, positive, negative, price, price_usd, steam_url'
        )
        
        if max_price is not None:
            query = query.lte('price_usd', max_price)
        
        # Apply SQL-level filtering for arrays using PostgreSQL's array contains operator
        # For steam_genres: use @> operator to check if genres array contains all selected genres
        if steam_genres and len(steam_genres) > 0:
            # PostgreSQL's @> operator checks if left array contains all elements of right array
            # We need to format it properly for PostgREST
            # Using cs (contains) operator with proper JSON array format
            print(f"DEBUG: Applying SQL-level genre filter for: {steam_genres}")
            for genre in steam_genres:
                # Use contains operator - genres column must contain this value
                query = query.contains('genres', [genre])
        
        # Apply SQL-level filtering for languages
        if languages and len(languages) > 0:
            print(f"DEBUG: Applying SQL-level language filter for: {languages}")
            for language in languages:
                query = query.contains('languages', [language])
        
        # Apply SQL-level filtering for categories
        if steam_categories and len(steam_categories) > 0:
            print(f"DEBUG: Applying SQL-level category filter for: {steam_categories}")
            for category in steam_categories:
                query = query.contains('categories', [category])
        
        # Apply SQL-level filtering for tags
        if tags and len(tags) > 0:
            print(f"DEBUG: Applying SQL-level tags filter for: {tags}")
            for tag in tags:
                query = query.contains('tags', [tag])
        
        # For other filters, we still need Python-side filtering
        # Fetch based on whether we have filters
        has_additional_filters = any([platforms, min_release_date, max_release_date, min_positive_reviews, min_negative_reviews])
        
        if has_additional_filters:
            # Conservative multiplier to avoid timeout
            fetch_limit = min(limit * 3, 3000)
        else:
            fetch_limit = limit
        
        # Sort by positive reviews in descending order
        query = query.order('positive', desc=True).limit(fetch_limit)
        result = query.execute()
        
        if not result.data:
            return []
        
        games_list = []
        checked_count = 0
        
        for db_game in result.data:
            checked_count += 1
            
            # Extract game data
            game_genres = db_game.get('genres', [])
            game_languages = db_game.get('languages', [])
            game_categories = db_game.get('categories', [])
            game_platforms = db_game.get('platforms', {})
            game_release_date = db_game.get('release_date', '')
            game_positive = db_game.get('positive', 0) or 0
            game_negative = db_game.get('negative', 0) or 0
            
            # Steam Genres, Languages, Categories - SKIPPED, already done at SQL level
            
            # Platforms Filter (OR logic - game must be on at least one selected platform)
            if platforms:
                if not isinstance(game_platforms, dict):
                    continue
                
                platform_match = False
                for platform in platforms:
                    platform_lower = platform.lower()
                    if game_platforms.get(platform_lower) == True:
                        platform_match = True
                        break
                
                if not platform_match:
                    continue
            
            # Release Date Filters
            if min_release_date and game_release_date:
                if game_release_date < min_release_date:
                    continue
            
            if max_release_date and game_release_date:
                if game_release_date > max_release_date:
                    continue
            
            # Positive Reviews Filter
            if min_positive_reviews is not None:
                if game_positive < min_positive_reviews:
                    continue
            
            # Negative Reviews Filter
            if min_negative_reviews is not None:
                if game_negative < min_negative_reviews:
                    continue
            
            price_usd = db_game.get('price_usd', 0.0) or 0.0
            price_formatted = db_game.get('price', 'Free')
            
            # Check content appropriateness (filter out adult content)
            # Convert database format to format expected by is_content_appropriate
            game_data_for_filter = {
                'name': db_game.get('name', ''),
                'short_description': db_game.get('short_desc', ''),
                'detailed_description': db_game.get('detailed_desc', ''),
                'content_descriptors': db_game.get('content', {}),
                'content': db_game.get('content', {}),
                'required_age': db_game.get('required_age', 0) or 0,
                'tags': db_game.get('tags', []),
                'categories': [{'description': cat} for cat in game_categories] if isinstance(game_categories, list) else [],
                'genres': [{'description': genre} for genre in game_genres] if isinstance(game_genres, list) else []
            }
            
            if not is_content_appropriate(game_data_for_filter):
                continue
            
            games_list.append({
                "appid": db_game.get('game_id'),
                "name": db_game.get('name', f"Game {db_game.get('game_id')}"),
                "header_image": db_game.get('image', ''),
                "short_description": db_game.get('short_desc', ''),
                "detailed_description": db_game.get('detailed_desc', ''),
                "genres": game_genres,
                "languages": game_languages,
                "categories": game_categories,
                "tags": db_game.get('tags', []),
                "platforms": game_platforms,
                "release_date": game_release_date,
                "developers": db_game.get('developers', []),
                "publishers": db_game.get('publishers', []),
                "positive": game_positive,
                "negative": game_negative,
                "price": price_formatted,
                "price_usd": price_usd,
                "steam_url": db_game.get('steam_url', f"https://store.steampowered.com/app/{db_game.get('game_id')}")
            })
            
            if len(games_list) >= limit:
                break
        
        return games_list
        
    except Exception as e:
        print(f"DEBUG: Error in Python filtering: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


async def get_filtered_games_from_db_batch(
    appids: List[int],
    steam_genres: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    steam_categories: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    min_release_date: Optional[str] = None,
    max_release_date: Optional[str] = None,
    min_positive_reviews: Optional[int] = None,
    min_negative_reviews: Optional[int] = None,
    max_price: Optional[float] = None
):
    """
    Fetch multiple games from games_db with filtering for optimal performance
    
    Args:
        appids: List of Steam app IDs to fetch
        steam_genres: Optional list of Steam genres to filter by
        languages: Optional list of languages to filter by
        steam_categories: Optional list of Steam categories to filter by
        platforms: Optional list of platforms (mac, linux, windows)
        min_release_date: Optional minimum release date (YYYY-MM-DD)
        max_release_date: Optional maximum release date (YYYY-MM-DD)
        min_positive_reviews: Optional minimum positive review count
        min_negative_reviews: Optional minimum negative review count
        max_price: Optional maximum price in USD
    
    Returns:
        Dictionary mapping appid -> game info for all matching games
    """
    try:
        if not appids:
            return {}
        
        # Start with base query
        query = supabase.table('games_db').select('*').in_('game_id', appids)
        
        # Apply price filter at SQL level
        if max_price is not None:
            query = query.lte('price_usd', max_price)
        
        # Sort by positive reviews in descending order
        query = query.order('positive', desc=True)
        
        # Execute query
        result = query.execute()
        
        if not result.data:
            print(f"DEBUG: SQL query returned 0 results for {len(appids)} appids")
            return {}
        
        print(f"DEBUG: SQL query returned {len(result.data)} games before filtering")
        if steam_genres:
            print(f"DEBUG: Filtering for steam_genres: {steam_genres}")
        if languages:
            print(f"DEBUG: Filtering for languages: {languages}")
        if steam_categories:
            print(f"DEBUG: Filtering for steam_categories: {steam_categories}")
        
        # Post-process for all filters
        games_dict = {}
        filtered_out_count = 0
        for db_game in result.data:
            appid = db_game.get('game_id')
            
            # Extract game data
            game_genres = db_game.get('genres', [])
            game_languages = db_game.get('languages', [])
            game_categories = db_game.get('categories', [])
            game_platforms = db_game.get('platforms', {})
            game_release_date = db_game.get('release_date', '')
            game_positive = db_game.get('positive', 0) or 0
            game_negative = db_game.get('negative', 0) or 0
            
            # Steam Genres Filter (AND logic - must have ALL selected genres)
            if steam_genres:
                game_genres_lower = [g.lower() if isinstance(g, str) else g for g in game_genres]
                genres_lower = [g.lower() if isinstance(g, str) else g for g in steam_genres]
                
                # Check if ALL selected genres are present
                if not all(genre in game_genres_lower for genre in genres_lower):
                    filtered_out_count += 1
                    continue
            
            # Languages Filter (AND logic - must have ALL selected languages)
            if languages:
                if not isinstance(game_languages, list):
                    filtered_out_count += 1
                    continue
                game_languages_lower = [str(l).lower() for l in game_languages]
                languages_lower = [str(l).lower() for l in languages]
                # Check if ALL selected languages are present
                if not all(lang in game_languages_lower for lang in languages_lower):
                    filtered_out_count += 1
                    continue
            
            # Steam Categories Filter (AND logic - must have ALL selected categories)
            if steam_categories:
                if not isinstance(game_categories, list):
                    filtered_out_count += 1
                    continue
                game_categories_lower = [str(c).lower() for c in game_categories]
                categories_lower = [str(c).lower() for c in steam_categories]
                # Check if ALL selected categories are present
                if not all(cat in game_categories_lower for cat in categories_lower):
                    filtered_out_count += 1
                    continue
            
            # Platforms Filter
            if platforms:
                if not isinstance(game_platforms, dict):
                    filtered_out_count += 1
                    continue
                platform_match = False
                for platform in platforms:
                    if game_platforms.get(platform.lower()) == True:
                        platform_match = True
                        break
                if not platform_match:
                    filtered_out_count += 1
                    continue
            
            # Release Date Filters
            if min_release_date and game_release_date:
                if game_release_date < min_release_date:
                    filtered_out_count += 1
                    continue
            if max_release_date and game_release_date:
                if game_release_date > max_release_date:
                    filtered_out_count += 1
                    continue
            
            # Positive Reviews Filter
            if min_positive_reviews is not None:
                if game_positive < min_positive_reviews:
                    filtered_out_count += 1
                    continue
            
            # Negative Reviews Filter
            if min_negative_reviews is not None:
                if game_negative < min_negative_reviews:
                    filtered_out_count += 1
                    continue
            
            # Extract price information
            price_usd = db_game.get('price_usd', 0.0) or 0.0
            price_formatted = db_game.get('price', 'Free')
            
            # Check content appropriateness (filter out adult content)
            # Convert database format to format expected by is_content_appropriate
            game_data_for_filter = {
                'name': db_game.get('name', ''),
                'short_description': db_game.get('short_desc', ''),
                'detailed_description': db_game.get('detailed_desc', ''),
                'content_descriptors': db_game.get('content', {}),
                'content': db_game.get('content', {}),  # Also include as 'content' for database format
                'required_age': db_game.get('required_age', 0) or 0,
                'tags': db_game.get('tags', []),
                'categories': [{'description': cat} for cat in game_categories] if isinstance(game_categories, list) else [],
                'genres': [{'description': genre} for genre in game_genres] if isinstance(game_genres, list) else []
            }
            
            if not is_content_appropriate(game_data_for_filter):
                filtered_out_count += 1
                continue
            
            games_dict[appid] = {
                "appid": appid,
                "name": db_game.get('name', f"Game {appid}"),
                "header_image": db_game.get('image', ''),
                "short_description": db_game.get('short_desc', ''),
                "detailed_description": db_game.get('detailed_desc', ''),
                "genres": game_genres,
                "languages": game_languages,
                "categories": game_categories,
                "tags": db_game.get('tags', []),
                "platforms": game_platforms,
                "release_date": game_release_date,
                "developers": db_game.get('developers', []),
                "publishers": db_game.get('publishers', []),
                "positive": game_positive,
                "negative": game_negative,
                "price": price_formatted,
                "price_usd": price_usd,
                "steam_url": db_game.get('steam_url', f"https://store.steampowered.com/app/{appid}")
            }
        
        
        return games_dict
        
    except Exception as e:
        print(f"DEBUG: Error batch fetching games from database: {str(e)}")
        return {}


@router.get("/collaborative-recommendations/{steam_id}/")
async def get_collaborative_filtering_recommendations(
    steam_id: int,
    top_n_games: Optional[int] = 5,
    min_playtime: Optional[int] = 600,
    max_similar_users: Optional[int] = 1000,
    max_recommendations: Optional[int] = 20,
    steam_genres: Optional[List[str]] = Query(None),
    languages: Optional[List[str]] = Query(None),
    steam_categories: Optional[List[str]] = Query(None),
    tags: Optional[List[str]] = Query(None),
    platforms: Optional[List[str]] = Query(None),
    min_release_date: Optional[str] = None,
    max_release_date: Optional[str] = None,
    min_positive_reviews: Optional[int] = None,
    min_negative_reviews: Optional[int] = None,
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
        steam_genres: List of Steam genres to filter by (optional)
        languages: List of languages to filter by (optional)
        steam_categories: List of Steam categories to filter by (optional)
        tags: List of SteamSpy tags to filter by (optional)
        platforms: List of platforms to filter by - mac, linux, windows (optional)
        min_release_date: Minimum release date in YYYY-MM-DD format (optional)
        max_release_date: Maximum release date in YYYY-MM-DD format (optional)
        min_positive_reviews: Minimum positive review count (optional)
        min_negative_reviews: Minimum negative review count (optional)
        max_price: Maximum price in USD to filter by (optional, None = no limit)
    
    Returns:
        Dictionary containing recommendations, similar users, and metadata
    """
    try:
        # Request more recommendations than needed to account for filtering
        # This ensures we still get enough results after filtering
        buffer_multiplier = 1
        has_filters = any([steam_genres, languages, steam_categories, tags, platforms, min_release_date, max_release_date, min_positive_reviews, min_negative_reviews, max_price])
        if has_filters:
            if steam_genres is not None:
                buffer_multiplier += len(steam_genres)*10
            if max_price is not None:
                buffer_multiplier += 5
            if languages or steam_categories or platforms:
                buffer_multiplier += 5

        internal_max_recommendations = max_recommendations * buffer_multiplier if max_recommendations else 60
        
        # Handle "no limit" case for max_similar_users (large number means no practical limit)
        effective_max_similar_users = max_similar_users if (max_similar_users and max_similar_users < 500000) else 999999
        
        result = await get_collaborative_recommendations(
            steam_id=steam_id,
            top_n_games=top_n_games if top_n_games is not None else 5,
            min_playtime=min_playtime if min_playtime is not None else 600,
            max_similar_users=effective_max_similar_users,
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
        
        # If filters are applied, use a hybrid approach:
        # 1. Get all games matching filters from database
        # 2. Prioritize games that appear in collaborative recommendations
        # 3. Fill remaining slots with other filtered games
        if has_filters:
            # Get all games matching filters
            all_filtered_games = await get_all_games_by_filter(
                steam_genres=steam_genres,
                languages=languages,
                steam_categories=steam_categories,
                tags=tags,
                platforms=platforms,
                min_release_date=min_release_date,
                max_release_date=max_release_date,
                min_positive_reviews=min_positive_reviews,
                min_negative_reviews=min_negative_reviews,
                max_price=max_price,
                limit=500  # Reduced from 1000 to avoid timeout
            )
            
            if not all_filtered_games:
                print("DEBUG: No games found matching filters in database")
                return {
                    "success": True,
                    "recommendations": [],
                    "similar_users": result.get("similar_users", []),
                    "user_top_games": result.get("user_top_games", []),
                    "total_users_analyzed": result.get("total_users_analyzed", 0),
                    "similar_users_found": result.get("similar_users_found", 0),
                    "message": "No games found matching the specified filters"
                }
            
            # Create a map of recommended appids to their scores
            rec_scores = {rec["appid"]: {
                "recommendation_score": rec["recommendation_score"],
                "recommended_by_count": rec["recommended_by_count"]
            } for rec in result.get("recommendations", [])}
            
            # Separate games into recommended and non-recommended
            recommended_filtered = []
            other_filtered = []
            
            for game in all_filtered_games:
                if game["appid"] in rec_scores:
                    game["recommendation_score"] = rec_scores[game["appid"]]["recommendation_score"]
                    game["recommended_by_count"] = rec_scores[game["appid"]]["recommended_by_count"]
                    recommended_filtered.append(game)
                else:
                    game["recommendation_score"] = 0
                    game["recommended_by_count"] = 0
                    other_filtered.append(game)
            
            # Sort recommended games by score
            recommended_filtered.sort(key=lambda x: x["recommendation_score"], reverse=True)
            
            # Combine: prioritize collaborative recommendations, then other filtered games
            recommendations_with_details = recommended_filtered[:max_recommendations or 20]
            
            # Fill remaining slots if needed
            remaining_slots = (max_recommendations or 20) - len(recommendations_with_details)
            if remaining_slots > 0:
                recommendations_with_details.extend(other_filtered[:remaining_slots])
                        
            return {
                "success": True,
                "recommendations": recommendations_with_details,
                "similar_users": result.get("similar_users", []),
                "user_top_games": result.get("user_top_games", []),
                "total_users_analyzed": result.get("total_users_analyzed", 0),
                "similar_users_found": result.get("similar_users_found", 0),
                "failed_games_count": 0
            }
        
        # Extract all appids from recommendations
        recommended_appids = [rec["appid"] for rec in result.get("recommendations", [])]
        
        # Batch fetch games from database with filtering
        db_games = await get_filtered_games_from_db_batch(
            recommended_appids,
            steam_genres=steam_genres,
            languages=languages,
            steam_categories=steam_categories,
            platforms=platforms,
            min_release_date=min_release_date,
            max_release_date=max_release_date,
            min_positive_reviews=min_positive_reviews,
            min_negative_reviews=min_negative_reviews,
            max_price=max_price
        )
        print(f"DEBUG: Retrieved {len(db_games)} games from database after filtering")
        
        # Build recommendations list using database results
        recommendations_with_details = []
        missing_appids = []
        
        for rec in result.get("recommendations", []):
            # Stop once we have enough recommendations
            if len(recommendations_with_details) >= (max_recommendations or 20):
                break
            
            appid = rec["appid"]
            
            # Check if we got this game from database
            if appid in db_games:
                game_info = db_games[appid]
                game_info["recommendation_score"] = rec["recommendation_score"]
                game_info["recommended_by_count"] = rec["recommended_by_count"]
                recommendations_with_details.append(game_info)
            else:
                # Game not in database or filtered out - track for potential Steam API fallback
                missing_appids.append(appid)
        
        # If we don't have enough recommendations, fall back to Steam API for missing games
        failed_games = []
        if len(recommendations_with_details) < (max_recommendations or 20) and missing_appids:
            print(f"DEBUG: Fetching {len(missing_appids[:10])} missing games from Steam API")
            
            # Map appids to their recommendation data
            rec_map = {rec["appid"]: rec for rec in result.get("recommendations", [])}
            
            async with httpx.AsyncClient() as client:
                for appid in missing_appids:
                    if len(recommendations_with_details) >= (max_recommendations or 20):
                        break
                    
                    try:
                        url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=US"
                        response = await client.get(url, timeout=5.0)
                        
                        if response.status_code == 200:
                            data = response.json()
                            
                            if str(appid) in data and data[str(appid)]["success"]:
                                game_data = data[str(appid)]["data"]
                                
                                # Check content appropriateness first
                                if not is_content_appropriate(game_data):
                                    continue
                                
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
                                
                                # Apply steam genre filter
                                if steam_genres:
                                    if not any(genre in game_genres for genre in steam_genres):
                                        continue
                                
                                # Apply price filter
                                if max_price is not None and price_usd > max_price:
                                    continue
                                
                                rec = rec_map.get(appid, {})
                                recommendations_with_details.append({
                                    "appid": appid,
                                    "name": game_data.get("name", f"Game {appid}"),
                                    "header_image": game_data.get("header_image", ""),
                                    "short_description": game_data.get("short_description", ""),
                                    "genres": game_genres,
                                    "price": price_formatted,
                                    "price_usd": price_usd,
                                    "recommendation_score": rec.get("recommendation_score", 0),
                                    "recommended_by_count": rec.get("recommended_by_count", 0),
                                    "steam_url": f"https://store.steampowered.com/app/{appid}"
                                })
                            else:
                                failed_games.append(appid)
                        else:
                            failed_games.append(appid)
                            
                    except Exception as e:
                        print(f"Error fetching details for game {appid}: {str(e)}")
                        failed_games.append(appid)
        
        if failed_games:
            print(f"Failed to fetch details for {len(failed_games)} games: {failed_games[:10]}")
        
        return {
            "success": True,
            "recommendations": recommendations_with_details,
            "similar_users": result.get("similar_users", []),
            "user_top_games": result.get("user_top_games", []),
            "total_users_analyzed": result.get("total_users_analyzed", 0),
            "similar_users_found": result.get("similar_users_found", 0),
            "failed_games_count": len(failed_games)
        }
        
    except Exception as e:
        print(f"Error in get_collaborative_filtering_recommendations: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
