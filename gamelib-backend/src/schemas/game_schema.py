"""
Game schema definitions
Pydantic model for game data structure
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class Game(BaseModel):
    """
    Complete game information with optional recommendation metadata
    Single unified class for all game data
    """
    # Core game data
    game_id: int
    name: Optional[str] = None
    header_image: Optional[str] = Field(None, alias='image')
    short_description: Optional[str] = Field(None, alias='short_desc')
    genres: Optional[List[str]] = []
    languages: Optional[List[str]] = []
    categories: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    platforms: Optional[Dict[str, bool]] = {}
    release_date: Optional[str] = None
    developers: Optional[List[str]] = []
    publishers: Optional[List[str]] = []
    positive: Optional[int] = 0
    negative: Optional[int] = 0
    price: Optional[str] = "Free"
    price_usd: Optional[float] = 0.0
    steam_url: Optional[str] = ""
    content: Optional[Dict] = None
    required_age: Optional[int] = 0
    
    # Optional recommendation metadata
    recommendation_score: Optional[float] = None
    recommended_by_count: Optional[int] = None
    recommended_by_users: Optional[List[int]] = None
    
    # Optional source information for recommendations
    based_on: Optional[Dict] = None  # For cluster-based recommendations
    
    class Config:
        populate_by_name = True
        from_attributes = True
