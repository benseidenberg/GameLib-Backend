from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from src.recommender.recommender import get_game_clusters
import os
import httpx
import asyncio
import openai
import pandas as pd
from typing import Optional, List, Dict, Any
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json
from datasets import load_dataset

# Get Steam API key from environment variables (loaded in main.py)
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
if not STEAM_API_KEY:
    raise ValueError("STEAM_API_KEY environment variable is required")

# Get OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

# Initialize OpenAI client
openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

# Pydantic model for AI recommendation request
class AIRecommendationRequest(BaseModel):
    prompt: str

router = APIRouter()

# Global variable to cache the dataset
_steam_dataset = None
_dataset_loaded = False


async def get_steam_app_details(app_id: int):
    """
    Fetch detailed game information from Steam API with content filtering
    """
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&format=json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Steam API returns data with app_id as key
                app_data = data.get(str(app_id))
                if app_data and app_data.get('success') and 'data' in app_data:
                    game_data = app_data['data']
                    
                    # Check if content is appropriate
                    if not is_content_appropriate(game_data):
                        print(f"DEBUG: Filtered out inappropriate content for app_id: {app_id}")
                        return None
                    
                    # Extract relevant information
                    game_info = {
                        "app_id": app_id,
                        "title": game_data.get('name', 'Unknown Game'),
                        "description": game_data.get('short_description', ''),
                        "image": game_data.get('header_image', ''),
                        "price": game_data.get('price_overview', {}).get('final_formatted', 'Free'),
                        "genres": [genre.get('description', '') for genre in game_data.get('genres', [])],
                        "categories": [cat.get('description', '') for cat in game_data.get('categories', [])],
                        "developers": game_data.get('developers', []),
                        "publishers": game_data.get('publishers', []),
                        "release_date": game_data.get('release_date', {}).get('date', ''),
                        "steam_url": f"https://store.steampowered.com/app/{app_id}/"
                    }
                    
                    return game_info
                else:
                    return None
            else:
                return None
                
    except Exception as e:
        print(f"DEBUG: Error fetching Steam app details for {app_id}: {str(e)}")
        return None


def is_content_appropriate(game_data):
    """
    Check if game content is appropriate (filters out sexual/adult content)
    """
    try:
        # Check content descriptors for adult content
        content_descriptors = game_data.get('content_descriptors', {})
        if content_descriptors:
            descriptor_ids = content_descriptors.get('ids', [])
            descriptor_notes = content_descriptors.get('notes') or ''
            
            # Steam's adult content descriptor IDs
            adult_descriptor_ids = [3, 4]  # 3: Nudity/Sexual Content, 4: Adult Only Sexual Content
            
            if any(desc_id in adult_descriptor_ids for desc_id in descriptor_ids):
                return False
            
            # Check descriptor notes for sexual content keywords
            sexual_keywords = ['sexual', 'nudity', 'mature', 'adult', 'erotic', 'hentai']
            if any(keyword in descriptor_notes.lower() for keyword in sexual_keywords):
                return False
        
        # Check age ratings
        required_age = game_data.get('required_age', 0)
        if required_age >= 18:
            # Additional check for adult content categories
            categories = game_data.get('categories', [])
            for category in categories:
                cat_desc = (category.get('description') or '').lower()
                if 'adult only' in cat_desc or 'mature' in cat_desc:
                    return False
        
        # Check game name and description for inappropriate content
        game_name = (game_data.get('name') or '').lower()
        game_desc = (game_data.get('short_description') or '').lower()
        
        # List of inappropriate keywords
        inappropriate_keywords = [
            'hentai', 'porn', 'erotic', 'xxx', 'adult only', 'sexual',
            'nudity', 'strip', 'mature content', 'adult content'
        ]
        
        # Check if any inappropriate keywords are in the title or description
        for keyword in inappropriate_keywords:
            if keyword in game_name or keyword in game_desc:
                return False
        
        # Check genres for adult content
        genres = game_data.get('genres', [])
        for genre in genres:
            genre_desc = (genre.get('description') or '').lower()
            if any(keyword in genre_desc for keyword in ['adult', 'sexual', 'mature']):
                return False
        
        return True
        
    except Exception as e:
        print(f"DEBUG: Error in content filtering: {str(e)}")
        # If there's an error in filtering, err on the side of caution and allow the content
        return True


async def get_steam_app_details_basic(app_id: int):
    """
    Fetch basic game details (just title and app_id) for source games
    """
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&format=json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Steam API returns data with app_id as key
                app_data = data.get(str(app_id))
                if app_data and app_data.get('success') and 'data' in app_data:
                    game_data = app_data['data']
                    
                    return {
                        "app_id": app_id,
                        "title": game_data.get('name', 'Unknown Game')
                    }
            
            return None
            
    except Exception as e:
        print(f"DEBUG: Error fetching basic Steam app details for {app_id}: {str(e)}")
        return None


@router.get("/clusters/{steam_id}")
async def get_clusters(steam_id: int):
    """
    Get game recommendations/clusters for a user by Steam ID
    """
    print(f"DEBUG: Starting recommendations for steam_id: {steam_id}")
    try:
        print("DEBUG: About to call get_game_clusters")
        clusters = await get_game_clusters(steam_id)
        print(f"DEBUG: get_game_clusters returned: {type(clusters)} - {clusters}")
        if not clusters:
            raise HTTPException(status_code=404, detail="No recommendations found")
        return clusters
    except ValueError as e:
        print(f"DEBUG: ValueError occurred: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"DEBUG: Unexpected error occurred: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/steam/profile/{steam_id}")
async def get_steam_profile(steam_id: int):
    """
    Get Steam user's owned games and play data
    """
    try:
        url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json&include_appinfo=1&include_played_free_games=1"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                
                if "response" in data and "games" in data["response"]:
                    # Process the games data
                    games = data["response"]["games"]
                    
                    # Create a simplified version for the API response
                    processed_games = []
                    for game in games:
                        if game.get("playtime_forever", 0) > 0:  # Only include played games
                            processed_games.append({
                                "appid": game.get("appid"),
                                "name": game.get("name", "Unknown Game"),
                                "playtime_forever": game.get("playtime_forever", 0),
                                "playtime_2weeks": game.get("playtime_2weeks", 0),
                                "img_icon_url": game.get("img_icon_url", ""),
                                "rtime_last_played": game.get("rtime_last_played")
                            })
                    
                    return {
                        "steam_id": steam_id,
                        "total_games": len(processed_games),
                        "games": processed_games
                    }
                else:
                    return {"steam_id": steam_id, "total_games": 0, "games": []}
            else:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch Steam profile")
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Steam profile: {str(e)}")


@router.get("/steam/player/{steam_id}")
async def get_steam_player_summary(steam_id: int):
    """
    Get Steam user's profile information (name, avatar, etc.)
    """
    try:
        url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        params = {
            'key': STEAM_API_KEY,
            'steamids': str(steam_id)
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if "response" in data and "players" in data["response"] and len(data["response"]["players"]) > 0:
                player = data["response"]["players"][0]
                return {
                    "steamid": player.get("steamid"),
                    "personaname": player.get("personaname"),
                    "profileurl": player.get("profileurl"),
                    "avatar": player.get("avatar"),
                    "avatarmedium": player.get("avatarmedium"),
                    "avatarfull": player.get("avatarfull"),
                    "personastate": player.get("personastate"),
                    "communityvisibilitystate": player.get("communityvisibilitystate"),
                    "profilestate": player.get("profilestate"),
                    "lastlogoff": player.get("lastlogoff"),
                    "commentpermission": player.get("commentpermission")
                }
            else:
                raise HTTPException(status_code=404, detail="Player not found")
                
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Steam API error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Steam player summary: {str(e)}")


@router.get("/steam/game-details/{app_id}")
async def get_steam_game_details_endpoint(app_id: int):
    """
    Get detailed information about a specific Steam game
    """
    try:
        print(f"DEBUG: Fetching game details for app_id: {app_id}")
        game_info = await get_steam_app_details(app_id)
        
        if not game_info:
            print(f"DEBUG: No game info returned for app_id: {app_id}")
            raise HTTPException(status_code=404, detail=f"Game with app_id {app_id} not found or filtered out")
        
        print(f"DEBUG: Successfully fetched game details for: {game_info.get('title', 'Unknown')}")
        return game_info
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        print(f"DEBUG: Error in get_steam_game_details for app_id {app_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching game details: {str(e)}")


@router.get("/recommendations/test/{steam_id}")
async def test_recommendations(steam_id: int):
    """
    Test endpoint that returns 3 games with their details from Steam API
    Uses the provided Steam ID to get clusters, then returns first 3 games with full details
    """
    try:
        # Get game clusters for the provided Steam ID
        clusters_data = await get_game_clusters(steam_id)
        
        # Extract app IDs from clusters with their source games
        app_ids_with_source = []  # Will store tuples of (app_id, source_game_info)
        if clusters_data and isinstance(clusters_data, dict):
            # Handle the actual structure: clusters_data['response']['clusters']
            response_data = clusters_data.get('response', {})
            clusters_list = response_data.get('clusters', [])
            
            print(f"DEBUG: Found {len(clusters_list)} clusters")
            
            if clusters_list:
                # Sort clusters by relevance (recent playtime + total playtime + popularity)
                def cluster_score(cluster):
                    recent_playtime = cluster.get('playtime_2weeks', 0)
                    total_playtime = cluster.get('playtime_forever', 0)
                    popularity = cluster.get('similar_item_popularity_score', 0)
                    
                    # Weight recent activity higher, but also consider total time and popularity
                    score = (recent_playtime * 10) + (total_playtime * 0.1) + (popularity * 1000)
                    return score
                
                # Sort clusters by relevance score
                sorted_clusters = sorted(clusters_list, key=cluster_score, reverse=True)
                
                print(f"DEBUG: Top clusters by relevance:")
                for i, cluster in enumerate(sorted_clusters[:5]):
                    score = cluster_score(cluster)
                    recent = cluster.get('playtime_2weeks', 0)
                    total = cluster.get('playtime_forever', 0)
                    print(f"  Cluster {cluster.get('cluster_id')}: score={score:.1f}, recent={recent}min, total={total}min")
                
                # Take from the most relevant clusters
                for cluster in sorted_clusters[:5]:  # Check top 5 clusters
                    if len(app_ids_with_source) >= 3:
                        break
                        
                    cluster_id = cluster.get('cluster_id')
                    print(f"DEBUG: Processing cluster {cluster_id}")
                    
                    # Get played games and similar games
                    similar_apps = cluster.get('similar_items_appids', [])
                    played_apps = cluster.get('played_appids', [])
                    
                    print(f"DEBUG: Found {len(played_apps)} played apps and {len(similar_apps)} similar apps")
                    print(f"DEBUG: Played games in this cluster: {played_apps}")
                    print(f"DEBUG: Similar games available: {similar_apps[:8]}")  # Show first 8
                    
                    # For each cluster, we'll pick the most played game as the "source"
                    # and recommend similar games based on it
                    if played_apps:
                        # Choose the first played game as the primary source for this cluster
                        source_app_id = played_apps[0]  # Could be improved to pick by playtime
                        
                        # Fetch source game details
                        source_game_info = await get_steam_app_details_basic(source_app_id)
                        
                        if source_game_info:
                            # Add similar games with this source
                            for app_id in similar_apps[:8]:  # Try more games per cluster
                                if len(app_ids_with_source) < 3:
                                    # Check if we already have this app_id
                                    existing_app_ids = [item[0] for item in app_ids_with_source]
                                    if app_id not in existing_app_ids:
                                        app_ids_with_source.append((app_id, source_game_info))
                                        print(f"DEBUG: Added similar app_id: {app_id} based on {source_game_info['title']}")
                                else:
                                    break
        
        print(f"DEBUG: Final app_ids with sources: {[(item[0], item[1]['title']) for item in app_ids_with_source]}")
        
        # If we don't have enough games from clusters, add some popular games as fallback
        if len(app_ids_with_source) < 3:
            print(f"DEBUG: Only got {len(app_ids_with_source)} games from clusters, adding fallback games")
            fallback_games = [570, 440, 730]  # Dota 2, TF2, CS:GO
            
            for app_id in fallback_games:
                if len(app_ids_with_source) >= 3:
                    break
                # Add fallback games without a specific source
                existing_app_ids = [item[0] for item in app_ids_with_source]
                if app_id not in existing_app_ids:
                    app_ids_with_source.append((app_id, {"title": "Popular games", "app_id": None}))
        
        # Limit to 3 games
        app_ids_with_source = app_ids_with_source[:3]
        print(f"DEBUG: Final app_ids to fetch: {[item[0] for item in app_ids_with_source]}")
        
        # Fetch game details for each app ID with content filtering
        games_data = []
        
        for app_id, source_info in app_ids_with_source:
            game_info = await get_steam_app_details(app_id)
            if game_info:  # Only add if not filtered out
                # Add the source information to the game data
                game_info["based_on"] = {
                    "title": source_info["title"],
                    "app_id": source_info.get("app_id")
                }
                games_data.append(game_info)
        
        # If we don't have enough games after filtering, try to get more from additional clusters
        if len(games_data) < 3 and clusters_data:
            print(f"DEBUG: Only got {len(games_data)} appropriate games, fetching more...")
            response_data = clusters_data.get('response', {})
            clusters_list = response_data.get('clusters', [])
            
            # Sort clusters by relevance (reuse the scoring function)
            def cluster_score(cluster):
                recent_playtime = cluster.get('playtime_2weeks', 0)
                total_playtime = cluster.get('playtime_forever', 0)
                popularity = cluster.get('similar_item_popularity_score', 0)
                score = (recent_playtime * 10) + (total_playtime * 0.1) + (popularity * 1000)
                return score
            
            sorted_clusters = sorted(clusters_list, key=cluster_score, reverse=True)
            
            # Try more clusters if available
            for cluster in sorted_clusters[5:15]:  # Try clusters 6-15
                if len(games_data) >= 3:
                    break
                
                played_apps = cluster.get('played_appids', [])
                similar_apps = cluster.get('similar_items_appids', [])
                
                if played_apps:
                    source_app_id = played_apps[0]
                    source_game_info = await get_steam_app_details_basic(source_app_id)
                    
                    if source_game_info:
                        for app_id in similar_apps[:5]:  # Try more games per cluster
                            if len(games_data) >= 3:
                                break
                            
                            # Check if we already have this game
                            existing_app_ids = [game['app_id'] for game in games_data]
                            if app_id not in existing_app_ids:
                                game_info = await get_steam_app_details(app_id)
                                if game_info:
                                    game_info["based_on"] = {
                                        "title": source_game_info["title"],
                                        "app_id": source_game_info.get("app_id")
                                    }
                                    games_data.append(game_info)
        
        # Final fallback to safe, popular games if still not enough
        if len(games_data) < 3:
            safe_fallback_games = [570, 440, 730, 359550, 271590]  # Dota 2, TF2, CS:GO, Rainbow Six, GTA V
            for app_id in safe_fallback_games:
                if len(games_data) >= 3:
                    break
                
                existing_app_ids = [game['app_id'] for game in games_data]
                if app_id not in existing_app_ids:  # Avoid duplicates
                    game_info = await get_steam_app_details(app_id)
                    if game_info:
                        game_info["based_on"] = {
                            "title": "Popular games",
                            "app_id": None
                        }
                        games_data.append(game_info)
        
        return {
            "message": "Test recommendations successful",
            "steam_id": steam_id,
            "total_games": len(games_data),
            "games": games_data
        }
        
    except Exception as e:
        print(f"DEBUG: Error in test_recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting test recommendations: {str(e)}")


async def load_steam_dataset():
    """
    Load the Steam games dataset from Hugging Face
    """
    global _steam_dataset, _dataset_loaded
    
    if _dataset_loaded:
        return _steam_dataset
    
    try:
        print("DEBUG: Loading Steam games dataset from Hugging Face...")
        # Load the Steam games dataset
        dataset = load_dataset("FronkonGames/steam-games-dataset", split="train")
        
        # Convert to pandas DataFrame for easier manipulation
        _steam_dataset = pd.DataFrame(dataset)
        
        # Clean and prepare the dataset
        # Remove games without descriptions or names
        _steam_dataset = _steam_dataset.dropna(subset=['description', 'name'])
        
        # Create a combined text field for similarity matching
        _steam_dataset['combined_text'] = (
            _steam_dataset['name'].astype(str) + " " + 
            _steam_dataset['description'].astype(str) + " " + 
            _steam_dataset.get('genres', '').astype(str) + " " + 
            _steam_dataset.get('tags', '').astype(str)
        )
        
        _dataset_loaded = True
        print(f"DEBUG: Successfully loaded {len(_steam_dataset)} games from dataset")
        
        return _steam_dataset
        
    except Exception as e:
        print(f"DEBUG: Error loading Steam dataset: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading game dataset: {str(e)}")


async def analyze_prompt_with_ai(prompt: str) -> Dict[str, Any]:
    """
    Use OpenAI to analyze the user's prompt and extract preferences
    """
    try:
        system_prompt = """
        You are a gaming assistant that analyzes user prompts to understand their game preferences.
        
        Extract the following information from the user's prompt:
        1. Game genres they're interested in
        2. Gameplay elements they want (multiplayer, story-driven, action, puzzle, etc.)
        3. Setting/theme preferences (fantasy, sci-fi, historical, modern, etc.)
        4. Price preferences (if mentioned - free, under $X, budget, premium, etc.)
        5. Platform preferences (if mentioned)
        6. Similar games they mention
        7. Mood/feeling they want (relaxing, challenging, competitive, etc.)
        
        Return your analysis as JSON with these keys:
        - genres: list of genres
        - gameplay_elements: list of gameplay types
        - themes: list of themes/settings
        - price_preference: string describing budget constraints
        - similar_games: list of mentioned games
        - mood: list of desired moods/feelings
        - summary: brief summary of what they're looking for
        
        Be concise and only extract information that's clearly mentioned or strongly implied.
        """
        
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        # Parse the JSON response
        analysis_text = response.choices[0].message.content
        
        # Try to extract JSON from the response
        try:
            # Look for JSON in the response
            json_start = analysis_text.find('{')
            json_end = analysis_text.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                analysis = json.loads(analysis_text[json_start:json_end])
            else:
                # Fallback: create a basic structure
                analysis = {
                    "genres": [],
                    "gameplay_elements": [],
                    "themes": [],
                    "price_preference": "",
                    "similar_games": [],
                    "mood": [],
                    "summary": analysis_text
                }
        except json.JSONDecodeError:
            # If JSON parsing fails, create a fallback analysis
            analysis = {
                "genres": [],
                "gameplay_elements": [],
                "themes": [],
                "price_preference": "",
                "similar_games": [],
                "mood": [],
                "summary": analysis_text
            }
        
        return analysis
        
    except Exception as e:
        print(f"DEBUG: Error in AI analysis: {str(e)}")
        # Return a basic fallback analysis
        return {
            "genres": [],
            "gameplay_elements": [],
            "themes": [],
            "price_preference": "",
            "similar_games": [],
            "mood": [],
            "summary": prompt
        }


def extract_price_preference(prompt: str, ai_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract price preferences from the prompt and AI analysis
    """
    price_info = {
        "max_price": None,
        "free_only": False,
        "budget_conscious": False,
        "preference_text": ""
    }
    
    prompt_lower = prompt.lower()
    
    # Check for free games preference
    if any(keyword in prompt_lower for keyword in ['free', 'f2p', 'free to play', 'no cost']):
        price_info["free_only"] = True
        price_info["preference_text"] = "free games"
    
    # Check for budget mentions
    budget_keywords = ['cheap', 'budget', 'affordable', 'inexpensive', 'low cost']
    if any(keyword in prompt_lower for keyword in budget_keywords):
        price_info["budget_conscious"] = True
        price_info["preference_text"] = "budget-friendly games"
    
    # Look for specific price mentions ($X, under $X, etc.)
    price_patterns = [
        r'under \$(\d+)',
        r'less than \$(\d+)',
        r'below \$(\d+)',
        r'maximum \$(\d+)',
        r'max \$(\d+)',
        r'\$(\d+) or less',
        r'budget of \$(\d+)'
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, prompt_lower)
        if match:
            price_info["max_price"] = int(match.group(1))
            price_info["preference_text"] = f"under ${price_info['max_price']}"
            break
    
    # Also check AI analysis for price preferences
    ai_price = ai_analysis.get("price_preference", "")
    if ai_price and not price_info["preference_text"]:
        price_info["preference_text"] = ai_price
    
    return price_info


async def find_similar_games(ai_analysis: Dict[str, Any], price_info: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find games similar to the user's preferences using the dataset
    """
    try:
        dataset = await load_steam_dataset()
        
        if dataset is None or dataset.empty:
            return []
        
        # Create search query from AI analysis
        search_terms = []
        
        # Add genres
        search_terms.extend(ai_analysis.get("genres", []))
        
        # Add gameplay elements
        search_terms.extend(ai_analysis.get("gameplay_elements", []))
        
        # Add themes
        search_terms.extend(ai_analysis.get("themes", []))
        
        # Add mood descriptors
        search_terms.extend(ai_analysis.get("mood", []))
        
        # Create the search query
        search_query = " ".join(search_terms)
        
        if not search_query.strip():
            # Fallback to using the summary if no specific terms found
            search_query = ai_analysis.get("summary", "")
        
        print(f"DEBUG: Search query: {search_query}")
        
        # Use TF-IDF to find similar games
        if 'combined_text' not in dataset.columns:
            print("DEBUG: combined_text column missing, recreating...")
            dataset['combined_text'] = (
                dataset['name'].astype(str) + " " + 
                dataset['description'].astype(str)
            )
        
        # Create TF-IDF vectors
        vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=2
        )
        
        # Fit on the game descriptions and transform
        tfidf_matrix = vectorizer.fit_transform(dataset['combined_text'].fillna(''))
        
        # Transform the search query
        query_vector = vectorizer.transform([search_query])
        
        # Calculate cosine similarity
        similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()
        
        # Get top similar games
        top_indices = similarities.argsort()[-limit*3:][::-1]  # Get more than needed to allow for filtering
        
        # Filter and prepare results
        results = []
        for idx in top_indices:
            if len(results) >= limit:
                break
                
            game = dataset.iloc[idx]
            similarity_score = similarities[idx]
            
            # Skip if similarity is too low
            if similarity_score < 0.1:
                continue
            
            # Extract game information
            game_info = {
                "name": str(game.get('name', 'Unknown')),
                "description": str(game.get('description', '')),
                "genres": str(game.get('genres', '')),
                "tags": str(game.get('tags', '')),
                "similarity_score": float(similarity_score),
                "price": str(game.get('price', 'N/A')),
                "steam_appid": game.get('steam_appid', None)
            }
            
            # Apply price filtering if specified
            if price_info.get("free_only"):
                price_str = str(game.get('price', '')).lower()
                if 'free' not in price_str and '0' not in price_str:
                    continue
            
            if price_info.get("max_price"):
                price_str = str(game.get('price', ''))
                # Try to extract numeric price
                price_match = re.search(r'\$?(\d+\.?\d*)', price_str)
                if price_match:
                    try:
                        price_value = float(price_match.group(1))
                        if price_value > price_info["max_price"]:
                            continue
                    except ValueError:
                        pass
            
            results.append(game_info)
        
        print(f"DEBUG: Found {len(results)} similar games")
        return results
        
    except Exception as e:
        print(f"DEBUG: Error finding similar games: {str(e)}")
        return []


@router.post("/recommendations/ai")
async def get_ai_recommendations(request: AIRecommendationRequest):
    """
    Get AI-powered game recommendations based on a text prompt.
    Uses OpenAI to analyze the prompt and the Steam games dataset to find similar games.
    """
    try:
        prompt = request.prompt.strip()
        
        # Validate prompt
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        
        print(f"DEBUG: AI recommendations requested with prompt: {prompt[:100]}...")
        
        # Step 1: Analyze the prompt with OpenAI
        ai_analysis = await analyze_prompt_with_ai(prompt)
        print(f"DEBUG: AI Analysis: {ai_analysis}")
        
        # Step 2: Extract price preferences
        price_info = extract_price_preference(prompt, ai_analysis)
        print(f"DEBUG: Price preferences: {price_info}")
        
        # Step 3: Find similar games using the dataset
        similar_games = await find_similar_games(ai_analysis, price_info, limit=5)
        
        # Step 4: Enhance results with Steam API data if possible
        enhanced_games = []
        for game in similar_games:
            enhanced_game = game.copy()
            
            # Ensure steam_appid is always included in the response
            enhanced_game["app_id"] = game.get('steam_appid', None)
            
            # Try to get additional info from Steam API if we have an app_id
            steam_appid = game.get('steam_appid')
            if steam_appid and str(steam_appid).isdigit():
                try:
                    steam_info = await get_steam_app_details(int(steam_appid))
                    if steam_info:
                        # Merge Steam API data with dataset data
                        enhanced_game.update({
                            "steam_title": steam_info.get("title"),
                            "steam_description": steam_info.get("description"),
                            "steam_image": steam_info.get("image"),
                            "steam_price": steam_info.get("price"),
                            "steam_genres": steam_info.get("genres", []),
                            "steam_url": steam_info.get("steam_url"),
                            "developers": steam_info.get("developers", []),
                            "publishers": steam_info.get("publishers", []),
                            "app_id": steam_appid  # Ensure app_id is set from Steam API too
                        })
                except Exception as e:
                    print(f"DEBUG: Error fetching Steam data for {steam_appid}: {str(e)}")
            
            enhanced_games.append(enhanced_game)
        
        # Step 5: Generate explanation using AI
        explanation = await generate_recommendation_explanation(prompt, ai_analysis, enhanced_games)
        
        return {
            "message": "AI recommendations generated successfully",
            "prompt": prompt,
            "analysis": {
                "preferences": ai_analysis,
                "price_constraints": price_info
            },
            "explanation": explanation,
            "total_games": len(enhanced_games),
            "recommendations": enhanced_games
        }
        
    except Exception as e:
        print(f"DEBUG: Error in get_ai_recommendations: {str(e)}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error getting AI recommendations: {str(e)}")


async def generate_recommendation_explanation(prompt: str, analysis: Dict[str, Any], games: List[Dict[str, Any]]) -> str:
    """
    Generate an explanation for why these games were recommended
    """
    try:
        game_names = [game.get('name', game.get('steam_title', 'Unknown')) for game in games[:3]]
        
        explanation_prompt = f"""
        Based on the user's request: "{prompt}"
        
        And the analysis that they want: {analysis.get('summary', '')}
        
        I recommended these games: {', '.join(game_names)}
        
        Write a brief, friendly explanation (2-3 sentences) of why these games are perfect for what they're looking for.
        Focus ONLY on the positive aspects and features that match their preferences.
        Do not mention what the games lack or don't have - only highlight what makes them great matches.
        Use enthusiastic, positive language about what these games DO offer.
        """
        
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an enthusiastic gaming assistant. Provide brief, friendly explanations for game recommendations. Focus ONLY on positive aspects - never mention what games lack or don't have. Highlight what makes each recommendation exciting and perfect for the user's needs."},
                {"role": "user", "content": explanation_prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"DEBUG: Error generating explanation: {str(e)}")
        return f"I found these games based on your interest in {analysis.get('summary', 'games matching your description')}."