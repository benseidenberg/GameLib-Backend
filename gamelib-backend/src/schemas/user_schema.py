from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str

    class Config:
        orm_mode = True