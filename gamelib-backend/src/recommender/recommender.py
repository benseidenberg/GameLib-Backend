# Placeholder for game recommendation ML logic
STEAM_API_KEY="968317D323A2D4C8ED61E3D9F5E2FAB1"
import pandas as pd
import json
import datetime


async def get_game_clusters(steam_id: int):
    import httpx
    url = f"https://api.steampowered.com/IStoreAppSimilarityService/IdentifyClustersFromPlaytime/v1/?key={STEAM_API_KEY}&steamid={steam_id}&format=json&randomize=false"
    async with httpx.AsyncClient() as client:
        response = await client.post(url)
        if response.status_code == 200:
            data = response.json()

            return data
        else:
            raise ValueError(f"Failed to fetch: {response.status_code}")
    return None
#https://api.steampowered.com/IStoreAppSimilarityService/IdentifyClustersFromPlaytime/v1/?access_token=eyAidHlwIjogIkpXVCIsICJhbGciOiAiRWREU0EiIH0.eyAiaXNzIjogInI6MDAwMl8yNkZDQzNFRl9ENTEyNSIsICJzdWIiOiAiNzY1NjExOTg5ODA2NjA2MjciLCAiYXVkIjogWyAid2ViOmNvbW11bml0eSIgXSwgImV4cCI6IDE3NTkyNjAxMDEsICJuYmYiOiAxNzUwNTMyNjM0LCAiaWF0IjogMTc1OTE3MjYzNCwgImp0aSI6ICIwMDE5XzI2RkNDM0U0XzkxMzVGIiwgIm9hdCI6IDE3NTkxNzI2MzQsICJydF9leHAiOiAxNzc3MTI4MTA2LCAicGVyIjogMCwgImlwX3N1YmplY3QiOiAiMTQwLjIzMi4xNzcuMTQ2IiwgImlwX2NvbmZpcm1lciI6ICIxNDAuMjMyLjE2My4yOCIgfQ.Ob602cgjEiiOESorPFGJg9DPfsdFCI8_7m5-uti9ipT9EYxnMmqyjvVqhIZ5KQPgLVXuzreGdE4ZD-wHkbVuCg&steamid=76561198980660627