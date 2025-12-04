from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import users
from src.api.auth import router as auth_router
from src.api.recommendations import router as recommendations_router
from src.api.collaborative_filtering import router as collaborative_filtering_router
from src.services.ai_chatbot import initialize_ai_system

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
    """Initialize AI recommendation system at server startup for optimal performance"""
    print("="*60)
    print("🚀 Starting GameLib Backend Server...")
    print("="*60)
    try:
        await initialize_ai_system()
        print("="*60)
        print("✅ Server ready! AI recommendations fully optimized.")
        print("="*60)
    except Exception as e:
        print("="*60)
        print(f"⚠️  Warning: AI system initialization failed: {e}")
        print("⚠️  Server will start but AI recommendations may be slower.")
        print("="*60)

app.include_router(auth_router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(recommendations_router, prefix="/api")
app.include_router(collaborative_filtering_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to the GameLib Backend API!"}