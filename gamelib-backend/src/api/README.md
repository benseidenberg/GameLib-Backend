# API Layer

This folder contains all FastAPI route handlers (HTTP endpoints). The API layer is responsible for:
- Receiving HTTP requests
- Validating request parameters
- Calling appropriate services
- Returning HTTP responses

## Design Principles

1. **Only Route Handlers**: This folder should contain ONLY FastAPI route definitions
2. **No Business Logic**: All business logic belongs in the `/services` layer
3. **No Database Calls**: All database access goes through `/db/repositories`
4. **Thin Controllers**: Keep endpoints thin - delegate to services

## Files

### `auth.py`
Steam OAuth authentication endpoints.
- `POST /auth/steam-login` - Initiate Steam login flow

### `users.py`
User management endpoints.
- `GET /users/{steam_id}` - Get user data
- `POST /users/` - Create new user
- `PUT /users/{steam_id}` - Update user
- `DELETE /users/{steam_id}` - Delete user
- `GET /users/{steam_id}/name` - Get user's Steam name
- `POST /users/{steam_id}/refresh` - Refresh user data from Steam

### `recommendations.py`
Game recommendation endpoints.
- `GET /clusters/{steam_id}` - Get cluster recommendations
- `GET /steam/profile/{steam_id}` - Get Steam profile
- `GET /steam/player/{steam_id}` - Get player summary
- `GET /steam/game-details/{game_id}` - Get game details
- `GET /recommendations/clusters/{steam_id}` - Detailed cluster recommendations

### `collaborative_filtering.py`
Collaborative filtering recommendation endpoints.
- `GET /tags` - Get available filter tags
- `GET /collaborative-recommendations/{steam_id}/` - Get collaborative recommendations with optional filters

## Request/Response Flow

```
HTTP Request
    ↓
FastAPI Endpoint (api/)
    ↓
Service Layer (services/)
    ↓
Repository Layer (db/repositories/)
    ↓
Database (Supabase)
    ↓
Response back up the chain
```

## Input Validation

All endpoints use Pydantic models for request validation. Additional validation includes:
- Steam ID range checks (0 < id < 999999999999999999)
- App ID range checks (0 < id < 999999999)
- Required parameter validation
- Type checking

## Error Handling

All endpoints use FastAPI's `HTTPException` for error responses:
- `400` - Bad Request (invalid input)
- `404` - Not Found
- `500` - Internal Server Error

## Adding New Endpoints

When adding a new endpoint:
1. Create the route handler in the appropriate file
2. Use Pydantic models for request/response validation
3. Add input validation for IDs and parameters
4. Delegate business logic to a service
5. Handle errors appropriately
6. Document the endpoint with docstrings

Example:
```python
@router.get("/endpoint/{id}")
async def get_something(id: int):
    """
    Brief description of what this endpoint does
    """
    try:
        # Validate input
        if id <= 0:
            raise HTTPException(status_code=400, detail="Invalid ID")
        
        # Call service
        result = await service.do_something(id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```
