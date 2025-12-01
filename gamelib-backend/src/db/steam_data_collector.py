"""
Continuously running background worker that collects Steam user data
and populates the database for collaborative filtering.
Uses a BFS (Breadth-First Search) friend-based crawling approach starting from existing users.
"""

import asyncio
import random
import os
from dotenv import load_dotenv
from pathlib import Path
import httpx
from datetime import datetime
from typing import List, Set, Dict
from collections import deque
from src.db.supabase_client import supabase
from src.api.steam_breakdown import fetch_steam_profile, fetch_steam_player_summary

# Import configuration
try:
    from src.db.collector_config import (
        TARGET_USERS, MAX_ATTEMPTS, MIN_GAMES_REQUIRED, MIN_PLAYTIME_REQUIRED,
        DELAY_BETWEEN_USERS, BATCH_SIZE, BATCH_DELAY, STEAM_ID_BASE, 
        STEAM_ID_MAX_OFFSET, MAX_RETRIES, REQUEST_TIMEOUT
    )
except ImportError:
    # Fallback to default values if config not found
    TARGET_USERS = 50
    MAX_ATTEMPTS = 500
    MIN_GAMES_REQUIRED = 5
    MIN_PLAYTIME_REQUIRED = 60
    DELAY_BETWEEN_USERS = 2
    BATCH_SIZE = 10
    BATCH_DELAY = 30
    STEAM_ID_BASE = 76561197960265728
    STEAM_ID_MAX_OFFSET = 300000000
    MAX_RETRIES = 3
    REQUEST_TIMEOUT = 10

# Load environment variables
current_dir = Path(__file__).resolve().parent
env_path = current_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

STEAM_API_KEY = os.getenv("STEAM_API_KEY")


async def get_all_existing_steam_ids() -> List[int]:
    """Get all Steam IDs currently in the database"""
    try:
        response = supabase.table('users').select('steam_id').execute()
        steam_ids = [user['steam_id'] for user in response.data]
        print(f"Found {len(steam_ids)} existing users in database")
        return steam_ids
    except Exception as e:
        print(f"Error fetching existing Steam IDs: {e}")
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
                print(f"Friend list for {steam_id} is private")
                return []
            
            if response.status_code != 200:
                print(f"Failed to fetch friend list for {steam_id}: {response.status_code}")
                return []
            
            data = response.json()
            friends = data.get('friendslist', {}).get('friends', [])
            
            friend_ids = [int(friend['steamid']) for friend in friends]
            print(f"Found {len(friend_ids)} friends for Steam ID {steam_id}")
            
            return friend_ids
            
    except Exception as e:
        print(f"Error fetching friend list for {steam_id}: {e}")
        return []


def generate_random_steam_id() -> int:
    """
    Generate a random Steam ID within the valid range.
    Used as fallback if no seed users exist.
    """
    random_id = STEAM_ID_BASE + random.randint(0, STEAM_ID_MAX_OFFSET)
    return random_id


async def check_if_user_exists(steam_id: int) -> bool:
    """Check if user already exists in database"""
    try:
        response = supabase.table('users').select('steam_id').eq('steam_id', steam_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking user existence: {e}")
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
                print(f"Profile {steam_id} is private or not fully public")
                return False
            
            return True
            
    except Exception as e:
        print(f"Error validating Steam profile {steam_id}: {e}")
        return False


async def fetch_and_store_steam_user(steam_id: int) -> bool:
    """
    Fetch Steam user data and store in database.
    Returns True if successful, False otherwise.
    """
    try:
        print(f"\n{'='*60}")
        print(f"Processing Steam ID: {steam_id}")
        print(f"{'='*60}")
        
        # Check if user already exists
        if await check_if_user_exists(steam_id):
            print(f"✓ User {steam_id} already exists in database, skipping...")
            return False
        
        # Validate profile exists and is public
        print(f"→ Validating profile...")
        if not await validate_steam_profile(steam_id):
            print(f"✗ Profile {steam_id} is invalid or private, skipping...")
            return False
        
        print(f"✓ Profile is valid and public")
        
        # Fetch player summary
        print(f"→ Fetching player summary...")
        player_profile = await fetch_steam_player_summary(steam_id)
        
        if not player_profile:
            print(f"✗ Could not fetch player profile for {steam_id}")
            return False
        
        persona_name = player_profile.get('personaname', 'Unknown')
        print(f"✓ Found user: {persona_name}")
        
        # Fetch games data
        print(f"→ Fetching games library...")
        games_data, games_dict = await fetch_steam_profile(steam_id)
        
        if not games_dict or len(games_dict) < MIN_GAMES_REQUIRED:
            print(f"✗ User {steam_id} has insufficient games ({len(games_dict) if games_dict else 0} games)")
            return False
        
        print(f"✓ Found {len(games_dict)} games")
        
        # Calculate total playtime
        total_playtime = sum(
            game.get('playtime_forever', 0) 
            for game in games_dict.values()
        )
        
        if total_playtime < MIN_PLAYTIME_REQUIRED:
            print(f"✗ User {steam_id} has insufficient playtime ({total_playtime} minutes)")
            return False
        
        print(f"✓ Total playtime: {total_playtime} minutes ({total_playtime/60:.1f} hours)")
        
        # Store in database
        print(f"→ Storing user in database...")
        response = supabase.table("users").insert({
            "steam_id": steam_id,
            "data": player_profile,
            "games": games_dict,
            "login_count": 0  # Set to 0 for auto-collected users
        }).execute()
        
        if not response.data:
            print(f"✗ Failed to store user {steam_id} in database")
            return False
        
        print(f"✓ Successfully added {persona_name} (Steam ID: {steam_id}) to database!")
        print(f"  - Games: {len(games_dict)}")
        print(f"  - Total playtime: {total_playtime/60:.1f} hours")
        
        return True
        
    except Exception as e:
        print(f"✗ Error processing Steam ID {steam_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def scrape_user_and_friends(steam_id: int) -> Dict:
    """
    Scrape a user and all their friends synchronously.
    If user is not found in database, scrape them and their entire friend network.
    
    Returns a dict with:
        - user_added: bool - whether the main user was added
        - friends_added: int - number of friends successfully added
        - friends_found: int - total friends found
        - all_friend_ids: List[int] - all friend IDs discovered
    """
    result = {
        'user_added': False,
        'friends_added': 0,
        'friends_found': 0,
        'all_friend_ids': []
    }
    
    print(f"\n{'='*70}")
    print(f"🔍 SCRAPING USER AND FRIENDS: {steam_id}")
    print(f"{'='*70}")
    
    # Try to add the main user
    user_success = await fetch_and_store_steam_user(steam_id)
    result['user_added'] = user_success
    
    # Get all friends of this user
    print(f"\n→ Fetching complete friend list for {steam_id}...")
    friend_ids = await get_friend_list(steam_id)
    result['friends_found'] = len(friend_ids)
    result['all_friend_ids'] = friend_ids
    
    if not friend_ids:
        print(f"✗ No friends found for {steam_id}")
        return result
    
    print(f"✓ Found {len(friend_ids)} friends, attempting to scrape all...")
    
    # Scrape all friends synchronously
    for idx, friend_id in enumerate(friend_ids, 1):
        print(f"\n[Friend {idx}/{len(friend_ids)}]")
        
        # Check if friend already exists
        if await check_if_user_exists(friend_id):
            print(f"  ✓ Friend {friend_id} already in database, skipping")
            continue
        
        # Try to add friend
        friend_success = await fetch_and_store_steam_user(friend_id)
        if friend_success:
            result['friends_added'] += 1
        
        # Rate limiting
        await asyncio.sleep(DELAY_BETWEEN_USERS)
    
    print(f"\n{'='*70}")
    print(f"✓ SCRAPING COMPLETE FOR {steam_id}")
    print(f"  - Main user added: {'Yes' if result['user_added'] else 'No'}")
    print(f"  - Friends found: {result['friends_found']}")
    print(f"  - Friends added: {result['friends_added']}")
    print(f"{'='*70}\n")
    
    return result


async def get_or_scrape_user(steam_id: int) -> bool:
    """
    Check if user exists in database. If not, scrape them and all their friends.
    Returns True if user now exists in database (either already existed or was just added).
    """
    # Check if user already exists
    if await check_if_user_exists(steam_id):
        print(f"✓ User {steam_id} found in database")
        return True
    
    print(f"⚠️  User {steam_id} not found in database - initiating full scrape...")
    
    # Scrape user and all friends
    result = await scrape_user_and_friends(steam_id)
    
    return result['user_added']


async def run_continuous_collector(
    target_users: int = 100,
    max_attempts: int = 1000
):
    """
    Continuously collect Steam user data using BFS (Breadth-First Search) friend-based crawling.
    Starts from existing users in the database and crawls their friends level by level.
    If a user is not found, will scrape them and all their friends synchronously.
    
    Args:
        target_users: Number of users to collect
        max_attempts: Maximum attempts before stopping
    """
    print("\n" + "="*70)
    print("STEAM DATA COLLECTOR - BFS FRIEND-BASED CRAWLING")
    print("="*70)
    print(f"Target users: {target_users}")
    print(f"Max attempts: {max_attempts}")
    print(f"Min games required: {MIN_GAMES_REQUIRED}")
    print(f"Min playtime required: {MIN_PLAYTIME_REQUIRED} minutes")
    print("="*70 + "\n")
    
    users_added = 0
    attempts = 0
    batch_count = 0
    
    start_time = datetime.now()
    
    # Get existing users from database to use as seeds
    print("→ Fetching existing users from database as seed users...")
    existing_steam_ids = await get_all_existing_steam_ids()
    
    # BFS data structures
    visited: Set[int] = set(existing_steam_ids)  # All IDs we've seen
    bfs_queue: deque = deque()  # Queue for BFS (FIFO)
    current_level = 0
    
    # If we have existing users, add SOME of their friends to BFS queue (not all)
    if existing_steam_ids:
        # Only use first 3-5 users as seeds to get the ball rolling
        seed_count = min(5, len(existing_steam_ids))
        seed_users = existing_steam_ids[:seed_count]
        
        print(f"→ Initializing BFS with {seed_count} seed users (out of {len(existing_steam_ids)} total)...")
        print(f"→ Fetching friends (Level 1) from seeds only...")
        
        # Get friends from ONLY the seed users (not all existing users)
        for seed_id in seed_users:
            friends = await get_friend_list(seed_id)
            for friend_id in friends:
                if friend_id not in visited:
                    bfs_queue.append(friend_id)
                    visited.add(friend_id)
            await asyncio.sleep(0.5)  # Rate limit
        
        print(f"✓ BFS initialized with {len(bfs_queue)} Level 1 friends from {seed_count} seeds")
        print(f"  (Skipped {len(existing_steam_ids) - seed_count} existing users to speed up initialization)\n")
    else:
        print("⚠️  No existing users in database. Starting with random Steam IDs.\n")
        # Add some random Steam IDs to start
        for _ in range(5):
            random_id = generate_random_steam_id()
            if random_id not in visited:
                bfs_queue.append(random_id)
                visited.add(random_id)
    
    try:
        while users_added < target_users and attempts < max_attempts:
            attempts += 1
            
            # Check if queue is empty
            if not bfs_queue:
                print("⚠️  BFS queue empty, generating random Steam IDs...")
                for _ in range(5):
                    random_id = generate_random_steam_id()
                    if random_id not in visited:
                        bfs_queue.append(random_id)
                        visited.add(random_id)
            
            # BFS: Process next user in queue (FIFO)
            steam_id = bfs_queue.popleft()
            
            print(f"\n[BFS] Processing from queue (Queue size: {len(bfs_queue)}, Visited: {len(visited)})")
            
            # Try to fetch and store (or scrape if not found)
            success = await fetch_and_store_steam_user(steam_id)
            
            if success:
                users_added += 1
                batch_count += 1
                
                # BFS: Add this user's friends to the END of the queue (breadth-first)
                print(f"→ [BFS] Adding friends to queue...")
                friends = await get_friend_list(steam_id)
                new_friends = 0
                for friend_id in friends:
                    if friend_id not in visited:
                        bfs_queue.append(friend_id)  # Add to END for BFS
                        visited.add(friend_id)
                        new_friends += 1
                
                print(f"✓ [BFS] Added {new_friends} new friends to queue (total queue: {len(bfs_queue)})")
                
                print(f"\n{'*'*60}")
                print(f"PROGRESS: {users_added}/{target_users} users added ({attempts} attempts)")
                print(f"Success rate: {(users_added/attempts)*100:.1f}%")
                print(f"BFS Queue size: {len(bfs_queue)}")
                print(f"Total visited: {len(visited)}")
                print(f"{'*'*60}\n")
            
            # Delay between users
            await asyncio.sleep(DELAY_BETWEEN_USERS)
            
            # Longer delay after batch
            if batch_count >= BATCH_SIZE:
                print(f"\n--- Batch complete ({BATCH_SIZE} users), pausing for {BATCH_DELAY} seconds ---\n")
                await asyncio.sleep(BATCH_DELAY)
                batch_count = 0
        
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
        print(f"Remaining in queue: {len(bfs_queue)}")
        print(f"Total users visited: {len(visited)}")
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("STEAM DATA COLLECTOR - STOPPED BY USER")
        print("="*70)
        print(f"Users added: {users_added}")
        print(f"Total attempts: {attempts}")
        print(f"Remaining in queue: {len(bfs_queue)}")
        print(f"Total users visited: {len(visited)}")
        print("="*70 + "\n")
    
    except Exception as e:
        print(f"\n\nFATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point for the collector"""
    await run_continuous_collector(
        target_users=TARGET_USERS,
        max_attempts=MAX_ATTEMPTS
    )


if __name__ == "__main__":
    # Run the collector
    asyncio.run(main())
