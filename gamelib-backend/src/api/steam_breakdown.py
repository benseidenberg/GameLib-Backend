STEAM_API_KEY="968317D323A2D4C8ED61E3D9F5E2FAB1"

async def fetch_steam_profile(steam_id: int):
    import httpx
    url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            data = response.json()
            if "response" in data and "players" in data["response"] and len(data["response"]["players"]) > 0:
                return data["response"]["players"][0]
    return None