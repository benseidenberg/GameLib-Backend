"""
Continuously running background worker that collects Steam user data
and populates the database for collaborative filtering.
Simplified approach: randomly select existing users → fetch their friends → add friends to database.
"""

import sys
from pathlib import Path

# Add project root to Python path for proper imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import random
import os
from dotenv import load_dotenv
import httpx
from datetime import datetime
from typing import List, Dict, Optional
from src.db.supabase_client import supabase
from src.schemas.user_schema import User


# Configuration
MIN_GAMES_REQUIRED = 5
MIN_PLAYTIME_REQUIRED = 1200  # minutes
DELAY_BETWEEN_USERS = 0.5  # seconds
BATCH_SIZE = 100  # Process this many users before longer delay
BATCH_DELAY = 30  # seconds between batches
REQUEST_TIMEOUT = 10  # seconds
FRIENDS_PER_USER = 50  # How many friends to fetch per user

# Load environment variables
current_dir = Path(__file__).resolve().parent
env_path = current_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

STEAM_API_KEY = os.getenv("STEAM_API_KEY")


async def get_random_users_from_db(count: int = 5) -> List[int]:
    """Get random users from the database to fetch their friends"""
    try:
        response = supabase.table('users').select('steam_id').execute()
        
        if not response.data:
            print("⚠️  No users found in database")
            return []
        
        steam_ids = [user['steam_id'] for user in response.data]
        
        # Return random sample
        sample_size = min(count, len(steam_ids))
        random_users = random.sample(steam_ids, sample_size)
        
        print(f"✓ Selected {len(random_users)} random users from database ({len(steam_ids)} total)")
        return random_users
        
    except Exception as e:
        print(f"✗ Error fetching random users: {e}")
        return []


async def get_friend_list(steam_id: int) -> List[int]:
    """
    Fetch the friend list for a given Steam ID.
    Returns a list of Steam IDs of the user's friends.
    """
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
            params = {
                'key': STEAM_API_KEY,
                'steamid': str(steam_id),
                'relationship': 'friend'
            }
            
            response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 401:
                print(f"  ⚠️  Friend list for {steam_id} is private")
                return []
            
            if response.status_code != 200:
                print(f"  ✗ Failed to fetch friend list: {response.status_code}")
                return []
            
            data = response.json()
            friends = data.get('friendslist', {}).get('friends', [])
            
            friend_ids = [int(friend['steamid']) for friend in friends]
            print(f"  ✓ Found {len(friend_ids)} friends")
            
            return friend_ids
            
    except Exception as e:
        print(f"  ✗ Error fetching friend list: {e}")
        return []


async def check_if_user_exists(steam_id: int) -> bool:
    """Check if user already exists in database"""
    try:
        response = supabase.table('users').select('steam_id').eq('steam_id', steam_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"  ✗ Error checking user existence: {e}")
        return False


async def validate_steam_profile(steam_id: int) -> bool:
    """
    Validate that a Steam profile exists and is public.
    Returns True if profile is valid and accessible.
    """
    try:
        async with httpx.AsyncClient() as client:
            url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
            params = {
                'key': STEAM_API_KEY,
                'steamids': str(steam_id)
            }
            
            response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            players = data.get('response', {}).get('players', [])
            
            if not players:
                return False
            
            player = players[0]
            
            # Check if profile is public (communityvisibilitystate == 3)
            visibility = player.get('communityvisibilitystate', 0)
            if visibility != 3:
                print(f"  ⚠️  Profile is private or not fully public")
                return False
            
            return True
            
    except Exception as e:
        print(f"  ✗ Error validating Steam profile: {e}")
        return False


async def fetch_and_store_steam_user(steam_id: int) -> bool:
    """
    Fetch Steam user data and store in database.
    Returns True if successful, False otherwise.
    """
    try:
        print(f"\n  → Processing Steam ID: {steam_id}")
        
        # Check if user already exists
        if await check_if_user_exists(steam_id):
            print(f"    ✓ Already exists, skipping...")
            return False
        
        # Validate profile exists and is public
        if not await validate_steam_profile(steam_id):
            print(f"    ✗ Invalid or private profile, skipping...")
            return False
        
        # Fetch player summary
        player_profile = await User.fetch_player_summary(steam_id)
        
        if not player_profile:
            print(f"    ✗ Could not fetch player profile")
            return False
        
        persona_name = player_profile.get('personaname', 'Unknown')
        
        # Fetch games data using the User method
        profile_data = await User.fetch_profile_data(steam_id)
        
        if not profile_data or not profile_data.get('games'):
            print(f"    ✗ Could not fetch games data")
            return False
        
        # Convert games list to dict format
        games_dict = {}
        for game in profile_data['games']:
            game_id = str(game.get('appid'))
            games_dict[game_id] = {
                'name': game.get('name', 'Unknown Game'),
                'playtime_forever': game.get('playtime_forever', 0),
                'playtime_2weeks': game.get('playtime_2weeks', 0),
                'img_icon_url': game.get('img_icon_url', ''),
                'rtime_last_played': game.get('rtime_last_played', 0)
            }
        
        if not games_dict or len(games_dict) < MIN_GAMES_REQUIRED:
            print(f"    ✗ Insufficient games ({len(games_dict) if games_dict else 0})")
            return False
        
        # Calculate total playtime
        total_playtime = sum(
            game.get('playtime_forever', 0) 
            for game in games_dict.values()
        )
        
        if total_playtime < MIN_PLAYTIME_REQUIRED:
            print(f"    ✗ Insufficient playtime ({total_playtime} minutes)")
            return False
        
        # Create games_array: sorted list of game IDs by playtime_forever
        games_array = sorted(
            games_dict.keys(),
            key=lambda game_id: games_dict[game_id].get('playtime_forever', 0),
            reverse=True
        )
        
        # Store in database
        response = supabase.table("users").insert({
            "steam_id": steam_id,
            "data": player_profile,
            "games": games_dict,
            "games_array": games_array,
            "login_count": 0  # Set to 0 for auto-collected users
        }).execute()
        
        if not response.data:
            print(f"    ✗ Failed to store in database")
            return False
        
        print(f"    ✓ Successfully added {persona_name} ({len(games_dict)} games, {total_playtime/60:.1f}h)")
        
        return True
        
    except Exception as e:
        print(f"    ✗ Error: {str(e)}")
        return False


async def run_continuous_collector(
    target_users: int = 100,
    max_attempts: int = 1000
):
    """
    Continuously collect Steam user data by randomly selecting existing users
    and scraping their friends.
    
    Simple approach:
    1. Get random users from database
    2. Fetch their friend lists
    3. Try to add those friends to database
    4. Repeat
    
    Args:
        target_users: Number of users to collect
        max_attempts: Maximum attempts before stopping
    """
    print("\n" + "="*70)
    print("STEAM DATA COLLECTOR - FRIEND SCRAPING")
    print("="*70)
    print(f"Target users: {target_users}")
    print(f"Max attempts: {max_attempts}")
    print(f"Min games required: {MIN_GAMES_REQUIRED}")
    print(f"Min playtime required: {MIN_PLAYTIME_REQUIRED} minutes")
    print(f"Friends per user: {FRIENDS_PER_USER}")
    print("="*70 + "\n")
    
    users_added = 0
    attempts = 0
    batch_count = 0
    
    start_time = datetime.now()
    
    try:
        while users_added < target_users and attempts < max_attempts:
            # Get random users from database
            random_users = await get_random_users_from_db(count=BATCH_SIZE)
            
            if not random_users:
                print("⚠️  No users in database to fetch friends from. Please add seed users first.")
                break
            
            print(f"\n{'='*70}")
            print(f"BATCH {batch_count + 1}: Processing {len(random_users)} random users")
            print(f"{'='*70}")
            
            # For each random user, get their friends
            for user_idx, steam_id in enumerate(random_users, 1):
                print(f"\n[{user_idx}/{len(random_users)}] Fetching friends for Steam ID: {steam_id}")
                
                # Get friend list
                friend_ids = await get_friend_list(steam_id)
                
                if not friend_ids:
                    print(f"  ⚠️  No friends found or friend list is private")
                    continue
                
                # Limit number of friends to process
                friends_to_process = friend_ids[:FRIENDS_PER_USER]
                print(f"  → Processing {len(friends_to_process)} friends (out of {len(friend_ids)} total)...")
                
                # Try to add each friend
                for friend_id in friends_to_process:
                    attempts += 1
                    
                    success = await fetch_and_store_steam_user(friend_id)
                    
                    if success:
                        users_added += 1
                        
                        print(f"\n{'*'*60}")
                        print(f"PROGRESS: {users_added}/{target_users} users added ({attempts} attempts)")
                        print(f"Success rate: {(users_added/attempts)*100:.1f}%")
                        print(f"{'*'*60}\n")
                        
                        # Check if we hit target
                        if users_added >= target_users:
                            break
                    
                    # Delay between users
                    await asyncio.sleep(DELAY_BETWEEN_USERS)
                
                # Check if we hit target
                if users_added >= target_users:
                    break
            
            batch_count += 1
            
            # Check if we hit target or max attempts
            if users_added >= target_users or attempts >= max_attempts:
                break
            
            # Longer delay between batches
            print(f"\n--- Batch complete, pausing for {BATCH_DELAY} seconds ---\n")
            await asyncio.sleep(BATCH_DELAY)
        
        # Final summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "="*70)
        print("STEAM DATA COLLECTOR - COMPLETED")
        print("="*70)
        print(f"Users added: {users_added}/{target_users}")
        print(f"Total attempts: {attempts}")
        print(f"Success rate: {(users_added/attempts)*100:.1f}%")
        print(f"Duration: {duration/60:.1f} minutes")
        print(f"Average time per user: {duration/users_added:.1f} seconds" if users_added > 0 else "N/A")
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("STEAM DATA COLLECTOR - STOPPED BY USER")
        print("="*70)
        print(f"Users added: {users_added}")
        print(f"Total attempts: {attempts}")
        print("="*70 + "\n")
    
    except Exception as e:
        print(f"\n\nFATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point for the collector"""
    await run_continuous_collector(
        target_users=10000,
        max_attempts=5000
    )


if __name__ == "__main__":
    # Run the collector
    asyncio.run(main())

