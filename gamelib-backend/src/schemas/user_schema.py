from pydantic import BaseModel
from typing import Optional, List

class UserCreate(BaseModel):
    steam_id: int
    data: Optional[dict] = None
    games: Optional[dict] = None
    games_array: Optional[List[str]] = None
    login_count : Optional[int] = 1

class UserResponse(BaseModel):
    steam_id : int
    data: Optional[dict] = None
    games: Optional[dict] = None
    games_array: Optional[List[str]] = None
    login_count : Optional[int] = 1

    class Config:
        from_attributes = True

