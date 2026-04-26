-- =============================================================================
-- 001_initial_schema.sql — Stocxi initial database schema
--
-- Run this once in the Supabase SQL editor (or psql) to create all tables.
-- All tables are in the public schema (Supabase default).
--
-- Table overview:
--   stocks            — master reference table for NSE symbols + BSE codes
--   fundamental_cache — slow-changing fundamental data (ratios, statements, holdings)
--   technical_cache   — pre-computed EOD technical indicators
--   nodes             — per-analysis data nodes (partitioned by month)
--   node_edges        — knowledge-graph edges between nodes
--   analyses          — full audit log for every analysis run (partitioned by month)
--
-- Partitioning note:
--   nodes and analyses are RANGE-partitioned by date.
--   You must CREATE new monthly partitions before data arrives for that month.
--   See the partition_maintenance section at the bottom of this file.
-- =============================================================================

-- Enable pgcrypto for gen_random_uuid() (already present in Supabase)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- 1. stocks — master reference table
-- =============================================================================

CREATE TABLE IF NOT EXISTS stocks (
    symbol              VARCHAR(20)  PRIMARY KEY,   -- NSE symbol, e.g. "RELIANCE"
    bse_code            VARCHAR(10),                -- BSE scrip code, e.g. "500325"
    company_name        VARCHAR(200) NOT NULL,
    sector              VARCHAR(100),
    industry            VARCHAR(100),
    yfinance_ticker     VARCHAR(30),                -- e.g. "RELIANCE.NS" or alt from alt_tickers.yaml
    market_cap_tier     VARCHAR(10)
        CHECK (market_cap_tier IN ('large', 'mid', 'small', 'micro')),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    last_verified       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stocks_bse    ON stocks (bse_code);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks (sector);
CREATE INDEX IF NOT EXISTS idx_stocks_tier   ON stocks (market_cap_tier);

-- Auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER stocks_updated_at
    BEFORE UPDATE ON stocks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =============================================================================
-- 2. fundamental_cache — slow-changing fundamental data
-- =============================================================================
-- TTLs enforced by expires_at column. Stale rows are filtered in queries
-- (WHERE expires_at > NOW()) and cleaned up by a nightly cron.
-- UNIQUE(symbol, data_type, source_id) — UPSERT keeps table small; no partitioning needed.

CREATE TABLE IF NOT EXISTS fundamental_cache (
    id              BIGSERIAL    PRIMARY KEY,
    symbol          VARCHAR(20)  NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    data_type       VARCHAR(50)  NOT NULL,  -- "ratios" | "quarterly_pl" | "annual_pl" | "balance_sheet" | "cash_flow" | "shareholding"
    source_id       VARCHAR(30)  NOT NULL,  -- "bse_library" | "screener_in" | "yfinance_fundamentals"
    source_type     VARCHAR(20),            -- "consolidated" | "standalone" (for screener data)
    confidence      FLOAT        NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    data            JSONB        NOT NULL,  -- full raw payload from source
    period_latest   VARCHAR(20),            -- most recent period in payload, e.g. "Mar 2025"
    fetched_at      TIMESTAMPTZ  NOT NULL,
    expires_at      TIMESTAMPTZ  NOT NULL,  -- fetched_at + TTL from sources.yaml

    UNIQUE (symbol, data_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_fund_cache_symbol  ON fundamental_cache (symbol, data_type);
CREATE INDEX IF NOT EXISTS idx_fund_cache_expires ON fundamental_cache (expires_at);

-- =============================================================================
-- 3. technical_cache — pre-computed EOD technical indicators
-- =============================================================================
-- Populated by EOD cron at 4:00 PM IST for top-500 stocks, on-demand for rest.
-- Old rows are deleted where as_of_date < NOW() - 90 days (nightly cleanup).

CREATE TABLE IF NOT EXISTS technical_cache (
    id              BIGSERIAL    PRIMARY KEY,
    symbol          VARCHAR(20)  NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    indicator       VARCHAR(30)  NOT NULL,  -- e.g. "RSI_14", "MACD", "SMA_200"
    value_raw       JSONB        NOT NULL,  -- computed result (numeric or structured)
    signal          VARCHAR(10)  NOT NULL CHECK (signal IN ('positive', 'negative', 'neutral')),
    as_of_date      DATE         NOT NULL,
    computed_at     TIMESTAMPTZ  NOT NULL,

    UNIQUE (symbol, indicator, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_tech_cache_symbol_date ON technical_cache (symbol, as_of_date DESC);

-- =============================================================================
-- 4. nodes — per-analysis data nodes (partitioned by as_of_date)
-- =============================================================================
-- node_id is the deterministic key: "{stock}|{category}|{name}|{as_of_date}"
-- Same (stock, category, name, date) tuple = idempotent insert (ON CONFLICT DO NOTHING).

CREATE TABLE IF NOT EXISTS nodes (
    node_id             VARCHAR(200) NOT NULL,  -- partition key must be in PK
    stock               VARCHAR(20)  NOT NULL,
    category            VARCHAR(20)  NOT NULL CHECK (category IN ('technical', 'fundamental', 'news', 'announcement', 'context')),
    name                VARCHAR(50)  NOT NULL,
    value               VARCHAR(200) NOT NULL,  -- human-readable display string
    value_raw           JSONB        NOT NULL,  -- original source payload for audit
    signal              VARCHAR(10)  NOT NULL CHECK (signal IN ('positive', 'negative', 'neutral')),
    confidence          FLOAT        NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    source_id           VARCHAR(30)  NOT NULL,
    source_url          VARCHAR(500),
    horizon_relevance   VARCHAR(10)  NOT NULL CHECK (horizon_relevance IN ('short', 'long', 'both')),
    weight              FLOAT        NOT NULL DEFAULT 0.0,
    weight_version      VARCHAR(20)  NOT NULL,
    schema_version      INT          NOT NULL DEFAULT 1,
    fetched_at_ist      TIMESTAMPTZ  NOT NULL,
    as_of_date          DATE         NOT NULL,
    sanitized           BOOLEAN      NOT NULL DEFAULT FALSE,

    PRIMARY KEY (node_id, as_of_date)
) PARTITION BY RANGE (as_of_date);

CREATE INDEX IF NOT EXISTS idx_nodes_stock_date       ON nodes (stock, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_stock_cat_date   ON nodes (stock, category, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_fetched          ON nodes (fetched_at_ist DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_category         ON nodes (category, as_of_date DESC);

-- =============================================================================
-- 5. node_edges — knowledge-graph edges between nodes
-- =============================================================================
-- One row per directed edge between two nodes, scoped to one analysis_id.

CREATE TABLE IF NOT EXISTS node_edges (
    id              BIGSERIAL    PRIMARY KEY,
    from_id         VARCHAR(200) NOT NULL,      -- references nodes(node_id) — no FK (partitioned)
    to_id           VARCHAR(200) NOT NULL,
    relation        VARCHAR(20)  NOT NULL
        CHECK (relation IN ('supports', 'contradicts', 'derived_from', 'correlates', 'caused_by', 'part_of', 'same_domain')),
    strength        FLOAT        NOT NULL CHECK (strength >= 0 AND strength <= 1),
    analysis_id     UUID         NOT NULL,
    built_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_edges_analysis ON node_edges (analysis_id);
CREATE INDEX IF NOT EXISTS idx_edges_from     ON node_edges (from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to       ON node_edges (to_id);

-- =============================================================================
-- 6. analyses — full audit log for every analysis run (partitioned by created_at_ist)
-- =============================================================================
-- Append-only. Never update. Every row is a complete point-in-time snapshot of one
-- analysis so it can be replayed deterministically.

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id         UUID         NOT NULL,   -- partition key in PK
    stock               VARCHAR(20)  NOT NULL,
    profile_hash        VARCHAR(64)  NOT NULL,   -- sha256(horizon + risk)
    as_of_date          DATE         NOT NULL,
    data_hash           VARCHAR(64)  NOT NULL,   -- sha256(sorted node_ids)
    prompt_version      VARCHAR(20)  NOT NULL,
    weight_version      VARCHAR(20)  NOT NULL,
    model_id            VARCHAR(100) NOT NULL,
    input_nodes         JSONB        NOT NULL,   -- array of node_ids used
    full_prompt         TEXT         NOT NULL,   -- exact prompt sent to LLM (anonymized)
    raw_output          TEXT         NOT NULL,   -- raw LLM JSON response string
    final_output        JSONB        NOT NULL,   -- structured AnalysisResult
    conflicts_resolved  JSONB,                   -- list of ContradictionLink objects
    stripped_claims     INT          NOT NULL DEFAULT 0,
    low_fidelity        BOOLEAN      NOT NULL DEFAULT FALSE,
    cache_key           VARCHAR(300),            -- Redis key this analysis was stored under
    latency_ms          INT,
    tokens_in           INT,
    tokens_out          INT,
    created_at_ist      TIMESTAMPTZ  NOT NULL,

    PRIMARY KEY (analysis_id, created_at_ist)
) PARTITION BY RANGE (created_at_ist);

CREATE INDEX IF NOT EXISTS idx_analyses_stock  ON analyses (stock, created_at_ist DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_cache  ON analyses (cache_key);
CREATE INDEX IF NOT EXISTS idx_analyses_date   ON analyses (as_of_date DESC);

-- =============================================================================
-- 7. Initial monthly partitions
-- =============================================================================
-- Add a new partition each month before data arrives. The maintenance section
-- below shows the pattern to repeat.

-- nodes partitions
CREATE TABLE IF NOT EXISTS nodes_2026_04
    PARTITION OF nodes FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS nodes_2026_05
    PARTITION OF nodes FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS nodes_2026_06
    PARTITION OF nodes FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

-- analyses partitions
CREATE TABLE IF NOT EXISTS analyses_2026_04
    PARTITION OF analyses FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS analyses_2026_05
    PARTITION OF analyses FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS analyses_2026_06
    PARTITION OF analyses FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

-- =============================================================================
-- 8. Partition maintenance template (run monthly)
-- =============================================================================
-- Replace YYYY_MM and dates accordingly. Run before the month starts.
--
--   CREATE TABLE nodes_YYYY_MM
--       PARTITION OF nodes FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM-01' + interval '1 month');
--
--   CREATE TABLE analyses_YYYY_MM
--       PARTITION OF analyses FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM-01' + interval '1 month');
--
-- Cleanup (run monthly to drop data older than 3 years for nodes, 90 days for technical_cache):
--
--   DELETE FROM technical_cache WHERE as_of_date < NOW() - INTERVAL '90 days';
--   -- Drop old node partitions (check data is not needed for active backtests first)
--   -- DROP TABLE nodes_YYYY_MM;
-- =============================================================================
