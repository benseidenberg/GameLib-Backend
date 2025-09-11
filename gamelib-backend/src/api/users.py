from fastapi import APIRouter, HTTPException
from src.db.supabase_client import supabase
from src.schemas.user_schema import UserCreate, UserResponse
from postgrest.exceptions import APIError
from src.schemas.user_schema import UserCreate
from src.api.steam_breakdown import fetch_steam_profile
import asyncio

STEAM_API_KEY="968317D323A2D4C8ED61E3D9F5E2FAB1"
router = APIRouter()



@router.post("/users/", response_model=UserResponse)
async def create_user(user: UserCreate):
    try:
        response = supabase.table("users").insert({"steam_id": user.steam_id, "data": user.data}).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create user")
        return UserResponse(**response.data[0])
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def create_user_with_steam_id(steam_id: int):
    # Check if user already exists
    response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
    if response.data:
        # User already exists, return existing user
        return response.data[0]
    # Create new user with steam_id and optional data
    data = await fetch_steam_profile(steam_id)
    user_create = UserCreate(steam_id=steam_id, data=data)
    created = await create_user(user_create)
    # Fetch and return the created user
    response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
    if response.data:
        return response.data[0]
    return None


@router.get("/users/{steam_id}", response_model=UserResponse)
async def get_user(steam_id: int):
    try:
        response = supabase.table("users").select("*").eq("steam_id", steam_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(**response.data[0])
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.put("/users/{steam_id}", response_model=UserResponse)
async def update_user(steam_id: int, user: UserCreate):
    try:
        response = supabase.table("users").update({"data": user.data}).eq("steam_id", steam_id).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to update user")
        return UserResponse(**response.data[0])
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.delete("/users/{steam_id}")
async def delete_user(steam_id: int):
    try:
        response = supabase.table("users").delete().eq("steam_id", steam_id).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to delete user")
        return {"detail": "User deleted successfully"}
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))