# Steam Data Collector

Automatically collects Steam user data to populate the database for collaborative filtering recommendations.

## Features

- 🎯 Generates random Steam IDs and validates profiles
- 🔍 Only collects public profiles with sufficient game data
- 📊 Tracks progress and success rates in real-time
- ⏱️ Rate-limited to respect Steam API limits
- 🛑 Can be stopped and resumed at any time
- ⚙️ Fully configurable via config file

## Quick Start

### 1. Basic Usage

Run the collector with default settings (50 users):

```bash
cd gamelib-backend
python run_collector.py
```

### 2. Custom Configuration

Edit `src/db/collector_config.py` to adjust settings:

```python
TARGET_USERS = 100          # Collect 100 users
MIN_GAMES_REQUIRED = 10     # Users must have at least 10 games
MIN_PLAYTIME_REQUIRED = 120 # Users must have 2+ hours playtime
```

### 3. Stop the Collector

Press `Ctrl+C` at any time to stop gracefully.

## Configuration Options

### Collection Targets
- `TARGET_USERS`: How many users to collect (default: 50)
- `MAX_ATTEMPTS`: Maximum attempts before stopping (default: 500)

### Validation Requirements
- `MIN_GAMES_REQUIRED`: Minimum games a user must have (default: 5)
- `MIN_PLAYTIME_REQUIRED`: Minimum total playtime in minutes (default: 60)

### Rate Limiting
- `DELAY_BETWEEN_USERS`: Seconds between processing users (default: 2)
- `BATCH_SIZE`: Users to process before longer pause (default: 10)
- `BATCH_DELAY`: Seconds to wait after each batch (default: 30)

## How It Works

1. **Generate Random Steam ID**: Creates a random valid Steam ID
2. **Validate Profile**: Checks if profile exists and is public
3. **Fetch Data**: Gets player info and game library
4. **Validate Requirements**: Ensures user meets minimum thresholds
5. **Store in Database**: Saves user data for collaborative filtering
6. **Repeat**: Continues until target is reached

## Output Example

```
==========================================================
Processing Steam ID: 76561198123456789
==========================================================
→ Validating profile...
✓ Profile is valid and public
→ Fetching player summary...
✓ Found user: PlayerName123
→ Fetching games library...
✓ Found 147 games
✓ Total playtime: 2,341 minutes (39.0 hours)
→ Storing user in database...
✓ Successfully added PlayerName123 to database!

**********************************************************
PROGRESS: 15/50 users added (47 attempts)
Success rate: 31.9%
**********************************************************
```

## Important Notes

### Steam API Limits
- The collector includes rate limiting to stay within Steam's API limits
- Default settings: 2 seconds between users, 30-second pause every 10 users
- Adjust these in the config if needed

### Profile Requirements
- Only **public** Steam profiles are collected
- Profiles must have at least the minimum required games
- Profiles must have at least the minimum required playtime

### Database
- Each user is stored with:
  - Steam ID (unique identifier)
  - Player profile data (name, avatar, etc.)
  - Full games library with playtime
  - Login count (set to 0 for auto-collected users)

## Troubleshooting

### "No users being added"
- Most Steam profiles are private by default
- Increase `MAX_ATTEMPTS` to try more profiles
- Lower `MIN_GAMES_REQUIRED` or `MIN_PLAYTIME_REQUIRED`

### "Error: SUPABASE_URL environment variable is required"
- Make sure your `.env` file exists in `src/` directory
- Ensure all required environment variables are set

### "Rate limit exceeded"
- Increase `DELAY_BETWEEN_USERS` in config
- Increase `BATCH_DELAY` in config

## Running as Background Service

To run continuously in the background:

### Windows (PowerShell)
```powershell
Start-Process python -ArgumentList "run_collector.py" -WindowStyle Hidden
```

### Linux/Mac
```bash
nohup python run_collector.py > collector.log 2>&1 &
```

## Monitoring Progress

The collector outputs real-time progress including:
- Current user being processed
- Games found and total playtime
- Overall success rate
- Users added vs. target

You can stop and resume at any time without losing progress!
