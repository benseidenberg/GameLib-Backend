from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from src.db.repositories.users_db import UsersRepository
from src.schemas.user_schema import User, fetch_steam_profile
from postgrest.exceptions import APIError

router = APIRouter()


@router.post("/users/", response_model=User)
async def create_user(user: User):
    """Create a new user"""
    try:
        # Validate steam_id
        if user.steam_id <= 0 or user.steam_id > 999999999999999999:
            raise HTTPException(status_code=400, detail="Invalid Steam ID")
        
        # Use repository method with automatic games_array generation
        created_user = UsersRepository.create_with_games(
            steam_id=user.steam_id,
            data=user.data or {},
            games=user.games or {},
            login_count=user.login_count
        )
        
        if not created_user:
            raise HTTPException(status_code=400, detail="Failed to create user")
        
        return created_user
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{steam_id}", response_model=User)
async def get_user(steam_id: int, refresh: bool = False):
    """
    Get user data by steam_id.
    If refresh=True, fetches fresh data from Steam API and updates database.
    If refresh=False (default), returns existing data from database.
    """
    try:
        # Validate steam_id
        if steam_id <= 0 or steam_id > 999999999999999999:
            raise HTTPException(status_code=400, detail="Invalid Steam ID")
        
        if refresh:
            # Fetch fresh Steam data
            profile_data = await fetch_steam_profile(steam_id)
            if not profile_data or 'profile' not in profile_data:
                raise HTTPException(status_code=400, detail="Could not fetch Steam profile")
            
            user_data = await UsersRepository.refresh_user_steam_data(steam_id, profile_data)
        else:
            # Get existing data from database
            user_data = UsersRepository.find_by_steam_id(steam_id)
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user_data
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{steam_id}", response_model=User)
async def update_user(steam_id: int, user: Optional[User] = None, refresh_steam: bool = False):
    """
    Update user data by steam_id.
    If user data is provided, updates with that data (including login_count if provided).
    If refresh_steam=True, fetches fresh data from Steam API and increments login_count.
    If both are provided, user data takes precedence.
    """
    try:
        if user and user.data:
            # Update with provided user data
            if user.games:
                # Use repository method with automatic games_array generation
                updated_user = UsersRepository.update_with_games(
                    steam_id=steam_id,
                    data=user.data,
                    games=user.games,
                    increment_login=False
                )
            else:
                # Simple update without games
                update_data: Dict[str, Any] = {"data": user.data}
                if user.login_count is not None:
                    update_data["login_count"] = user.login_count
                updated_user = UsersRepository.update(steam_id, update_data)
            
            if not updated_user:
                raise HTTPException(status_code=400, detail="Failed to update user")
            return updated_user
            
        elif refresh_steam:
            # Fetch fresh Steam data
            profile_data = await fetch_steam_profile(steam_id)
            if not profile_data or 'profile' not in profile_data:
                raise HTTPException(status_code=400, detail="Could not fetch Steam profile")
            
            user_data = await UsersRepository.refresh_user_steam_data(steam_id, profile_data)
            if not user_data:
                raise HTTPException(status_code=400, detail="Failed to update user with Steam data")
            return user_data
        else:
            raise HTTPException(status_code=400, detail="Either provide user data or set refresh_steam=True")
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{steam_id}/refresh", response_model=User)
async def refresh_user_steam_data(steam_id: int):
    """
    Refresh user data by fetching fresh data from Steam API and updating database.
    """
    try:
        profile_data = await fetch_steam_profile(steam_id)
        if not profile_data or 'profile' not in profile_data:
            raise HTTPException(status_code=400, detail="Could not fetch Steam profile")
        
        user_data = await UsersRepository.refresh_user_steam_data(steam_id, profile_data)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found or failed to refresh Steam data")
        return user_data
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{steam_id}")
async def delete_user(steam_id: int):
    """Delete a user by steam_id"""
    try:
        success = UsersRepository.delete(steam_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete user")
        return {"detail": "User deleted successfully"}
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{steam_id}/name")
async def get_user_name(steam_id: int):
    """
    Get just the user's Steam name and avatar - simplified endpoint for frontend
    If user doesn't exist in database, triggers login process to create them
    """
    try:
        # First try to get from database using find_by_steam_id
        user_data = UsersRepository.find_by_steam_id(steam_id)
        
        if user_data:
            # User exists in database, get name and avatar from stored data
            player_name = user_data.persona_name
            player_avatar = user_data.avatar
            print(f"Found user in database, player_name: {player_name}, avatar: {player_avatar}")
            return {"name": player_name, "avatar": player_avatar}
        else:
            # User doesn't exist, fetch from Steam and create
            print(f"User {steam_id} not found, creating...")
            profile_data = await fetch_steam_profile(steam_id)
            
            if not profile_data or 'profile' not in profile_data:
                raise HTTPException(status_code=400, detail="Could not fetch Steam profile")
            
            # Create user via login
            login_result = await UsersRepository.user_login(steam_id, profile_data)
            
            if login_result:
                player_name = login_result.get('data', {}).get('personaname', 'Unknown Player')
                player_avatar = login_result.get('data', {}).get('avatarfull') or login_result.get('data', {}).get('avatar', '')
                print(f"Created user successfully, player_name: {player_name}, avatar: {player_avatar}")
                return {"name": player_name, "avatar": player_avatar}
            else:
                raise HTTPException(status_code=500, detail="Failed to create user")
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_user_name: {e}")
        raise HTTPException(status_code=500, detail=str(e))