# Schemas Layer

This folder contains Pydantic models and static data operation methods. Schemas define data structures and provide operations for fetching/transforming data.

## Design Principles

1. **Data Models**: Pydantic models for validation and serialization
2. **Static Operations**: Class methods for data operations (fetch, transform)
3. **Type Safety**: Strong typing with Python type hints
4. **Single Source**: One schema class per entity type

## Files

### `user_schema.py`
User-related data models and operations.

**Models:**
- `User` - Complete user information
- `UserCreate` - Schema for creating users
- `UserUpdate` - Schema for updating users
- `UserResponse` - User data response
- `SteamProfile` - Steam profile data
- `SimilarUser` - Similar user with matching score

**Operations:**
- `User.fetch_profile_data()` - Fetch Steam owned games
- `User.fetch_player_summary()` - Fetch Steam player profile

**Properties:**
- `persona_name` - User's Steam name
- `avatar` - User's avatar URL
- `profile_url` - Steam profile URL
- Methods: `get_top_games()`, `owns_game()`

### `game_schema.py`
Game-related data models and operations.

**Models:**
- `Game` - Complete game information
- `GameRecommendation` - Game with recommendation metadata
- `GameFilters` - Filters for querying games

**Operations (GameOperations class):**
- `fetch_from_db()` - Get game from database
- `fetch_from_steam()` - Get game from Steam API
- `fetch_details()` - Get game (DB first, Steam fallback)
- `fetch_basic()` - Get basic game info (ID + title)

## Pydantic Configuration

All models use Pydantic v2 features:
- Field validation with `Field()`
- Alias support for database field mapping
- `from_attributes` for ORM compatibility
- Type coercion and validation

## Usage Patterns

### As Data Models
```python
from src.schemas.user_schema import User

user = User(
    steam_id=76561198000000000,
    data={"personaname": "Player"},
    login_count=1
)
```

### As Operations
```python
from src.schemas.game_schema import GameOperations
from src.db.supabase_client import supabase

# Fetch game details
game = await GameOperations.fetch_details(
    game_id=570,
    supabase_client=supabase
)

# Fetch from Steam only
steam_game = await GameOperations.fetch_from_steam(
    game_id=570,
    skip_content_filter=True
)
```

### With Properties
```python
user = User(**user_data)
print(user.persona_name)  # Access computed property
print(user.profile_url)   # Steam profile URL
top_games = user.get_top_games(n=10)  # Method call
```

## Field Aliases

Database fields often use different names than API responses. Use aliases:

```python
class Game(BaseModel):
    game_id: int = Field(alias='game_id')  # DB: game_id, API: game_id
    name: str
    header_image: Optional[str] = Field(None, alias='image')
    
    class Config:
        populate_by_name = True  # Accept both names
```

## Adding New Schemas

When adding a new schema:

1. Create the base model with Pydantic
2. Add field validation and aliases
3. Add properties for computed fields
4. Create operation methods if needed
5. Document all fields and methods

Example:
```python
from pydantic import BaseModel, Field
from typing import Optional
import httpx

class Example(BaseModel):
    \"\"\"Example entity\"\"\"
    id: int
    name: str
    value: Optional[float] = None
    
    class Config:
        from_attributes = True
    
    @property
    def display_name(self) -> str:
        \"\"\"Formatted display name\"\"\"
        return f"{self.name} ({self.id})"
    
    @staticmethod
    async def fetch_by_id(id: int) -> Optional[dict]:
        \"\"\"Fetch example by ID\"\"\"
        # Implementation
        pass
```

## Validation

Pydantic automatically validates:
- Required vs optional fields
- Type correctness
- Value constraints (min/max, regex, etc.)
- Custom validators

Add custom validation with validators:
```python
from pydantic import validator

class Example(BaseModel):
    score: int
    
    @validator('score')
    def validate_score(cls, v):
        if v < 0 or v > 100:
            raise ValueError('Score must be 0-100')
        return v
```
