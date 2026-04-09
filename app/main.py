from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.session import async_session_maker, engine
from app.models.base import Base
from app.routers.auth import router as auth_router
from app.routers.content import router as content_router


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        await init_db(session, app.state.redis)
    yield
    await app.state.redis.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(content_router)


@app.get("/")
async def root():
    return {"message": "Backend test task is running"}
