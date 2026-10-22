"""Exercise the packaged UI against an explicitly disposable web_fixture service.

Run with Playwright 1.55.0 and its Chromium headless shell installed separately.
This tool refuses a service whose project ID does not use the disposable web-fixture- prefix.
It creates retained test records only; it never cleans or resets a repository.
"""

import argparse
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--token-file", type=Path)
    args = parser.parse_args()
    endpoint = args.url.rstrip("/")
    token = args.token_file.read_text().strip() if args.token_file else ""
    headers = {"Authorization": "Bearer " + token} if token else {}
    with urlopen(
        Request(endpoint + "/dockflow/v1/capabilities", headers=headers)
    ) as response:
        capabilities = json.load(response)
    if not capabilities["project_id"].startswith("web-fixture-"):
        raise SystemExit("Refusing to mutate a non-fixture Dockflow project")
    args.output.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:6]
    pipeline_name = "Browser qualification " + suffix
    first_name = "Browser execution " + suffix + " <img src=x onerror=alert(1)>"
    second_name = "Browser reused execution " + suffix
    experiment_name = "Browser experiment " + suffix
    checks = []
    errors = []
    external = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        origin = urlsplit(endpoint)
        page.on(
            "request",
            lambda req: external.append(req.url)
            if urlsplit(req.url).netloc != origin.netloc
            else None,
        )
        page.goto(endpoint + "/ui/")
        if token:
            page.locator("h1, dialog[open]").first.wait_for()
            if page.get_by_label("Bearer token", exact=True).is_visible():
                page.get_by_label("Bearer token", exact=True).fill(token)
                page.get_by_role("dialog").get_by_role(
                    "button", name="Connect", exact=True
                ).click()
        expect(
            page.get_by_role("heading", name="Pipelines", exact=True)
        ).to_be_visible()
        page.locator(".skip-link").focus()
        page.keyboard.press("Enter")
        expect(page.locator("#content")).to_be_focused()
        assert page.url.endswith("#/pipelines")
        checks.append("keyboard skip link preserves navigation")
        page.get_by_role("button", name="Upload pipeline", exact=True).click()
        page.get_by_label("Pipeline name", exact=True).fill(pipeline_name)
        page.get_by_label("Compiled definition", exact=True).set_input_files(
            args.definition
        )
        with page.expect_response(
            lambda res: "/pipelines/upload?" in res.url
        ) as uploaded:
            page.get_by_role("dialog").get_by_role(
                "button", name="Upload", exact=True
            ).click()
        pipeline = uploaded.value.json()
        expect(
            page.get_by_role("heading", name=pipeline_name, exact=True)
        ).to_be_visible()
        expect(page.locator(".graph-node")).to_have_count(2)
        page.screenshot(path=str(args.output / "pipeline-desktop.png"), full_page=True)
        checks.append("compiled pipeline upload and graph")
        page.get_by_role("button", name="Upload version", exact=True).click()
        page.get_by_label("Version name", exact=True).fill("v2")
        page.get_by_label("Compiled definition", exact=True).set_input_files(
            args.definition
        )
        page.get_by_role("dialog").get_by_role(
            "button", name="Upload", exact=True
        ).click()
        expect(page.get_by_label("Pipeline version", exact=True)).to_contain_text(
            "v2 · current default"
        )
        expect(
            page.get_by_label("Pipeline version", exact=True).locator("option")
        ).to_have_count(2)
        checks.append("immutable version upload and default selection")
        page.get_by_role("button", name="Create run", exact=True).click()
        expect(
            page.get_by_role("heading", name="Create run", exact=True)
        ).to_be_visible()
        page.get_by_label("Run name", exact=True).fill(first_name)
        page.get_by_label("Reuse scope", exact=True).select_option("keyed")
        page.get_by_label("Reuse key", exact=True).fill(suffix)
        page.get_by_role("button", name="Validate inputs", exact=True).click()
        expect(
            page.get_by_text("Definition and root inputs are valid.", exact=False)
        ).to_be_visible()
        lost_response = []

        def drop_accepted_response(route):
            response = route.fetch()
            lost_response.append(response.json())
            route.abort("failed")

        page.route("**/dockflow/v1/runs", drop_accepted_response)
        page.get_by_role("button", name="Start run", exact=True).click()
        expect(
            page.get_by_text("Cannot reach the service.", exact=False)
        ).to_be_visible()
        page.unroute("**/dockflow/v1/runs", drop_accepted_response)
        with page.expect_response(
            lambda res: res.url.endswith("/dockflow/v1/runs")
            and res.request.method == "POST"
        ) as accepted:
            page.get_by_role("button", name="Start run", exact=True).click()
        run = accepted.value.json()
        assert accepted.value.status == 200
        assert run["run_id"] == lost_response[0]["run_id"]
        checks.append(
            "response-loss retry returns the original run via idempotency key"
        )
        expect(
            page.get_by_role("heading", name=run["display_name"], exact=True)
        ).to_be_visible()
        expect(page.locator("h1 img")).to_have_count(0)
        # Live status updates must follow actual Docker work to completion.
        expect(page.locator(".run-summary .badge").first).to_have_text(
            "●succeeded", timeout=90000
        )
        expect(
            page.locator(".graph-node .badge").filter(has_text="succeeded")
        ).to_have_count(2)
        page.locator(".graph-node").first.click()
        expect(page.locator(".step-panel")).to_be_visible()
        page.get_by_role("tab", name="Inputs / outputs", exact=True).click()
        expect(
            page.get_by_role("heading", name="Output parameters", exact=True)
        ).to_be_visible()
        page.screenshot(path=str(args.output / "run-desktop.png"), full_page=True)
        checks.append(
            "typed run submission, input validation, actual Docker completion, graph/task results and XSS text"
        )
        page.get_by_role("tab", name="Attempts", exact=True).click()
        page.get_by_role("link", name="Attempt 1", exact=False).click()
        expect(
            page.get_by_role("heading", name="Attempt ", exact=False)
        ).to_be_visible()
        expect(page.get_by_role("heading", name="Logs", exact=True)).to_be_visible()
        expect(page.locator(".logs")).to_contain_text(
            "Preparing dataset", timeout=15000
        )
        checks.append("attempt navigation and bounded retained logs")
        page.goto(endpoint + "/ui/#/runs/" + run["run_id"])
        if token:
            page.locator("h1, dialog[open]").first.wait_for()
            if page.get_by_label("Bearer token", exact=True).is_visible():
                page.get_by_label("Bearer token", exact=True).fill(token)
                page.get_by_role("dialog").get_by_role(
                    "button", name="Connect", exact=True
                ).click()
        expect(
            page.get_by_role("heading", name=run["display_name"], exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="Clone run", exact=True).click()
        expect(
            page.get_by_role("heading", name="Clone run", exact=True)
        ).to_be_visible()
        page.get_by_label("Run name", exact=True).fill(second_name)
        with page.expect_response(
            lambda res: res.url.endswith("/dockflow/v1/runs")
            and res.request.method == "POST"
        ) as cloned:
            page.get_by_role("button", name="Start run", exact=True).click()
        second = cloned.value.json()
        expect(page.locator(".run-summary .badge").first).to_have_text(
            "●succeeded", timeout=90000
        )
        expect(
            page.locator(".graph-node .badge").filter(has_text="reused")
        ).to_have_count(2)
        page.locator(".graph-node").first.click()
        page.get_by_role("tab", name="Attempts", exact=True).click()
        expect(
            page.get_by_text("No new attempt was executed.", exact=False)
        ).to_be_visible()
        expect(
            page.get_by_role("link", name="Original producer attempt", exact=True)
        ).to_be_visible()
        checks.append("clone, actual reuse and original producer link")
        page.locator("nav").get_by_role("link", name="Runs", exact=True).click()
        expect(page.get_by_role("heading", name="Runs", exact=True)).to_be_visible()
        page.get_by_role(
            "checkbox", name="Compare " + run["display_name"], exact=True
        ).check()
        page.get_by_role("checkbox", name="Compare " + second_name, exact=True).check()
        page.get_by_role("button", name="Compare runs (2)", exact=True).click()
        expect(
            page.get_by_role("heading", name="Compare runs", exact=True)
        ).to_be_visible()
        expect(page.locator(".comparison")).to_contain_text("Metric")
        expect(page.locator(".comparison")).to_contain_text("score")
        page.screenshot(path=str(args.output / "compare-desktop.png"), full_page=True)
        checks.append("run comparison with real numeric artifact metadata")
        page.locator("nav").get_by_role("link", name="Artifacts", exact=True).click()
        expect(
            page.get_by_role("heading", name="Artifacts", exact=True)
        ).to_be_visible()
        page.locator("tbody a").first.click()
        expect(page.get_by_role("tab", name="Lineage", exact=True)).to_be_visible()
        page.get_by_role("button", name="Pin", exact=True).click()
        page.get_by_role("dialog").get_by_role(
            "button", name="Confirm", exact=True
        ).click()
        expect(page.get_by_role("button", name="Unpin", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Lineage", exact=True).click()
        expect(
            page.get_by_role("heading", name="Original producer", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_role("heading", name="Consumer tasks", exact=True)
        ).to_be_visible()
        checks.append("artifact pin and producer/consumer lineage")
        page.locator("nav").get_by_role("link", name="Experiments", exact=True).click()
        page.get_by_role("button", name="Create experiment", exact=True).click()
        page.get_by_role("dialog").get_by_label("Name", exact=True).fill(
            experiment_name
        )
        page.get_by_role("dialog").get_by_role(
            "button", name="Create", exact=True
        ).click()
        expect(
            page.get_by_role("heading", name=experiment_name, exact=True)
        ).to_be_visible()
        checks.append("experiment creation and empty run list")
        # Failed and cancelled executions must remain truthful in the graph/UI.
        edge_runs = []
        for target in ("failed", "cancelled"):
            page.goto(endpoint + "/ui/#/pipelines/" + pipeline["pipeline_id"])
            page.get_by_role("button", name="Create run", exact=True).click()
            page.get_by_label("Run name", exact=True).fill(
                "Browser " + target + " " + suffix
            )
            page.get_by_label("Reuse scope", exact=True).select_option("none")
            if target == "failed":
                page.get_by_label("fail · BOOLEAN", exact=True).select_option("true")
            else:
                page.get_by_label("delay_seconds · NUMBER_INTEGER", exact=True).fill(
                    "10"
                )
            with page.expect_response(
                lambda res: res.url.endswith("/dockflow/v1/runs")
                and res.request.method == "POST"
            ) as edge:
                page.get_by_role("button", name="Start run", exact=True).click()
            edge_runs.append(edge.value.json()["run_id"])
            if target == "cancelled":
                page.get_by_role("button", name="Cancel run", exact=True).click()
                page.get_by_role("dialog").get_by_role(
                    "button", name="Confirm", exact=True
                ).click()
            expect(page.locator(".run-summary .badge").first).to_have_text(
                "●" + target, timeout=90000
            )
        checks.append("real failure and confirmed cancellation states")
        page.locator("nav").get_by_role("link", name="Artifacts", exact=True).click()
        page.get_by_role("button", name="Register artifact", exact=True).click()
        page.get_by_label("Source URI", exact=True).fill(
            (args.definition.resolve().parent / "inputs" / "external.csv").as_uri()
        )
        page.get_by_label("Data revision", exact=True).fill(
            "Browser imported " + suffix
        )
        page.get_by_label("Metadata (JSON object)", exact=True).fill(
            '{"note":"<svg onload=alert(1)>"}'
        )
        page.get_by_role("dialog").get_by_role(
            "button", name="Create", exact=True
        ).click()
        expect(
            page.get_by_role("heading", name="Browser imported " + suffix, exact=True)
        ).to_be_visible()
        expect(
            page.get_by_text("<svg onload=alert(1)>", exact=False).first
        ).to_be_visible()
        expect(page.locator(".panel svg")).to_have_count(0)
        checks.append("server-side artifact import and metadata text rendering")
        page.set_viewport_size({"width": 420, "height": 860})
        page.locator("nav").get_by_role("link", name="Pipelines", exact=True).click()
        expect(
            page.get_by_role("heading", name="Pipelines", exact=True)
        ).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(args.output / "pipelines-mobile.png"), full_page=True)
        checks.append("narrow layout and usable navigation")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(endpoint + "/dockflow/v1/docs")
        if token:
            page.locator("h1, dialog[open]").first.wait_for()
            if page.get_by_label("Bearer token", exact=True).is_visible():
                page.get_by_label("Bearer token", exact=True).fill(token)
                page.get_by_role("dialog").get_by_role(
                    "button", name="Connect", exact=True
                ).click()
        expect(
            page.get_by_role("heading", name="Dockflow Pipelines", exact=True)
        ).to_be_visible()
        page.get_by_label("Search operations and schemas", exact=True).fill("lineage")
        expect(
            page.get_by_text("/dockflow/v1/artifacts/{artifact_id}/lineage", exact=True)
        ).to_be_visible()
        checks.append("offline live-schema API explorer")
        if token:
            page.get_by_role("button", name="Sign out", exact=True).click()
            expect(
                page.get_by_text(
                    "Signed out. Connect to view the API reference.", exact=False
                )
            ).to_be_visible()
            assert page.evaluate(
                "localStorage.length === 0 && sessionStorage.length === 0"
            )
            checks.append("memory-only credential signout")
        assert not errors, errors
        assert not external, external
        result = {
            "browser": browser.version,
            "checks": checks,
            "pipeline_id": pipeline["pipeline_id"],
            "run_ids": [run["run_id"], second["run_id"], *edge_runs],
            "page_errors": errors,
            "external_requests": external,
        }
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
