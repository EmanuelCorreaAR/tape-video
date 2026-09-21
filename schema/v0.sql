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

-- Fixed temporal grid (default 1s bins). Cheap signals live here.
CREATE TABLE IF NOT EXISTS timeline_bins (
  t0         REAL NOT NULL,
  t1         REAL NOT NULL,
  motion     REAL,          -- 0..1 normalized frame-diff energy
  audio_rms  REAL,          -- 0..1 normalized RMS
  audio_onset INTEGER,      -- 1 if onset-ish spike vs previous bin
  luma       REAL,          -- mean luminance 0..1
  PRIMARY KEY (t0, t1)
);

CREATE INDEX IF NOT EXISTS idx_bins_motion ON timeline_bins(motion);
CREATE INDEX IF NOT EXISTS idx_bins_audio ON timeline_bins(audio_rms);

-- Semantic / derived intervals (activity, speech, plugins, manual)
CREATE TABLE IF NOT EXISTS segments (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  kind    TEXT NOT NULL,     -- e.g. activity, silence, speech, custom
  start_s REAL NOT NULL,
  end_s   REAL NOT NULL,
  score   REAL,
  source  TEXT NOT NULL,     -- pipeline that produced it
  meta_json TEXT,
  CHECK (end_s > start_s)
);

CREATE INDEX IF NOT EXISTS idx_segments_kind ON segments(kind);
CREATE INDEX IF NOT EXISTS idx_segments_span ON segments(start_s, end_s);

-- Optional map for cheap seeking / future byte-range work
CREATE TABLE IF NOT EXISTS byte_index (
  pts_s       REAL PRIMARY KEY,
  file_offset INTEGER
);
