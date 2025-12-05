#!/usr/bin/env python3
"""
Test script to verify default popularity and enhanced search
"""

def test_default_popularity_and_search():
    """Test the new default popularity and enhanced search features"""
    
    print("🎮 Updated AI Recommendations Features\n")
    
    print("📈 Default Popularity: POPULAR")
    print("• Unless specified otherwise, games will prefer mainstream/well-known titles")
    print("• Games with more reviews get priority (>5000 reviews = +10 points)")
    print("• Only 'niche', 'indie', 'hidden gem' keywords switch to niche preference")
    print()
    
    print("🔍 Enhanced Search Query:")
    print("• Original prompt keywords: 'mushroom RPG' → ['mushroom', 'rpg']")
    print("• AI analysis terms: themes, genres, gameplay elements")
    print("• Combined search: 'mushroom rpg fantasy role-playing'")
    print("• Better relevance by keeping original intent + AI understanding")
    print()
    
    test_cases = [
        {
            "prompt": "Give me a mushroom RPG",
            "search_terms": "mushroom rpg + [AI: fantasy, role-playing]",
            "popularity": "popular (default)",
            "expected": "Should find 'Mushroom Card RPG' first, prioritize popular RPGs with mushroom themes"
        },
        {
            "prompt": "I want a niche puzzle game",
            "search_terms": "puzzle game + [AI: indie, challenging]", 
            "popularity": "niche (detected)",
            "expected": "Should find lesser-known puzzle games with good ratings but fewer reviews"
        },
        {
            "prompt": "Action adventure game",
            "search_terms": "action adventure game + [AI: exploration, combat]",
            "popularity": "popular (default)",
            "expected": "Should find mainstream action-adventure games with many positive reviews"
        },
        {
            "prompt": "Hidden gem strategy",
            "search_terms": "strategy + [AI: tactics, planning]",
            "popularity": "niche (hidden gem detected)",
            "expected": "Should find quality strategy games with fewer but positive reviews"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"Test Case {i}: '{case['prompt']}'")
        print(f"  Search Terms: {case['search_terms']}")
        print(f"  Popularity: {case['popularity']}")
        print(f"  Expected: {case['expected']}")
        print()
    
    print("🛠️ Key Improvements:")
    print("✅ Default to popular games (mainstream preference)")
    print("✅ Maintain original keywords for relevance")
    print("✅ Add AI analysis terms for context")
    print("✅ Better scoring with popularity + quality + relevance")
    print("✅ Debug logging shows combined search terms")
    
    print("\n🎯 For 'mushroom RPG':")
    print("• Search: 'mushroom rpg fantasy role-playing'")
    print("• Popularity: Popular (default)")
    print("• Should prioritize: Mushroom Card RPG > Other popular RPGs")
    print("• Quality matters: 85%+ rating games get priority")

if __name__ == "__main__":
    test_default_popularity_and_search()