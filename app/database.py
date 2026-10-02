import logging
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


def resolve_database_url(url: str) -> str:
    """If using direct Supabase hostname db.<ref>.supabase.co, automatically rewrite

    to the IPv4 pooler host because cloud environments like Render lack outbound IPv6.
    """
    m = re.search(r"@db\.([a-zA-Z0-9]+)\.supabase\.co(?::\d+)?", url)
    if m:
        project_ref = m.group(1)
        # Transform postgres:<pass>@db.<ref>.supabase.co -> postgres.<ref>:<pass>@aws-0-ap-southeast-1.pooler.supabase.com:5432
        new_url = re.sub(
            r"//([^:@]+):([^@]+)@db\." + project_ref + r"\.supabase\.co(?::\d+)?",
            r"//\1." + project_ref + r":\2@aws-0-ap-southeast-1.pooler.supabase.com:5432",
            url,
        )
        logger.info("Auto-redirected Supabase direct host to IPv4 pooler: %s", new_url.split("@")[-1])
        return new_url
    return url


effective_db_url = resolve_database_url(settings.DATABASE_URL)

engine = create_engine(
    effective_db_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
