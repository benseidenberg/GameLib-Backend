from typing import Optional
from fastapi import APIRouter, HTTPException
from src.db.supabase_client import supabase
from src.schemas.user_schema import UserCreate, UserResponse
from postgrest.exceptions import APIError
from src.api.steam_breakdown import fetch_steam_profile, fetch_steam_player_summary
import asyncio

router = APIRouter()



@router.post("/users/", response_model=UserResponse)
async def create_user(user: UserCreate):
    try:
        response = supabase.table("users").insert({
            "steam_id": user.steam_id, 
            "data": user.data, 
            "login_count": user.login_count
        }).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create user")
        return UserResponse(**response.data[0])
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def user_login(steam_id: int):
    print(f"User login attempt for steam_id: {steam_id}")
    # Check if user already exists
    response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
    
    if response.data:
        # User already exists, update Steam data and increment login_count
        return await update_user_data(steam_id)
    else:
        print("Creating new user")
        
        # Fetch both games data and player profile
        games_data, df = await fetch_steam_profile(steam_id)
        player_profile = await fetch_steam_player_summary(steam_id)
        
        if not player_profile:
            raise Exception("Could not fetch Steam player profile")
        
        # Store the player profile data (which includes personaname)
        user_create = UserCreate(steam_id=steam_id, data=player_profile, login_count=1)
        print(f"Creating user with data: {user_create}")
        created = await create_user(user_create)
        
        # Fetch and return the created user
        response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
        if response.data:
            print(f"Created user: {response.data[0]}")
            return response.data[0]
        return None

async def get_user_data(steam_id: int):
    """Retrieve existing user data from database without updating"""
    try:
        response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error in get_user_data: {str(e)}")
        return None

async def update_user_data(steam_id: int):
    try:
        # Fetch fresh Steam player profile data
        print(f"Fetching Steam player profile for steam_id: {steam_id}")
        player_profile = await fetch_steam_player_summary(steam_id)
        
        if not player_profile:
            raise Exception("Could not fetch Steam player profile")
        
        print(f"Fetched Steam player profile: {player_profile}")
        
        # Get current user to increment login_count
        current_user_response = supabase.table('users').select('login_count').eq('steam_id', steam_id).execute()
        
        current_login_count = 1  # Default for new users
        if current_user_response.data and len(current_user_response.data) > 0:
            existing_count = current_user_response.data[0].get('login_count', 0)
            current_login_count = existing_count + 1
            print(f"Found existing login_count: {existing_count}, incrementing to: {current_login_count}")
        else:
            print(f"No existing user found, using default login_count: {current_login_count}")
        
        # Update database with fresh player profile data and incremented login_count
        update_payload = {
            'data': player_profile,
            'login_count': current_login_count
        }
        print(f"Update payload: {update_payload}")
        
        response = supabase.table('users').update(update_payload).eq('steam_id', steam_id).execute()
        #print(f"Database update response: {response}")
        print(f"Updated login_count to: {current_login_count}")
        
        if response.data and len(response.data) > 0:
            print(f"Returning updated user: {response.data[0]}")
            return response.data[0]
        else:
            print("No data returned from database update")
            # If update didn't return data, fetch the user record
            get_response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
            if get_response.data and len(get_response.data) > 0:
                print(f"Fetched user after update: {get_response.data[0]}")
                return get_response.data[0]
            return None
    except Exception as e:
        print(f"Error in update_user_data: {str(e)}")
        return None

@router.get("/users/{steam_id}", response_model=UserResponse)
async def get_user(steam_id: int, refresh: bool = False):
    """
    Get user data by steam_id.
    If refresh=True, fetches fresh data from Steam API and updates database.
    If refresh=False (default), returns existing data from database.
    """
    try:
        if refresh:
            # Fetch fresh Steam data and update database
            user_data = await update_user_data(steam_id)
        else:
            # Just get existing data from database
            user_data = await get_user_data(steam_id)
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserResponse(**user_data)
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.put("/users/{steam_id}", response_model=UserResponse)
async def update_user(steam_id: int, user: Optional[UserCreate] = None, refresh_steam: bool = False):
    """
    Update user data by steam_id.
    If user data is provided, updates with that data (including login_count if provided).
    If refresh_steam=True, fetches fresh data from Steam API and increments login_count.
    If both are provided, user data takes precedence.
    """
    try:
        if user and user.data:
            # Update with provided user data
            update_data: dict = {"data": user.data}
            if user.login_count is not None:
                update_data["login_count"] = user.login_count
            
            response = supabase.table("users").update(update_data).eq("steam_id", steam_id).execute()
            if not response.data:
                raise HTTPException(status_code=400, detail="Failed to update user")
            return UserResponse(**response.data[0])
        elif refresh_steam:
            # Fetch fresh Steam data and update (this will increment login_count)
            user_data = await update_user_data(steam_id)
            if not user_data:
                raise HTTPException(status_code=400, detail="Failed to update user with Steam data")
            return UserResponse(**user_data)
        else:
            raise HTTPException(status_code=400, detail="Either provide user data or set refresh_steam=True")
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/users/{steam_id}/refresh", response_model=UserResponse)
async def refresh_user_steam_data(steam_id: int):
    """
    Refresh user data by fetching fresh data from Steam API and updating database.
    """
    try:
        user_data = await update_user_data(steam_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found or failed to refresh Steam data")
        return UserResponse(**user_data)
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

@router.get("/users/{steam_id}/name")
async def get_user_name(steam_id: int):
    """
    Get just the user's Steam name - simplified endpoint for frontend
    If user doesn't exist in database, triggers login process to create them
    """
    try:
        print(f"get_user_name called for steam_id: {steam_id}")
        
        # First try to get from database
        user_data = await get_user_data(steam_id)
        print(f"User data from database: {user_data}")
        
        if user_data:
            # User exists in database, get name from stored data
            steam_data = user_data.get('data', {})
            player_name = steam_data.get('personaname', 'Unknown Player')
            print(f"Found user in database, player_name: {player_name}")
            return {"name": player_name}
        else:
            # User doesn't exist in database, trigger login process to create them
            print(f"User {steam_id} not found in database, creating user via login process")
            
            try:
                login_result = await user_login(steam_id)
                print(f"Login result: {login_result}")
                
                if login_result:
                    # User was successfully created/updated, get name from database result
                    steam_data = login_result.get('data', {})
                    player_name = steam_data.get('personaname', 'Unknown Player')
                    print(f"Created user successfully, player_name: {player_name}")
                    return {"name": player_name}
                else:
                    print("Login result was None")
                    raise HTTPException(status_code=500, detail="Failed to create user - login returned None")
                    
            except Exception as login_error:
                print(f"Error during user_login: {login_error}")
                raise HTTPException(status_code=500, detail=f"Failed to create user: {str(login_error)}")
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_user_name: {e}")
        raise HTTPException(status_code=500, detail=str(e))