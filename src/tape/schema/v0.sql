-- Tape schema v0 — embedded temporal database for long video
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
  id          INTEGER PRIMARY KEY CHECK (id = 1),
  path        TEXT NOT NULL,
  abs_path    TEXT NOT NULL,
  sha256      TEXT,
  duration_s  REAL NOT NULL,
  fps         REAL,
  width       INTEGER,
  height      INTEGER,
  has_audio   INTEGER NOT NULL DEFAULT 0,
  proxy_path  TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS timeline_bins (
  t0         REAL NOT NULL,
  t1         REAL NOT NULL,
  motion     REAL,
  audio_rms  REAL,
  audio_onset INTEGER,
  luma       REAL,
  PRIMARY KEY (t0, t1)
);

CREATE INDEX IF NOT EXISTS idx_bins_motion ON timeline_bins(motion);
CREATE INDEX IF NOT EXISTS idx_bins_audio ON timeline_bins(audio_rms);

CREATE TABLE IF NOT EXISTS segments (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  kind    TEXT NOT NULL,
  start_s REAL NOT NULL,
  end_s   REAL NOT NULL,
  score   REAL,
  source  TEXT NOT NULL,
  meta_json TEXT,
  CHECK (end_s > start_s)
);

CREATE INDEX IF NOT EXISTS idx_segments_kind ON segments(kind);
CREATE INDEX IF NOT EXISTS idx_segments_span ON segments(start_s, end_s);

CREATE TABLE IF NOT EXISTS byte_index (
  pts_s       REAL PRIMARY KEY,
  file_offset INTEGER
);
