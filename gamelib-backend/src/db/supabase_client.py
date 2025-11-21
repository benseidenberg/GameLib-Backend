from supabase import create_client, Client
from dotenv import load_dotenv
import os
from pathlib import Path

# Get the directory where this file is located
current_dir = Path(__file__).resolve().parent
# Go up to src directory and load .env from there
env_path = current_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
if url is None:
    raise ValueError("SUPABASE_URL environment variable is required")
if key is None:
    raise ValueError("SUPABASE_KEY environment variable is required")
#assert url is not None and key is not None, "SUPABASE_URL and SUPABASE_KEY must be set"
supabase: Client = create_client(url, key)

def get_user(user_id: str):
    response = supabase.table('users').select('*').eq('id', user_id).execute()
    return response.data

def create_user(email: str, password: str):
    response = supabase.table('users').insert({'email': email, 'password': password}).execute()
    return response.data

def update_user(user_id, email = None, password = None):
    data = {}
    if email:
        data['email'] = email
    if password:
        data['password'] = password
    response = supabase.table('users').update(data).eq('id', user_id).execute()
    return response.data

def delete_user(user_id: str):
    response = supabase.table('users').delete().eq('id', user_id).execute()
    return response.data