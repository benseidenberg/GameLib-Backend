# Repositories Layer

This folder contains database access classes. Repositories provide a clean abstraction over database operations.

## Design Principles

1. **Single Responsibility**: Each repository manages one table/entity
2. **No Business Logic**: Pure data access only
3. **Async Operations**: All methods are async for performance
4. **Type Safety**: Return typed data structures

## Files

### `games_db.py`
**GamesRepository** - Manages games_db table operations

**Methods:**
- `get_all_games()` - Fetch all games with optional limit
- `get_game_by_id(game_id)` - Get single game by ID
- `get_games_by_ids(game_ids)` - Batch fetch games by IDs
- `get_filtered_games(filters)` - Complex filtered game queries
- `search_games(query)` - Text search on game names
- `get_games_by_genre(genres)` - Filter by genres
- `get_games_by_tags(tags)` - Filter by tags
- `get_games_by_price_range(min_price, max_price)` - Price filtering
- `count_games()` - Get total game count

### `users_db.py`
**UsersRepository** - Manages users table operations

**Methods:**
- `get_all_users()` - Fetch all users
- `get_user_by_steam_id(steam_id)` - Get user by Steam ID
- `create_user(user_data)` - Insert new user
- `update_user(steam_id, user_data)` - Update existing user
- `delete_user(steam_id)` - Delete user
- `user_exists(steam_id)` - Check if user exists
- `increment_login_count(steam_id)` - Increment login counter
- `get_users_by_game(game_id)` - Find users who own a game

## Repository Pattern

Repositories isolate database logic from business logic:

```
Service
    ↓
Repository (Abstract data operations)
    ↓
Supabase Client (Database connection)
    ↓
PostgreSQL Database
```

## Usage Pattern

```python
from src.db.repositories.games_db import GamesRepository

# Initialize repository
games_repo = GamesRepository()

# Fetch data
all_games = await games_repo.get_all_games(limit=100)
single_game = await games_repo.get_game_by_id(570)
action_games = await games_repo.get_games_by_genre(["Action"])

# Filtered query
filters = {
    "steam_genres": ["Action", "RPG"],
    "max_price": 60.0,
    "platforms": ["windows"]
}
filtered_games = await games_repo.get_filtered_games(filters)
```

## Database Connection

All repositories use the Supabase client:

```python
from src.db.supabase_client import supabase

class ExampleRepository:
    def __init__(self):
        self.supabase = supabase
    
    async def fetch_data(self):
        result = self.supabase.table("table_name").select("*").execute()
        return result.data
```

## Query Building

Use Supabase's query builder for clean, readable queries:

```python
# Simple select
result = supabase.table("games_db").select("*").execute()

# With filters
result = supabase.table("games_db")\
    .select("*")\
    .eq("game_id", 570)\
    .execute()

# Complex query
result = supabase.table("games_db")\
    .select("game_id, name, price_usd")\
    .in_("genres", ["Action", "RPG"])\
    .lte("price_usd", 60.0)\
    .order("name")\
    .limit(100)\
    .execute()

# Array contains
result = supabase.table("games_db")\
    .select("*")\
    .contains("tags", ["Multiplayer"])\
    .execute()
```

## Error Handling

Repositories should handle database errors gracefully:

```python
async def get_game_by_id(self, game_id: int) -> Optional[Dict]:
    try:
        result = self.supabase.table("games_db")\
            .select("*")\
            .eq("game_id", game_id)\
            .execute()
        
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        print(f"Error fetching game {game_id}: {str(e)}")
        return None
```

## Adding New Repositories

When creating a new repository:

1. Create a new file: `table_name.py`
2. Create a class: `TableNameRepository`
3. Initialize Supabase client in `__init__`
4. Add CRUD methods (Create, Read, Update, Delete)
5. Add specialized query methods as needed
6. Document all methods with docstrings

Example template:
```python
\"\"\"
Repository for [table] operations
Handles database access for [entity]
\"\"\"
from typing import List, Dict, Optional
from src.db.supabase_client import supabase

class ExampleRepository:
    \"\"\"Repository for example table operations\"\"\"
    
    def __init__(self):
        self.supabase = supabase
        self.table_name = "example_table"
    
    async def get_by_id(self, id: int) -> Optional[Dict]:
        \"\"\"
        Fetch record by ID
        
        Args:
            id: Record ID
        
        Returns:
            Record data or None if not found
        \"\"\"
        try:
            result = self.supabase.table(self.table_name)\
                .select("*")\
                .eq("id", id)\
                .execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error fetching record {id}: {str(e)}")
            return None
    
    async def get_all(self, limit: int = 1000) -> List[Dict]:
        \"\"\"Fetch all records\"\"\"
        try:
            result = self.supabase.table(self.table_name)\
                .select("*")\
                .limit(limit)\
                .execute()
            
            return result.data or []
        except Exception as e:
            print(f"Error fetching records: {str(e)}")
            return []
```

## Performance Tips

1. **Use .select()** to fetch only needed columns
2. **Add .limit()** to prevent large result sets
3. **Use .in_()** for batch queries instead of loops
4. **Index frequently queried columns** in the database
5. **Use .contains()** for array column searches
