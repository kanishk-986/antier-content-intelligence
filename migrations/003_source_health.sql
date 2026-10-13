-- Source health. Every ingestion run records its outcome per source, so the
-- question "why did 85 of 105 sources yield nothing" is answerable from the
-- database rather than re-diagnosed by hand each time.
--
-- fetch_state records the items a source produced. Nothing recorded the runs where
-- it produced none, which is the case that matters for coverage: a 403, a
-- JavaScript-rendered listing and a genuinely quiet week look identical in a
-- corpus, and only the third is acceptable.

CREATE TABLE IF NOT EXISTS source_fetch_log (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    run_at          TEXT NOT NULL,
    status          TEXT NOT NULL,   -- ok | no_feed | no_listing | js_rendered
                                     -- | blocked | blocked_known | error
    via             TEXT,            -- feed | listing | -
    http_status     INTEGER,
    new_items       INTEGER NOT NULL DEFAULT 0,
    duplicate_items INTEGER NOT NULL DEFAULT 0,
    detail          TEXT
);

CREATE INDEX IF NOT EXISTS idx_fetch_log_source ON source_fetch_log(source_id, run_at);
CREATE INDEX IF NOT EXISTS idx_fetch_log_run ON source_fetch_log(run_at);
