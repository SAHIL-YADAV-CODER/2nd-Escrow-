import os
import asyncio
import logging
import yaml
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher.filters import Command
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from database import db
from handlers import escrow as escrow_handlers  # package-style; ensure __init__ imports
from aiogram.types import ParseMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load config
with open("config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

TOKEN = os.getenv("BOT_TOKEN") or cfg["bot"]["token"]
if not TOKEN or TOKEN.startswith("REPLACE"):
    raise RuntimeError("Set BOT_TOKEN in environment or config.yaml before running")

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Register commands
@dp.message_handler(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(f"Welcome to {cfg['ui']['brand']} — the PW Escrow Bot.\nUse /escrow to begin.")

@dp.message_handler(Command("escrow"))
async def cmd_escrow(message: types.Message):
    args = message.get_args().strip()
    if args.startswith("form") or args == "":
        await escrow_handlers.cmd_escrow_form(message, dp.current_state(user=message.from_user.id))
    else:
        await escrow_handlers.cmd_escrow_start(message)

@dp.message_handler(lambda m: True, content_types=types.ContentTypes.TEXT)
async def catch_all_text(message: types.Message):
    state = dp.current_state(user=message.from_user.id)
    st = await state.get_state()
    if st == "AWAITING_ESCROW_FORM":
        await escrow_handlers.on_form_message(message, state)
        return
    # other free text handling
    # keep messages clean (no spam)
    await message.answer("Unrecognized command. Use /escrow to start a new escrow or /help.")

@dp.callback_query_handler(lambda c: True)
async def process_callback(callback_query: types.CallbackQuery):
    await escrow_handlers.callback_router(callback_query, bot)

async def on_startup(dp):
    await db.connect()
    logger.info("Database pool created")
    # In production, run migrations. For now assume tables exist.
    # Optionally create admin users from config
    logger.info("Bot started")

async def on_shutdown(dp):
    await db.close()
    await bot.close()

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)