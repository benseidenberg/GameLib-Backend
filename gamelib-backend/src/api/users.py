
from fastapi import APIRouter, HTTPException
from src.db.supabase_client import supabase
from src.schemas.user_schema import UserCreate, UserResponse
from postgrest.exceptions import APIError

router = APIRouter()



@router.post("/users/", response_model=UserResponse)
async def create_user(user: UserCreate):
    try:
        response = supabase.table("users").insert({"email": user.email, "password": user.password}).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create user")
        return UserResponse(**response.data[0])
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    try:
        response = supabase.table("users").select("*").eq("id", user_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(**response.data[0])
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserCreate):
    try:
        response = supabase.table("users").update({"email": user.email, "password": user.password}).eq("id", user_id).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to update user")
        return UserResponse(**response.data[0])
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    try:
        response = supabase.table("users").delete().eq("id", user_id).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to delete user")
        return {"detail": "User deleted successfully"}
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))