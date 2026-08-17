from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class User(Base, TimestampMixin):
    """Auth-ready user record. The MVP runs single-user ("default"), but every
    owned resource already carries ``user_id`` so real authentication can be
    added without schema changes."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(default=True)


DEFAULT_USER_EMAIL = "default@local"
