from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models import User
from app.repositories.users import get_or_create_default_user

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(session: DbSession) -> User:
    """Single-user MVP resolution. Swap this dependency for real
    authentication (JWT/OIDC) without touching route signatures."""
    user = await get_or_create_default_user(session)
    await session.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
