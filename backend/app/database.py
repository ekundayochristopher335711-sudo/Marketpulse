import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./marketpulse.db")
is_sqlite = DATABASE_URL.startswith("sqlite")
engine_options = {
    "connect_args": {"check_same_thread": False} if is_sqlite else {},
}
if not is_sqlite:
    # Keep each serverless/API process from opening a large pool of Supabase
    # connections. The scheduled worker shares this engine for its short runs.
    engine_options.update(pool_size=1, max_overflow=0, pool_pre_ping=True)

engine = create_engine(DATABASE_URL, **engine_options)


def get_session():
    with Session(engine) as session:
        yield session
