"""
User schema definitions
Pydantic model for user-related data structures
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import httpx
import os


class User(BaseModel):
    """Complete user information with Steam profile and games data"""
    steam_id: int
    data: Optional[Dict] = None  # Steam profile data (personaname, avatar, etc.)
    games: Optional[Dict] = None  # Game library: game_id -> {playtime_forever, playtime_2weeks, etc}
    games_array: Optional[List[str]] = None  # Game IDs sorted by playtime
    login_count: int = 1
    
    class Config:
        from_attributes = True
    
    @staticmethod
    async def fetch_profile_data(steam_id: int) -> Optional[Dict]:
        """
        Fetch Steam user's owned games and play data
        
        Args:
            steam_id: Steam user ID
        
        Returns:
            Dictionary with games data and metadata
        """
        steam_api_key = os.getenv("STEAM_API_KEY")
        if not steam_api_key:
            raise ValueError("STEAM_API_KEY environment variable is required")
        
        try:
            url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={steam_api_key}&steamid={steam_id}&format=json&include_appinfo=1&include_played_free_games=1"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    
                    if "response" in data and "games" in data["response"]:
                        games = data["response"]["games"]
                        
                        # Process games data as a dictionary with appid as key
                        processed_games = {}
                        for game in games:
                            if game.get("playtime_forever", 0) > 0:
                                appid = str(game.get("appid"))  # Use string key for consistency
                                processed_games[appid] = {
                                    "name": game.get("name", "Unknown Game"),
                                    "playtime_forever": game.get("playtime_forever", 0),
                                    "playtime_2weeks": game.get("playtime_2weeks", 0),
                                    "img_icon_url": game.get("img_icon_url", ""),
                                    "rtime_last_played": game.get("rtime_last_played")
                                }
                        
                        return {
                            "steam_id": steam_id,
                            "total_games": len(processed_games),
                            "games": processed_games
                        }
                    else:
                        return {"steam_id": steam_id, "total_games": 0, "games": {}}
                else:
                    return None
                    
        except Exception as e:
            print(f"Error fetching Steam profile for {steam_id}: {str(e)}")
            return None
    
    @staticmethod
    async def fetch_player_summary(steam_id: int) -> Optional[Dict]:
        """
        Fetch Steam user's profile information (name, avatar, etc.)
        
        Args:
            steam_id: Steam user ID
        
        Returns:
            Dictionary with player summary data
        """
        steam_api_key = os.getenv("STEAM_API_KEY")
        if not steam_api_key:
            raise ValueError("STEAM_API_KEY environment variable is required")
        
        try:
            url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
            params = {
                'key': steam_api_key,
                'steamids': str(steam_id)
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'response' in data and 'players' in data['response']:
                        players = data['response']['players']
                        if players:
                            return players[0]
                    
                    return None
                else:
                    return None
                    
        except Exception as e:
            print(f"Error fetching player summary for {steam_id}: {str(e)}")
            return None
    
    @property
    def persona_name(self) -> str:
        """Get user's Steam persona name"""
        if self.data:
            return self.data.get('personaname', 'Unknown User')
        return 'Unknown User'
    
    @property
    def avatar(self) -> Optional[str]:
        """Get user's Steam avatar URL"""
        if self.data:
            return self.data.get('avatarfull') or self.data.get('avatar')
        return None
    
    @property
    def profile_url(self) -> str:
        """Get user's Steam profile URL"""
        if self.data:
            return self.data.get('profileurl', f'https://steamcommunity.com/profiles/{self.steam_id}')
        return f'https://steamcommunity.com/profiles/{self.steam_id}'
    
    def get_top_games(self, n: int = 5) -> List[str]:
        """Get user's top N games by playtime"""
        if self.games_array:
            return self.games_array[:n]
        return []
    
    def owns_game(self, game_id: int) -> bool:
        """Check if user owns a specific game"""
        if self.games:
            return str(game_id) in self.games
        return False


# Steam API helper functions
STEAM_API_KEY = os.getenv("STEAM_API_KEY")


async def fetch_steam_profile(steam_id: int) -> Optional[Dict]:
    """
    Fetch Steam player profile and owned games
    Combines player summary and owned games in one call
    """
    if not STEAM_API_KEY:
        raise ValueError("STEAM_API_KEY environment variable is required")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch player summary
            profile_url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
            profile_params = {'key': STEAM_API_KEY, 'steamids': str(steam_id)}
            profile_response = await client.get(profile_url, params=profile_params)
            
            if profile_response.status_code != 200:
                return None
            
            profile_data = profile_response.json()
            if 'response' not in profile_data or 'players' not in profile_data['response']:
                return None
            
            players = profile_data['response']['players']
            if not players:
                return None
            
            player = players[0]
            
            # Fetch owned games
            games_url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
            games_params = {
                'key': STEAM_API_KEY,
                'steamid': steam_id,
                'format': 'json',
                'include_appinfo': 1,
                'include_played_free_games': 1
            }
            games_response = await client.get(games_url, params=games_params)
            
            games_data = {}
            if games_response.status_code == 200:
                games_json = games_response.json()
                if 'response' in games_json and 'games' in games_json['response']:
                    for game in games_json['response']['games']:
                        game_id = str(game.get('appid'))  # Steam API uses 'appid' not 'game_id'
                        games_data[game_id] = {
                            'name': game.get('name', 'Unknown Game'),
                            'playtime_forever': game.get('playtime_forever', 0),
                            'playtime_2weeks': game.get('playtime_2weeks', 0),
                            'img_icon_url': game.get('img_icon_url', ''),
                            'rtime_last_played': game.get('rtime_last_played', 0)
                        }
            
            # Generate games_array sorted by playtime
            games_array = sorted(
                games_data.keys(),
                key=lambda x: games_data[x].get('playtime_forever', 0),
                reverse=True
            )
            
            return {
                'profile': player,
                'games': games_data,
                'games_array': games_array
            }
            
    except Exception as e:
        print(f"Error fetching Steam profile for {steam_id}: {str(e)}")
        return None

