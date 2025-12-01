from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import users
from src.api.auth import router as auth_router
from src.api.recommendations import router as recommendations_router, load_steam_dataset
from src.api.c_filtering import router as c_filtering_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Load dataset on server startup for faster AI recommendations"""
    print("🚀 Starting server initialization...")
    print("📦 Loading Steam dataset for AI recommendations...")
    try:
        await load_steam_dataset()
        print("✅ Dataset loaded successfully! AI recommendations ready.")
    except Exception as e:
        print(f"❌ Warning: Failed to load dataset on startup: {e}")
        print("⚠️  AI recommendations may be slower on first request.")

app.include_router(auth_router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(recommendations_router, prefix="/api")
app.include_router(c_filtering_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to the GameLib Backend API!"}