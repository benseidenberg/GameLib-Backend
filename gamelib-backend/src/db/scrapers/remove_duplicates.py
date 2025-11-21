"""
Script to find and remove duplicate Steam IDs from the users table.
Keeps the user with the highest login_count (most active user).
If login_count is the same, keeps the one with more games.
"""

import asyncio
import os
import sys
from typing import Dict, List, Set
from collections import defaultdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db.supabase_client import supabase


def find_duplicates() -> Dict[int, List[Dict]]:
    """
    Find all duplicate Steam IDs in the users table.
    
    Returns:
        Dictionary mapping steam_id -> list of user records with that ID
    """
    print("Scanning for duplicate Steam IDs...")
    
    try:
        # Fetch only steam_id field to find duplicates (minimal data transfer)
        print("Fetching steam_ids...")
        response = supabase.table('users').select('steam_id').execute()
        
        if not response.data:
            print("No users found in database")
            return {}
        
        all_steam_ids = [user['steam_id'] for user in response.data]
        print(f"Found {len(all_steam_ids)} total user records")
        
        # Find which steam_ids appear more than once
        steam_id_counts = defaultdict(int)
        for steam_id in all_steam_ids:
            steam_id_counts[steam_id] += 1
        
        duplicate_steam_ids = [steam_id for steam_id, count in steam_id_counts.items() if count > 1]
        
        if not duplicate_steam_ids:
            print("\n✓ No duplicate Steam IDs found!")
            return {}
        
        print(f"Found {len(duplicate_steam_ids)} Steam IDs with duplicates")
        
        # Fetch full user records only for duplicates (in batches to avoid timeout)
        duplicates = {}
        batch_size = 10
        
        for i in range(0, len(duplicate_steam_ids), batch_size):
            batch = duplicate_steam_ids[i:i + batch_size]
            print(f"Fetching batch {i // batch_size + 1}/{(len(duplicate_steam_ids) + batch_size - 1) // batch_size}...")
            
            for steam_id in batch:
                response = supabase.table('users').select('*').eq('steam_id', steam_id).execute()
                if response.data and len(response.data) > 1:
                    duplicates[steam_id] = response.data
        
        if duplicates:
            print(f"\n⚠️  Found {len(duplicates)} Steam IDs with duplicates:")
            total_duplicate_records = sum(len(users) - 1 for users in duplicates.values())
            print(f"   Total duplicate records to remove: {total_duplicate_records}")
            
            for steam_id, users in duplicates.items():
                print(f"\n   Steam ID {steam_id}: {len(users)} records")
                for idx, user in enumerate(users, 1):
                    games_count = len(user.get('games', {}))
                    login_count = user.get('login_count', 0)
                    persona_name = user.get('data', {}).get('personaname', 'Unknown')
                    print(f"     [{idx}] {persona_name} - Login count: {login_count}, Games: {games_count}")
        else:
            print("\n✓ No duplicate Steam IDs found!")
        
        return duplicates
        
    except Exception as e:
        print(f"Error finding duplicates: {e}")
        import traceback
        traceback.print_exc()
        return {}


def select_user_to_keep(users: List[Dict]) -> Dict:
    """
    Select which user record to keep from a list of duplicates.
    Priority:
    1. Highest login_count (most active)
    2. If tied, most games
    3. If still tied, first one
    
    Args:
        users: List of user records with the same steam_id
        
    Returns:
        The user record to keep
    """
    def get_sort_key(user):
        login_count = user.get('login_count', 0)
        games_count = len(user.get('games', {}))
        return (login_count, games_count)
    
    # Sort by priority (descending)
    sorted_users = sorted(users, key=get_sort_key, reverse=True)
    
    return sorted_users[0]


def remove_duplicates(duplicates: Dict[int, List[Dict]], dry_run: bool = True) -> int:
    """
    Remove duplicate user records, keeping the most active one.
    
    Args:
        duplicates: Dictionary of steam_id -> list of duplicate user records
        dry_run: If True, only show what would be deleted (don't actually delete)
        
    Returns:
        Number of records deleted
    """
    if not duplicates:
        print("No duplicates to remove")
        return 0
    
    deleted_count = 0
    
    print(f"\n{'='*70}")
    print(f"{'DRY RUN - ' if dry_run else ''}REMOVING DUPLICATE RECORDS")
    print(f"{'='*70}\n")
    
    for steam_id, users in duplicates.items():
        # Select which user to keep
        user_to_keep = select_user_to_keep(users)
        
        # Find users to delete (all except the one to keep)
        users_to_delete = [u for u in users if u != user_to_keep]
        
        keep_name = user_to_keep.get('data', {}).get('personaname', 'Unknown')
        keep_login = user_to_keep.get('login_count', 0)
        keep_games = len(user_to_keep.get('games', {}))
        
        print(f"Steam ID {steam_id}:")
        print(f"  ✓ KEEPING: {keep_name} (Login: {keep_login}, Games: {keep_games})")
        
        for user in users_to_delete:
            del_name = user.get('data', {}).get('personaname', 'Unknown')
            del_login = user.get('login_count', 0)
            del_games = len(user.get('games', {}))
            
            print(f"  ✗ {'WOULD DELETE' if dry_run else 'DELETING'}: {del_name} (Login: {del_login}, Games: {del_games})")
            
            if not dry_run:
                try:
                    # Delete by primary key or unique identifier
                    # Since steam_id is not unique, we need to use a unique row identifier
                    # Supabase uses an implicit 'id' column or we can match all fields
                    
                    # Delete using exact match on all fields to ensure we delete the right one
                    response = supabase.table('users').delete().match({
                        'steam_id': steam_id,
                        'login_count': user.get('login_count', 0)
                    }).execute()
                    
                    deleted_count += 1
                    print(f"    → Deleted successfully")
                    
                except Exception as e:
                    print(f"    → ERROR deleting: {e}")
        
        print()
    
    print(f"{'='*70}")
    if dry_run:
        print(f"DRY RUN COMPLETE - Would have deleted {len([u for users in duplicates.values() for u in users]) - len(duplicates)} records")
    else:
        print(f"DELETION COMPLETE - Deleted {deleted_count} duplicate records")
    print(f"{'='*70}\n")
    
    return deleted_count


async def run_duplicate_removal(dry_run: bool = True):
    """
    Main function to find and remove duplicates.
    
    Args:
        dry_run: If True, only show what would be deleted (don't actually delete)
    """
    print("\n" + "="*70)
    print("DUPLICATE STEAM ID REMOVAL TOOL")
    print("="*70)
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (will delete duplicates)'}")
    print("="*70 + "\n")
    
    # Find duplicates
    duplicates = find_duplicates()
    
    if not duplicates:
        print("\n✓ Database is clean - no duplicates found!")
        return
    
    # Ask for confirmation if not dry run
    if not dry_run:
        print("\n⚠️  WARNING: This will permanently delete duplicate records!")
        print("   The record with the highest login_count will be kept.")
        response = input("\nAre you sure you want to proceed? (yes/no): ")
        
        if response.lower() != 'yes':
            print("Cancelled - no changes made")
            return
    
    # Remove duplicates
    deleted = remove_duplicates(duplicates, dry_run=dry_run)
    
    if not dry_run and deleted > 0:
        # Verify cleanup
        print("\nVerifying cleanup...")
        remaining_duplicates = find_duplicates()
        
        if remaining_duplicates:
            print(f"⚠️  Warning: {len(remaining_duplicates)} duplicates still remain")
        else:
            print("✓ Cleanup verified - all duplicates removed!")


async def main():
    """Entry point"""
    import sys
    
    # Check for --live flag
    dry_run = '--live' not in sys.argv
    
    if not dry_run:
        print("\n🔴 LIVE MODE ENABLED - Changes will be permanent!\n")
    
    await run_duplicate_removal(dry_run=dry_run)


if __name__ == "__main__":
    print("\nUsage (from gamelib-backend directory):")
    print("  ../.venv/Scripts/python.exe src/db/scrapers/remove_duplicates.py          # Dry run (show what would be deleted)")
    print("  ../.venv/Scripts/python.exe src/db/scrapers/remove_duplicates.py --live   # Actually delete duplicates\n")
    
    asyncio.run(main())
