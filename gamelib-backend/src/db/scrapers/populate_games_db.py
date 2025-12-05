"""
Steam Games Database Populator

This script populates the games_db table with comprehensive game information from Steam.
It fetches games in batches of 100 and enriches each with detailed metadata.

Usage:
    python populate_games_db.py
    python populate_games_db.py --mode populate --token YOUR_TOKEN
    python populate_games_db.py --mode update

The script will prompt for your Steam Web API access token if not provided.
"""

import asyncio
import httpx
import json
import sys
import os
import argparse
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# Add src directory to path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db.supabase_client import supabase
import time


def load_existing_tags(tags_file_path: Path) -> set:
    """
    Load existing tags from tags.txt file
    
    Args:
        tags_file_path: Path to the tags.txt file
    
    Returns:
        Set of existing tags
    """
    if not tags_file_path.exists():
        return set()
    
    try:
        content = tags_file_path.read_text(encoding='utf-8').strip()
        if not content:
            return set()
        # Split by comma and strip whitespace from each tag
        tags = {tag.strip() for tag in content.split(',') if tag.strip()}
        return tags
    except Exception as e:
        print(f"Warning: Could not load existing tags: {e}")
        return set()


def save_new_tags(tags_file_path: Path, new_tags: set):
    """
    Append new tags to tags.txt file
    
    Args:
        tags_file_path: Path to the tags.txt file
        new_tags: Set of new tags to add
    """
    if not new_tags:
        return
    
    try:
        # Read existing content
        existing_content = ''
        if tags_file_path.exists():
            existing_content = tags_file_path.read_text(encoding='utf-8').strip()
        
        # Prepare new tags as comma-separated string
        new_tags_str = ', '.join(sorted(new_tags))
        
        # Append to file
        if existing_content:
            updated_content = existing_content + ', ' + new_tags_str
        else:
            updated_content = new_tags_str
        
        tags_file_path.write_text(updated_content, encoding='utf-8')
        print(f"  💾 Added {len(new_tags)} new tags to tags.txt")
    except Exception as e:
        print(f"  Warning: Could not save new tags: {e}")


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


async def get_steamspy_details(app_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch game information from SteamSpy API
    
    Args:
        app_id: Steam app ID
    
    Returns:
        Dictionary containing SteamSpy data (tags, languages, positive, negative) or None
    """
    try:
        url = f"https://steamspy.com/api.php?request=appdetails&appid={app_id}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract only the fields we need
                # Convert tags dict to array of just the tag names (keys)
                tags_dict = data.get('tags', {})
                tags_array = list(tags_dict.keys()) if tags_dict else []
                
                steamspy_info = {
                    "tags": tags_array,
                    "languages": data.get('languages', '').split(', ') if data.get('languages') else [],
                    "positive": data.get('positive', 0),
                    "negative": data.get('negative', 0)
                }
                
                return steamspy_info
            else:
                print(f"  SteamSpy HTTP {response.status_code} for app {app_id}")
                return None
                
    except Exception as e:
        print(f"  Error fetching SteamSpy details for {app_id}: {str(e)}")
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
    url = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?access_token={access_token}&have_description_language=english&last_appid={last_appid}&max_results={max_results}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"Error fetching app list: {e}")
        raise


async def get_game_details_with_retry(app_id: int, max_retries: int = 10) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed game information from both Steam and SteamSpy with retry logic
    
    Args:
        app_id: Steam app ID
        max_retries: Maximum retry attempts for non-rate-limit errors
    
    Returns:
        Dictionary containing combined Steam and SteamSpy information or None if not found
    """
    import random
    
    attempt = 0
    rate_limit_retries = 0
    
    while attempt < max_retries:
        try:
            # Fetch from Steam API
            game_details = await get_steam_app_details(app_id, skip_content_filter=True)
            
            if game_details:
                # Fetch from SteamSpy API (no retry needed, it's more reliable)
                steamspy_details = await get_steamspy_details(app_id)
                
                # Merge SteamSpy data into game_details
                if steamspy_details:
                    game_details.update(steamspy_details)
                else:
                    # Add empty values if SteamSpy fails
                    game_details.update({
                        "tags": [],
                        "languages": [],
                        "positive": 0,
                        "negative": 0
                    })
                
                return game_details
            else:
                # Game not found or no data (not an error, just doesn't exist)
                print(f"  Game {app_id} not found or no data available")
                return None
                
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                # Rate limited - wait 30-60 seconds and retry indefinitely
                rate_limit_retries += 1
                wait_time = random.randint(10, 50)
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
        game_details: Detailed game information from get_game_details_with_retry (includes SteamSpy data)
    
    Returns:
        Formatted dictionary ready for database insertion or None if essential data is missing
    """
    if not game_details:
        # Minimal record with just ID and name
        return {
            "game_id": app_id,
            "name": name,
            "short_desc": None,
            "image": None,
            "platforms": {},
            "categories": [],
            "genres": [],
            "release_date": None,
            "metacritic": {},
            "content": {},
            "is_free": False,
            "price": None,
            "price_usd": None,
            "developers": [],
            "publishers": [],
            "steam_url": None,
            "tags": [],
            "languages": [],
            "positive": 0,
            "negative": 0
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
    categories = game_details.get('categories', [])
    genres = game_details.get('genres', [])
    
    # SteamSpy data
    tags = game_details.get('tags', [])
    languages = game_details.get('languages', [])
    positive = game_details.get('positive', 0)
    negative = game_details.get('negative', 0)
    
    # Parse release date
    release_date_str = game_details.get('release_date', '')
    release_date = parse_release_date(release_date_str)
    
    # Format the data
    formatted_data = {
        "game_id": app_id,
        "name": game_details.get('title', name),
        "short_desc": game_details.get('description'),
        "image": game_details.get('image'),
        "platforms": platforms,
        "categories": categories,
        "genres": genres,
        "release_date": release_date,
        "metacritic": metacritic,
        "content": content_descriptors,
        "is_free": is_free,
        "price": price,
        "price_usd": price_usd,
        "developers": developers,
        "publishers": publishers,
        "steam_url": steam_url,
        "tags": tags,
        "languages": languages,
        "positive": positive,
        "negative": negative
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


async def process_game_batch(games: List[Dict[str, Any]], batch_number: int, existing_tags: set, tags_file_path: Path) -> tuple[int, set]:
    """
    Process a batch of games and insert them into the database
    
    Args:
        games: List of game dictionaries from Steam API
        batch_number: Current batch number for logging
        existing_tags: Set of tags already in tags.txt
        tags_file_path: Path to the tags.txt file
    
    Returns:
        Tuple of (number of successfully processed games, set of new tags found)
    """
    successful_count = 0
    new_tags_in_batch = set()
    
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
        await asyncio.sleep(0.5)
        
        # Format the data
        formatted_data = format_game_data(app_id, name, game_details)
        
        if formatted_data:
            # Track new tags from this game
            game_tags = formatted_data.get('tags', [])
            date = formatted_data.get('release_date')
            positive = formatted_data.get('positive', 0)
            name = formatted_data.get('name', 'Unknown Game').lower()
            short_desc = formatted_data.get('short_desc', '')
            if short_desc:
                short_desc = short_desc.strip().lower()
            else:
                short_desc = ''
            if any(word in name or word in short_desc for word in ["hentai", "adult", "nudity", "sexual content", "explicit"]) \
            or (game_tags == [] and date == None and positive == 0):
                print(f"  ⚠️  Warning: Skipping game {name} due to adult content or insufficient data")
                continue
            for tag in game_tags:
                if tag and tag not in existing_tags and tag not in new_tags_in_batch:
                    new_tags_in_batch.add(tag)
            
            # Insert into database
            if insert_game_to_db(formatted_data):
                print(f"  ✓ Successfully inserted {name}")
                successful_count += 1
            else:
                print(f"  ✗ Failed to insert {name}")
        else:
            print(f"  ✗ Could not format data for {name}")
    
    # Save any new tags found in this batch
    if new_tags_in_batch:
        save_new_tags(tags_file_path, new_tags_in_batch)
    
    print(f"\n{'='*60}")
    print(f"Batch #{batch_number} Complete: {successful_count}/{len(games)} successful")
    if new_tags_in_batch:
        print(f"New tags discovered: {len(new_tags_in_batch)}")
    print(f"{'='*60}\n")
    
    return successful_count, new_tags_in_batch


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
    total_time_elapsed = 0.0
    overall_start_time = time.time()
    
    # Load existing tags and set up tags file path
    tags_file_path = Path(__file__).resolve().parent / 'tags.txt'
    existing_tags = load_existing_tags(tags_file_path)
    total_new_tags = 0
    print(f"Loaded {len(existing_tags)} existing tags from tags.txt")
    
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
                print("Waiting 30 seconds before retrying...")
                await asyncio.sleep(30)
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
            successful, new_tags = await process_game_batch(apps, batch_number, existing_tags, tags_file_path)
            total_processed += successful
            
            # Update existing tags set with new tags found
            if new_tags:
                existing_tags.update(new_tags)
                total_new_tags += len(new_tags)
            
            # Calculate timing statistics
            total_time_elapsed = time.time() - overall_start_time
            avg_time_per_game = total_time_elapsed / total_processed if total_processed > 0 else 0
            
            # Update last_appid for next iteration
            last_appid = apps[-1].get('appid', last_appid)
            
            print(f"\n📊 Progress Summary:")
            print(f"   Batches processed: {batch_number}")
            print(f"   Total games added: {total_processed}")
            print(f"   Total unique tags: {len(existing_tags)} ({total_new_tags} new)")
            print(f"   Current app_id: {last_appid}")
            print(f"   Total time elapsed: {total_time_elapsed:.2f}s ({total_time_elapsed/60:.2f} min)")
            print(f"   Average time per game: {avg_time_per_game:.2f}s")
            print(f"   Estimated games/hour: {int(3600 / avg_time_per_game) if avg_time_per_game > 0 else 0}")
            
            batch_number += 1
            
            # Small delay between batches
            print("\nWaiting 30 seconds before next batch...\n")
            await asyncio.sleep(30)

    except KeyboardInterrupt:
        total_time_elapsed = time.time() - overall_start_time
        avg_time_per_game = total_time_elapsed / total_processed if total_processed > 0 else 0
        
        print("\n\n" + "="*60)
        print("Process interrupted by user")
        print("="*60)
        print("\nFinal Statistics:")
        print(f"  Batches processed: {batch_number - 1}")
        print(f"  Total games added: {total_processed}")
        print(f"  Total unique tags collected: {len(existing_tags)} ({total_new_tags} new)")
        print(f"  Last app_id: {last_appid}")
        print(f"  Total time elapsed: {total_time_elapsed:.2f}s ({total_time_elapsed/60:.2f} min)")
        print(f"  Average time per game: {avg_time_per_game:.2f}s")
        print(f"  Games processed per hour: {int(3600 / avg_time_per_game) if avg_time_per_game > 0 else 0}")
        print("\nYou can resume by running the script again.")
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nDatabase population process ended.")


async def update_existing_games_with_steamspy():
    """
    Update all existing games in the database with SteamSpy data (tags, languages, positive, negative)
    
    This function fetches all games from the database and enriches them with SteamSpy information.
    It will automatically skip games that already have SteamSpy data, so you can safely restart it.
    """
    print("\n" + "="*60)
    print("STEAMSPY DATA UPDATER")
    print("="*60 + "\n")
    
    # Fetch games from database that don't have SteamSpy data yet (tags is null or empty)
    print("Fetching games without SteamSpy data from database...")
    try:
        result = supabase.table('games_db').select('game_id, name, tags').is_('tags', 'null').execute()
        games = result.data
    except Exception as e:
        print(f"❌ Error fetching games from database: {e}")
        return
    
    if not games:
        print("✓ All games already have SteamSpy data!")
        return
    
    total_games = len(games)
    print(f"Found {total_games} games to update\n")
    print("Press Ctrl+C to stop the process at any time.\n")
    
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    start_time = time.time()
    
    try:
        for idx, game in enumerate(games, 1):
            game_id = game.get('game_id')
            game_name = game.get('name', 'Unknown')
            
            if not game_id:
                print(f"[{idx}/{total_games}] Skipping game with no ID")
                skipped_count += 1
                continue
            
            print(f"[{idx}/{total_games}] Updating {game_name} (ID: {game_id})")
            
            # Fetch SteamSpy data
            steamspy_data = await get_steamspy_details(game_id)
            
            if steamspy_data:
                # Update database with SteamSpy data
                try:
                    update_result = supabase.table('games_db').update({
                        'tags': steamspy_data.get('tags', {}),
                        'languages': steamspy_data.get('languages', []),
                        'positive': steamspy_data.get('positive', 0),
                        'negative': steamspy_data.get('negative', 0)
                    }).eq('game_id', game_id).execute()
                    
                    print(f"  ✓ Updated with {len(steamspy_data.get('tags', {}))} tags, {len(steamspy_data.get('languages', []))} languages")
                    updated_count += 1
                except Exception as e:
                    print(f"  ✗ Failed to update in database: {e}")
                    failed_count += 1
            else:
                print(f"  ✗ No SteamSpy data available")
                failed_count += 1
            
            # Add delay to avoid overwhelming SteamSpy
            await asyncio.sleep(1)
            
            # Progress update every 100 games
            if idx % 100 == 0:
                elapsed_time = time.time() - start_time
                avg_time = elapsed_time / idx
                remaining = total_games - idx
                est_remaining_time = avg_time * remaining
                
                print(f"\n📊 Progress Update:")
                print(f"   Updated: {updated_count} | Failed: {failed_count} | Skipped: {skipped_count}")
                print(f"   Time elapsed: {elapsed_time/60:.1f} min")
                print(f"   Est. remaining: {est_remaining_time/60:.1f} min")
                print(f"   Avg time/game: {avg_time:.2f}s\n")
    
    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("Process interrupted by user")
        print("="*60)
    
    # Final statistics
    elapsed_time = time.time() - start_time
    print("\n" + "="*60)
    print("STEAMSPY UPDATE COMPLETE")
    print("="*60)
    print(f"\nFinal Statistics:")
    print(f"  Total games processed: {updated_count + failed_count + skipped_count}")
    print(f"  Successfully updated: {updated_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Total time: {elapsed_time/60:.1f} minutes")
    print(f"  Average time per game: {elapsed_time/(updated_count + failed_count) if (updated_count + failed_count) > 0 else 0:.2f}s")
    print("="*60 + "\n")


def main():
    """
    Entry point for the script
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Steam Games Database Populator')
    parser.add_argument('--mode', choices=['populate', 'update'], help='Mode: populate (add new games) or update (add SteamSpy data to existing)')
    parser.add_argument('--token', help='Steam Web API access token (only for populate mode)')
    args = parser.parse_args()
    
    # If arguments provided, run non-interactively
    if args.mode:
        if args.mode == 'populate':
            access_token = args.token
            if not access_token:
                print("\n❌ Error: --token is required for populate mode!")
                print("Usage: python populate_games_db.py --mode populate --token YOUR_TOKEN")
                return
            
            print("\n" + "="*60)
            print("POPULATE NEW GAMES (NON-INTERACTIVE MODE)")
            print("="*60)
            print("\nStarting database population...")
            print("This will run continuously. Press Ctrl+C to stop.\n")
            
            asyncio.run(populate_games_db(access_token))
        
        elif args.mode == 'update':
            print("\n" + "="*60)
            print("UPDATE EXISTING GAMES WITH STEAMSPY DATA (NON-INTERACTIVE MODE)")
            print("="*60)
            print("\nStarting SteamSpy data update...")
            print("Press Ctrl+C to stop.\n")
            
            asyncio.run(update_existing_games_with_steamspy())
        
        return
    
    # Interactive mode (original behavior)
    print("\n" + "="*60)
    print("Steam Games Database Populator")
    print("="*60)
    print("\nChoose an option:")
    print("1. Populate database with new games (continuous)")
    print("2. Update existing games with SteamSpy data")
    print("="*60 + "\n")
    
    choice = input("Enter your choice (1 or 2): ").strip()
    
    if choice == "1":
        print("\n" + "="*60)
        print("POPULATE NEW GAMES")
        print("="*60)
        print("\nThis will continuously fetch and process games until interrupted.")
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
    
    elif choice == "2":
        print("\n" + "="*60)
        print("UPDATE EXISTING GAMES WITH STEAMSPY DATA")
        print("="*60)
        print("\nThis will update all existing games with SteamSpy data.")
        print("(tags, languages, positive reviews, negative reviews)")
        print("\n" + "="*60 + "\n")
        
        confirm = input("Continue? (y/n): ").strip().lower()
        
        if confirm == 'y':
            print("\nStarting SteamSpy data update...")
            print("Press Ctrl+C to stop.\n")
            asyncio.run(update_existing_games_with_steamspy())
        else:
            print("\nCancelled.")
    
    else:
        print("\n❌ Invalid choice. Please run the script again and choose 1 or 2.")


if __name__ == "__main__":
    main()
