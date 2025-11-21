"""
Simple runner script for the Steam data collector.
Run this to start collecting Steam user data for collaborative filtering.
"""

import sys
import os

# Add parent directory to path so we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.steam_data_collector import main
import asyncio

if __name__ == "__main__":
    print("\n🎮 Starting Steam Data Collector...")
    print("Press Ctrl+C to stop at any time.\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Collector stopped. Goodbye!")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
