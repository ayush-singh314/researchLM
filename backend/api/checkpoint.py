"""Process-wide LangGraph Postgres checkpointer (public schema tables)."""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

from backend.api.db import get_psycopg_conninfo

_pool: ConnectionPool | None = None


def create_checkpoint_pool() -> ConnectionPool:
    return ConnectionPool(
        conninfo=get_psycopg_conninfo(),
        min_size=1,
        max_size=8,
        kwargs={
            "autocommit": True,
            "prepare_threshold": None,
            "row_factory": dict_row,
        },
    )


def init_checkpointer(pool: ConnectionPool | None = None) -> tuple[ConnectionPool, PostgresSaver]:
    global _pool
    if pool is None:
        pool = create_checkpoint_pool()
        pool.open()
        _pool = pool
    saver = PostgresSaver(pool)
    saver.setup()
    return pool, saver


def close_checkpoint_pool(pool: ConnectionPool | None = None) -> None:
    global _pool
    target = pool or _pool
    if target is not None:
        target.close()
    if target is _pool:
        _pool = None
