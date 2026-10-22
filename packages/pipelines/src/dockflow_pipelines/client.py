"""Standard-library remote client; no execution or server imports."""

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .canonical import loads
from .config import validate_endpoint
from .errors import DockflowError


class _RejectRedirects(HTTPRedirectHandler):
    """API calls stay at the configured endpoint, including their credentials."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DockflowError(
            "Service returned an HTTP redirect; configure the canonical service endpoint",
            "UNAVAILABLE",
            503,
        )


class Client:
    def __init__(self, endpoint: str, options: dict | None = None):
        self.endpoint = validate_endpoint(endpoint)
        options = options or {}
        self.headers = {"Accept": "application/json"}
        if options.get("token_file"):
            try:
                token = options["token_file"].read_text().strip()
            except OSError as exc:
                raise DockflowError("Cannot read client token file") from exc
            if not token or "\n" in token or "\r" in token:
                raise DockflowError("Client token file is invalid")
            self.headers["Authorization"] = f"Bearer {token}"
        self.context = ssl.create_default_context(
            cafile=str(options["ca_file"]) if options.get("ca_file") else None
        )
        if not options.get("tls_verify", True):
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE
        self.opener = build_opener(
            HTTPSHandler(context=self.context), _RejectRedirects()
        )

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        query: dict | None = None,
        key: str | None = None,
    ):
        url = self.endpoint + path
        if query:
            url += "?" + urlencode(
                {name: value for name, value in query.items() if value is not None}
            )
        headers = dict(self.headers)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            headers["Content-Type"] = "application/json; charset=utf-8"
        if key:
            headers["Idempotency-Key"] = key
        try:
            with self.opener.open(
                Request(url, data=data, headers=headers, method=method),
                timeout=30,
            ) as response:
                return loads(response.read())
        except HTTPError as exc:
            try:
                error = loads(exc.read())["error"]
                domain_error = DockflowError(
                    error["message"], error["code"], exc.code, error.get("details", [])
                )
                domain_error.request_id = error.get(
                    "request_id", domain_error.request_id
                )
                raise domain_error from None
            except (KeyError, ValueError):
                raise DockflowError(
                    f"Service returned HTTP {exc.code}", "UNAVAILABLE", 503
                ) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise DockflowError(
                f"Cannot reach the selected service: {exc.reason if isinstance(exc, URLError) else type(exc).__name__}",
                "UNAVAILABLE",
                503,
            ) from None

    def operate(self, action: str, values: dict):
        prefix = "/dockflow/v1"
        if action == "capabilities":
            return self.request("GET", prefix + "/capabilities")
        if action.endswith(".list"):
            collection = action.split(".")[0]
            query = {
                "page_size": values.get("page_size", 50),
                "page_token": values.get("page_token"),
                **values.get("filters", {}),
            }
            if "experiment_id" not in query and "experiment" in query:
                query["experiment_id"] = query.pop("experiment")
            return self.request("GET", prefix + "/" + collection, query=query)
        if action.endswith(".show"):
            collection = action.split(".")[0]
            identifier = values["id"]
            if collection == "definitions" and not identifier.startswith("definition_"):
                refreshed = self.operate("definitions.refresh", {})
                diagnostic = next(
                    (
                        item
                        for item in refreshed.get("diagnostics", [])
                        if item.get("name") == identifier
                    ),
                    None,
                )
                if diagnostic:
                    raise DockflowError(
                        f"Definition {identifier}: {diagnostic['reason']}"
                    )
                page = self.request(
                    "GET",
                    prefix + "/definitions",
                    query={"name": identifier, "page_size": 200},
                )
                available = [item for item in page["items"] if item.get("available")]
                if not available:
                    raise DockflowError(
                        f"Unknown registered definition: {identifier}", "NOT_FOUND", 404
                    )
                return available[0]
            return self.request("GET", prefix + f"/{collection}/{identifier}")
        if action == "logs":
            return self.request(
                "GET",
                prefix + f"/runs/{values['run_id']}/logs",
                query={key: value for key, value in values.items() if key != "run_id"},
            )
        if action in {"runs.cancel", "artifacts.pin", "artifacts.unpin"}:
            collection, operation = action.split(".")
            return self.request(
                "POST", prefix + f"/{collection}/{values['id']}/{operation}", {}
            )
        path = {
            "definitions.validate": "/definitions/validate",
            "definitions.refresh": "/definitions/refresh",
            "artifacts.create": "/artifacts",
            "experiments.create": "/experiments",
            "metadata.check": "/metadata/check",
            "metadata.rebuild": "/metadata/rebuild",
            "clean": "/clean",
        }.get(action)
        if path is None:
            raise DockflowError(f"Unknown remote operation: {action}")
        return self.request("POST", prefix + path, values)
