from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    authenticate_user,
    blacklist_token,
    create_token_pair,
    decode_token,
    get_current_user,
    is_token_active,
    bearer_scheme,
    redis_client,
    store_whitelist,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, MeResponse, RefreshRequest, TokenPair


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_client)):
    user = await authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token, refresh_token = create_token_pair(user)
    access_data = decode_token(access_token)
    refresh_data = decode_token(refresh_token)
    await store_whitelist(redis, access_data)
    await store_whitelist(redis, refresh_data)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, redis: Redis = Depends(redis_client), db: AsyncSession = Depends(get_db)):
    refresh_data = decode_token(payload.refresh_token)
    if refresh_data.get("typ") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    if not await is_token_active(redis, refresh_data):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked or reused")

    user = await get_current_user_from_username(db, refresh_data["sub"])
    await blacklist_token(redis, refresh_data)
    access_token, new_refresh_token = create_token_pair(user)
    access_data = decode_token(access_token)
    new_refresh_data = decode_token(new_refresh_token)
    await store_whitelist(redis, access_data)
    await store_whitelist(redis, new_refresh_data)
    return TokenPair(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    redis: Redis = Depends(redis_client),
):
    if not isinstance(credentials, HTTPAuthorizationCredentials):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    access_data = decode_token(credentials.credentials)
    if access_data.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    await blacklist_token(redis, access_data)

    if payload.refresh_token:
        refresh_data = decode_token(payload.refresh_token)
        await blacklist_token(redis, refresh_data)

    return {"detail": "Logged out"}


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return user


async def get_current_user_from_username(db: AsyncSession, username: str) -> User:
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
