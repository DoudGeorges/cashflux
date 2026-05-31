"""MongoDB Atlas connection — single shared Motor client."""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        uri = os.environ["MONGODB_URI"]
        _client = AsyncIOMotorClient(uri)
    return _client


def get_db():
    db_name = os.getenv("MONGODB_DB_NAME", "brim_guardian")
    return get_client()[db_name]


async def close_client():
    global _client
    if _client:
        _client.close()
        _client = None
