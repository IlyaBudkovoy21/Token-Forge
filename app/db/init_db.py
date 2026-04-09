from sqlalchemy import func, select

from app.core.security import hash_password
from app.models import Content, ContentAudience, User, UserRole


async def init_db(session, _redis) -> None:
    user_count = await session.scalar(select(func.count()).select_from(User))
    if not user_count:
        users = [
            User(username="role1_user", hashed_password=hash_password("password1"), role=UserRole.role1),
            User(username="role2_user", hashed_password=hash_password("password2"), role=UserRole.role2),
        ]
        session.add_all(users)

    content_count = await session.scalar(select(func.count()).select_from(Content))
    if not content_count:
        session.add_all(
            [
                Content(title="Common content", body="Visible to both roles", audience=ContentAudience.common),
                Content(title="Role 1 secret", body="Visible only to role 1", audience=ContentAudience.role1),
                Content(title="Role 2 secret", body="Visible only to role 2", audience=ContentAudience.role2),
            ]
        )

    await session.commit()
