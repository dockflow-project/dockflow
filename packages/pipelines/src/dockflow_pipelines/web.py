"""Packaged, same-origin browser shell and read-only artifact lineage projection."""

from importlib.resources import files

from dockflow_core.errors import DockflowError
from fastapi import Request
from fastapi.responses import RedirectResponse, Response

ASSETS = {
    "app.js": "text/javascript",
    "json.js": "text/javascript",
    "logs.js": "text/javascript",
    "api.js": "text/javascript",
    "dom.js": "text/javascript",
    "graph.js": "text/javascript",
    "views.js": "text/javascript",
    "forms.js": "text/javascript",
    "styles.css": "text/css",
    "api-docs.js": "text/javascript",
}
SHELL_PATHS = {"/", "/ui", "/ui/", "/dockflow/v1/docs"}
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def is_public_shell(method: str, path: str) -> bool:
    return method in {"GET", "HEAD"} and (
        path in SHELL_PATHS or path in {"/ui/assets/" + name for name in ASSETS}
    )


def mount_web(app, core) -> None:
    def resource(name: str, media_type: str) -> Response:
        return Response(
            files("dockflow_pipelines").joinpath("static", name).read_bytes(),
            media_type=media_type,
            headers=HEADERS,
        )

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    @app.api_route("/ui", methods=["GET", "HEAD"], include_in_schema=False)
    def home():
        return RedirectResponse("ui/", headers=HEADERS)

    @app.api_route("/ui/", methods=["GET", "HEAD"], include_in_schema=False)
    def shell():
        return resource("index.html", "text/html")

    @app.api_route(
        "/dockflow/v1/docs", methods=["GET", "HEAD"], include_in_schema=False
    )
    def documentation():
        return resource("api-docs.html", "text/html")

    @app.api_route(
        "/ui/assets/{name}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def asset(name: str):
        if name not in ASSETS:
            raise DockflowError("Unknown web asset", "NOT_FOUND", 404)
        return resource(name, ASSETS[name])

    @app.get("/dockflow/v1/artifacts/{artifact_id}/lineage")
    def lineage(artifact_id: str, request: Request):
        """Original producer and a stable page of actual consumer Tasks."""
        allowed = {"page_size", "page_token"}
        if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise DockflowError("Unknown or duplicate lineage query arguments")
        try:
            size = int(request.query_params.get("page_size", "50"))
        except ValueError as exc:
            raise DockflowError("page_size must be an integer") from exc
        with core.mutex:
            artifact = core.store.get("artifacts", artifact_id)
            consumers = core.page(
                "tasks",
                page_size=size,
                page_token=request.query_params.get("page_token"),
                filters={"input_artifact_id": artifact_id},
            )
            return {
                "artifact_id": artifact_id,
                "producer": artifact.get("producer"),
                "items": consumers["items"],
                "next_page_token": consumers["next_page_token"],
            }
