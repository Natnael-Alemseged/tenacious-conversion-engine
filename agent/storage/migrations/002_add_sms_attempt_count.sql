alter table conversation_state
  add column if not exists outbound_sms_attempt_count integer not null default 0;
