from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.content import Content, ContentAudience
from app.models.user import User, UserRole
from app.schemas.content import ContentRead


router = APIRouter(prefix="/content", tags=["content"])


@router.get("", response_model=list[ContentRead])
async def list_content(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed_audiences = [ContentAudience.common]
    if user.role == UserRole.role1:
        allowed_audiences.append(ContentAudience.role1)
    if user.role == UserRole.role2:
        allowed_audiences.append(ContentAudience.role2)

    result = await db.execute(select(Content).where(Content.audience.in_(allowed_audiences)).order_by(Content.id))
    return list(result.scalars().all())
