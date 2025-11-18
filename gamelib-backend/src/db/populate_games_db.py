"""
Steam Games Database Populator

This script populates the games_db table with comprehensive game information from Steam.
It fetches games in batches of 100 and enriches each with detailed metadata.

Usage:
    python populate_games_db.py

The script will prompt for your Steam Web API access token.
"""

import asyncio
import httpx
import json
import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# Add src directory to path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
sys.path.insert(0, str(src_dir))

from db.supabase_client import supabase
import time


# Define a standalone version of get_steam_app_details to avoid import issues
async def get_steam_app_details(app_id: int, skip_content_filter: bool = True) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed game information from Steam API
    """
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&format=json"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            # Check for rate limiting
            if response.status_code == 429:
                raise Exception("Rate limited (HTTP 429)")
            
            if response.status_code == 200:
                data = response.json()
                
                app_data = data.get(str(app_id))
                if app_data and app_data.get('success') and 'data' in app_data:
                    game_data = app_data['data']
                    
                    # Extract price information
                    is_free = game_data.get('is_free', False)
                    price_usd = None
                    price_formatted = 'Free'
                    
                    if not is_free and 'price_overview' in game_data:
                        price_info = game_data['price_overview']
                        price_usd = price_info.get('final', 0) / 100.0
                        price_formatted = price_info.get('final_formatted', 'N/A')
                    
                    game_info = {
                        "app_id": app_id,
                        "title": game_data.get('name', 'Unknown Game'),
                        "description": game_data.get('short_description', ''),
                        "detailed_description": game_data.get('detailed_description', ''),
                        "image": game_data.get('header_image', ''),
                        "price": price_formatted,
                        "price_usd": price_usd,
                        "is_free": is_free,
                        "genres": [genre.get('description', '') for genre in game_data.get('genres', [])],
                        "categories": [cat.get('description', '') for cat in game_data.get('categories', [])],
                        "platforms": game_data.get('platforms', {}),
                        "metacritic": game_data.get('metacritic', {}),
                        "content_descriptors": game_data.get('content_descriptors', {}),
                        "developers": game_data.get('developers', []),
                        "publishers": game_data.get('publishers', []),
                        "release_date": game_data.get('release_date', {}).get('date', ''),
                        "steam_url": f"https://store.steampowered.com/app/{app_id}/"
                    }
                    
                    return game_info
                else:
                    return None
            else:
                print(f"  HTTP {response.status_code} for app {app_id}")
                return None
                
    except Exception as e:
        # Re-raise rate limit exceptions so they can be handled by retry logic
        if "429" in str(e) or "rate limit" in str(e).lower():
            raise
        print(f"  Error fetching Steam app details for {app_id}: {str(e)}")
        return None


async def get_steam_app_list(access_token: str, last_appid: int = 0, max_results: int = 100) -> Dict[str, Any]:
    """
    Fetch a list of Steam games from the Steam API
    
    Args:
        access_token: Steam Web API access token
        last_appid: The last app ID fetched (for pagination)
        max_results: Number of results to fetch (default 100)
    
    Returns:
        Dictionary containing the API response with game list
    """
    url = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
    params = {
        "access_token": access_token,
        "have_description_language": "english",
        "last_appid": last_appid,
        "max_results": max_results
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"Error fetching app list: {e}")
        raise


async def get_game_details_with_retry(app_id: int, max_retries: int = 10) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed game information with retry logic and rate limit handling
    
    Args:
        app_id: Steam app ID
        max_retries: Maximum retry attempts for non-rate-limit errors
    
    Returns:
        Dictionary containing detailed game information or None if not found
    """
    import random
    
    attempt = 0
    rate_limit_retries = 0
    
    while attempt < max_retries:
        try:
            game_details = await get_steam_app_details(app_id, skip_content_filter=True)
            
            if game_details:
                return game_details
            else:
                # Game not found or no data (not an error, just doesn't exist)
                print(f"  Game {app_id} not found or no data available")
                return None
                
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                # Rate limited - wait 30-60 seconds and retry indefinitely
                rate_limit_retries += 1
                wait_time = random.randint(30, 60)
                print(f"  ⚠️  Rate limited! Waiting {wait_time} seconds before retry #{rate_limit_retries}...")
                await asyncio.sleep(wait_time)
                # Don't increment attempt counter for rate limits - keep trying
                continue
            else:
                # Other error - use normal retry logic
                attempt += 1
                print(f"  Error fetching details for {app_id} (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2)
                else:
                    print(f"  ✗ Failed after {max_retries} attempts")
                    return None
    
    return None


def parse_release_date(date_string: str) -> Optional[str]:
    """
    Parse Steam's release date format to ISO date format (YYYY-MM-DD)
    
    Args:
        date_string: Date string from Steam (e.g., "Oct 23, 2013" or "Coming soon")
    
    Returns:
        ISO formatted date string or None if cannot be parsed
    """
    if not date_string or date_string.lower() in ['coming soon', 'to be announced', 'tba']:
        return None
    
    try:
        # Try common Steam date formats
        formats = [
            "%b %d, %Y",      # Oct 23, 2013
            "%B %d, %Y",      # October 23, 2013
            "%d %b, %Y",      # 23 Oct, 2013
            "%d %B, %Y",      # 23 October, 2013
            "%Y-%m-%d",       # 2013-10-23 (already ISO)
            "%m/%d/%Y",       # 10/23/2013
        ]
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_string.strip(), fmt)
                return parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # If no format matches, try to extract just the year
        if len(date_string) == 4 and date_string.isdigit():
            return f"{date_string}-01-01"
        
        print(f"  Could not parse date: {date_string}")
        return None
        
    except Exception as e:
        print(f"  Error parsing date '{date_string}': {e}")
        return None


def format_game_data(app_id: int, name: str, game_details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Format game data for database insertion
    
    Args:
        app_id: Steam app ID
        name: Game name
        game_details: Detailed game information from get_steam_app_details
    
    Returns:
        Formatted dictionary ready for database insertion or None if essential data is missing
    """
    if not game_details:
        # Minimal record with just ID and name
        return {
            "game_id": app_id,
            "name": name,
            "detailed_desc": None,
            "short_desc": None,
            "image": None,
            "platforms": {},  # Store as dict, not JSON string
            "categories": [],  # Store as list, not JSON string
            "genres": [],  # Store as list, not JSON string
            "release_date": None,
            "metacritic": {},  # Store as dict, not JSON string
            "content": {},  # Store as dict, not JSON string
            "is_free": False,
            "price": None,
            "price_usd": None,
            "developers": [],  # Store as list, not JSON string
            "publishers": [],  # Store as list, not JSON string
            "steam_url": None
        }
    
    # Data already extracted by get_steam_app_details
    is_free = game_details.get('is_free', False)
    price = game_details.get('price')
    price_usd = game_details.get('price_usd')
    platforms = game_details.get('platforms', {})
    metacritic = game_details.get('metacritic', {})
    content_descriptors = game_details.get('content_descriptors', {})
    developers = game_details.get('developers', [])
    publishers = game_details.get('publishers', [])
    steam_url = game_details.get('steam_url', '')
    # Categories and genres are already lists of descriptions (strings)
    categories = game_details.get('categories', [])
    genres = game_details.get('genres', [])
    
    # Parse release date
    release_date_str = game_details.get('release_date', '')
    release_date = parse_release_date(release_date_str)
    
    # Format the data - store lists and objects directly (not as JSON strings)
    # Supabase/PostgreSQL will handle the JSON/JSONB conversion
    formatted_data = {
        "game_id": app_id,
        "name": game_details.get('title', name),
        "detailed_desc": game_details.get('detailed_description'),
        "short_desc": game_details.get('description'),
        "image": game_details.get('image'),
        "platforms": platforms,  # Store as dict, not JSON string
        "categories": categories,  # Store as list, not JSON string
        "genres": genres,  # Store as list, not JSON string
        "release_date": release_date,
        "metacritic": metacritic,  # Store as dict, not JSON string
        "content": content_descriptors,  # Store as dict, not JSON string
        "is_free": is_free,
        "price": price,
        "price_usd": price_usd,
        "developers": developers,  # Store as list, not JSON string
        "publishers": publishers,  # Store as list, not JSON string
        "steam_url": steam_url
        
    }
    
    return formatted_data


def get_highest_game_id() -> int:
    """
    Get the highest game_id from the games_db table
    
    Returns:
        Highest game_id or 0 if table is empty
    """
    try:
        response = supabase.table('games_db').select('game_id').order('game_id', desc=True).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            highest_id = response.data[0]['game_id']
            print(f"Highest game_id in database: {highest_id}")
            return highest_id
        else:
            print("Database is empty, starting from 0")
            return 0
            
    except Exception as e:
        print(f"Error getting highest game_id: {e}")
        return 0


def insert_game_to_db(game_data: Dict[str, Any]) -> bool:
    """
    Insert a game record into the games_db table
    
    Args:
        game_data: Formatted game data
    
    Returns:
        True if successful, False otherwise
    """
    try:
        response = supabase.table('games_db').insert(game_data).execute()
        
        if response.data:
            return True
        else:
            print(f"  Failed to insert game {game_data['game_id']}: No data returned")
            return False
            
    except Exception as e:
        print(f"  Error inserting game {game_data['game_id']}: {e}")
        return False


def game_exists_in_db(game_id: int) -> bool:
    """
    Check if a game already exists in the database
    
    Args:
        game_id: Steam app ID to check
    
    Returns:
        True if game exists, False otherwise
    """
    try:
        response = supabase.table('games_db').select('game_id').eq('game_id', game_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"  Error checking if game exists: {e}")
        return False


async def process_game_batch(games: List[Dict[str, Any]], batch_number: int) -> int:
    """
    Process a batch of games and insert them into the database
    
    Args:
        games: List of game dictionaries from Steam API
        batch_number: Current batch number for logging
    
    Returns:
        Number of successfully processed games
    """
    successful_count = 0
    
    print(f"\n{'='*60}")
    print(f"Processing Batch #{batch_number} ({len(games)} games)")
    print(f"{'='*60}")
    
    for idx, game in enumerate(games, 1):
        app_id = game.get('appid')
        name = game.get('name', 'Unknown')
        
        # Skip if app_id is invalid
        if not app_id or not isinstance(app_id, int):
            print(f"[{idx}/{len(games)}] Skipping game with invalid app_id: {app_id}")
            continue
        
        # Skip if already exists
        if game_exists_in_db(app_id):
            print(f"[{idx}/{len(games)}] Game {app_id} ({name}) already exists, skipping...")
            successful_count += 1
            continue
        
        print(f"\n[{idx}/{len(games)}] Processing: {name} (ID: {app_id})")
        
        # Fetch detailed information
        game_details = await get_game_details_with_retry(app_id)
        
        # Add a small delay to avoid rate limiting
        await asyncio.sleep(0.75)
        
        # Format the data
        formatted_data = format_game_data(app_id, name, game_details)
        
        if formatted_data:
            # Insert into database
            if insert_game_to_db(formatted_data):
                print(f"  ✓ Successfully inserted {name}")
                successful_count += 1
            else:
                print(f"  ✗ Failed to insert {name}")
        else:
            print(f"  ✗ Could not format data for {name}")
    
    print(f"\n{'='*60}")
    print(f"Batch #{batch_number} Complete: {successful_count}/{len(games)} successful")
    print(f"{'='*60}\n")
    
    return successful_count


async def populate_games_db(access_token: str):
    """
    Main function to populate the games database
    
    Continuously fetches games from Steam API and populates database with detailed information.
    Processes games in batches of 100, starting from the highest game_id in the database.
    
    Args:
        access_token: Steam Web API access token
    """
    print("\n" + "="*60)
    print("STEAM GAMES DATABASE POPULATOR")
    print("="*60 + "\n")
    
    # Get starting point
    last_appid = get_highest_game_id()
    batch_number = 1
    total_processed = 0
    
    print(f"\nStarting from app_id: {last_appid}")
    print("Press Ctrl+C to stop the process at any time.\n")
    
    try:
        while True:
            print(f"\n{'*'*60}")
            print(f"Fetching batch #{batch_number} (starting from app_id {last_appid})...")
            print(f"{'*'*60}")
            
            # Fetch next batch of games
            try:
                app_list_response = await get_steam_app_list(access_token, last_appid, max_results=100)
            except Exception as e:
                print(f"\n❌ Error fetching app list: {e}")
                print("Waiting 60 seconds before retrying...")
                await asyncio.sleep(60)
                continue
            
            # Extract games from response
            response_data = app_list_response.get('response', {})
            apps = response_data.get('apps', [])
            
            if not apps:
                print("\n" + "="*60)
                print("No more games to fetch. Database is up to date!")
                print("="*60)
                break
            
            print(f"Fetched {len(apps)} games")
            
            # Process the batch
            successful = await process_game_batch(apps, batch_number)
            total_processed += successful
            
            # Update last_appid for next iteration
            last_appid = apps[-1].get('appid', last_appid)
            
            print(f"\n📊 Progress Summary:")
            print(f"   Batches processed: {batch_number}")
            print(f"   Total games added: {total_processed}")
            print(f"   Current app_id: {last_appid}")
            
            batch_number += 1
            
            # Small delay between batches
            print("\nWaiting 5 seconds before next batch...\n")
            await asyncio.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("Process interrupted by user")
        print("="*60)
        print(f"\nFinal Statistics:")
        print(f"  Batches processed: {batch_number - 1}")
        print(f"  Total games added: {total_processed}")
        print(f"  Last app_id: {last_appid}")
        print("\nYou can resume by running the script again.")
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nDatabase population process ended.")


def main():
    """
    Entry point for the script
    """
    print("\n" + "="*60)
    print("Steam Games Database Populator")
    print("="*60)
    print("\nThis script will populate your games_db table with Steam games.")
    print("It will continuously fetch and process games until interrupted.")
    print("\n" + "="*60 + "\n")
    
    # Prompt for access token
    access_token = input("Enter your Steam Web API access token: ").strip()
    
    if not access_token:
        print("\n❌ Error: Access token is required!")
        return
    
    print("\n✓ Access token received")
    print("\nStarting database population...")
    print("This will run continuously. Press Ctrl+C to stop.\n")
    
    # Run the async function
    asyncio.run(populate_games_db(access_token))


if __name__ == "__main__":
    main()
