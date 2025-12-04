"""
Script to populate games_db.csv with data from Supabase games_db table
Fetches games in batches of 500 to avoid request timeouts
"""
import csv
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from db.supabase_client import supabase


def fetch_games_batch(offset: int, batch_size: int = 500):
    """
    Fetch a batch of games from the database
    
    Args:
        offset: Number of records to skip
        batch_size: Number of records to fetch (default 500)
        
    Returns:
        List of game records
    """
    try:
        response = supabase.table('games_db') \
            .select('*') \
            .order('game_id') \
            .range(offset, offset + batch_size - 1) \
            .execute()
        
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching batch at offset {offset}: {str(e)}")
        return []


def get_total_count():
    """Get total number of games in the database"""
    try:
        response = supabase.table('games_db') \
            .select('game_id') \
            .limit(1) \
            .execute()
        
        return response.count if hasattr(response, 'count') else 0
    except Exception as e:
        print(f"Error getting total count: {str(e)}")
        return 0


def populate_csv():
    """
    Main function to populate games_db.csv with all games from database
    Processes in batches of 500 to prevent timeouts
    """
    # Define CSV file path
    csv_path = Path(__file__).resolve().parent.parent / 'repositories' / 'games_db.csv'
    
    print(f"Starting CSV population...")
    print(f"Output file: {csv_path}")
    
    # Get total count for progress tracking
    total_games = get_total_count()
    print(f"Total games in database: {total_games}")
    
    if total_games == 0:
        print("No games found in database. Exiting.")
        return
    
    # Fetch first batch to get column names
    first_batch = fetch_games_batch(0, 500)
    
    if not first_batch:
        print("Failed to fetch first batch. Exiting.")
        return
    
    # Get column names from first record
    columns = list(first_batch[0].keys())
    print(f"Found {len(columns)} columns: {', '.join(columns[:5])}...")
    
    # Open CSV file for writing
    games_written = 0
    batch_number = 0
    offset = 0
    batch_size = 500
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        
        # Process batches
        while True:
            batch_number += 1
            print(f"\nProcessing batch {batch_number} (offset: {offset})...")
            
            # Fetch batch
            games = fetch_games_batch(offset, batch_size)
            
            if not games:
                print(f"No more games to fetch. Finished.")
                break
            
            # Write batch to CSV
            for game in games:
                # Convert list fields to string representation for CSV
                processed_game = {}
                for key, value in game.items():
                    if isinstance(value, list):
                        # Convert lists to comma-separated string
                        processed_game[key] = '|'.join(str(v) for v in value) if value else ''
                    elif isinstance(value, dict):
                        # Convert dicts to JSON-like string
                        processed_game[key] = str(value)
                    else:
                        processed_game[key] = value
                
                writer.writerow(processed_game)
                games_written += 1
            
            print(f"Wrote {len(games)} games (Total: {games_written}/{total_games})")
            
            # Check if we're done
            if len(games) < batch_size:
                print(f"\nReached end of data. Last batch had {len(games)} games.")
                break
            
            # Move to next batch
            offset += batch_size
    
    print(f"\n✓ Successfully wrote {games_written} games to {csv_path}")
    print(f"CSV file size: {csv_path.stat().st_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    try:
        populate_csv()
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user. Partial data may have been written.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
