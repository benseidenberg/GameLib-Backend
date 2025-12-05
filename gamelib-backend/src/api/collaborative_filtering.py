"""
Collaborative Filtering API Routes
HTTP endpoints for collaborative filtering recommendations
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Optional, List, cast
from src.services.collaborative_recommendations import CollaborativeRecommendationService
from src.services.filtering import FilteringService
from src.schemas.game_schema import Game
from src.db.repositories.games_db import GamesRepository
import httpx

router = APIRouter()

# Initialize services
collab_service = CollaborativeRecommendationService()
filtering_service = FilteringService()


@router.get("/tags")
async def get_available_tags():
    """
    Get all available tags for filtering
    
    Returns:
        List of available tags
    """
    try:
        tags = FilteringService.get_available_tags()
        return {"tags": tags}
    except Exception as e:
        print(f"Error getting tags: {e}")
        return {"tags": []}


@router.get("/collaborative-recommendations/{steam_id}/")
async def get_collaborative_filtering_recommendations(
    steam_id: int,
    top_n_games: Optional[int] = 5,
    min_playtime: Optional[int] = 60,
    max_total_users: Optional[int] = 1000,
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
    Get game recommendations based on collaborative filtering
    
    Args:
        steam_id: User's Steam ID
        top_n_games: Number of top games to use for matching (default: 5)
        min_playtime: Minimum playtime in minutes (default: 60)
        max_similar_users: Maximum similar users to analyze (default: 1000)
        max_recommendations: Maximum recommendations to return (default: 20)
        steam_genres: Filter by Steam genres
        languages: Filter by languages
        steam_categories: Filter by categories
        tags: Filter by tags
        platforms: Filter by platforms (windows, mac, linux)
        min_release_date: Minimum release date (YYYY-MM-DD)
        max_release_date: Maximum release date (YYYY-MM-DD)
        min_positive_reviews: Minimum positive reviews
        min_negative_reviews: Minimum negative reviews
        max_price: Maximum price in USD
    
    Returns:
        Recommendations with metadata
    """
    try:
        # Validate steam_id
        if steam_id <= 0 or steam_id > 999999999999999999:
            raise HTTPException(status_code=400, detail="Invalid Steam ID")
        
        # Get collaborative recommendations
        result = await collab_service.get_recommendations(
            steam_id=steam_id,
            top_n_games=top_n_games or 5,
            min_playtime=min_playtime or 60,
            max_total_users=max_total_users or 1000,
            max_recommendations=(max_recommendations * 3) if max_recommendations else 60  # Get extra for filtering
        )
        
        if "error" in result and result["error"]:
            return {
                "success": False,
                "error": result["error"],
                "recommendations": [],
                "similar_users": result.get("similar_users", []),
                "user_top_games": result.get("user_top_games", [])
            }
        
        # Check if any filters are applied
        has_filters = any([
            steam_genres, languages, steam_categories, tags, platforms,
            min_release_date, max_release_date, min_positive_reviews,
            min_negative_reviews, max_price
        ])
        
        # Step 1: Get recommended game_ids from collaborative filtering
        recommended_game_ids = [rec["game_id"] for rec in result.get("recommendations", [])]
        
        if not recommended_game_ids:
            return {
                "success": True,
                "recommendations": [],
                "similar_users": result.get("similar_users", []),
                "user_top_games": result.get("user_top_games", []),
                "total_users_analyzed": result.get("total_users_analyzed", 0),
                "message": "No recommendations found"
            }
        
        # Create recommendation score map for later sorting
        rec_scores = {
            rec["game_id"]: {
                "recommendation_score": rec["recommendation_score"],
                "recommended_by_count": rec["recommended_by_count"]
            }
            for rec in result.get("recommendations", [])
        }
        
        # Set target count early for use in queries
        target_count = max_recommendations or 20
        
        # Step 2: Filter recommended games by game_ids + filters
        # Content filtering happens in find_by_filters when filters are present
        print(f"DEBUG: Filtering {len(recommended_game_ids)} recommended games with filters")
        result_from_filter = await filtering_service.get_filtered_games(
            game_ids=recommended_game_ids,
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
            limit=target_count * 3,  # Get extra for sorting and limiting
            return_dict=False,
            apply_content_filter=True  # Content filter in DB layer
        )
        
        filtered_games: List[Game] = cast(List[Game], result_from_filter)
        print(f"DEBUG: After DB filtering: {len(filtered_games)} games")
        for game in filtered_games[:5]:
            print(f"  - {game.game_id}: {game.name}")
        
        # Step 3: Content filtering (only if NO filters were applied)
        # When filters exist, content filtering already happened in find_by_filters
        content_filtered_games = []
        if not has_filters:
            print(f"DEBUG: No filters - applying content filtering to {len(filtered_games)} games")
            for game in filtered_games:
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
                
                if filtering_service.is_content_appropriate(game_data):
                    content_filtered_games.append(game)
            print(f"DEBUG: After content filtering but no game filters: {len(content_filtered_games)} games")
        else:
            # Filters were applied, content already filtered in DB
            print(f"DEBUG: Filters applied - content already filtered, {len(filtered_games)} games")
            content_filtered_games = filtered_games
        
        # Step 4: Backfill if we don't have enough games
        target_count = max_recommendations or 20
        if len(content_filtered_games) < target_count:
            needed_count = target_count - len(content_filtered_games)
            print(f"DEBUG: Need {needed_count} more games, fetching additional matches")
            
            # Get already included game_ids to avoid duplicates
            existing_game_ids = {game.game_id for game in content_filtered_games}
            
            # Fetch additional games WITHOUT game_id restriction
            # stop_limit prevents searching forever
            additional_games_result = await filtering_service.get_filtered_games(
                game_ids=None,  # Open query
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
                limit=needed_count + 50,  # stop_limit: get a bit extra for deduplication
                return_dict=False,
                apply_content_filter=True  # Content filter in DB
            )
            
            additional_games: List[Game] = cast(List[Game], additional_games_result)
            
            # Add non-duplicate games
            for game in additional_games:
                if game.game_id in existing_game_ids:
                    continue  # Skip duplicates
                
                if len(content_filtered_games) >= target_count:
                    break
                
                content_filtered_games.append(game)
                existing_game_ids.add(game.game_id)
            
            print(f"DEBUG: After backfill: {len(content_filtered_games)} games total")
        
        # Step 5: Add recommendation metadata and sort by recommended_by_count
        final_recommendations = []
        for game in content_filtered_games:
            if game.game_id in rec_scores:
                # Game from collaborative filtering - use actual scores
                game_with_rec = game.model_copy(update={
                    'recommendation_score': rec_scores[game.game_id]["recommendation_score"],
                    'recommended_by_count': rec_scores[game.game_id]["recommended_by_count"]
                })
            else:
                # Backfill game - assign default scores
                game_with_rec = game.model_copy(update={
                    'recommendation_score': 0,
                    'recommended_by_count': 0
                })
            final_recommendations.append(game_with_rec)
        
        # Sort by recommended_by_count (number of users who play each game)
        final_recommendations.sort(key=lambda x: x.recommended_by_count or 0, reverse=True)
        
        # Limit to max_recommendations
        final_recommendations = final_recommendations[:target_count]
        
        return {
            "success": True,
            "recommendations": [game.model_dump() for game in final_recommendations],
            "similar_users": result.get("similar_users", []),
            "user_top_games": result.get("user_top_games", []),
            "total_users_analyzed": result.get("total_users_analyzed", 0)
        }
        
    except Exception as e:
        print(f"Error in collaborative filtering: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
