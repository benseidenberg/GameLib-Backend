"""
Filtering service
Business logic for game filtering and content appropriateness
"""
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from src.db.repositories.games_db import GamesRepository

if TYPE_CHECKING:
    from src.schemas.game_schema import Game


class FilteringService:
    """Service for filtering games and checking content appropriateness"""
    
    def __init__(self):
        self.games_repo = GamesRepository()
    
    # Available tags for filtering (replaces tags.txt)
    AVAILABLE_TAGS = [
        "Action", "Adventure", "RPG", "Strategy", "Simulation", "Casual",
        "Singleplayer", "Multiplayer", "Co-op", "Story Rich", "Open World",
        "First-Person", "Third Person", "Shooter", "Puzzle", "Horror", "Survival",
        "Atmospheric", "Exploration", "Sandbox", "Platformer", "Fantasy", "Sci-fi",
        "Medieval", "Historical", "FPS", "Turn-Based", "Real-Time", "Tower Defense",
        "Card Game", "Board Game", "Racing", "Sports", "Fighting", "Stealth",
        "Tactical", "Roguelike", "Roguelite", "Metroidvania", "Souls-like",
        "Point & Click", "Visual Novel", "Interactive Fiction", "Dating Sim",
        "Management", "Building", "City Builder", "Colony Sim", "Crafting",
        "Survival Horror", "Psychological Horror", "Gore", "Violent", "Dark",
        "Comedy", "Funny", "Cartoon", "Anime", "Pixel Graphics", "Retro",
        "Low Poly", "Hand-drawn", "2D", "3D", "VR", "Controller", "Keyboard",
        "Mouse", "Touch", "Local Co-Op", "Online Co-Op", "Local Multiplayer",
        "Online Multiplayer", "Cross-Platform Multiplayer", "PvP", "PvE",
        "Competitive", "Team-Based", "Class-Based", "Hero Shooter", "MOBA",
        "Battle Royale", "MMO", "MMORPG", "Massively Multiplayer", "Persistent World",
        "Open World Survival Craft", "Base Building", "Resource Management",
        "Economy", "Trading", "Loot", "Character Customization", "Character Action",
        "Hack and Slash", "Bullet Hell", "Shoot 'Em Up", "Twin Stick Shooter",
        "Top-Down", "Isometric", "Side Scroller", "Beat 'em up", "Arcade",
        "Score Attack", "Time Attack", "Difficult", "Relaxing", "Great Soundtrack",
        "Soundtrack", "Music", "Rhythm", "Musical", "Education", "Tutorial",
        "Mature", "Nudity", "Sexual Content", "NSFW", "Adult", "Realistic",
        "Stylized", "Abstract", "Minimalist", "Colorful", "Dark Fantasy", "Space",
        "Post-apocalyptic", "Dystopian", "Cyberpunk", "Steampunk", "Magic",
        "Dragons", "Demons", "Zombies", "Vampires", "Pirates", "Ninjas", "Robots",
        "Mechs", "Dinosaurs", "Western", "Crime", "Detective", "Mystery", "Thriller",
        "War", "Military", "World War I", "World War II", "Modern Warfare",
        "Futuristic", "Time Travel", "Alternate History", "Choose Your Own Adventure",
        "Multiple Endings", "Choices Matter", "Narrative", "Cinematic", "Quick-Time Events",
        "Inventory Management", "Perma Death", "Procedural Generation", "Dynamic Narration",
        "Moddable", "Level Editor", "User-Generated Content", "Workshop", "Achievements",
        "Trading Cards", "Cloud Saves", "Partial Controller Support", "Full Controller Support",
        "Steam Achievements", "Steam Cloud", "Steam Workshop", "Steam Trading Cards",
        "In-App Purchases", "DLC", "Episodic", "Early Access", "Free to Play",
        "Indie", "AAA", "Short", "Long", "Replay Value", "Family Friendly",
        "Physics", "Destruction", "Environmental", "Parkour", "Transhumanism",
        "Political", "Satire", "Parody", "Experimental", "Surreal", "Text-Based"
    ]
    
    # Content descriptor IDs for adult/inappropriate content
    ADULT_CONTENT_DESCRIPTORS = [3, 4]  # Mature Sexual Content, Nudity or Sexual Content
    
    # Inappropriate keywords
    INAPPROPRIATE_KEYWORDS = [
        'adult', 'nsfw', 'hentai', 'erotic', 'xxx', 'porn', 'sexual',
        'nude', 'nudity', 'mature sexual', '18+', 'adults only'
    ]
    
    # Inappropriate tags
    INAPPROPRIATE_TAGS = [
        'Nudity', 'Sexual Content', 'NSFW', 'Adult', 'Hentai', 'Erotic',
        'Mature', 'Dating Sim', 'Anime', 'Visual Novel'  # Can contain adult content
    ]
    
    @staticmethod
    def is_content_appropriate(game: Dict[str, Any]) -> bool:
        """
        Check if game content is appropriate (no adult/sexual content)
        
        Args:
            game: Game dictionary with fields like content_descriptors, tags, name, etc.
            
        Returns:
            True if content is appropriate, False otherwise
        """
        # Check content descriptors
        content_descriptors = game.get('content_descriptors', [])
        if content_descriptors:
            if any(desc_id in FilteringService.ADULT_CONTENT_DESCRIPTORS for desc_id in content_descriptors):
                return False
        
        # Check age ratings
        required_age = game.get('required_age', 0)
        if required_age and required_age >= 18:
            return False
        
        # Check tags for inappropriate content
        game_tags = game.get('tags', [])
        if game_tags:
            for tag in game_tags:
                if tag in FilteringService.INAPPROPRIATE_TAGS:
                    return False
        
        # Check name and description for keywords
        name = game.get('name', '').lower()
        short_desc = game.get('short_description', '').lower()
        
        for keyword in FilteringService.INAPPROPRIATE_KEYWORDS:
            if keyword in name or keyword in short_desc:
                return False
        
        return True
    
    @staticmethod
    def apply_content_filter(games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out inappropriate content from list of games
        
        Args:
            games: List of game dictionaries
            
        Returns:
            Filtered list with only appropriate games
        """
        return [game for game in games if FilteringService.is_content_appropriate(game)]
    
    @staticmethod
    def get_available_tags() -> List[str]:
        """
        Get list of all available tags for filtering
        
        Returns:
            List of tag names
        """
        return FilteringService.AVAILABLE_TAGS.copy()
    
    @staticmethod
    def validate_filters(
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Validate and sanitize filter inputs
        
        Args:
            genres: List of genre filters
            tags: List of tag filters
            categories: List of category filters
            languages: List of language filters
            platforms: List of platform filters
            
        Returns:
            Dictionary of validated filters
        """
        validated = {}
        
        if genres:
            validated['genres'] = [g.strip() for g in genres if g and g.strip()]
        
        if tags:
            validated['tags'] = [t.strip() for t in tags if t and t.strip()]
        
        if categories:
            validated['categories'] = [c.strip() for c in categories if c and c.strip()]
        
        if languages:
            validated['languages'] = [l.strip() for l in languages if l and l.strip()]
        
        if platforms:
            valid_platforms = ['windows', 'mac', 'linux']
            validated['platforms'] = [p.lower().strip() for p in platforms 
                                     if p and p.lower().strip() in valid_platforms]
        
        return validated
    
    @staticmethod
    def calculate_similarity_score(
        user_games: List[str],
        similar_user_games: List[str],
        top_n: int = 10
    ) -> float:
        """
        Calculate similarity score between two users based on game overlap
        
        Args:
            user_games: Current user's games array (sorted by playtime)
            similar_user_games: Similar user's games array (sorted by playtime)
            top_n: Number of top games to weight more heavily
            
        Returns:
            Similarity score (higher = more similar)
        """
        if not user_games or not similar_user_games:
            return 0.0
        
        user_set = set(user_games)
        similar_set = set(similar_user_games)
        
        # Calculate total overlap
        total_overlap = len(user_set & similar_set)
        
        # Calculate top N overlap (weighted more heavily)
        user_top = set(user_games[:top_n])
        similar_top = set(similar_user_games[:top_n])
        top_overlap = len(user_top & similar_top)
        
        # Weighted score: top games count 3x more
        score = (top_overlap * 3.0) + total_overlap
        
        return score
    
    async def get_filtered_games(
        self,
        steam_genres: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        steam_categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
        min_release_date: Optional[str] = None,
        max_release_date: Optional[str] = None,
        min_positive_reviews: Optional[int] = None,
        min_negative_reviews: Optional[int] = None,
        max_price: Optional[float] = None,
        limit: int = 1000,
        order_by: str = 'positive'
    ) -> List['Game']:
        """
        Get filtered games from database with content appropriateness check
        
        Args:
            steam_genres: Filter by Steam genres
            languages: Filter by supported languages
            steam_categories: Filter by Steam categories
            tags: Filter by tags
            platforms: Filter by platforms (windows, mac, linux)
            min_release_date: Minimum release date (YYYY-MM-DD)
            max_release_date: Maximum release date (YYYY-MM-DD)
            min_positive_reviews: Minimum positive review count
            min_negative_reviews: Minimum negative review count
            max_price: Maximum price in USD
            limit: Maximum number of games to return
            order_by: Column to order by
            
        Returns:
            List of Game objects with full details
        """
        from src.schemas.game_schema import Game
        
        # Fetch games from repository (returns Game objects)
        games = self.games_repo.find_by_filters(
            genres=steam_genres,
            tags=tags,
            categories=steam_categories,
            languages=languages,
            platforms=platforms,
            min_price=None,
            max_price=max_price,
            min_positive=min_positive_reviews,
            min_negative=min_negative_reviews,
            limit=limit * 2 if limit else 2000,  # Fetch extra to account for filtering
            order_by=order_by,
            ascending=False
        )
        
        # Apply content filtering
        filtered_games = []
        for game in games:
            # Build game data structure for content check
            game_data = {
                'name': game.name,
                'short_description': game.short_description or '',
                'content_descriptors': game.content or {},
                'content': game.content or {},
                'required_age': game.required_age or 0,
                'tags': game.tags,
                'categories': game.categories,
                'genres': game.genres
            }
            
            if not self.is_content_appropriate(game_data):
                continue
            
            # Apply additional filters (release date, etc.)
            if min_release_date and game.release_date and game.release_date < min_release_date:
                continue
            if max_release_date and game.release_date and game.release_date > max_release_date:
                continue
            
            filtered_games.append(game)
            
            if len(filtered_games) >= limit:
                break
        
        return filtered_games
    
    async def get_filtered_games_batch(
        self,
        game_ids: List[int],
        steam_genres: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        steam_categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
        min_release_date: Optional[str] = None,
        max_release_date: Optional[str] = None,
        min_positive_reviews: Optional[int] = None,
        min_negative_reviews: Optional[int] = None,
        max_price: Optional[float] = None
    ) -> Dict[int, 'Game']:
        """
        Get specific games by IDs with filtering applied
        
        Args:
            game_ids: List of Steam app IDs to fetch
            (other args same as get_filtered_games)
            
        Returns:
            Dictionary mapping game_id -> Game object
        """
        from src.schemas.game_schema import Game
        
        if not game_ids:
            return {}
        
        # Fetch from repository (returns Game objects)
        games = self.games_repo.find_by_filters_batch(
            batch_ids=game_ids,
            genres=steam_genres,
            tags=tags,
            categories=steam_categories,
            languages=languages,
            platforms=platforms,
            min_price=None,
            max_price=max_price,
            order_by='positive'
        )
        
        # Apply content filtering and additional filters
        filtered_dict = {}
        for game in games:
            # Build game data for content check
            game_data = {
                'name': game.name,
                'short_description': game.short_description or '',
                'content_descriptors': game.content or {},
                'content': game.content or {},
                'required_age': game.required_age or 0,
                'tags': game.tags,
                'categories': game.categories,
                'genres': game.genres
            }
            
            if not self.is_content_appropriate(game_data):
                continue
            
            # Apply additional filters
            if min_release_date and game.release_date and game.release_date < min_release_date:
                continue
            if max_release_date and game.release_date and game.release_date > max_release_date:
                continue
            if min_positive_reviews and game.positive is not None and game.positive < min_positive_reviews:
                continue
            if min_negative_reviews and game.negative is not None and game.negative < min_negative_reviews:
                continue
            
            filtered_dict[game.game_id] = game
        
        return filtered_dict
