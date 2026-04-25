-- Conversation memory schema (threads/messages/state/events).
-- Uses pgcrypto for gen_random_uuid().

create extension if not exists pgcrypto;

create table if not exists conversation_threads (
  id uuid primary key default gen_random_uuid(),
  thread_key text not null unique,
  hubspot_contact_id text null,
  lead_email text null,
  lead_phone text null,
  company_name text null,
  company_domain text null,
  primary_channel text not null,
  status text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists conversation_threads_hubspot_contact_id_idx
  on conversation_threads (hubspot_contact_id);
create index if not exists conversation_threads_lead_email_idx
  on conversation_threads (lead_email);
create index if not exists conversation_threads_lead_phone_idx
  on conversation_threads (lead_phone);
create index if not exists conversation_threads_company_domain_idx
  on conversation_threads (company_domain);

create table if not exists conversation_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references conversation_threads(id) on delete cascade,
  channel text not null,
  direction text not null,
  provider text not null,
  provider_message_id text null,
  provider_thread_key text null,
  in_reply_to text null,
  subject text null,
  body_text text null,
  from_address text null,
  to_address text null,
  sent_at timestamptz not null,
  is_autoresponder boolean null,
  outbound_variant text null,
  draft boolean not null default true,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists conversation_messages_thread_sent_at_idx
  on conversation_messages (thread_id, sent_at desc);
create index if not exists conversation_messages_provider_message_id_idx
  on conversation_messages (provider_message_id);
create index if not exists conversation_messages_provider_thread_key_idx
  on conversation_messages (provider_thread_key);

create table if not exists conversation_state (
  thread_id uuid primary key references conversation_threads(id) on delete cascade,
  last_channel text null,
  last_inbound_at timestamptz null,
  last_outbound_at timestamptz null,
  email_replied boolean not null default false,
  sms_replied boolean not null default false,
  sms_opted_out boolean not null default false,
  booking_requested boolean not null default false,
  booking_created boolean not null default false,
  booking_uid text null,
  bench_gate_passed boolean null,
  icp_segment integer null,
  segment_confidence double precision null,
  ai_maturity_score integer null,
  outbound_variant text null,
  last_unanswered_question text null,
  qualification_json jsonb not null default '{}'::jsonb,
  memory_json jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists conversation_events (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references conversation_threads(id) on delete cascade,
  event_type text not null,
  event_at timestamptz not null,
  payload_json jsonb not null default '{}'::jsonb
);

create index if not exists conversation_events_thread_event_at_idx
  on conversation_events (thread_id, event_at desc);

