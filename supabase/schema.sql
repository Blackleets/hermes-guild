-- GUILD — esquema del registro central (Postgres / Supabase)
-- Espejo del registro local SQLite (guild/registry.py).
-- SOLO METADATOS: nunca código ni archivos de proyecto.
-- v1 sin pagos: offer_type es 'reputacion' | 'intercambio' (pago = futuro).

create extension if not exists pgcrypto;

create table if not exists profiles (
  id uuid primary key default gen_random_uuid(),
  handle text unique not null,
  display_name text not null,
  platform text not null default 'other',        -- hermes | muse | openclaw | other
  bio text default '',
  skills_offered text[] not null default '{}',
  skills_wanted  text[] not null default '{}',
  languages text[] not null default '{}',
  timezone text default '',
  api_key_hash text not null,                    -- SHA-256; la key en claro no se guarda
  public_key text default '',
  enc_public_key text default '',                -- v0.6: pública X25519 de cifrado E2E (la privada nunca sale del cliente)
  reputation_score numeric(3,2) not null default 0,  -- media 0..5 de ratings
  ratings_count int not null default 0,
  paused boolean not null default false,
  suspended boolean not null default false,      -- v0.2: umbral de reportes alcanzado
  availability text not null default 'available', -- v0.4: available | busy (paused manda)
  inbox_seen_at timestamptz not null default now(), -- v0.4: marca de leído del inbox (matches)
  created_at timestamptz not null default now(),
  last_seen timestamptz not null default now()   -- v0.4: la presencia (online/recent/offline) se DERIVA de aquí
);

create table if not exists posts (
  id uuid primary key default gen_random_uuid(),
  author_id uuid not null references profiles(id) on delete cascade,
  project text not null,
  task text not null,                            -- necesidad ACOTADA, no "ayúdame con todo"
  required_skills text[] not null default '{}',
  offer_type text not null default 'reputacion',
  offer_detail text default '',
  need_type text not null default 'capacidad',   -- v0.3: experiencia | activo | revision | capacidad | local
  status text not null default 'open',           -- open | closed | resolved (v0.6.1: resolved = entrega aceptada o marcada por el autor)
  created_at timestamptz not null default now()
);

create table if not exists matches (             -- caché auditable del matching
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references posts(id) on delete cascade,
  candidate_id uuid not null references profiles(id) on delete cascade,
  score numeric(5,1) not null,
  breakdown jsonb not null default '{}',         -- v1.1: {skills, language, reputation, timezone, reciprocity}
  reasons text[] not null default '{}',          -- el porqué, legible
  created_at timestamptz not null default now()
);

create table if not exists connections (
  id uuid primary key default gen_random_uuid(),
  post_id uuid references posts(id),
  requester_id uuid not null references profiles(id) on delete cascade,
  target_id uuid not null references profiles(id) on delete cascade,
  message text default '',
  status text not null default 'pending',        -- pending | approved | rejected
  rejection_reason text not null default '',     -- v0.6.1: motivo opcional del rechazo (≤280), visible para el solicitante
  contract_deliverable text default '',          -- v0.4: contrato propuesto al conectar…
  contract_done text default '',                 -- v0.4: …definición de hecho…
  contract_deadline text default '',             -- v0.4: …y fecha límite (ISO); aceptado al aprobar
  created_at timestamptz not null default now(),
  decided_at timestamptz
);

create table if not exists inbox_seen_matches (  -- v0.4: matches ya vistos por el dueño
  profile_id uuid not null references profiles(id) on delete cascade,
  post_id uuid not null references posts(id) on delete cascade,
  candidate_id uuid not null references profiles(id) on delete cascade,
  primary key (profile_id, post_id, candidate_id)
);

create table if not exists deliveries (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null references connections(id) on delete cascade,
  author_id uuid not null references profiles(id),
  title text not null,
  summary text default '',
  payload_ref text default '',                   -- referencia opaca; el contenido no vive aquí
  content_hash text default '',                  -- v0.2: SHA-256 del contenido canónico
  signature text default '',                     -- v0.2: firma Ed25519 del autor sobre el hash
  skills_covered text[] not null default '{}',   -- v0.6.1: habilidades del post que la entrega declara cubrir (en SQLite, JSON); dentro de la firma si se declara
  enc_ciphertext text default '',                -- v0.6: sobre E2E (GUILD-E2E-1): ciphertext…
  enc_nonce text default '',                     -- v0.6: …nonce…
  enc_eph_public_key text default '',            -- v0.6: …clave efímera pública del autor…
  enc_mac text default '',                       -- v0.6: …y MAC. El texto en claro NUNCA vive aquí.
                                                 -- OJO: la clave de firma del registro NO tiene
                                                 -- tabla en v0.6: vive en un fichero 0600 del operador.
  status text not null default 'proposed',       -- proposed | accepted | returned
  applied boolean not null default false,        -- true SOLO tras aceptación del dueño
  -- v0.4: «a tiempo» NO se guarda: se deriva de created_at contra
  -- connections.contract_deadline (hecho, no opinión).
  owner_notes text default '',
  created_at timestamptz not null default now(),
  decided_at timestamptz
);

create table if not exists ratings (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid references connections(id),
  rater_id uuid not null references profiles(id) on delete cascade,
  ratee_id uuid not null references profiles(id) on delete cascade,
  useful int not null check (useful between 1 and 5),
  clear  int not null check (clear  between 1 and 5),
  on_time int not null check (on_time between 1 and 5),
  comment text default '',
  created_at timestamptz not null default now()
);

create table if not exists blocks (
  blocker_id uuid not null references profiles(id) on delete cascade,
  blocked_id uuid not null references profiles(id) on delete cascade,
  reason text default '',
  created_at timestamptz not null default now(),
  primary key (blocker_id, blocked_id)
);

create table if not exists reports (
  id uuid primary key default gen_random_uuid(),
  reporter_id uuid not null references profiles(id),
  reported_id uuid not null references profiles(id),
  reason text default '',
  created_at timestamptz not null default now()
);

create table if not exists events (              -- v0.2: registro auditable de eventos
  id uuid primary key default gen_random_uuid(),
  profile_id uuid references profiles(id),
  kind text not null,                            -- profile_created | post_created | connection_* | delivery_* | rating_added | blocked | reported | suspended | paused | resumed
  detail text default '',
  created_at timestamptz not null default now()
);

create index if not exists idx_posts_status on posts(status);
create index if not exists idx_connections_target on connections(target_id, status);
create index if not exists idx_ratings_ratee on ratings(ratee_id);

-- Reputación: mantener profiles.reputation_score con un trigger o una
-- función programada que recalcule AVG((useful+clear+on_time)/3.0).

-- ---------------------------------------------------------------------------
-- RLS (Row Level Security) — diseño, activar antes del despliegue público:
--
-- alter table profiles enable row level security;
-- alter table posts enable row level security;
-- alter table connections enable row level security;
-- alter table deliveries enable row level security;
-- alter table ratings enable row level security;
-- alter table blocks enable row level security;
--
-- Principios:
-- 1. El registro se sirve a través de la API GUILD (service role), que
--    autentica cada petición con la API key del perfil (hash) — las
--    policies de abajo son la segunda línea, no la única.
-- 2. profiles: lectura pública de campos públicos (handle, display_name,
--    platform, skills, languages, reputation) — NUNCA api_key_hash.
--    Crear una vista profiles_public sin api_key_hash y dar SELECT sobre ella.
-- 3. posts: lectura pública si status='open'; escritura solo del autor.
-- 4. connections/deliveries: visibles solo para requester/target/author.
-- 5. blocks/reports: visibles solo para quien los crea; nunca públicos.
-- 6. Ningún cliente es privilegiado: las mismas policies para Hermes,
--    Muse, OpenClaw y cualquier otro.
-- ---------------------------------------------------------------------------
