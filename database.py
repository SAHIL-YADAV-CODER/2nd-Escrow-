import os
import asyncio
import asyncpg
import yaml
from datetime import datetime, timedelta
from typing import Optional, Any

# Load config
with open("config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

DATABASE_URL = os.getenv("DATABASE_URL") or cfg["database"].get("url")
SQLITE_FALLBACK = cfg["database"].get("sqlite_fallback")

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.pool.Pool] = None
        self._url = DATABASE_URL or SQLITE_FALLBACK
        self._is_sqlite = self._url.startswith("sqlite")

    async def connect(self):
        if self._is_sqlite:
            # For SQLite fallback we use aiosqlite via an adapter or sync. Keep simple:
            raise RuntimeError("SQLite fallback requires separate adapter; configure Postgres in production.")
        self.pool = await asyncpg.create_pool(dsn=self._url, min_size=1, max_size=10)

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def transaction(self):
        if not self.pool:
            raise RuntimeError("Pool not initialized")
        return self.pool.acquire().__aenter__()  # usage: async with db.transaction() as conn:

    # Helper: run a function inside a transaction with a connection
    async def with_transaction(self, func):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await func(conn)


db = Database()