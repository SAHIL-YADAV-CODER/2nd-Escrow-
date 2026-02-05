from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid
from typing import Callable, Optional

# Callback data format:
# action|escrow_code|token
# token is a UUID created server-side and stored in DB (action token)

def action_button(label: str, action: str, escrow_code: str, token: str) -> InlineKeyboardButton:
    data = f"{action}|{escrow_code}|{token}"
    return InlineKeyboardButton(label, callback_data=data)

def agreement_keyboard(escrow_code: str, buyer_token: str, seller_token: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(action_button("✅ Agree (Buyer)", "agree_buyer", escrow_code, buyer_token))
    kb.add(action_button("✅ Agree (Seller)", "agree_seller", escrow_code, seller_token))
    kb.add(action_button("❌ Disagree", "disagree", escrow_code, seller_token))
    return kb

def release_confirmation_keyboard(escrow_code: str, token: str):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(action_button("✅ Yes, Release", "confirm_release", escrow_code, token))
    kb.add(action_button("❌ Cancel", "cancel_release", escrow_code, token))
    return kb

def payment_keyboard(escrow_code: str):
    # one-time tokens for actions will be created in handlers and injected
    return InlineKeyboardMarkup().add(InlineKeyboardButton("I've Paid — Notify", callback_data=f"paid_notify|{escrow_code}|none"))