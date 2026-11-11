-- academic-faction-finder / SQLite data model
-- Scope: co-authorship ONLY. No advisor/advisee, no affiliation-interest inference.
-- Store the raw co-signed paper count and the role-weighted total.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS work (
  work_id TEXT PRIMARY KEY,
  doi     TEXT,
  title   TEXT,
  year    INTEGER,
  venue   TEXT,
  issn    TEXT,
  zone    TEXT
);

CREATE TABLE IF NOT EXISTS person (
  person_id    TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  name_key     TEXT NOT NULL,
  orcid        TEXT,
  org_keys     TEXT NOT NULL DEFAULT '[]',
  org_names    TEXT NOT NULL DEFAULT '[]',
  first_year   INTEGER,
  last_year    INTEGER,
  n_papers     INTEGER DEFAULT 0,
  review_flag  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_person_name ON person(name_key);
CREATE INDEX IF NOT EXISTS idx_person_orcid ON person(orcid);

CREATE TABLE IF NOT EXISTS person_org (
  person_id  TEXT NOT NULL,
  org_key    TEXT NOT NULL,
  org_name   TEXT,
  first_year INTEGER,
  last_year  INTEGER,
  PRIMARY KEY (person_id, org_key)
);

CREATE TABLE IF NOT EXISTS authorship (
  work_id      TEXT NOT NULL,
  person_id    TEXT NOT NULL,
  author_order INTEGER,
  is_first     TEXT NOT NULL,
  is_corresponding TEXT NOT NULL,
  role_source  TEXT,
  PRIMARY KEY (work_id, person_id)
);

-- Every merge decision is auditable. decision values:
-- orcid_match | org_match | ambiguous | orcid_conflict | new_person | unresolved | no_org_unique
CREATE TABLE IF NOT EXISTS merge_log (
  log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  name_key   TEXT,
  decision   TEXT,
  person_id  TEXT,
  work_id    TEXT,
  evidence   TEXT,
  detail     TEXT
);

-- Stores ALL pairs, including one-off collaborations.
-- Filtering by --min-collab happens at query time, so the threshold stays adjustable.
CREATE TABLE IF NOT EXISTS coauthor_edge (
  src         TEXT NOT NULL,
  dst         TEXT NOT NULL,
  n_papers    INTEGER NOT NULL,
  first_year  INTEGER,
  last_year   INTEGER,
  year_counts TEXT NOT NULL DEFAULT '{}',
  role_weight REAL NOT NULL,
  PRIMARY KEY (src, dst)
);

-- A faction is a computed community, never a hand-written label.
CREATE TABLE IF NOT EXISTS faction (
  run_id          TEXT NOT NULL,
  person_id       TEXT NOT NULL,
  community_id    INTEGER NOT NULL,
  algorithm       TEXT,
  params          TEXT,
  weighted_degree REAL,
  role            TEXT,
  PRIMARY KEY (run_id, person_id)
);

CREATE TABLE IF NOT EXISTS faction_membership (
  run_id             TEXT NOT NULL,
  person_id          TEXT NOT NULL,
  community_id       INTEGER NOT NULL,
  is_primary         INTEGER NOT NULL,
  is_base            INTEGER NOT NULL,
  role               TEXT NOT NULL,
  supporting_papers  INTEGER NOT NULL,
  community_partners INTEGER NOT NULL,
  first_year         INTEGER,
  last_year          INTEGER,
  year_counts        TEXT NOT NULL,
  affiliations       TEXT NOT NULL,
  work_ids           TEXT NOT NULL,
  PRIMARY KEY (run_id, person_id, community_id)
);

CREATE TABLE IF NOT EXISTS run_meta (
  run_id TEXT PRIMARY KEY,
  ts     TEXT,
  query  TEXT,
  params TEXT,
  stats  TEXT
);
