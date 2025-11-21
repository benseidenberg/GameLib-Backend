"""
Script to update existing users in the database with the new games_array column.
games_array contains game IDs sorted by playtime_forever in descending order.
Processes users in batches to handle large databases.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

from src.db.supabase_client import supabase

# Configuration
BATCH_SIZE = 100  # Number of users to fetch per batch
UPDATE_DELAY = 0.1  # Delay between individual updates (seconds)


async def update_games_array_for_all_users():
    """
    Fetch all users from the database in batches and update their games_array column.
    games_array is created by sorting the keys of the games dictionary by playtime_forever.
    """
    print("\n" + "="*70)
    print("UPDATING GAMES_ARRAY FOR ALL USERS (BATCH MODE)")
    print("="*70)
    print(f"Batch size: {BATCH_SIZE} users")
    print("="*70 + "\n")
    
    try:
        # First, get total count of users
        print("→ Counting total users with NULL games_array...")
        count_response = supabase.table('users').select('steam_id').is_('games_array', 'null').execute()
        total_users = len(count_response.data) if count_response.data else 0
        
        if not total_users or total_users == 0:
            print("✗ No users found with NULL games_array")
            return
        
        print(f"✓ Found {total_users} total users to update\n")
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        # Process in batches
        batch_num = 0
        
        while updated_count + skipped_count + error_count < total_users:
            batch_num += 1
            print(f"\n{'='*70}")
            print(f"BATCH {batch_num} - Remaining users to process: {total_users - (updated_count + skipped_count + error_count)}")
            print(f"{'='*70}\n")
            
            # Fetch batch of users (always from offset 0 since we're filtering by NULL)
            # After each batch is processed, those users are no longer NULL, so next batch gets the next set
            print(f"→ Fetching batch of {BATCH_SIZE} users with NULL games_array...")
            response = supabase.table('users').select('steam_id, games').is_('games_array', 'null').limit(BATCH_SIZE).execute()
            users = response.data
            
            if not users:
                print("✗ No more users to process")
                break
            
            print(f"✓ Fetched {len(users)} users\n")
            
            # Process each user in the batch
            for idx, user in enumerate(users, 1):
                steam_id = user.get('steam_id')
                games_dict = user.get('games', {})
                
                global_idx = updated_count + skipped_count + error_count + idx
                print(f"[{global_idx}/{total_users}] Processing Steam ID: {steam_id}")
                
                # Skip if no games
                if not games_dict or not isinstance(games_dict, dict):
                    print(f"  ✗ No valid games data, skipping")
                    skipped_count += 1
                    continue
                
                try:
                    # Create games_array: sorted list of game IDs by playtime_forever (descending)
                    games_array = sorted(
                        games_dict.keys(),
                        key=lambda game_id: games_dict[game_id].get('playtime_forever', 0) if isinstance(games_dict[game_id], dict) else 0,
                        reverse=True
                    )
                    
                    print(f"  → Created games_array with {len(games_array)} games")
                    
                    # Update the user record
                    update_response = supabase.table('users').update({
                        'games_array': games_array
                    }).eq('steam_id', steam_id).execute()
                    
                    if update_response.data:
                        print(f"  ✓ Successfully updated")
                        updated_count += 1
                    else:
                        print(f"  ✗ Failed to update")
                        error_count += 1
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(UPDATE_DELAY)
                        
                except Exception as e:
                    print(f"  ✗ Error: {str(e)}")
                    error_count += 1
                    continue
            
            # Progress summary after each batch
            print(f"\n--- Batch {batch_num} Complete ---")
            print(f"Updated so far: {updated_count}/{total_users}")
            print(f"Skipped: {skipped_count}, Errors: {error_count}")
            print(f"Progress: {((updated_count + skipped_count + error_count)/total_users)*100:.1f}%\n")
        
        # Final summary
        print("\n" + "="*70)
        print("UPDATE COMPLETE")
        print("="*70)
        print(f"Total users: {total_users}")
        print(f"Successfully updated: {updated_count}")
        print(f"Skipped (no games): {skipped_count}")
        print(f"Errors: {error_count}")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point"""
    await update_games_array_for_all_users()


if __name__ == "__main__":
    asyncio.run(main())
