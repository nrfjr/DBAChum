import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient


load_dotenv()

MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://localhost:27017"
)

MONGODB_DATABASE = os.getenv(
    "MONGODB_DATABASE",
    "dbachum"
)


app = FastAPI(
    title="DBAChum API",
    version="2.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",

        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mongo_client = AsyncMongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=3000
)

db = mongo_client[MONGODB_DATABASE]


@app.get("/")
async def root():
    return {
        "name": "DBAChum API",
        "status": "running"
    }


@app.get("/api/health")
async def health():
    try:
        await mongo_client.admin.command("ping")

        return {
            "api": "healthy",
            "mongodb": "healthy"
        }

    except Exception as exc:
        return {
            "api": "healthy",
            "mongodb": "unhealthy",
            "error": str(exc)
        }