"""Project-scoped ID/name search expressions and bounded recent filter options."""

from dockflow_core.errors import DockflowError

COLLECTIONS = {
    "pipelines",
    "definitions",
    "components",
    "experiments",
    "runs",
    "tasks",
    "attempts",
    "artifacts",
}


def validate_search(value):
    if not isinstance(value, str) or len(value) > 256:
        raise DockflowError("Search must be a string of at most 256 characters")
    return value


def expressions(database, collection):
    """Only authoritative, non-retired direct context participates in names."""
    adapter = database.adapter

    def field(alias, path):
        return adapter.json_text(alias + ".value", path)

    def lookup(alias, target, identifier, expression):
        active = " AND ".join(
            field(alias, key) + " IS NULL" for key in ("deleted_at", "retiring_plan_id")
        )
        return (
            f"(SELECT {expression} FROM dockflow_state_resources {alias} "
            f"WHERE {alias}.project_id=r.project_id AND {alias}.collection='{target}' "
            f"AND {alias}.public_id={identifier} AND {active})"
        )

    def pipeline(alias):
        # KFP camelCase keys are fixed schema constants, never request paths.
        paths = (
            "pipeline_spec.pipelineInfo.name",
            "pipeline_spec.pipelineSpec.pipelineInfo.name",
        )
        values = [
            f"({alias}.value::jsonb #>> '{{{path.replace('.', ',')}}}')"
            if database.backend == "postgresql"
            else f"CAST(json_extract(CAST({alias}.value AS TEXT), '$.{path}') AS TEXT)"
            for path in paths
        ]
        return "COALESCE(" + ",".join([*values, field(alias, "name")]) + ")"

    own = [field("r", "display_name"), field("r", "name")]
    names = list(own)
    if collection in {"runs", "pipelines"}:
        key = "definition_id" if collection == "runs" else "default_version_id"
        names.append(lookup("d", "definitions", field("r", key), pipeline("d")))
    elif collection == "definitions":
        names += [pipeline("r"), field("r", "version_name")]
    elif collection in {"tasks", "attempts"}:
        component = lookup(
            "c", "components", field("t", "component_id"), field("c", "name")
        )
        if collection == "attempts":
            names += [
                lookup("t", "tasks", field("r", "task_id"), component),
                lookup("t", "tasks", field("r", "task_id"), field("t", "name")),
            ]
        else:
            names.append(
                lookup(
                    "c", "components", field("r", "component_id"), field("c", "name")
                )
            )
    elif collection == "artifacts":
        names += [field("r", "version"), field("r", "upload.filename")]
    # Include invocation names and human context in captions, preserving exact ID.
    caption = " || ' · ' || ".join(f"COALESCE({name},'')" for name in names)
    created = field("r", "created_at")
    recent = (
        f"COALESCE({field('r', 'started_at')},{created},'')"
        if collection in {"runs", "tasks", "attempts"}
        else f"COALESCE({created},'')"
    )
    return names, caption, recent


def search_predicate(database, collection, value):
    value = validate_search(value)
    names, _, _ = expressions(database, collection)
    pattern = (
        "%"
        + value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        + "%"
    )
    fields = ["r.public_id", *names]
    return "(" + " OR ".join(
        f"LOWER(COALESCE({field},'')) LIKE ? ESCAPE '\\'" for field in fields
    ) + ")", [pattern] * len(fields)


def filter_options(core, collection, search="", field=None, **scopes):
    if (
        collection not in COLLECTIONS
        or field not in {None, "type"}
        or (field and collection != "artifacts")
    ):
        raise DockflowError("Unknown filter option collection or field")
    validate_search(search)
    db = core.store.database
    predicate, values = db.queries._predicate(
        collection, {"search": search} if search and not field else {}
    )
    allowed_scopes = {
        "components": {"definition_id"},
        "runs": {"definition_id", "experiment_id"},
        "definitions": {"experiment_id"},
        "tasks": {"run_id"},
        "attempts": {"run_id", "task_id"},
    }.get(collection, set())
    if set(scopes) - allowed_scopes or (field and scopes):
        raise DockflowError("Unsupported filter option scope")
    for key, value in scopes.items():
        parent = {
            "definition_id": "definitions",
            "experiment_id": "experiments",
            "run_id": "runs",
            "task_id": "tasks",
        }[key]
        core.store._validate_resource(parent, {key: value})
        live_parent = " AND ".join(
            db.adapter.json_text("p.value", name) + " IS NULL"
            for name in ("deleted_at", "retiring_plan_id")
        )
        predicate += f" AND EXISTS (SELECT 1 FROM dockflow_state_resources p WHERE p.project_id=r.project_id AND p.collection=? AND p.public_id=? AND {live_parent})"
        values.extend([parent, value])
        if collection == "definitions":
            experiment = db.adapter.json_text("u.value", "experiment_id")
            definition = db.adapter.json_text("u.value", "definition_id")
            live_run = " AND ".join(
                db.adapter.json_text("u.value", name) + " IS NULL"
                for name in ("deleted_at", "retiring_plan_id")
            )
            predicate += f" AND EXISTS (SELECT 1 FROM dockflow_state_resources u WHERE u.project_id=r.project_id AND u.collection='runs' AND {experiment}=? AND {definition}=r.public_id AND {live_run})"
        else:
            predicate += " AND " + db.adapter.json_text("r.value", key) + "=?"
        values.append(value)
    _, caption, recent = expressions(db, collection)
    if field:
        kind = db.adapter.json_text("r.value", "type.schema_title")
        pattern = (
            "%"
            + search.lower()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            + "%"
        )
        predicate += f" AND {kind} IS NOT NULL AND LOWER({kind}) LIKE ? ESCAPE '\\'"
        values.append(pattern)
        sql = f"SELECT {kind},{kind},MAX({recent}),COUNT(*) OVER() FROM dockflow_state_resources r WHERE {predicate} GROUP BY {kind} ORDER BY MAX({recent}) DESC,{kind} ASC LIMIT 10"
    else:
        sql = f"SELECT r.public_id,{caption},{recent},COUNT(*) OVER() FROM dockflow_state_resources r WHERE {predicate} ORDER BY {db.adapter.text_order(recent)} DESC,r.public_id ASC LIMIT 10"
    with db.snapshot(), db.reader() as connection:
        rows = (
            db.execute(connection, sql, tuple(values)).fetchall()
            if connection is not None
            else []
        )
    return {
        "remaining_count": max(0, int(rows[0][3]) - len(rows)) if rows else 0,
        "items": [
            {
                "id": row[0],
                "name": " · ".join(
                    dict.fromkeys(part for part in row[1].split(" · ") if part)
                ),
                "value": row[0],
                "recent_at": row[2],
            }
            for row in rows
        ],
    }
