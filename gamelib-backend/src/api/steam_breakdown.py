STEAM_API_KEY="968317D323A2D4C8ED61E3D9F5E2FAB1"
import pandas as pd
import json
import datetime

async def fetch_steam_profile(steam_id: int):
    import httpx
    url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            data = response.json()

            #print("Fetched Steam profile data:", data)
            #if "response" in data and "players" in data["response"] and len(data["response"]["players"]) > 0:
            df = pd.json_normalize(data["response"]["games"])
            remove = [col for col in df.columns if col not in ["appid", "playtime_forever", "rtime_last_played"]]
            df = df.drop(columns=remove)
            df = df[df["playtime_forever"] > 0]
            df["rtime_last_played"] = df["rtime_last_played"].apply(lambda x: datetime.datetime.fromtimestamp(x).strftime("%Y-%m-%d") if pd.notnull(x) else None)
            df = df.set_index("appid").to_dict(orient="index")

            return (data, df)
        else:
            raise ValueError(f"Failed to fetch Steam profile: {response.status_code}")
    return None