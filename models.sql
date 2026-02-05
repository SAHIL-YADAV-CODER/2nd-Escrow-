-- SQL schema (Postgres). For SQLite, adapt types accordingly.
-- Run this file once to create tables, or use migrations.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY, -- Telegram user id
  username TEXT,
  first_name TEXT,
  last_name TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TYPE escrow_state AS ENUM (
  'CREATED',
  'FORM_SUBMITTED',
  'AGREEMENT_PREVIEW',
  'AGREED',
  'FUNDED',
  'DELIVERED',
  'RELEASE_REQUESTED',
  'RELEASE_CONFIRMED',
  'COMPLETED',
  'DISPUTED',
  'CANCELLED',
  'EXPIRED'
);

CREATE TABLE IF NOT EXISTS escrows (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  escrow_code TEXT UNIQUE, -- e.g., PW-102934
  chat_id BIGINT NOT NULL,   -- origin chat or group
  buyer_id BIGINT NOT NULL,
  seller_id BIGINT NOT NULL,
  deal_title TEXT,
  description TEXT,
  amount NUMERIC(18,2) NOT NULL,
  fee_amount NUMERIC(18,2) NOT NULL,
  delivery_deadline TIMESTAMP WITH TIME ZONE,
  refund_conditions TEXT,
  dispute_agreement BOOLEAN,
  state escrow_state NOT NULL DEFAULT 'CREATED',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action_tokens (
  token UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  escrow_id UUID NOT NULL REFERENCES escrows(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  user_id BIGINT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  used BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS escrow_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  escrow_id UUID REFERENCES escrows(id) ON DELETE CASCADE,
  chat_id BIGINT,
  actor_id BIGINT,
  action TEXT,
  payload JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);