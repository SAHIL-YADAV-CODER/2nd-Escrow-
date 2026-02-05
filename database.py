import os
import asyncpg
import yaml
import aiosqlite
from typing import Optional

# ---------- Load config safely ----------
cfg = {}
if os.path.exists("config.yaml"):
    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f) or {}

db_cfg = cfg.get("database", {})

DATABASE_URL = os.getenv("DB_URL") or db_cfg.get("url")
SQLITE_FALLBACK = db_cfg.get("sqlite_fallback", "sqlite:///escrow.db")
ENV = os.getenv("ENV", "test")  # test | production


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.pool.Pool] = None
        self.sqlite: Optional[aiosqlite.Connection] = None
        self._url = DATABASE_URL or SQLITE_FALLBACK
        self._is_sqlite = self._url.startswith("sqlite")

    async def connect(self):
        if self._is_sqlite:
            if ENV == "production":
                raise RuntimeError(
                    "SQLite is not allowed in production. Use PostgreSQL."
                )

            # ✅ SQLite for testing
            self.sqlite = await aiosqlite.connect("escrow.db")
            await self.sqlite.execute("PRAGMA foreign_keys = ON")
            await self.sqlite.commit()
            return

        # ✅ PostgreSQL
        self.pool = await asyncpg.create_pool(
            dsn=self._url, min_size=1, max_size=10
        )

    async def close(self):
        if self.pool:
            await self.pool.close()
        if self.sqlite:
            await self.sqlite.close()

    # ---------- Query helpers ----------
    async def fetch(self, query: str, *args):
        if self.sqlite:
            cursor = await self.sqlite.execute(query, args)
            rows = await cursor.fetchall()
            return rows

        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, *args):
        if self.sqlite:
            await self.sqlite.execute(query, args)
            await self.sqlite.commit()
            return

        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)


db = Database()
