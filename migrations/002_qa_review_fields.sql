-- Section 19's decision object carries `problems` and the questions that failed.
-- The section 9.6 column list predates that detail, and stuffing them into
-- risk_flags would make section 27's "rejected topics with reasons" unreadable and
-- section 30's feedback loop unparseable. Added as first-class columns instead.
--
-- SQLite has no IF NOT EXISTS for ADD COLUMN, so the store applies these defensively
-- and ignores a duplicate-column error, which keeps migrate() idempotent.
ALTER TABLE qa_reviews ADD COLUMN problems TEXT;
ALTER TABLE qa_reviews ADD COLUMN failed_questions TEXT;
ALTER TABLE qa_reviews ADD COLUMN prompt_version TEXT;
