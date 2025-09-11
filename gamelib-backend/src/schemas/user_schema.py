from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    steam_id: int
    data: Optional[dict] = None

class UserResponse(BaseModel):
    steam_id : int
    data: Optional[dict] = None

    class Config:
        from_attributes = True

