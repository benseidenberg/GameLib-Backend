#!/usr/bin/env python3
"""
Test script to isolate the 500 error in the recommendations endpoint
"""
import asyncio
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def test_get_webapi_token():
    """Test the get_webapi_token function in isolation"""
    try:
        
        test_steam_id = 76561198000000000  # Example Steam ID
        print(f"Testing with steam_id: {test_steam_id}")
        
        
    except Exception as e:
        print(f"ERROR in get_webapi_token: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Full traceback:\n{traceback.format_exc()}")
        return None

async def test_get_game_clusters():
    """Test the get_game_clusters function"""
    try:
        from src.recommender.recommender import get_game_clusters
        print("\n=== Testing get_game_clusters ===")

        test_steam_id = 76561198980660627  # Example Steam ID
        print(f"Testing with steam_id: {test_steam_id}")
        
        clusters = await get_game_clusters(test_steam_id)
        print(f"SUCCESS: Got clusters: {type(clusters)} - {str(clusters)[:200]}...")
        return clusters
        
    except Exception as e:
        print(f"ERROR in get_game_clusters: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Full traceback:\n{traceback.format_exc()}")
        return None

async def main():
    print("Starting isolated testing...\n")
    clusters = await test_get_game_clusters()
    if clusters:
        print("SUCCESS: Got clusters")
        print(clusters)
    else:
        print("Skipping cluster test due to token failure")

if __name__ == "__main__":
    asyncio.run(main())