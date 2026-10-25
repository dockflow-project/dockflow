"""Pipelines-owned execution/cache schema, query expressions and export selection."""

from dockflow_artifacts.persistence import ARTIFACT_SCHEMA, ARTIFACT_TABLE
from dockflow_artifacts.persistence import initialize_schema as initialize_artifacts
from dockflow_artifacts.persistence import project_rows as artifact_rows
from dockflow_core import Database, Schema
from dockflow_core.errors import DockflowError

SCHEMA_VERSION = 1
STATE_SCHEMA = [
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
    ARTIFACT_TABLE,
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


def resource_sort_name(adapter, column="value", collection="collection"):
    version = adapter.json_text(column, "version_name")
    name = adapter.json_text(column, "name")
    display = adapter.json_text(column, "display_name")
    return f"CASE WHEN {collection}='definitions' THEN COALESCE(NULLIF({version},''),{name},'') WHEN {collection}='pipelines' THEN COALESCE({name},'') ELSE COALESCE({display},'') END"


def event_field(adapter, field):
    paths = {
        "kind": ("event_kind", "kind"),
        "run_id": (
            "payload.run_id",
            "payload.marker.run_id",
            "payload.manifest.producer.run_id",
        ),
        "attempt_id": (
            "payload.attempt_id",
            "payload.marker.attempt_id",
            "payload.manifest.producer.attempt_id",
        ),
    }[field]
    return (
        "COALESCE(" + ",".join(adapter.json_text("value", path) for path in paths) + ")"
    )


def query_indexes(adapter, connection):
    created = adapter.text_order(
        f"COALESCE({adapter.json_text('value', 'created_at')},'')"
    )
    name = adapter.text_order(resource_sort_name(adapter))
    connection.execute(
        f"CREATE INDEX dockflow_resource_created ON dockflow_state_resources(project_id,collection,{created} DESC,public_id)"
    )
    connection.execute(
        f"CREATE INDEX dockflow_resource_name_order ON dockflow_state_resources(project_id,collection,{name},public_id)"
    )
    for field in RESOURCE_QUERY_FIELDS:
        identifier = "dockflow_query_" + field.replace(".", "_")
        expression = adapter.json_text("value", field)
        connection.execute(
            f"CREATE INDEX {identifier} ON dockflow_state_resources(project_id,collection,{expression},{created} DESC,public_id)"
        )
    state = adapter.json_text("value", "state")
    sequence = f"CAST({adapter.json_text('value', 'acceptance_sequence')} AS BIGINT)"
    connection.execute(
        f"CREATE INDEX dockflow_queue ON dockflow_state_resources(project_id,collection,{state},{sequence},public_id)"
    )
    event = event_field(adapter, "kind")
    run = event_field(adapter, "run_id")
    attempt = event_field(adapter, "attempt_id")
    connection.execute(
        f"CREATE INDEX dockflow_event_lookup ON dockflow_events(project_id,{event},{run},{attempt},sequence)"
    )

    connection.execute(
        f"CREATE INDEX dockflow_event_attempt ON dockflow_events(project_id,{event},{attempt},sequence)"
    )


def project_rows(adapter, connection, project_id: str):
    """Portable project export including all cache namespaces, excluding owners."""
    yield from artifact_rows(adapter, connection, project_id)
    for table in PROJECT_TABLES:
        if table == ARTIFACT_TABLE:
            continue
        predicate = (
            "project_id=?"
            if table.startswith("dockflow_") or table == "df_cache_scopes"
            else "scope_id IN (SELECT scope_id FROM df_cache_scopes WHERE project_id=?)"
        )
        cursor = adapter.execute(
            connection, f"SELECT * FROM {table} WHERE {predicate}", (project_id,)
        )
        columns = [column[0] for column in cursor.description]
        yield table, columns, cursor


PIPELINE_SCHEMA = Schema(
    name="pipelines",
    version=SCHEMA_VERSION,
    statements=tuple(STATE_SCHEMA + CACHE_SCHEMA),
    tables=frozenset(REQUIRED_TABLES - {ARTIFACT_TABLE}),
    indexes=frozenset(REQUIRED_INDEXES),
    initialize=query_indexes,
)


def validate_schema(adapter: Database, connection) -> None:
    adapter.validate_schema(connection, ARTIFACT_SCHEMA)
    adapter.validate_schema(connection, PIPELINE_SCHEMA)


def initialize_schema(adapter: Database, connection) -> None:
    if {"dockflow_schema", "df_cache_schema"} & adapter.tables(connection):
        raise DockflowError("Legacy database requires fresh state", "CONFLICT", 409)
    initialize_artifacts(adapter, connection)
    adapter.initialize_schema(connection, PIPELINE_SCHEMA)
