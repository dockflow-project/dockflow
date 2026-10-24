"""One versioned schema for domain state, artifact publication and cache coordination."""

SCHEMA_VERSION = 5
SCHEMA_LOCK = 0x444F434B44415441
STATE_SCHEMA = [
    "CREATE TABLE dockflow_artifact_records (project_id TEXT NOT NULL, storage_id TEXT NOT NULL, namespace TEXT NOT NULL, record_key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(project_id,storage_id,namespace,record_key))",
    "CREATE TABLE dockflow_project_counters (project_id TEXT PRIMARY KEY, sequence BIGINT NOT NULL CHECK(sequence>=0))",
    "CREATE TABLE dockflow_run_owners (project_id TEXT NOT NULL, run_id TEXT NOT NULL, owner_id TEXT NOT NULL, fence BIGINT NOT NULL CHECK(fence>0), lease_expires_at DOUBLE PRECISION NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)), PRIMARY KEY(project_id,run_id))",
    "CREATE INDEX dockflow_run_expiry ON dockflow_run_owners(project_id,active,lease_expires_at)",
    "CREATE TABLE dockflow_project_metadata (project_id TEXT NOT NULL, name TEXT NOT NULL, value {binary} NOT NULL, PRIMARY KEY(project_id,name))",
    "CREATE TABLE dockflow_events (project_id TEXT NOT NULL, sequence BIGINT NOT NULL CHECK(sequence>0), value TEXT NOT NULL, PRIMARY KEY(project_id,sequence))",
    "CREATE TABLE dockflow_definition_sources (project_id TEXT NOT NULL, definition_id TEXT NOT NULL, value {binary} NOT NULL, PRIMARY KEY(project_id,definition_id))",
    "CREATE TABLE dockflow_output_sets (project_id TEXT NOT NULL, attempt_id TEXT NOT NULL, value {binary} NOT NULL, PRIMARY KEY(project_id,attempt_id))",
    "CREATE TABLE dockflow_cache_observations (project_id TEXT NOT NULL, attempt_id TEXT NOT NULL, value {binary} NOT NULL, PRIMARY KEY(project_id,attempt_id))",
    "CREATE TABLE dockflow_log_snapshots (project_id TEXT NOT NULL, attempt_id TEXT NOT NULL, stream TEXT NOT NULL CHECK(stream IN ('stdout','stderr')), value {binary} NOT NULL, PRIMARY KEY(project_id,attempt_id,stream))",
    "CREATE TABLE dockflow_state_resources (project_id TEXT NOT NULL, collection TEXT NOT NULL, public_id TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(project_id,collection,public_id))",
    "CREATE TABLE dockflow_resource_inputs (project_id TEXT NOT NULL, collection TEXT NOT NULL, public_id TEXT NOT NULL, input_name TEXT NOT NULL, artifact_id TEXT NOT NULL, PRIMARY KEY(project_id,collection,public_id,input_name))",
    "CREATE INDEX dockflow_input_consumers ON dockflow_resource_inputs(project_id,collection,artifact_id,public_id)",
    "CREATE TABLE dockflow_log_entries (project_id TEXT NOT NULL, sequence BIGINT NOT NULL, run_id TEXT NOT NULL, task_id TEXT, attempt_id TEXT, value TEXT NOT NULL, PRIMARY KEY(project_id,sequence))",
    "CREATE INDEX dockflow_log_run ON dockflow_log_entries(project_id,run_id,sequence)",
    "CREATE INDEX dockflow_log_task ON dockflow_log_entries(project_id,run_id,task_id,sequence)",
    "CREATE INDEX dockflow_log_attempt ON dockflow_log_entries(project_id,run_id,attempt_id,sequence)",
    "CREATE TABLE dockflow_state_ids (project_id TEXT NOT NULL, collection TEXT NOT NULL, public_id TEXT NOT NULL, numeric_id BIGINT NOT NULL, PRIMARY KEY(project_id,collection,public_id), UNIQUE(project_id,collection,numeric_id))",
    "CREATE TABLE dockflow_state_owners (project_id TEXT PRIMARY KEY, value {binary} NOT NULL)",
]
PROJECT_TABLES = (
    "dockflow_artifact_records",
    "dockflow_project_counters",
    "dockflow_project_metadata",
    "dockflow_events",
    "dockflow_definition_sources",
    "dockflow_output_sets",
    "dockflow_cache_observations",
    "dockflow_log_snapshots",
    "dockflow_state_resources",
    "dockflow_state_ids",
    "dockflow_resource_inputs",
    "dockflow_log_entries",
    "df_cache_scopes",
    "df_cache_entries",
    "df_cache_attempts",
    "df_cache_artifacts",
)
REQUIRED_TABLES = {
    *PROJECT_TABLES,
    "dockflow_state_owners",
    "dockflow_run_owners",
    "dockflow_schema",
}
REQUIRED_INDEXES = {
    "df_cache_active",
    "df_cache_expiry",
    "df_cache_history",
    "df_cache_retry",
    "dockflow_run_expiry",
}

CACHE_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS df_cache_scopes (
        scope_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, configuration TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS df_cache_entries (
        scope_id TEXT NOT NULL REFERENCES df_cache_scopes(scope_id),
        cache_key TEXT NOT NULL, key_schema_version TEXT NOT NULL,
        generation BIGINT NOT NULL CHECK(generation >= 0),
        revision BIGINT NOT NULL CHECK(revision >= 0),
        current_attempt_id TEXT, published_artifact_id TEXT,
        episode_id TEXT NOT NULL, attempts_started INTEGER NOT NULL CHECK(attempts_started >= 0),
        next_retry_at DOUBLE PRECISION NOT NULL, blocked_reason TEXT,
        created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL,
        PRIMARY KEY(scope_id, cache_key))""",
    """CREATE TABLE IF NOT EXISTS df_cache_attempts (
        attempt_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, cache_key TEXT NOT NULL,
        episode_id TEXT NOT NULL, fencing_token BIGINT NOT NULL CHECK(fencing_token > 0),
        owner_id TEXT NOT NULL, run_id TEXT NOT NULL, step_id TEXT NOT NULL,
        claim_request_id TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('RUNNING','VALIDATING','SUCCEEDED','FAILED','CANCELLED','EXPIRED')),
        lease_expires_at DOUBLE PRECISION NOT NULL, heartbeat_at DOUBLE PRECISION NOT NULL,
        started_at DOUBLE PRECISION NOT NULL, finished_at DOUBLE PRECISION,
        artifact_id TEXT, error_code TEXT, retryable INTEGER,
        FOREIGN KEY(scope_id, cache_key) REFERENCES df_cache_entries(scope_id, cache_key),
        UNIQUE(scope_id, cache_key, fencing_token))""",
    """CREATE UNIQUE INDEX IF NOT EXISTS df_cache_active
        ON df_cache_attempts(scope_id, cache_key) WHERE state IN ('RUNNING','VALIDATING')""",
    """CREATE TABLE IF NOT EXISTS df_cache_artifacts (
        artifact_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, cache_key TEXT NOT NULL,
        producer_attempt_id TEXT NOT NULL UNIQUE REFERENCES df_cache_attempts(attempt_id),
        state TEXT NOT NULL CHECK(state IN ('AVAILABLE','INVALID')),
        storage_identity TEXT NOT NULL, manifest TEXT NOT NULL, manifest_digest TEXT NOT NULL,
        validation_version TEXT NOT NULL, validated_at DOUBLE PRECISION NOT NULL,
        published_at DOUBLE PRECISION NOT NULL, valid_until DOUBLE PRECISION,
        invalidated_at DOUBLE PRECISION, invalidation_reason TEXT,
        FOREIGN KEY(scope_id, cache_key) REFERENCES df_cache_entries(scope_id, cache_key))""",
    "CREATE INDEX IF NOT EXISTS df_cache_expiry ON df_cache_attempts(state, lease_expires_at)",
    "CREATE INDEX IF NOT EXISTS df_cache_history ON df_cache_attempts(scope_id, cache_key, fencing_token)",
    "CREATE INDEX IF NOT EXISTS df_cache_retry ON df_cache_entries(next_retry_at)",
]

# Scalar query indexes leave canonical JSON text intact, including numeric types
# and signed zero. PostgreSQL JSON casts are a query view, not persisted authority.
RESOURCE_QUERY_FIELDS = (
    "name",
    "state",
    "run_id",
    "task_id",
    "pipeline_id",
    "definition_id",
    "experiment_id",
    "availability",
    "type.schema_title",
    "idempotency_key",
    "sha256",
    "signature.value",
    "reconciliation_required",
    "registration",
)
REQUIRED_INDEXES.update(
    {
        "dockflow_input_consumers",
        "dockflow_log_run",
        "dockflow_log_task",
        "dockflow_log_attempt",
        "dockflow_resource_created",
        "dockflow_resource_name_order",
        "dockflow_queue",
        "dockflow_event_lookup",
        "dockflow_event_attempt",
    }
)
REQUIRED_INDEXES.update(
    "dockflow_query_" + field.replace(".", "_") for field in RESOURCE_QUERY_FIELDS
)
