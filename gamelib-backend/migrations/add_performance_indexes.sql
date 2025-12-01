-- Performance optimization indexes for games_db table
-- These indexes significantly improve query performance for array overlap and numeric filters

-- GIN indexes for array columns (genres, tags, categories, languages)
-- GIN (Generalized Inverted Index) is optimal for array overlap operations
CREATE INDEX IF NOT EXISTS idx_games_genres_gin ON games_db USING GIN (genres);
CREATE INDEX IF NOT EXISTS idx_games_tags_gin ON games_db USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_games_categories_gin ON games_db USING GIN (categories);
CREATE INDEX IF NOT EXISTS idx_games_languages_gin ON games_db USING GIN (languages);

-- B-tree indexes for numeric columns used in range queries
CREATE INDEX IF NOT EXISTS idx_games_positive ON games_db (positive);
CREATE INDEX IF NOT EXISTS idx_games_negative ON games_db (negative);
CREATE INDEX IF NOT EXISTS idx_games_price ON games_db (price);

-- Composite index for common filtering pattern (positive reviews + price)
CREATE INDEX IF NOT EXISTS idx_games_positive_price ON games_db (positive DESC, price);

-- Index on release_date for date range filtering
CREATE INDEX IF NOT EXISTS idx_games_release_date ON games_db (release_date);

-- Analyze table to update statistics after creating indexes
ANALYZE games_db;
