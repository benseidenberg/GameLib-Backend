# GameLib Backend

A FastAPI-based backend service for Steam game recommendations, filtering, and user management with AI-powered features.

## Architecture

The backend follows a clean layered architecture pattern:

```
src/
├── api/               # API route handlers (FastAPI endpoints)
├── services/          # Business logic layer
├── db/
│   ├── repositories/  # Database access layer
│   └── scrapers/      # Data collection scripts
├── schemas/           # Pydantic models & data operations
└── models/            # Domain models
```

### Design Principles

- **Repository Pattern**: All database access goes through repository classes
- **Service Layer**: Business logic is centralized in service classes
- **Schema Classes**: Pydantic models with static operation methods
- **Single Responsibility**: Each module has one clear purpose
- **No Redundancy**: One source of truth for each functionality

## Features

### Game Recommendations
- **Collaborative Filtering**: User-based recommendations with similar player analysis
- **Cluster Recommendations**: Steam-based clustering for discovering similar games
- **Content Filtering**: Advanced filtering by genre, tags, price, platforms, and more
- **Content Safety**: Automatic filtering of inappropriate content

### User Management
- Steam profile integration
- Game library tracking
- Play statistics and preferences
- Login tracking

### Game Database
- 100,000+ Steam games
- Comprehensive metadata (genres, tags, categories, platforms)
- Price information
- Review scores
- Content descriptors

## API Endpoints

### Authentication & Users
- `POST /api/auth/steam-login` - Steam OAuth login
- `GET /api/users/{steam_id}` - Get user data
- `POST /api/users/` - Create new user
- `PUT /api/users/{steam_id}` - Update user
- `GET /api/users/{steam_id}/name` - Get user's Steam name

### Recommendations
- `GET /api/collaborative-recommendations/{steam_id}/` - Collaborative filtering recommendations
- `GET /api/clusters/{steam_id}` - Cluster-based recommendations
- `GET /api/recommendations/clusters/{steam_id}` - Detailed cluster recommendations

### Games
- `GET /api/steam/game-details/{game_id}` - Get game details
- `GET /api/tags` - Get available filter tags

### Steam Integration
- `GET /api/steam/profile/{steam_id}` - Get Steam profile and games
- `GET /api/steam/player/{steam_id}` - Get Steam player summary

## Tech Stack

- **FastAPI** - Modern async web framework
- **Supabase** - PostgreSQL database with real-time capabilities
- **Pydantic** - Data validation and serialization
- **httpx** - Async HTTP client for Steam API
- **scikit-learn** - Machine learning for recommendations
- **pandas & numpy** - Data processing
- **OpenAI** - AI chatbot integration

## Setup

### Prerequisites
- Python 3.8+
- Steam Web API Key
- Supabase project

### Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create `.env` file:
   ```env
   STEAM_API_KEY=your_steam_api_key
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   OPENAI_API_KEY=your_openai_key
   ```

5. Run the server:
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```

   For development with auto-reload (slower):
   ```bash
   uvicorn src.main:app --reload
   ```

The API will be available at `http://localhost:8000`

## Database Schema

### users
- `steam_id` (bigint, PK) - Steam user ID
- `data` (jsonb) - Steam profile data
- `games` (jsonb) - User's game library
- `games_array` (text[]) - Sorted game IDs by playtime
- `login_count` (int) - Number of logins

### games_db
- `game_id` (bigint, PK) - Steam app ID
- `name` (text) - Game title
- `short_desc` (text) - Short description
- `image` (text) - Header image URL
- `price` (text) - Formatted price
- `price_usd` (float) - Price in USD
- `genres` (text[]) - Game genres
- `categories` (text[]) - Game categories
- `tags` (text[]) - User-defined tags
- `platforms` (jsonb) - Platform availability
- `developers` (text[]) - Developer names
- `publishers` (text[]) - Publisher names
- `release_date` (date) - Release date
- `positive` (int) - Positive reviews
- `negative` (int) - Negative reviews
- `steam_url` (text) - Steam store URL
- `content` (jsonb) - Content descriptors
- `required_age` (int) - Age rating

## Development

### Project Structure

See folder-specific READMEs for details:
- [API Documentation](src/api/README.md)
- [Services Documentation](src/services/README.md)
- [Schemas Documentation](src/schemas/README.md)
- [Repositories Documentation](src/db/repositories/README.md)

### Code Style
- Follow PEP 8 guidelines
- Use type hints
- Document functions with docstrings
- Keep functions focused and single-purpose

### Testing
Run tests with:
```bash
pytest
```

## Contributing

1. Create a feature branch
2. Make your changes following the architecture patterns
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License
