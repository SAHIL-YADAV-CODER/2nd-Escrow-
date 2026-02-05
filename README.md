```markdown
# PW Escrow Bot — Ultimate Version (Starter)

This repository contains a production-oriented starter for "PW Escrow Bot" (PagalWorld Escrow). It implements the major architecture and security patterns required for a premium Telegram escrow bot.

Features
- Python + aiogram (preferred)
- PostgreSQL primary (asyncpg), SQLite fallback planned
- Strict Escrow state machine and atomic state transitions
- Role-based inline buttons (Buyer / Seller / Admin)
- Action tokens for anti-double-click and replay protection
- UPI QR generation (PNG) with Escrow ID embedded in transaction note
- Audit logs stored in DB and posted to configured log group
- Docker-ready and modular

Quickstart (Development)
1. Copy `.env.example` to `.env` and fill values (especially BOT_TOKEN and DATABASE_URL).
2. Ensure PostgreSQL is running (docker-compose provided).
3. Build & run:
   - docker-compose up --build
4. The bot will connect and listen using polling (recommended to use webhook in production).

Database
- models.sql contains the necessary SQL to initialize Postgres tables.
- In production, use proper migrations (Alembic recommended).

Security & Production Notes
- Do NOT commit your BOT_TOKEN or DB credentials.
- Use environment variables, secrets manager, or Docker secrets.
- For multi-instance scaling, add Redis for FSM storage and distributed locks, or use database advisory locks.
- Increase DB pool size and add connection pooling.
- Configure HTTPS webhook for production.

Extending
- Implement admin commands `/admin panel` endpoints with strict permission checks.
- Add full dispute resolution UI, file attachments, and message locking on dispute.
- Replace naive escrow code generation with a stronger unique ID generator.
- Add background tasks to auto-expire escrows and cleanup tokens.

This starter focuses on correctness, safe patterns, and a clear path to production.
```