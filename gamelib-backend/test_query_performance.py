"""
Query Performance Testing Script
Tests different query configurations to measure performance
"""
from src.db.repositories.games_db import GamesRepository
import json


def print_results(test_name: str, result: dict):
    """Pretty print test results"""
    print(f"\n{'=' * 60}")
    print(f"TEST: {test_name}")
    print(f"{'=' * 60}")
    
    if result.get("success"):
        print(f"✓ Success")
        print(f"  Results: {result['results_count']} games")
        print(f"  Limit: {result['limit']}")
        if result.get('use_range'):
            print(f"  Range: {result['start_index']} to {result['start_index'] + result['limit'] - 1}")
        if result.get('tags_filter'):
            print(f"  Tags Filter: {result['tags_filter']}")
        
        timing = result['timing']
        print(f"\n  Timing:")
        print(f"    Query Build: {timing['query_build_ms']} ms")
        print(f"    Execute:     {timing['execute_ms']} ms")
        print(f"    Convert:     {timing['convert_ms']} ms")
        print(f"    TOTAL:       {timing['total_ms']} ms")
        
        if result.get('sample_games'):
            print(f"\n  Sample Games:")
            for game in result['sample_games']:
                print(f"    - {game['name']} (ID: {game['game_id']}, +{game['positive']})")
    else:
        print(f"✗ Failed: {result.get('error', 'Unknown error')}")
    
    print(f"{'=' * 60}\n")


def run_tests():
    """Run various performance tests"""
    
    print("\n" + "=" * 60)
    print("QUERY PERFORMANCE TESTING")
    print("=" * 60)
    
    # Warmup query - first query is always slower (cold start, connection setup, cache warming)
    print("\n[WARMUP] Running warmup query to establish connection and warm cache...")
    warmup = GamesRepository.test_query_limit(limit=10, order_by='positive', use_range=False)
    print(f"  Warmup complete: {warmup['timing']['total_ms']} ms (this is expected to be slower)")
    
    # Test 1: Small limit with no filters (RERUN after warmup)
    print("\n[1/8] Testing: Small limit (10 games), no filters, using limit()")
    result1 = GamesRepository.test_query_limit(
        limit=10,
        order_by='positive',
        use_range=False
    )
    print_results("Small Limit - No Filters", result1)
    
    # Test 2: Medium limit with no filters
    print("\n[2/8] Testing: Medium limit (200 games), no filters, using limit()")
    result2 = GamesRepository.test_query_limit(
        limit=200,
        order_by='positive',
        use_range=False
    )
    print_results("Medium Limit - No Filters", result2)
    
    # Test 3: Large limit with no filters
    print("\n[3/8] Testing: Large limit (500 games), no filters, using limit()")
    result3 = GamesRepository.test_query_limit(
        limit=500,
        order_by='positive',
        use_range=False
    )
    print_results("Large Limit - No Filters", result3)
    
    # Test 4: Small limit with range
    print("\n[4/8] Testing: Small limit (50 games), no filters, using range()")
    result4 = GamesRepository.test_query_limit(
        limit=50,
        order_by='positive',
        use_range=True,
        start_index=0
    )
    print_results("Small Limit with Range - No Filters", result4)
    
    # Test 5: Range with offset
    print("\n[5/8] Testing: Range with offset (50 games starting at 100)")
    result5 = GamesRepository.test_query_limit(
        limit=50,
        order_by='positive',
        use_range=True,
        start_index=100
    )
    print_results("Range with Offset - No Filters", result5)
    
    # Test 6: Small limit with tag filter (RPG)
    print("\n[6/8] Testing: Small limit (50 games) WITH tag filter (RPG)")
    result6 = GamesRepository.test_query_limit(
        limit=50,
        order_by='positive',
        tags=['RPG'],
        use_range=False
    )
    print_results("Small Limit - RPG Tag Filter", result6)
    
    # Test 7: Medium limit with tag filter (RPG)
    print("\n[7/8] Testing: Medium limit (200 games) WITH tag filter (RPG)")
    result7 = GamesRepository.test_query_limit(
        limit=200,
        order_by='positive',
        tags=['RPG'],
        use_range=False
    )
    print_results("Medium Limit - RPG Tag Filter", result7)
    
    # Test 8: Multiple tags filter
    print("\n[8/8] Testing: Small limit (50 games) WITH multiple tag filters (RPG, Adventure)")
    result8 = GamesRepository.test_query_limit(
        limit=50,
        order_by='positive',
        tags=['RPG', 'Adventure'],
        use_range=False
    )
    print_results("Small Limit - Multiple Tag Filters", result8)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    print("\nNOTE: First query was slow due to cold start:")
    print(f"  - Warmup query: {warmup['timing']['total_ms']} ms")
    print(f"  - Includes: connection setup, cache warming, initial query planning")
    print(f"  - Subsequent queries benefit from warm cache and open connection\n")
    
    results = [
        ("Small Limit - No Filters", result1),
        ("Medium Limit - No Filters", result2),
        ("Large Limit - No Filters", result3),
        ("Small Limit with Range - No Filters", result4),
        ("Range with Offset - No Filters", result5),
        ("Small Limit - RPG Tag Filter", result6),
        ("Medium Limit - RPG Tag Filter", result7),
        ("Small Limit - Multiple Tag Filters", result8)
    ]
    
    print(f"\n{'Test Name':<45} {'Time (ms)':<12} {'Results':<10} {'Status'}")
    print("-" * 80)
    
    for name, result in results:
        if result.get("success"):
            time_ms = result['timing']['total_ms']
            count = result['results_count']
            status = "✓"
        else:
            time_ms = "N/A"
            count = "N/A"
            status = "✗"
        
        print(f"{name:<45} {str(time_ms):<12} {str(count):<10} {status}")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    if result6.get("success"):
        tag_time = result6['timing']['total_ms']
        if tag_time > 1000:
            print("⚠️  Array overlap queries (tags) are SLOW (>1s)")
            print("   → Recommendation: Use Python filtering strategy for tag queries")
            print("   → Consider adding GIN indexes on tag columns")
        else:
            print("✓ Array overlap queries are performing well")
    
    if result3.get("success"):
        large_time = result3['timing']['total_ms']
        if large_time > 2000:
            print("⚠️  Large limit queries (500+) are SLOW (>2s)")
            print("   → Recommendation: Keep batch sizes under 200")
        else:
            print("✓ Large limit queries are performing acceptably")
    
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    try:
        run_tests()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nFatal error during testing: {e}")
        import traceback
        traceback.print_exc()
