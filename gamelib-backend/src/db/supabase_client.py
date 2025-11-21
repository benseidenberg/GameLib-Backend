"""
Supabase client configuration
Centralized Supabase client instance for the entire application
"""
from supabase import create_client, Client
from dotenv import load_dotenv
import os
<<<<<<< Updated upstream

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
if url is None:
    raise ValueError("SUPABASE_URL environment variable is required")
if key is None:
    raise ValueError("SUPABASE_KEY environment variable is required")
#assert url is not None and key is not None, "SUPABASE_URL and SUPABASE_KEY must be set"
supabase: Client = create_client(url, key)
=======
from pathlib import Path

# Load environment variables
current_dir = Path(__file__).resolve().parent
env_path = current_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Get Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
>>>>>>> Stashed changes

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")

# Create single Supabase client instance
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
