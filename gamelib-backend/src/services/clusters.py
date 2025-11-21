"""
Clusters service
Business logic for game clustering recommendations using Steam API
"""
import httpx
import os
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")


class ClustersService:
    """Service for game clustering recommendations"""
    
    def __init__(self):
        self.steam_api_key = STEAM_API_KEY
        if not self.steam_api_key:
            raise ValueError("STEAM_API_KEY environment variable is required")
    
    async def get_cluster_recommendations(self, steam_id: int) -> Optional[Dict]:
        """
        Get game cluster recommendations from Steam API
        Uses Steam's IStoreAppSimilarityService to identify game clusters
        based on user's playtime patterns
        
        Args:
            steam_id: User's Steam ID
            
        Returns:
            Cluster data from Steam API or None if failed
        """
        try:
            url = f"https://api.steampowered.com/IStoreAppSimilarityService/IdentifyClustersFromPlaytime/v1/"
            params = {
                'key': self.steam_api_key,
                'steamid': steam_id,
                'format': 'json',
                'randomize': False
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    return data
                else:
                    print(f"Steam API returned status {response.status_code}")
                    return None
                    
        except Exception as e:
            print(f"Error fetching game clusters for {steam_id}: {str(e)}")
            return None


# Backward compatibility function
async def get_game_clusters(steam_id: int) -> Optional[Dict]:
    """
    Legacy function for backward compatibility
    Delegates to ClustersService
    """
    service = ClustersService()
    return await service.get_cluster_recommendations(steam_id)