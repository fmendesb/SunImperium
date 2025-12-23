-- Sun Imperium Console (v1) schema
-- Run in Supabase SQL editor.

-- Extensions
create extension if not exists pgcrypto;

-- Core settings (single row)
create table if not exists app_settings (
  id uuid primary key default gen_random_uuid(),
  current_week int not null default 1,
  gold_starting numeric not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Weeks
create table if not exists weeks (
  week int primary key,
  status text not null default 'open', -- open|closed
  opened_at timestamptz not null default now(),
  closed_at timestamptz
);

-- Ledger (Moonvault)
create table if not exists ledger_entries (
  id uuid primary key default gen_random_uuid(),
  week int not null,
  created_at timestamptz not null default now(),
  category text not null, -- resources_tax|moonblade_upkeep|dawnbreakers_upkeep|diplomacy_upkeep|infrastructure_upkeep|purchase|adjustment|other
  direction text not null check (direction in ('in','out')),
  amount numeric not null check (amount >= 0),
  note text,
  meta jsonb not null default '{}'::jsonb
);
create index if not exists idx_ledger_week on ledger_entries(week);

-- Action log for undo (per category)
create table if not exists action_logs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  category text not null, -- infrastructure|moonblade|dawnbreakers|diplomacy|reputation|legislation|war
  action text not null,   -- purchase|recruit|edit|resolve|etc
  payload jsonb not null default '{}'::jsonb,
  undone boolean not null default false
);
create index if not exists idx_action_logs_category_created on action_logs(category, created_at desc);

-- Silver Council: factions (regions + houses)
create table if not exists factions (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  kind text not null, -- region|house|international
  created_at timestamptz not null default now()
);

-- Reputation per faction
create table if not exists reputation (
  faction_id uuid references factions(id) on delete cascade,
  score int not null default 0,
  note text,
  updated_at timestamptz not null default now(),
  primary key (faction_id)
);

-- Legislation (manual edits)
create table if not exists legislation (
  id uuid primary key default gen_random_uuid(),
  chapter text,
  item text,
  article text,
  title text not null,
  dc int,
  status text not null default 'active', -- draft|active|repealed
  body text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Infrastructure store
create table if not exists infrastructure (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  category text not null, -- crafting|gathering|military|intel|diplomacy|social|economy
  tier int,
  cost numeric not null default 0,
  upkeep numeric not null default 0,
  description text,
  meta jsonb not null default '{}'::jsonb
);

create table if not exists infrastructure_owned (
  infrastructure_id uuid references infrastructure(id) on delete cascade,
  owned boolean not null default false,
  purchased_at timestamptz,
  primary key (infrastructure_id)
);

-- Units: Moonblade Guild
create table if not exists moonblade_units (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  unit_type text not null, -- guardians|archers|mages|clerics|other
  tier int not null default 1,
  power numeric not null default 1,
  cost numeric not null default 0,
  upkeep numeric not null default 0,
  meta jsonb not null default '{}'::jsonb
);

create table if not exists moonblade_roster (
  unit_id uuid references moonblade_units(id) on delete cascade,
  quantity int not null default 0,
  updated_at timestamptz not null default now(),
  primary key (unit_id)
);

-- Squads
create table if not exists squads (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  region text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists squad_members (
  squad_id uuid references squads(id) on delete cascade,
  unit_id uuid references moonblade_units(id) on delete cascade,
  quantity int not null default 0,
  primary key (squad_id, unit_id)
);

-- Dawnbreakers: intelligence units
create table if not exists dawnbreaker_units (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  role text not null, -- scout|infiltrator|spy|etc
  tier int not null default 1,
  success numeric not null default 0.5,
  cost numeric not null default 0,
  upkeep numeric not null default 0,
  meta jsonb not null default '{}'::jsonb
);

create table if not exists dawnbreaker_roster (
  unit_id uuid references dawnbreaker_units(id) on delete cascade,
  quantity int not null default 0,
  updated_at timestamptz not null default now(),
  primary key (unit_id)
);

-- Silver Council Diplomacy units
create table if not exists diplomacy_units (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  tier int not null default 1,
  influence numeric not null default 1,
  cost numeric not null default 0,
  upkeep numeric not null default 0,
  meta jsonb not null default '{}'::jsonb
);

create table if not exists diplomacy_roster (
  unit_id uuid references diplomacy_units(id) on delete cascade,
  quantity int not null default 0,
  updated_at timestamptz not null default now(),
  primary key (unit_id)
);

-- War simulator records
create table if not exists war_encounters (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  squad_id uuid references squads(id) on delete set null,
  enemy_name text,
  enemy_units jsonb not null default '[]'::jsonb, -- list of {unit_type, qty, power}
  result jsonb not null default '{}'::jsonb,
  resolved boolean not null default false
);

-- Weekly snapshot (what players see)
create table if not exists weekly_snapshots (
  week int primary key,
  created_at timestamptz not null default now(),
  snapshot jsonb not null default '{}'::jsonb
);
