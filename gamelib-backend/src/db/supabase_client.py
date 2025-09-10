from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
assert url is not None and key is not None, "SUPABASE_URL and SUPABASE_KEY must be set"
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