from fastapi import APIRouter, HTTPException
from src.recommender.recommender import get_game_clusters

router = APIRouter()

@router.get("/recommendations/{steam_id}")
async def get_recommendations(steam_id: int):
    """
    Get game recommendations/clusters for a user by Steam ID
    """
    print(f"DEBUG: Starting recommendations for steam_id: {steam_id}")
    try:
        print("DEBUG: About to call get_game_clusters")
        clusters = await get_game_clusters(steam_id)
        print(f"DEBUG: get_game_clusters returned: {type(clusters)} - {clusters}")
        if not clusters:
            raise HTTPException(status_code=404, detail="No recommendations found")
        return clusters
    except ValueError as e:
        print(f"DEBUG: ValueError occurred: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"DEBUG: Unexpected error occurred: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
#https://api.steampowered.com/IStoreAppSimilarityService/IdentifyClustersFromPlaytime/v1/?access_token=eyAidHlwIjogIkpXVCIsICJhbGciOiAiRWREU0EiIH0.eyAiaXNzIjogInI6MDAwMl8yNkZDQzNFRl9ENTEyNSIsICJzdWIiOiAiNzY1NjExOTg5ODA2NjA2MjciLCAiYXVkIjogWyAid2ViOmNvbW11bml0eSIgXSwgImV4cCI6IDE3NTkyNjAxMDEsICJuYmYiOiAxNzUwNTMyNjM0LCAiaWF0IjogMTc1OTE3MjYzNCwgImp0aSI6ICIwMDE5XzI2RkNDM0U0XzkxMzVGIiwgIm9hdCI6IDE3NTkxNzI2MzQsICJydF9leHAiOiAxNzc3MTI4MTA2LCAicGVyIjogMCwgImlwX3N1YmplY3QiOiAiMTQwLjIzMi4xNzcuMTQ2IiwgImlwX2NvbmZpcm1lciI6ICIxNDAuMjMyLjE2My4yOCIgfQ.Ob602cgjEiiOESorPFGJg9DPfsdFCI8_7m5-uti9ipT9EYxnMmqyjvVqhIZ5KQPgLVXuzreGdE4ZD-wHkbVuCg&steamid=76561198980660627