from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite has no timezone type, and mixing aware/naive
    # datetimes is the classic comparison bug. Convert at the API edge if needed.
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(settings.database_url, future=True)

# Trade execution (app/engine/trading.py) relies on SELECT ... FOR UPDATE to make its
# read-modify-write of listings.shares_outstanding atomic — but SQLite IGNORES FOR
# UPDATE. Under simultaneous trades on the same player that produces lost updates:
# shares_outstanding drifts below real holdings, corrupting AMM prices and net worth
# (reproduced at scale in scripts/simulate_season.py — 37 corrupted listings with the
# default engine, 0 with this fix). WAL + busy_timeout alone does NOT fix it; the write
# lock must be taken *before* the read. So: put SQLite in WAL, and BEGIN IMMEDIATE on
# every transaction so trades serialize (rivals wait via busy_timeout instead of racing
# or erroring with "database is locked"). Postgres keeps real FOR UPDATE, so guard on sqlite.
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        dbapi_conn.isolation_level = None  # disable pysqlite autobegin; we drive BEGIN
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    @event.listens_for(engine, "begin")
    def _sqlite_begin_immediate(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
