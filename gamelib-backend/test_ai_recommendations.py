#!/usr/bin/env python3
"""
Test script for AI recommendations functionality
This script tests the AI recommendations feature without running the full server
"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

async def test_ai_components():
    """
    Test individual components of the AI recommendations system
    """
    print("Testing AI Recommendations Components...")
    
    try:
        # Import the functions (this will test if all imports work)
        from src.api.recommendations import (
            load_steam_dataset, 
            analyze_prompt_with_ai, 
            extract_price_preference,
            find_similar_games
        )
        print("✓ All imports successful")
        
        # Test dataset loading
        print("\n1. Testing dataset loading...")
        try:
            dataset = await load_steam_dataset()
            if dataset is not None and len(dataset) > 0:
                print(f"✓ Dataset loaded successfully with {len(dataset)} games")
                print(f"✓ Dataset columns: {list(dataset.columns)}")
            else:
                print("✗ Dataset is empty or None")
        except Exception as e:
            print(f"✗ Dataset loading failed: {str(e)}")
        
        # Test AI analysis (only if OpenAI key is available)
        print("\n2. Testing AI prompt analysis...")
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                test_prompt = "I want a relaxing puzzle game that's free or under $10"
                analysis = await analyze_prompt_with_ai(test_prompt)
                print(f"✓ AI analysis successful: {analysis}")
                
                # Test price extraction
                price_info = extract_price_preference(test_prompt, analysis)
                print(f"✓ Price extraction successful: {price_info}")
                
                # Test game finding
                games = await find_similar_games(analysis, price_info, limit=3)
                print(f"✓ Found {len(games)} similar games")
                for game in games[:2]:  # Show first 2 games
                    print(f"  - {game.get('name', 'Unknown')}: {game.get('description', '')[:100]}...")
                    
            except Exception as e:
                print(f"✗ AI analysis failed: {str(e)}")
        else:
            print("⚠ OPENAI_API_KEY not found, skipping AI tests")
        
        print("\n3. Testing price preference extraction...")
        try:
            test_prompts = [
                "I want free games",
                "Something under $20",
                "Budget games please",
                "I'm looking for premium AAA titles"
            ]
            
            for prompt in test_prompts:
                mock_analysis = {"summary": prompt, "price_preference": ""}
                price_info = extract_price_preference(prompt, mock_analysis)
                print(f"✓ '{prompt}' -> {price_info}")
                
        except Exception as e:
            print(f"✗ Price extraction test failed: {str(e)}")
        
    except ImportError as e:
        print(f"✗ Import error: {str(e)}")
        print("Make sure all required packages are installed:")
        print("  pip install openai datasets pandas scikit-learn numpy")
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_ai_components())