"""Entry point — run with: uvicorn main:app --reload"""
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from db.connection import close_client
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(title="Brim Guardian", description="SMB Expense Intelligence Agent", version="0.1.0", lifespan=lifespan)
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import os, uvicorn
    uvicorn.run("main:app", host=os.getenv("API_HOST", "0.0.0.0"), port=int(os.getenv("API_PORT", 8000)), reload=True)
