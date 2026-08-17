from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DEFAULT_USER_EMAIL, User


async def get_or_create_default_user(session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, name="Default User")
        session.add(user)
        await session.flush()
    return user
