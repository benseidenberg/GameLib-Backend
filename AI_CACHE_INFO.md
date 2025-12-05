# AI TF-IDF Cache System

## Overview
The AI recommendation system now caches TF-IDF vectorization data to significantly speed up server startup times.

## How It Works

### First Startup (No Cache)
When you start the server for the first time, it will:
1. Download the Steam games dataset from Hugging Face
2. Process the data and create combined text fields
3. Calculate TF-IDF vectors (takes 10-30 seconds)
4. Save three pickle files in `src/services/`:
   - `tfidf_vectorizer.pkl` - The trained vectorizer
   - `tfidf_matrix.pkl` - The computed TF-IDF matrix
   - `steam_dataset.pkl` - The processed dataset

### Subsequent Startups (With Cache)
On future startups, the server will:
1. Detect the cached pickle files
2. Load them directly from disk (takes ~1-2 seconds)
3. Skip the expensive calculation step

## Commands

### Normal Startup (Uses Cache)
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```
- If cache files exist, loads them instantly
- If no cache files exist, calculates and saves them

### Force Recalculation

**Windows PowerShell:**
```powershell
$env:RECALCULATE_AI="true"; uvicorn src.main:app --host 0.0.0.0 --port 8000

$env:RECALCULATE_AI="false"; uvicorn src.main:app --host 0.0.0.0 --port 8000

```

**Windows CMD:**
```cmd
set RECALCULATE_AI=true && uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Linux/Mac:**
```bash
RECALCULATE_AI=true uvicorn src.main:app --host 0.0.0.0 --port 8000
```

- Forces recalculation even if cache files exist
- Useful when:
  - Dataset has been updated
  - You want to change TF-IDF parameters
  - Cache files may be corrupted

### Alternative: Add to .env file
Add this line to your `.env` file:
```
RECALCULATE_AI=true
```
Then start normally. Remember to remove or set to `false` after recalculation!

## Cache File Locations
All cache files are stored in:
```
GameLib-Backend/gamelib-backend/src/services/
├── tfidf_vectorizer.pkl
├── tfidf_matrix.pkl
└── steam_dataset.pkl
```

## Benefits
- **First startup**: ~10-30 seconds (with calculation + save)
- **Cached startup**: ~1-2 seconds (instant load)
- **Speedup**: ~10-15x faster server startup

## Troubleshooting

### Cache files not loading
If you see "Error loading cached files", the system will automatically fall back to recalculation.

### Force clean recalculation
1. Delete the pickle files manually:
   ```bash
   rm src/services/tfidf_*.pkl src/services/steam_dataset.pkl
   ```
2. Restart the server normally

### Update cache after code changes
If you modify TF-IDF parameters in `ai_chatbot.py`, use:

**PowerShell:**
```powershell
$env:RECALCULATE_AI="true"; uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Linux/Mac:**
```bash
RECALCULATE_AI=true uvicorn src.main:app --host 0.0.0.0 --port 8000
```
