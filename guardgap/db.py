import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, JSON, Integer, ForeignKey, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase): pass

def utc(): return datetime.now(timezone.utc).isoformat()

class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=utc)

class Token(Base):
    __tablename__ = "collector_tokens"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"))
    environment: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(120))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc)
    revoked: Mapped[int] = mapped_column(Integer, default=0)

class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"))
    environment: Mapped[str] = mapped_column(String(50))
    token_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    received_at: Mapped[str] = mapped_column(String(40), default=utc)
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id"))
    application_id: Mapped[str] = mapped_column(String(80), index=True)
    environment: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[str] = mapped_column(String(40), default=utc)
    payload: Mapped[dict] = mapped_column(JSON)

class Session(Base):
    __tablename__ = "sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[int] = mapped_column(Integer)

class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    window: Mapped[int] = mapped_column(Integer)

def connect(url):
    if url.startswith("postgres://"): url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"): url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, connect_args={"check_same_thread":False, "timeout":30} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine,"connect")
        def sqlite_settings(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False), engine
