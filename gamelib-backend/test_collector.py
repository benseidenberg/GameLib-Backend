"""
Test script for Steam Data Collector
This will attempt to collect just 1 user to verify everything works.
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.steam_data_collector import run_continuous_collector

async def test_collector():
    """Test the collector with minimal settings"""
    print("\n🧪 Testing Steam Data Collector...")
    print("Attempting to collect 1 user for testing...\n")
    
    await run_continuous_collector(
        target_users=1,      # Just collect 1 user for testing
        max_attempts=50      # Try up to 50 random IDs
    )
    
    print("\n✅ Test complete!")

if __name__ == "__main__":
    try:
        asyncio.run(test_collector())
    except KeyboardInterrupt:
        print("\n\n⏹️  Test stopped by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
