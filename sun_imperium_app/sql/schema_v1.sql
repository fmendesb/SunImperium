-- Sun Imperium Console (v1) schema
-- This schema matches the Streamlit app code in /pages.
-- Run in Supabase SQL editor.

create extension if not exists pgcrypto;

-- ===== Core settings / weeks / ledger =====

create table if not exists app_settings (
  id uuid primary key default gen_random_uuid(),
  current_week int not null default 1,
  gold_starting numeric not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists weeks (
  week int primary key,
  status text not null default 'open',
  opened_at timestamptz not null default now(),
  closed_at timestamptz
);

create table if not exists ledger_entries (
  id uuid primary key default gen_random_uuid(),
  week int not null,
  created_at timestamptz not null default now(),
  category text not null,
  direction text not null check (direction in ('in','out')),
  amount numeric not null check (amount >= 0),
  note text,
  meta jsonb not null default '{}'::jsonb
);
create index if not exists idx_ledger_week on ledger_entries(week);

-- Undo log (per category)
create table if not exists action_logs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  category text not null,
  action text not null,
  payload jsonb not null default '{}'::jsonb,
  undone boolean not null default false
);
create index if not exists idx_action_logs_category_created on action_logs(category, created_at desc);

-- ===== Silver Council: factions / reputation / legislation / infrastructure / diplomacy =====

create table if not exists factions (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  type text not null, -- region|house|international
  created_at timestamptz not null default now()
);

create table if not exists reputation (
  id uuid primary key default gen_random_uuid(),
  week int not null,
  faction_id uuid not null references factions(id) on delete cascade,
  score int not null default 0,
  dc int,
  bonus int,
  note text,
  updated_at timestamptz not null default now(),
  unique (week, faction_id)
);
create index if not exists idx_reputation_week on reputation(week);

create table if not exists legislation (
  id uuid primary key default gen_random_uuid(),
  chapter text,
  item text,
  article text,
  title text not null,
  dc int,
  description text,
  effects text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists infrastructure (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  category text not null,
  cost numeric not null default 0,
  upkeep numeric not null default 0,
  description text,
  prereq text
);

create table if not exists infrastructure_owned (
  infrastructure_id uuid primary key references infrastructure(id) on delete cascade,
  owned boolean not null default false,
  owned_at timestamptz
);

create table if not exists diplomacy_units (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  tier int not null default 1,
  purchase_cost numeric not null default 0,
  upkeep numeric not null default 0,
  description text
);

create table if not exists diplomacy_roster (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid not null references diplomacy_units(id) on delete cascade,
  quantity int not null default 0
);
create unique index if not exists idx_diplomacy_roster_unit on diplomacy_roster(unit_id);

-- ===== Dawnbreakers (intelligence) =====

create table if not exists dawnbreakers_units (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  tier int not null default 1,
  purchase_cost numeric not null default 0,
  upkeep numeric not null default 0,
  success int,
  description text
);

create table if not exists dawnbreakers_roster (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid not null references dawnbreakers_units(id) on delete cascade,
  quantity int not null default 0
);
create unique index if not exists idx_dawnbreakers_roster_unit on dawnbreakers_roster(unit_id);

-- ===== Moonblade Guild (military) =====

create table if not exists moonblade_units (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  unit_type text not null, -- guardian|archer|mage|cleric|other
  power numeric not null default 1,
  cost numeric not null default 0,
  upkeep numeric not null default 0,
  description text
);

create table if not exists moonblade_roster (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid not null references moonblade_units(id) on delete cascade,
  quantity int not null default 0
);
create unique index if not exists idx_moonblade_roster_unit on moonblade_roster(unit_id);

create table if not exists squads (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  region text,
  created_at timestamptz not null default now()
);

create table if not exists squad_members (
  id uuid primary key default gen_random_uuid(),
  squad_id uuid not null references squads(id) on delete cascade,
  unit_id uuid references moonblade_units(id) on delete set null,
  unit_type text not null,
  quantity int not null default 0
);
create index if not exists idx_squad_members_squad on squad_members(squad_id);

-- War log
create table if not exists wars (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  week int,
  squad_id uuid references squads(id) on delete set null,
  enemy jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  note text
);
