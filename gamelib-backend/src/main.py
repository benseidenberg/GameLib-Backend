from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import users
from src.api.auth import router as auth_router
from src.api.recommendations import router as recommendations_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api")
app.include_router(users.router)
app.include_router(recommendations_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to the GameLib Backend API!"}