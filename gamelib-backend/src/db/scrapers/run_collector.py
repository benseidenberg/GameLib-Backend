"""
Simple runner script for the Steam data collector.
Run this to start collecting Steam user data for collaborative filtering.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db.scrapers.steam_data_collector import main

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
