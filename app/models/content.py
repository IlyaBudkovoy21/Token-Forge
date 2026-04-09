import enum

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ContentAudience(str, enum.Enum):
    common = "common"
    role1 = "role1"
    role2 = "role2"


class Content(Base):
    __tablename__ = "content"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[ContentAudience] = mapped_column(Enum(ContentAudience, name="content_audience"), nullable=False, index=True)
