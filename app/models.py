"""SQLAlchemy 2.0 async modellari — 01_BAZA.md bo'yicha."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Business(Base):
    """Biznes egasi — Telegram orqali ro'yxatdan o'tgan foydalanuvchi."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True
    )
    business_name: Mapped[str | None] = mapped_column(String(255))
    ig_business_account_id: Mapped[str | None] = mapped_column(String(255))
    ig_access_token: Mapped[str | None] = mapped_column(Text)  # shifrlangan
    ig_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    license_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # relationships
    tracked_posts: Mapped[list["TrackedPost"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    error_logs: Mapped[list["ErrorLog"]] = relationship(
        back_populates="business"
    )


class TrackedPost(Base):
    """Kuzatilayotgan Instagram post — bitta postga bitta kalit so'z."""

    __tablename__ = "tracked_posts"
    __table_args__ = (
        UniqueConstraint("business_id", "ig_media_id", name="uq_biz_media"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    ig_media_id: Mapped[str] = mapped_column(String(255), nullable=False)
    post_url: Mapped[str | None] = mapped_column(Text)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # relationships
    business: Mapped["Business"] = relationship(back_populates="tracked_posts")
    responses: Mapped[list["PostResponse"]] = relationship(
        back_populates="tracked_post", cascade="all, delete-orphan"
    )
    reply_logs: Mapped[list["ReplyLog"]] = relationship(
        back_populates="tracked_post", cascade="all, delete-orphan"
    )


class PostResponse(Base):
    """Postga kelgan izohga beriladigan javob kontenti (matn/rasm/link)."""

    __tablename__ = "post_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracked_post_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracked_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'text' | 'image' | 'link'
    content_value: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # relationships
    tracked_post: Mapped["TrackedPost"] = relationship(
        back_populates="responses"
    )


class ReplyLog(Base):
    """Javob yuborilganlik logi — spam oldini olish (1 user = 1 post = 1 javob)."""

    __tablename__ = "reply_log"
    __table_args__ = (
        UniqueConstraint(
            "tracked_post_id",
            "ig_commenter_id",
            name="uq_post_commenter",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracked_post_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tracked_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    ig_commenter_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subscribe_prompt_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    final_reply_sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    # relationships
    tracked_post: Mapped["TrackedPost"] = relationship(
        back_populates="reply_logs"
    )


class ErrorLog(Base):
    """Xatolar jurnali."""

    __tablename__ = "error_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("businesses.id")
    )
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # relationships
    business: Mapped["Business | None"] = relationship(
        back_populates="error_logs"
    )
