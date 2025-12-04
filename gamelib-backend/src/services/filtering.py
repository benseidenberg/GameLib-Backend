"""
Filtering service
Business logic for game filtering and content appropriateness
"""
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING, cast
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
        game_ids: Optional[List[int]] = None,
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
        return_dict: bool = False,
        apply_content_filter: bool = True
    ) -> Union[List['Game'], Dict[int, 'Game']]:
        """
        Get filtered games using batch processing (ALWAYS uses batching for performance)
        
        Content filtering behavior:
        - When filters ARE provided: Content filtering happens in find_by_filters (database layer)
        - When NO filters provided: Content filtering should happen at API layer
        
        Args:
            game_ids: Optional list of specific game IDs to filter. If provided, only these games are considered.
            steam_genres: Filter by Steam genres
            languages: Filter by supported languages
            steam_categories: Filter by Steam categories
            tags: Filter by tags (uses SQL array overlap)
            platforms: Filter by platforms (windows, mac, linux)
            min_release_date: Minimum release date (YYYY-MM-DD)
            max_release_date: Maximum release date (YYYY-MM-DD)
            min_positive_reviews: Minimum positive review count
            min_negative_reviews: Minimum negative review count
            max_price: Maximum price in USD
            limit: Maximum number of games to return (used as stop_limit)
            return_dict: If True, return Dict[int, Game]. If False, return List[Game]
            apply_content_filter: If True, filters inappropriate content in database layer
            
        Returns:
            List[Game] or Dict[int, Game] depending on return_dict parameter
        """
        from src.schemas.game_schema import Game
        
        # Check if any filters are applied
        has_filters = any([
            steam_genres, tags, steam_categories, languages, platforms,
            min_positive_reviews, min_negative_reviews, max_price
        ])
        
        # Use batch processing with find_by_filters
        print(f"DEBUG: Filtering games with game_ids={len(game_ids) if game_ids else 'None'}, has_filters={has_filters}")
        games = self.games_repo.find_by_filters(
            game_ids=game_ids,
            genres=steam_genres,
            tags=tags,
            categories=steam_categories,
            languages=languages,
            platforms=platforms,
            min_price=None,
            max_price=max_price,
            min_positive=min_positive_reviews,
            min_negative=min_negative_reviews,
            stop_limit=limit if not return_dict else None,
            apply_content_filter=apply_content_filter and has_filters  # Only apply if filters exist
        )
        
        # Apply additional filters (date filters not in SQL)
        filtered_games = []
        filtered_dict = {}
        
        for game in games:
            # Apply date filters
            if min_release_date and game.release_date and game.release_date < min_release_date:
                continue
            if max_release_date and game.release_date and game.release_date > max_release_date:
                continue
            
            if return_dict:
                filtered_dict[game.game_id] = game
            else:
                filtered_games.append(game)
                if len(filtered_games) >= limit:
                    break
        
        return filtered_dict if return_dict else filtered_games
    