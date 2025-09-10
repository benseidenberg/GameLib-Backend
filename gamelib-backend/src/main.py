from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import users

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the GameLib Backend API!"}