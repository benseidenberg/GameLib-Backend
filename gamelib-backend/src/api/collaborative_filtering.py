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
        
        if has_filters:
            # Use filtering service to get games matching filters
            result_from_filter = await filtering_service.get_filtered_games(
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
                limit=500
            )
            
            # Type assertion: return_dict=False (default) returns List[Game]
            all_filtered_games: List[Game] = cast(List[Game], result_from_filter)
            
            if not all_filtered_games:
                return {
                    "success": True,
                    "recommendations": [],
                    "similar_users": result.get("similar_users", []),
                    "user_top_games": result.get("user_top_games", []),
                    "total_users_analyzed": result.get("total_users_analyzed", 0),
                    "message": "No games found matching filters"
                }
            
            # Map recommendation scores
            rec_scores = {
                rec["game_id"]: {
                    "recommendation_score": rec["recommendation_score"],
                    "recommended_by_count": rec["recommended_by_count"]
                }
                for rec in result.get("recommendations", [])
            }
            
            # Prioritize games that are in recommendations
            recommended_filtered = []
            other_filtered = []
            
            for game in all_filtered_games:
                if game.game_id in rec_scores:
                    # Create new Game instance with recommendation metadata
                    game_with_rec = game.model_copy(update={
                        'recommendation_score': rec_scores[game.game_id]["recommendation_score"],
                        'recommended_by_count': rec_scores[game.game_id]["recommended_by_count"]
                    })
                    recommended_filtered.append(game_with_rec)
                else:
                    # Create Game instance with zero recommendation scores
                    game_with_rec = game.model_copy(update={
                        'recommendation_score': 0,
                        'recommended_by_count': 0
                    })
                    other_filtered.append(game_with_rec)
            
            # Sort and combine
            recommended_filtered.sort(key=lambda x: x.recommendation_score or 0, reverse=True)
            final_recommendations = recommended_filtered[:max_recommendations or 20]
            
            # Fill remaining slots
            remaining = (max_recommendations or 20) - len(final_recommendations)
            if remaining > 0:
                final_recommendations.extend(other_filtered[:remaining])
            final_recommendations.sort(key=lambda x: x.recommendation_score or 0, reverse=True)
            
            return {
                "success": True,
                "recommendations": [game.model_dump() for game in final_recommendations],
                "similar_users": result.get("similar_users", []),
                "user_top_games": result.get("user_top_games", []),
                "total_users_analyzed": result.get("total_users_analyzed", 0)
            }
        
        # No filters - get game details for recommended game_ids
        recommended_game_ids = [rec["game_id"] for rec in result.get("recommendations", [])]
        
        db_games_list = GamesRepository.find_by_ids(recommended_game_ids)
        
        # Convert list to dict for fast lookup
        db_games: Dict[int, Dict] = {game['game_id']: game for game in db_games_list}
        
        # Build final recommendations list
        recommendations_with_details = []
        for rec in result.get("recommendations", []):
            if len(recommendations_with_details) >= (max_recommendations or 20):
                break
            
            game_id = rec["game_id"]
            if game_id in db_games:
                game_data = db_games[game_id]
                # Convert to Game object
                game = Game.model_validate(game_data)
                # Create Game with recommendation metadata
                game_with_rec = game.model_copy(update={
                    'recommendation_score': rec["recommendation_score"],
                    'recommended_by_count': rec["recommended_by_count"]
                })
                recommendations_with_details.append(game_with_rec.model_dump())
                recommendations_with_details.sort(key=lambda x: x.get('recommendation_score', 0), reverse=True)
        
        return {
            "success": True,
            "recommendations": recommendations_with_details,
            "similar_users": result.get("similar_users", []),
            "user_top_games": result.get("user_top_games", []),
            "total_users_analyzed": result.get("total_users_analyzed", 0)
        }
        
    except Exception as e:
        print(f"Error in collaborative filtering: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
