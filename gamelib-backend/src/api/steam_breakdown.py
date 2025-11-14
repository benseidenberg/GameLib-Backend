import requests
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
if not STEAM_API_KEY:
    raise ValueError("STEAM_API_KEY environment variable is required")
import json
import datetime

async def fetch_steam_profile(steam_id: int):
    import httpx
    url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            data = response.json()

            # Check if user has any games
            if "response" not in data or "games" not in data["response"]:
                # User has no games or empty library
                return (data, {})
            
            games = data["response"]["games"]
            if not games or len(games) == 0:
                # Empty games list
                return (data, {})
            
            #print("Fetched Steam profile data:", data)
            df = pd.json_normalize(games)
            remove = [col for col in df.columns if col not in ["appid", "playtime_forever", "rtime_last_played"]]
            df = df.drop(columns=remove)
            df = df[df["playtime_forever"] > 0]
            if "rtime_last_played" in df.columns:
                df["rtime_last_played"] = df["rtime_last_played"].apply(lambda x: datetime.datetime.fromtimestamp(x).strftime("%Y-%m-%d") if pd.notnull(x) else None)
            df = df.set_index("appid").to_dict(orient="index")

            return (data, df)
        else:
            raise ValueError(f"Failed to fetch Steam profile: {response.status_code}")
    return None

async def fetch_steam_player_summary(steam_id: int):
    """
    Fetch Steam user profile information using GetPlayerSummaries API
    This gets the user's name, avatar, profile URL, etc.
    """
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
            params = {
                'key': STEAM_API_KEY,
                'steamids': str(steam_id)
            }
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            players = data.get('response', {}).get('players', [])
            
            if players:
                player_data = players[0]
                print(f"Fetched Steam player summary: {player_data}")
                return player_data  # Returns player data with personaname, profileurl, avatarfull, etc.
            else:
                print(f"No player data found for steam_id: {steam_id}")
                return None
                
    except Exception as e:
        print(f"Error fetching Steam player summary: {e}")
        return None
