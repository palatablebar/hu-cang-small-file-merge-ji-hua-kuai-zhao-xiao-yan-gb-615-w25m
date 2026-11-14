-- 核心表结构参考（PostgreSQL 语法，运行时不执行；建表由 SQLAlchemy create_all 完成）
-- 对应 backend/src/models/*.py：lake_table / partition / data_file / compaction_job / snapshot

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(160) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(80)  NOT NULL,
    role            VARCHAR(20)  NOT NULL,
    org             VARCHAR(120),
    created_at      TIMESTAMP    NOT NULL
);

CREATE TABLE lake_tables (
    id                   SERIAL PRIMARY KEY,
    code                 VARCHAR(64)  NOT NULL UNIQUE,
    name                 VARCHAR(120) NOT NULL,
    layer                VARCHAR(12)  NOT NULL,          -- ods/dwd/dws/dim/ads
    fmt                  VARCHAR(16)  NOT NULL,          -- iceberg/hudi/paimon
    location             VARCHAR(255) NOT NULL,
    partition_spec       VARCHAR(120) NOT NULL,
    target_bytes         INTEGER      NOT NULL DEFAULT 134217728,
    min_files            INTEGER      NOT NULL DEFAULT 5,
    flow_lag_seconds     INTEGER      NOT NULL DEFAULT 900,
    stream_window_start  VARCHAR(5)   NOT NULL DEFAULT '00:00',
    stream_window_end    VARCHAR(5)   NOT NULL DEFAULT '06:30',
    owner                VARCHAR(80),
    note                 TEXT,
    enabled              BOOLEAN      NOT NULL DEFAULT TRUE,
    last_scanned_at      TIMESTAMP,
    created_at           TIMESTAMP    NOT NULL,
    updated_at           TIMESTAMP    NOT NULL
);

CREATE TABLE partitions (
    id                  SERIAL PRIMARY KEY,
    table_id            INTEGER      NOT NULL REFERENCES lake_tables(id) ON DELETE CASCADE,
    partition_key       VARCHAR(80)  NOT NULL,           -- dt=2026-11-13/hour=03
    dt                  VARCHAR(10)  NOT NULL,
    hour                VARCHAR(2)   NOT NULL,
    file_count          INTEGER      NOT NULL DEFAULT 0,
    data_file_count     INTEGER      NOT NULL DEFAULT 0,
    delete_file_count   INTEGER      NOT NULL DEFAULT 0,
    total_bytes         BIGINT       NOT NULL DEFAULT 0, -- 单分区可超 3GB，必须 BIGINT
    total_rows          BIGINT       NOT NULL DEFAULT 0,
    small_file_count    INTEGER      NOT NULL DEFAULT 0,
    needs_rewrite       BOOLEAN      NOT NULL DEFAULT FALSE,
    scanned_at          TIMESTAMP    NOT NULL,
    UNIQUE (table_id, partition_key)
);

CREATE TABLE data_files (
    id              SERIAL PRIMARY KEY,
    table_id        INTEGER      NOT NULL REFERENCES lake_tables(id) ON DELETE CASCADE,
    partition_id    INTEGER      NOT NULL REFERENCES partitions(id) ON DELETE CASCADE,
    partition_key   VARCHAR(80)  NOT NULL,
    path            VARCHAR(255) NOT NULL,
    kind            VARCHAR(10)  NOT NULL DEFAULT 'data', -- data | delete
    bytes           BIGINT       NOT NULL DEFAULT 0,
    rows            INTEGER      NOT NULL DEFAULT 0,
    checksum        BIGINT       NOT NULL DEFAULT 0,
    file_no         INTEGER      NOT NULL DEFAULT 0,
    committed_at    TIMESTAMP    NOT NULL,
    UNIQUE (table_id, path)
);
CREATE INDEX ix_data_files_table_partition ON data_files (table_id, partition_key);

CREATE TABLE compaction_jobs (
    id                   SERIAL PRIMARY KEY,
    plan_no              VARCHAR(40) NOT NULL UNIQUE,    -- CP20261113-0001
    table_id             INTEGER     NOT NULL REFERENCES lake_tables(id) ON DELETE CASCADE,
    trigger              VARCHAR(20) NOT NULL,           -- manual/schedule/backfill
    status               VARCHAR(16) NOT NULL,           -- planned/executed/blocked/failed
    target_bytes         INTEGER     NOT NULL,
    min_files            INTEGER     NOT NULL,
    flow_lag_seconds     INTEGER     NOT NULL,
    window_start         TIMESTAMP,
    window_end           TIMESTAMP,
    operator_email       VARCHAR(160) NOT NULL,
    metrics              JSON,                           -- 算法 A 汇总（含 io_saved_ratio）
    merge_groups         JSON,                           -- [{partition_key, group_no, files, bytes, rows, ...}]
    rewrite_partitions   JSON,
    skipped_partitions   JSON,
    conflict             JSON,                           -- 冲突窗口与建议窗口
    before_snapshot_id   INTEGER,
    after_snapshot_id    INTEGER,
    verify               JSON,                           -- 算法 B 结论
    review_status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewer             VARCHAR(160),
    review_note          TEXT,
    seed_key             VARCHAR(120) UNIQUE,
    created_at           TIMESTAMP   NOT NULL,
    executed_at          TIMESTAMP
);

CREATE TABLE snapshots (
    id                  SERIAL PRIMARY KEY,
    table_id            INTEGER      NOT NULL REFERENCES lake_tables(id) ON DELETE CASCADE,
    label               VARCHAR(10)  NOT NULL,           -- before | after
    seq_no              INTEGER      NOT NULL,
    snapshot_no         VARCHAR(40)  NOT NULL,
    job_id              INTEGER,
    manifest            JSON,                            -- [{path, partition_key, kind, bytes, rows, checksum}]
    data_file_count     INTEGER      NOT NULL DEFAULT 0,
    delete_file_count   INTEGER      NOT NULL DEFAULT 0,
    total_rows          INTEGER      NOT NULL DEFAULT 0,
    checksum            BIGINT       NOT NULL DEFAULT 0,
    bytes               BIGINT       NOT NULL DEFAULT 0,
    verdict             VARCHAR(16),                     -- consistent/lossy/unverifiable
    verify              JSON,
    committed_at        TIMESTAMP    NOT NULL,
    UNIQUE (table_id, label, seq_no)
);

CREATE TABLE audit_logs (
    id            SERIAL PRIMARY KEY,
    actor_email   VARCHAR(160) NOT NULL,
    actor_role    VARCHAR(20)  NOT NULL,
    action        VARCHAR(64)  NOT NULL,
    entity        VARCHAR(40)  NOT NULL,
    entity_id     VARCHAR(64),
    detail        JSON,
    layer         VARCHAR(16)  NOT NULL DEFAULT 'domain',
    ip            VARCHAR(64),
    seed_key      VARCHAR(120) UNIQUE,
    created_at    TIMESTAMP    NOT NULL
);
