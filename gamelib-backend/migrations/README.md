# Database Migrations

This folder contains SQL migration scripts for the GameLib Backend database.

## Available Migrations

### add_performance_indexes.sql
Adds performance optimization indexes to the `games_db` table to significantly improve query performance for collaborative filtering and game search features.

**Indexes added:**
- GIN indexes on array columns: `genres`, `tags`, `categories`, `languages`
- B-tree indexes on numeric columns: `positive`, `negative`, `price`
- Composite index on `(positive DESC, price)`
- B-tree index on `release_date`

**Impact:** These indexes reduce query execution time from timeout (>30s) to milliseconds for array overlap operations.

## How to Apply Migrations

### Option 1: Using Supabase Dashboard (Recommended)
1. Log in to your [Supabase Dashboard](https://app.supabase.com)
2. Navigate to your project
3. Go to **SQL Editor**
4. Copy the contents of the migration file (e.g., `add_performance_indexes.sql`)
5. Paste into the SQL Editor
6. Click **Run** to execute

### Option 2: Using Supabase CLI
```bash
# If you have Supabase CLI installed
supabase db push

# Or execute a specific migration
supabase db execute --file migrations/add_performance_indexes.sql
```

### Option 3: Using PostgreSQL Client
```bash
# If connecting directly to PostgreSQL
psql -h your-db-host -U postgres -d postgres -f migrations/add_performance_indexes.sql
```

## Verifying Indexes

After applying the migration, verify the indexes were created:

```sql
-- Check indexes on games_db table
SELECT 
    indexname, 
    indexdef 
FROM 
    pg_indexes 
WHERE 
    tablename = 'games_db' 
ORDER BY 
    indexname;
```

## Performance Impact

### Before Indexes
- Query with array overlap filters: **TIMEOUT** (>30s)
- Collaborative filtering: Failed with "statement timeout" error

### After Indexes
- Query with array overlap filters: **< 100ms**
- Collaborative filtering: Successfully returns results in under 1 second

## Notes

- All indexes use `IF NOT EXISTS` to prevent errors on re-application
- The `ANALYZE` command updates table statistics for the query planner
- GIN indexes are specifically designed for array operations and full-text search
- These indexes will increase storage space but drastically improve query performance
