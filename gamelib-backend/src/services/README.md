# Services Layer

This folder contains business logic for the application. Services orchestrate operations between repositories and external APIs.

## Design Principles

1. **Business Logic Only**: All business rules and workflows live here
2. **Stateless**: Services should be stateless and reusable
3. **Single Responsibility**: Each service handles one domain
4. **No Direct DB Access**: Use repositories for database operations

## Files

### `filtering.py`
**FilteringService** - Handles game filtering and content safety
- `get_filtered_games()` - Apply complex filters to games
- `get_filtered_games_batch()` - Filter specific games by IDs
- `is_content_appropriate()` - Check if game content is safe
- `AVAILABLE_TAGS` - Class constant with all available filter tags

**Key Features:**
- Content safety filtering (removes adult/inappropriate games)
- Multi-criteria filtering (genres, tags, platforms, price, etc.)
- Database query optimization
- Batch processing support

### `collaborative_recommendations.py`
**CollaborativeRecommendationService** - User-based collaborative filtering
- `get_recommendations()` - Find similar users and recommend their games
- `find_similar_users()` - Calculate user similarity scores
- `get_user_game_overlap()` - Analyze game library overlaps

**Algorithm:**
1. Find users with similar game libraries
2. Calculate similarity scores based on shared games
3. Recommend games that similar users enjoy
4. Filter by user preferences and content safety

### `clusters.py`
**ClustersService** - Steam cluster-based recommendations
- `get_cluster_recommendations()` - Fetch Steam's cluster data
- Uses Steam's internal clustering algorithm
- Provides recommendations based on playtime patterns

## Service Architecture

```
API Endpoint
    ↓
Service (Business Logic)
    ├→ Repository (Database)
    ├→ External API (Steam, etc.)
    └→ Other Services
    ↓
Return Results
```

## Usage Pattern

Services are instantiated in API routes and used to orchestrate operations:

```python
# In API route
from src.services.filtering import FilteringService

filtering_service = FilteringService()

@router.get("/games")
async def get_games():
    games = await filtering_service.get_filtered_games(
        steam_genres=["Action", "RPG"],
        max_price=60.0
    )
    return games
```

## Adding New Services

When creating a new service:

1. Create a new file: `service_name.py`
2. Create a class: `ServiceNameService`
3. Initialize dependencies in `__init__`
4. Add business logic methods
5. Document all public methods

Example:
```python
\"\"\"
Service description
Business logic for [domain]
\"\"\"
from typing import List, Optional
from src.db.repositories.example_repo import ExampleRepository

class ExampleService:
    \"\"\"Service for [domain] operations\"\"\"
    
    def __init__(self):
        self.repo = ExampleRepository()
    
    async def do_something(self, param: str) -> Optional[dict]:
        \"\"\"
        Brief description
        
        Args:
            param: Parameter description
        
        Returns:
            Result description
        \"\"\"
        # Business logic here
        data = await self.repo.fetch_data(param)
        # Process data
        return processed_data
```

## Testing

Services should be unit tested with mocked repositories:
- Test business logic independently
- Mock repository calls
- Test edge cases and error handling
- Verify data transformations
