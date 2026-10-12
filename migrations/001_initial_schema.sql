-- Schema from MASTER_BLUEPRINT.md section 9, implemented verbatim.
-- SQLite dialect. The Postgres translation changes column types and adds a pgvector
-- index; table and column names stay identical so the swap is an implementation of
-- src/database/store.py, not a rewrite (ARCHITECTURE.md).

-- 9.1 ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY,         -- source_id from the registry
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,
    source_type     TEXT,
    authority_score INTEGER NOT NULL,         -- section 5.2 tiers
    topics          TEXT,                     -- JSON array
    active          INTEGER NOT NULL DEFAULT 1,
    last_checked_at TEXT,                     -- drives the 10.2 efficiency rule
    last_item_at    TEXT
);

-- 9.2 ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_items (
    id            TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES sources(id),
    url           TEXT NOT NULL,
    title         TEXT,
    author        TEXT,
    published_at  TEXT,                       -- only when confirmed; never slug-inferred
    retrieved_at  TEXT NOT NULL,              -- section 33 attribution requirement
    raw_text      TEXT,
    clean_text    TEXT,
    content_hash  TEXT NOT NULL,              -- section 10.2 dedupe key
    language      TEXT,
    metadata      TEXT                        -- JSON
);
-- A story syndicated to two URLs is one item: dedupe on content, not location.
CREATE UNIQUE INDEX IF NOT EXISTS idx_content_hash ON content_items(content_hash);
CREATE INDEX IF NOT EXISTS idx_content_source     ON content_items(source_id);
CREATE INDEX IF NOT EXISTS idx_content_published  ON content_items(published_at);
CREATE INDEX IF NOT EXISTS idx_content_url        ON content_items(url);

-- 9.3 ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intelligence (
    content_id              TEXT PRIMARY KEY REFERENCES content_items(id),
    entities                TEXT,             -- JSON
    topics                  TEXT,             -- JSON
    claims                  TEXT,             -- JSON
    market_sentiment        REAL,
    institutional_sentiment REAL,
    developer_sentiment     REAL,
    regulatory_sentiment    REAL,
    enterprise_sentiment    REAL,
    community_sentiment     REAL,             -- 6th dimension per section 13
    importance_score        REAL,
    prompt_version          TEXT,             -- PROMPTS.md rule 4: traceability
    extracted_at            TEXT
);

-- 9.4 ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS narratives (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    embedding      TEXT,                      -- JSON float array; pgvector later
    first_seen_at  TEXT,
    last_seen_at   TEXT,
    velocity       REAL,
    acceleration   REAL,
    saturation     REAL,
    status         TEXT,                      -- emerging|rising|stable|declining
    baseline_rule  TEXT                       -- which zero-baseline rule applied (SCORING.md)
);
CREATE TABLE IF NOT EXISTS narrative_items (
    narrative_id TEXT NOT NULL REFERENCES narratives(id),
    content_id   TEXT NOT NULL REFERENCES content_items(id),
    similarity   REAL,
    PRIMARY KEY (narrative_id, content_id)
);

-- 9.5 ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS opportunities (
    id                   TEXT PRIMARY KEY,
    narrative_id         TEXT NOT NULL REFERENCES narratives(id),
    thesis               TEXT,
    antier_relevance     REAL,
    audience_relevance   REAL,
    commercial_relevance REAL,
    authority_potential  REAL,
    novelty              REAL,
    source_credibility   REAL,
    trend_velocity       REAL,
    whitespace           TEXT,                -- may be 'not_measured' (SCORING.md)
    opportunity_score    REAL,
    persona              TEXT,
    format               TEXT,
    status               TEXT,
    weights_version      TEXT,                -- which weights.yaml produced the score
    created_at           TEXT
);

-- 9.6 ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS qa_reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id  TEXT NOT NULL REFERENCES opportunities(id),
    ai_decision     TEXT,                     -- APPROVE|REJECT|RESEARCH_MORE
    confidence      REAL,
    evidence_issues TEXT,
    factual_issues  TEXT,
    brand_issues    TEXT,
    risk_flags      TEXT,
    human_decision  TEXT,
    reviewer        TEXT,
    reviewed_at     TEXT,
    created_at      TEXT
);

-- Section 33 audit trail. Append-only: rows are never rewritten, so an AI decision
-- and a later human override both survive.
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL,
    actor      TEXT NOT NULL,                 -- 'system' | 'llm:<model>' | reviewer
    action     TEXT NOT NULL,
    object_ref TEXT,
    detail     TEXT
);

-- Per-source fetch state for the 10.2 efficiency rule: never reprocess the whole
-- universe. Keyed by source + item url so a re-fetch is cheap to short-circuit.
CREATE TABLE IF NOT EXISTS fetch_state (
    source_id    TEXT NOT NULL REFERENCES sources(id),
    item_url     TEXT NOT NULL,
    content_hash TEXT,
    seen_at      TEXT,
    etag         TEXT,
    last_modified TEXT,
    PRIMARY KEY (source_id, item_url)
);
