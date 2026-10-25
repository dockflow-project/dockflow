"""Dispatch the small management operations without duplicating adapter logic."""

from dockflow_core.errors import DockflowError

from .core import capabilities


def operate(core, action: str, values: dict):
    if action.startswith("cache."):
        from .cache_registry import Registry

        options = {
            **core.settings.cache,
            "storage_token": core.artifacts.storage_identity(create=False),
        }
        registry = Registry(options, core.settings.project_id)
        key = values.get("id", "")
        if action == "cache.show":
            return registry.inspect(key)
        if action == "cache.invalidate":
            return registry.invalidate(
                key, values.get("artifact_id", ""), values.get("reason", "")
            )
        if action == "cache.reset":
            return registry.reset_retry_episode(
                key, values.get("revision", -1), values.get("reason", "")
            )
        raise DockflowError("Unknown cache operation")
    if action == "capabilities":
        return capabilities(core.settings)
    if action.endswith(".list"):
        collection = action.split(".")[0]
        filters = values.get("filters", {})
        if collection == "experiments" and "name" in filters:
            filters = {"display_name": filters["name"]}
        page = core.page(
            collection,
            page_size=values.get("page_size", 50),
            page_token=values.get("page_token"),
            filters=filters,
        )
        if collection == "definitions":
            page["items"] = [core.definition_view(item) for item in page["items"]]
        return page
    if action.endswith(".show"):
        collection = action.split(".")[0]
        identifier = values["id"]
        if collection == "components" and identifier.startswith("definition_"):
            return core.store.get("definitions", identifier)
        if collection == "definitions" and not identifier.startswith("definition_"):
            return core.definition_view(core.resolve(identifier, persist=False))
        if collection == "definitions":
            return core.definition_view(core.store.get(collection, identifier))
        if collection == "artifacts":
            return core.artifacts.get(identifier)
        return core.store.get(collection, identifier)
    if action == "definitions.validate":
        return core.validate(values)
    if action == "definitions.refresh":
        return core.refresh()
    if action == "runs.cancel":
        return core.cancel(values["id"])
    if action == "artifacts.create":
        return core.artifacts.register(
            values["uri"],
            values["type"],
            values.get("metadata", {}),
            managed=values["operation"] == "import",
            version=values.get("version"),
        )
    if action in {"artifacts.pin", "artifacts.unpin"}:
        return core.artifacts.pin(values["id"], action.endswith(".pin"))
    if action == "experiments.create":
        return core.create_experiment(
            values["display_name"], values.get("description", "")
        )
    if action == "metadata.check":
        return core.store.check(values.get("verify_contents", False), core.artifacts)
    if action == "metadata.rebuild":
        return core.store.rebuild(values.get("apply", False))
    if action == "clean":
        return core.store.clean(
            core.settings.work_directory, values.get("apply", False)
        )
    if action == "logs":
        return core.logs(**values)
    raise DockflowError(f"Unknown operation: {action}")
