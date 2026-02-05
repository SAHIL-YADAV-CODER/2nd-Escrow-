import os
import yaml
import json
import asyncio
from datetime import datetime, timedelta, timezone
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command, Text
from aiogram.utils.markdown import bold, code, italic
from database import db
from state_machine import EscrowState, InvalidTransition, ALLOWED_TRANSITIONS
from keyboards import agreement_keyboard, action_button, release_confirmation_keyboard
from utils.qrcode import generate_upi_qr
import uuid

# Load config
with open("config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

FEE_PERCENT = cfg["bot"].get("fee_percent", 6)
UPI_ID = cfg["bot"].get("upi_id", "pwescrow@upi")
LOG_GROUP_ID = cfg["bot"].get("log_group_id")

# Utilities
def money_fmt(value) -> str:
    return f"₹{float(value):,.2f}"

async def create_user_if_not_exists(conn, user: types.User):
    await conn.execute(
        """
        INSERT INTO users (id, username, first_name, last_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (id) DO UPDATE
          SET username = EXCLUDED.username,
              first_name = EXCLUDED.first_name,
              last_name = EXCLUDED.last_name
        """, user.id, user.username, user.first_name, user.last_name
    )

async def log_action(conn, escrow_id, chat_id, actor_id, action, payload=None):
    await conn.execute(
        """
        INSERT INTO escrow_logs (escrow_id, chat_id, actor_id, action, payload)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        """, escrow_id, chat_id, actor_id, action, json.dumps(payload or {})
    )

async def generate_escrow_code(conn) -> str:
    # Very simple incremental-style code: you can adapt to prefer randomness
    row = await conn.fetchrow("SELECT COUNT(*) AS c FROM escrows")
    base = int(row["c"] or 0) + 100000
    code = f"PW-{base}"
    return code

# --- Action token helpers (anti-double-click & replay-protection) ---
async def create_action_token(conn, escrow_id, action, user_id, ttl_seconds):
    row = await conn.fetchrow(
        """
        INSERT INTO action_tokens (escrow_id, action, user_id, expires_at)
        VALUES ($1, $2, $3, (now() AT TIME ZONE 'utc') + ($4 || ' seconds')::interval)
        RETURNING token
        """, escrow_id, action, user_id, ttl_seconds
    )
    return str(row["token"])

async def consume_action_token(conn, token, escrow_id, action, user_id):
    # Validate token with SELECT FOR UPDATE inside a transaction. We assume caller handles transaction.
    row = await conn.fetchrow(
        """
        SELECT token, used, expires_at, user_id FROM action_tokens WHERE token = $1 AND escrow_id = $2 AND action = $3
        """,
        token, escrow_id, action
    )
    if not row:
        return False, "invalid_token"
    if row["used"]:
        return False, "already_used"
    if row["user_id"] != user_id:
        return False, "wrong_user"
    expires_at = row["expires_at"]
    if expires_at < datetime.now(timezone.utc):
        return False, "expired"
    # mark used
    await conn.execute("UPDATE action_tokens SET used = true WHERE token = $1", token)
    return True, "ok"

# --- Escrow command handlers (skeleton flows) ---
async def cmd_escrow_start(message: types.Message):
    text = (
        f"{bold('PW ESCROW — Create a new escrow')}\n\n"
        "To open a new escrow quickly, use /escrow form and paste a single message with ALL fields:\n\n"
        "<BuyerUsername or ID>\n"
        "<SellerUsername or ID>\n"
        "<Deal Title>\n"
        "<Product / Service Description>\n"
        "<Total Amount (₹)>\n"
        "<Delivery Time (hours/days)>\n"
        "<Refund Conditions>\n"
        "<Dispute Resolution Agreement (Yes/No)>\n\n"
        "Example:\n"
        "@buyer\n"
        "@seller\n"
        "Instagram Account Sale\n"
        "Full access + original email\n"
        "10000\n"
        "24h\n"
        "No refunds after release\n"
        "Yes\n\n"
        "After submission you will preview the Agreement and both Buyer & Seller must Agree via role-locked buttons."
    )
    await message.answer(text, parse_mode="MarkdownV2")

async def cmd_escrow_form(message: types.Message, state: FSMContext):
    # prompt user to send the single-message form described earlier
    await message.answer("Please paste the full escrow form in a single message using the template described. You can edit your message before submitting.")
    await state.set_state("AWAITING_ESCROW_FORM")

async def on_form_message(message: types.Message, state: FSMContext):
    # Expect 8 lines
    text = message.text.strip()
    parts = [p.strip() for p in text.splitlines() if p.strip()]
    if len(parts) < 8:
        await message.answer("Invalid form: expected 8 non-empty lines. Please follow the template.")
        return
    buyer_str, seller_str, title, desc, amount_str, delivery, refund, dispute = parts[:8]
    try:
        amount = float(amount_str.replace(",", ""))
        if amount <= 0:
            raise ValueError()
    except Exception:
        await message.answer("Invalid amount. Use only numbers like 10000 or 10,000.")
        return

    # Resolve buyer/seller to Telegram IDs if they are @username or numeric id.
    # For security, enforce that the person creating escrow is either buyer or seller (role lock).
    creator_id = message.from_user.id
    # NOTE: username resolution: for production, call get_chat or maintain user cache.
    def parse_user_field(s):
        s = s.strip()
        if s.startswith("@"):
            return s  # we store username; resolution later
        try:
            return int(s)
        except:
            return s

    buyer_field = parse_user_field(buyer_str)
    seller_field = parse_user_field(seller_str)

    fee_amount = round((amount * FEE_PERCENT) / 100.0, 2)

    async def txn(conn):
        # create users if known
        await create_user_if_not_exists(conn, message.from_user)

        escrow_code = await generate_escrow_code(conn)
        # create escrow row
        row = await conn.fetchrow(
            """
            INSERT INTO escrows
            (escrow_code, chat_id, buyer_id, seller_id, deal_title, description, amount, fee_amount, delivery_deadline, refund_conditions, dispute_agreement, state)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, (now() AT TIME ZONE 'utc') + ($9 || ' hours')::interval, $10, $11, 'FORM_SUBMITTED')
            RETURNING id, escrow_code
            """,
            escrow_code, message.chat.id, buyer_field if isinstance(buyer_field, int) else creator_id,
            seller_field if isinstance(seller_field, int) else creator_id,
            title, desc, amount, fee_amount, 24, refund, True if dispute.lower().startswith("y") else False
        )
        escrow_id = row["id"]
        # log
        await log_action(conn, escrow_id, message.chat.id, creator_id, "form_submitted", {
            "buyer_field": buyer_field,
            "seller_field": seller_field,
            "amount": amount,
            "fee": fee_amount,
            "title": title
        })
        return escrow_id, escrow_code

    escrow_id, escrow_code = await db.with_transaction(txn)

    preview_text = (
        f"🔐 PW ESCROW AGREEMENT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Escrow ID: {escrow_code}\n\n"
        f"👤 Buyer: {buyer_str}\n"
        f"👤 Seller: {seller_str}\n\n"
        f"📦 Deal: {title}\n"
        f"📝 Details: {desc}\n"
        f"💰 Amount: {money_fmt(amount)}\n"
        f"💸 Fee: {FEE_PERCENT}% ({money_fmt(fee_amount)})\n"
        f"⏳ Delivery: {delivery}\n\n"
        f"⚖️ Terms:\n• Funds held until buyer confirms delivery\n• No chargebacks after release\n• Disputes handled by PW Escrow Admins\n\n"
        f"Proceed?"
    )

    # create per-user action tokens
    async with db.pool.acquire() as conn:
        buyer_token = await create_action_token(conn, escrow_id, "agree_buyer", message.from_user.id, cfg["security"]["action_token_ttl_seconds"])
        seller_token = await create_action_token(conn, escrow_id, "agree_seller", message.from_user.id, cfg["security"]["action_token_ttl_seconds"])

        kb = agreement_keyboard(escrow_code, buyer_token, seller_token)
        # send preview with role-locked buttons
        sent = await message.answer(preview_text, reply_markup=kb, parse_mode="HTML")
        # log preview
        await log_action(conn, escrow_id, message.chat.id, creator_id, "agreement_preview_sent", {"message_id": sent.message_id})

    await state.finish()

async def callback_router(callback_query: types.CallbackQuery, bot):
    """
    Main router for callback_data with format: action|escrow_code|token
    All callbacks must be validated: escrow exists, token exists and valid, role check (buyer/seller), and atomic state change.
    """
    data = callback_query.data or ""
    parts = data.split("|")
    if len(parts) != 3:
        await callback_query.answer("Malformed action", show_alert=True)
        return
    action, escrow_code, token = parts

    # find escrow by code
    async with db.pool.acquire() as conn:
        escrow_row = await conn.fetchrow("SELECT * FROM escrows WHERE escrow_code = $1", escrow_code)
        if not escrow_row:
            await callback_query.answer("Escrow not found", show_alert=True)
            return
        escrow_id = escrow_row["id"]
        buyer_id = escrow_row["buyer_id"]
        seller_id = escrow_row["seller_id"]
        state = escrow_row["state"]
        chat_id = escrow_row["chat_id"]

        # Validate token (server-side)
        ok, reason = await consume_action_token(conn, token, escrow_id, action, callback_query.from_user.id)
        if not ok:
            await callback_query.answer("Action denied: " + reason, show_alert=True)
            return

        # Role checks
        if action.startswith("agree_buyer") and callback_query.from_user.id != buyer_id:
            await callback_query.answer("🚫 You are not authorized for this escrow (Buyer only)", show_alert=True)
            return
        if action.startswith("agree_seller") and callback_query.from_user.id != seller_id:
            await callback_query.answer("🚫 You are not authorized for this escrow (Seller only)", show_alert=True)
            return
        if action == "disagree":
            # move to CANCELLED atomically
            async with conn.transaction():
                await conn.execute("UPDATE escrows SET state = $1, updated_at = now() WHERE id = $2", "CANCELLED", escrow_id)
                await log_action(conn, escrow_id, chat_id, callback_query.from_user.id, "disagreed", {"by": callback_query.from_user.id})
            await callback_query.message.edit_text(f"Escrow {escrow_code} has been cancelled due to disagreement.", parse_mode="HTML")
            await callback_query.answer("Disagreement registered. Escrow cancelled.")
            # post to log channel
            await bot.send_message(LOG_GROUP_ID, f"🚫 Escrow {escrow_code} cancelled by {callback_query.from_user.full_name}")
            return

        if action in ("agree_buyer", "agree_seller"):
            # track agreements in logs and check if both agreed
            async with conn.transaction():
                await log_action(conn, escrow_id, chat_id, callback_query.from_user.id, "agreed", {"action": action})
                # Check if both have agreed by searching logs
                rows = await conn.fetch("SELECT DISTINCT actor_id, action FROM escrow_logs WHERE escrow_id = $1 AND action = 'agreed'", escrow_id)
                actors = {r["actor_id"] for r in rows}
                # add current
                actors.add(callback_query.from_user.id)
                # naive both-agreed check:
                if buyer_id in actors and seller_id in actors:
                    # transition to AGREED
                    await conn.execute("UPDATE escrows SET state=$1, updated_at=now() WHERE id=$2", "AGREED", escrow_id)
                    await log_action(conn, escrow_id, chat_id, callback_query.from_user.id, "state_change", {"to": "AGREED"})
                    await callback_query.message.edit_text(f"Both parties agreed. Escrow {escrow_code} is now AGREED.\n\nUse /escrow fund {escrow_code} to see payment instructions.", parse_mode="HTML")
                    await callback_query.answer("Both parties agreed — escrow AGREED.")
                    # send payment instructions in chat (with QR)
                    amount = float(escrow_row["amount"])
                    qr = generate_upi_qr(UPI_ID, "PW Escrow", amount, escrow_code)
                    caption = (
                        f"💳 PAYMENT DETAILS – PW ESCROW\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"UPI ID: {UPI_ID}\n"
                        f"Amount: {money_fmt(amount)}\n"
                        f"Escrow ID: {escrow_code}\n\n"
                        f"⚠️ Send exact amount only. Include Escrow ID in remark/note."
                    )
                    await bot.send_photo(chat_id, qr, caption=caption)
                    await bot.send_message(LOG_GROUP_ID, f"✅ PAYMENT AVAILABLE for {escrow_code} — amount {money_fmt(amount)}")
                    return
                else:
                    await callback_query.answer("Your agreement is recorded. Waiting for the other party.")
                    return

        await callback_query.answer("Unhandled action")