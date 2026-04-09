from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User


settings = get_settings()
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_token(payload: dict[str, Any], expires_delta: timedelta) -> str:
    data = payload.copy()
    expire = _utcnow() + expires_delta
    data.update({"exp": expire, "iat": _utcnow(), "jti": str(uuid4())})
    return jwt.encode(data, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def ttl_from_exp(exp: int | float | datetime) -> int:
    if isinstance(exp, datetime):
        exp_dt = exp
    else:
        exp_dt = datetime.fromtimestamp(float(exp), tz=timezone.utc)
    ttl = int((exp_dt - _utcnow()).total_seconds())
    return max(ttl, 1)


async def redis_client_from_request(request: Request) -> Redis:
    redis = request.app.state.redis
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis is not available")
    return redis


redis_client = redis_client_from_request


async def store_whitelist(redis: Redis, token_data: dict[str, Any]) -> None:
    await redis.setex(f"whitelist:{token_data['jti']}", ttl_from_exp(token_data["exp"]), token_data["sub"])


async def blacklist_token(redis: Redis, token_data: dict[str, Any]) -> None:
    await redis.setex(f"blacklist:{token_data['jti']}", ttl_from_exp(token_data["exp"]), token_data["sub"])


async def is_token_active(redis: Redis, token_data: dict[str, Any]) -> bool:
    if await redis.exists(f"blacklist:{token_data['jti']}"):
        return False
    return bool(await redis.exists(f"whitelist:{token_data['jti']}") )


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_token_pair(user: User) -> tuple[str, str]:
    access_token = create_token(
        {"sub": user.username, "role": user.role.value, "typ": "access"},
        timedelta(minutes=settings.access_token_expire_minutes),
    )
    refresh_token = create_token(
        {"sub": user.username, "role": user.role.value, "typ": "refresh"},
        timedelta(days=settings.refresh_token_expire_days),
    )
    return access_token, refresh_token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(redis_client),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token_data = decode_token(credentials.credentials)
    if token_data.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    if not await is_token_active(redis, token_data):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked or missing")
    result = await db.execute(select(User).where(User.username == token_data["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
