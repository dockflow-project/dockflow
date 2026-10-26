"""Bounded presentation names from authoritative records and their direct context."""

from dockflow_core.errors import DockflowError

COLLECTIONS = {
    "runs",
    "tasks",
    "attempts",
    "pipelines",
    "definitions",
    "components",
    "experiments",
}


def reference_names(core, body: dict) -> dict:
    if set(body) != {"references"} or not isinstance(body["references"], list):
        raise DockflowError("Provide only a references array")
    references = body["references"]
    if not 1 <= len(references) <= 200:
        raise DockflowError("Provide 1–200 resource references")
    requested = []
    for item in references:
        if (
            not isinstance(item, dict)
            or set(item) != {"collection", "id"}
            or not isinstance(item["collection"], str)
            or item["collection"] not in COLLECTIONS
        ):
            raise DockflowError("Invalid resource name reference")
        core.store._validate_resource(
            item["collection"],
            {item["collection"].removesuffix("s") + "_id": item["id"]},
        )
        key = (item["collection"], item["id"])
        if key not in requested:
            requested.append(key)
    records = {}

    def get(collection, identifier):
        if not identifier:
            return None
        key = (collection, identifier)
        if key not in records:
            try:
                records[key] = core.store.get(collection, identifier)
            except DockflowError as error:
                if error.status not in {404, 410}:
                    raise
                records[key] = None
        return records[key]

    def pipeline_name(definition):
        if not definition:
            return None
        document = definition.get("pipeline_spec", {})
        document = document.get("pipelineSpec", document)
        return document.get("pipelineInfo", {}).get("name") or definition.get("name")

    def name(collection, identifier):
        record = get(collection, identifier)
        if not record:
            return None
        if collection == "attempts":
            return name("tasks", record.get("task_id"))
        if collection == "tasks":
            component = get("components", record.get("component_id"))
            return component.get("name") if component else None
        if collection == "runs":
            return pipeline_name(get("definitions", record.get("definition_id")))
        if collection == "definitions":
            return pipeline_name(record)
        if collection == "pipelines":
            compiled = pipeline_name(
                get("definitions", record.get("default_version_id"))
            )
            catalog = record.get("name")
            return (
                f"{catalog} ({compiled})"
                if catalog and compiled and compiled != catalog
                else catalog or compiled
            )
        return record.get("display_name" if collection == "experiments" else "name")

    with core.store.database.snapshot():
        items = []
        for collection, identifier in requested:
            value = name(collection, identifier)
            items.append(
                {
                    "collection": collection,
                    "id": identifier,
                    "name": value,
                    "available": bool(value),
                }
            )
    return {"items": items}
