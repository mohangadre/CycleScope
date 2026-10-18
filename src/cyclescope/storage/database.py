from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


def make_engine(url: str) -> Engine:
    if make_url(url).drivername != "postgresql+psycopg":
        raise ValueError("CycleScope requires a postgresql+psycopg DATABASE_URL")
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
