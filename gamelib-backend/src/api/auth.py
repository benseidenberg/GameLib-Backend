
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode
import httpx
import re

router = APIRouter()

# Steam OpenID settings
STEAM_OPENID_URL = "https://steamcommunity.com/openid"
# For development - replace with your ngrok URL when using ngrok
STEAM_RETURN_URL = "http://localhost:8000/api/auth/steam/callback"  # Change this to https://YOUR_NGROK_URL.ngrok.io/api/auth/steam/callback

def validate_steam_id(steam_id: str) -> bool:
    """Validate Steam ID format (17-digit number)"""
    return bool(re.match(r'^\d{17}$', steam_id))

def extract_steam_id_from_claimed_id(claimed_id: str) -> str:
    """Extract Steam ID from claimed_id URL"""
    # claimed_id format: https://steamcommunity.com/openid/id/{steam_id}
    match = re.search(r'/id/(\d+)$', claimed_id)
    if match:
        return match.group(1)
    return ""

@router.get("/auth/steam/login")
async def steam_login():
    """Initiate Steam OpenID authentication"""
    params = {
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.mode': 'checkid_setup',
        'openid.return_to': STEAM_RETURN_URL,
        'openid.realm': 'http://localhost:8000',
        'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
    }
    
    steam_url = f"{STEAM_OPENID_URL}/login?{urlencode(params)}"
    return RedirectResponse(url=steam_url)

@router.get("/auth/debug")
async def debug_endpoint():
    """Simple debug endpoint to test backend is working"""
    print("=== DEBUG ENDPOINT HIT ===")
    return {"message": "Backend auth router is working!", "timestamp": "2025-09-30"}

@router.get("/auth/test/callback")
async def test_callback():
    """Test callback with dummy Steam ID to verify frontend flow"""
    print("=== TEST CALLBACK HIT ===")
    test_steam_id = "76561198000000000"  # Dummy Steam ID for testing
    dashboard_url = f"http://localhost:3000/dashboard?steam_id={test_steam_id}"
    print(f"Test redirecting to dashboard: {dashboard_url}")
    return RedirectResponse(url=dashboard_url)

@router.get("/auth/steam/callback")
async def steam_callback(request: Request):
    """Handle Steam OpenID callback"""
    print("=== STEAM CALLBACK RECEIVED ===")
    print(f"Request URL: {request.url}")
    
    # Get all query parameters
    params = dict(request.query_params)
    print(f"Query parameters: {params}")
    
    # Check if authentication was successful
    if params.get('openid.mode') != 'id_res':
        error_msg = "Steam authentication failed"
        return RedirectResponse(url=f"http://localhost:3000/login?error={error_msg}")
    
    # Verify the response with Steam
    verification_params = params.copy()
    verification_params['openid.mode'] = 'check_authentication'
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{STEAM_OPENID_URL}/login", data=verification_params)
            
            if 'is_valid:true' not in response.text:
                error_msg = "Steam verification failed"
                return RedirectResponse(url=f"http://localhost:3000/login?error={error_msg}")
                
        except Exception as e:
            error_msg = "Steam verification error"
            return RedirectResponse(url=f"http://localhost:3000/login?error={error_msg}")
    
    # Extract Steam ID
    claimed_id = params.get('openid.claimed_id', '')
    print(f"Claimed ID: {claimed_id}")
    
    steam_id = extract_steam_id_from_claimed_id(claimed_id)
    print(f"Extracted steam_id: {steam_id}")
    
    if not steam_id or not validate_steam_id(steam_id):
        print(f"Steam ID validation failed: steam_id={steam_id}, valid={validate_steam_id(steam_id) if steam_id else False}")
        error_msg = "Invalid Steam ID"
        return RedirectResponse(url=f"http://localhost:3000/login?error={error_msg}")
    
    # Redirect to dashboard with Steam ID
    dashboard_url = f"http://localhost:3000/dashboard?steam_id={steam_id}"
    print(f"Redirecting to dashboard: {dashboard_url}")
    return RedirectResponse(url=dashboard_url)