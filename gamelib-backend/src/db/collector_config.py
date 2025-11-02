"""
Configuration for Steam Data Collector
Adjust these settings to control the data collection process.
"""

# Collection Targets
TARGET_USERS = 500  # How many users to collect
MAX_ATTEMPTS = 5000  # Maximum attempts before stopping

# Validation Requirements
MIN_GAMES_REQUIRED = 5  # Minimum games a user must have
MIN_PLAYTIME_REQUIRED = 60  # Minimum total playtime in minutes

# Rate Limiting
DELAY_BETWEEN_USERS = 1  # Seconds to wait between processing users
BATCH_SIZE = 15  # Number of users to process before a longer pause
BATCH_DELAY = 30  # Seconds to wait after processing a batch

# Steam ID Generation
STEAM_ID_BASE = 76561197960265728  # Minimum Steam ID
STEAM_ID_MAX_OFFSET = 300000000  # Maximum offset from base

# Retry Configuration
MAX_RETRIES = 10  # Maximum retries for failed requests
REQUEST_TIMEOUT = 10  # Timeout for HTTP requests in seconds
