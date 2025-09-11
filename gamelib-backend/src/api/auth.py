
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from openid.consumer.consumer import Consumer, SUCCESS
from openid.store.memstore import MemoryStore
from urllib.parse import urlencode, urlparse, parse_qs
from src.api.users import create_user_with_steam_id

STEAM_OPENID_URL = "https://steamcommunity.com/openid"
STEAM_RETURN_URL = "http://localhost:8000/api/auth/steam/callback"

router = APIRouter()

@router.get("/auth/steam/login")
async def steam_login_redirect(request: Request):
    # Start OpenID authentication with Steam
    consumer = Consumer({}, MemoryStore())
    openid_request = consumer.begin(STEAM_OPENID_URL)
    trust_root = f"{request.url.scheme}://{request.url.netloc}"
    redirect_url = openid_request.redirectURL(trust_root, STEAM_RETURN_URL)
    return RedirectResponse(redirect_url)

@router.get("/auth/steam/callback")
async def steam_callback(request: Request):
    # Complete OpenID authentication
    consumer = Consumer({}, MemoryStore())
    # Convert query params to dict
    query = dict(request.query_params)
    # Build full URL
    full_url = str(request.url)

    openid_response = consumer.complete(query, full_url)
    print("OpenID response status:", openid_response.status)
    print("OpenID response:", openid_response)
    if openid_response.status == SUCCESS:
        claimed_id = openid_response.getDisplayIdentifier()
        if claimed_id:
            # Extract SteamID from claimed_id
            steam_id = claimed_id.split("/")[-1]
            # Insert user into Supabase if not already present

            user = await create_user_with_steam_id(steam_id)
            return {"steam_id": steam_id, "data": user}
        else:
            raise HTTPException(status_code=400, detail="Steam authentication failed: No claimed_id returned.")
    else:
        raise HTTPException(status_code=400, detail="Steam authentication failed")