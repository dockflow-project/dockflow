"""Qualify readable resource references on an explicitly disposable web fixture.

Registers a pipeline, experiment and Runs for real execution/reuse. Never resets
or deletes data. Optional captures mask runtime identifiers and are for review/
discard; receipts retain neutral check descriptions. Requires optional Playwright.
"""

import argparse
import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    endpoint = args.url.rstrip("/")
    token = args.token_file.read_text().strip() if args.token_file else ""
    headers = {"Authorization": "Bearer " + token} if token else {}

    def api(path, body=None):
        with urlopen(
            Request(
                endpoint + "/dockflow/v1" + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={
                    **headers,
                    **(
                        {"Content-Type": "application/json"} if body is not None else {}
                    ),
                },
            )
        ) as response:
            return json.load(response)

    if not api("/capabilities")["project_id"].startswith("web-fixture-"):
        raise SystemExit("Use a disposable web_fixture service")
    suffix = uuid.uuid4().hex[:6]
    boundary = "reference-" + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="uploadfile"; filename="pipeline.json"\r\n\r\n'.encode()
        + args.definition.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    with urlopen(
        Request(
            endpoint
            + "/apis/v2beta1/pipelines/upload?"
            + urlencode({"name": "Readable catalog " + suffix}),
            data=body,
            headers={
                **headers,
                "Content-Type": "multipart/form-data; boundary=" + boundary,
            },
        )
    ) as response:
        catalog = json.load(response)
    catalog = api("/pipelines/" + catalog["pipeline_id"])
    definition = api("/definitions/" + catalog["default_version_id"])
    pipeline_name = definition["pipeline_spec"]["pipelineInfo"]["name"]
    experiment_name = "Human experiment <img src=x onerror=alert(1)> " + suffix
    experiment = api("/experiments", {"display_name": experiment_name})
    runs = []
    for index in range(2):
        run = api(
            "/runs",
            {
                "definition_id": definition["definition_id"],
                "display_name": f"Morning invocation {index + 1} " + suffix,
                "experiment_id": experiment["experiment_id"],
                "parameters": {"value": 7},
                "reuse": {"scope": "keyed", "key": suffix},
            },
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            run = api("/runs/" + run["run_id"])
            if run["state"] in {"succeeded", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(0.2)
        assert run["state"] == "succeeded", "Fixture Run did not succeed"
        runs.append(run)
    tasks = api("/tasks?" + urlencode({"run_id": runs[0]["run_id"]}))["items"]
    attempts = api("/attempts?" + urlencode({"run_id": runs[0]["run_id"]}))["items"]
    task = next(item for item in tasks if item["name"] == "prepare")
    attempt = next(item for item in attempts if item["task_id"] == task["task_id"])
    component = api("/components/" + task["component_id"])
    checks, errors, requests = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: requests.append(request.post_data_json)
            if request.url.endswith("/ui/reference-names")
            else None,
        )

        def open_route(route):
            page.goto(endpoint + "/ui/#/" + route)
            if token:
                page.locator("h1,dialog[open]").first.wait_for()
            if token and page.get_by_label("Bearer token", exact=True).is_visible():
                page.get_by_label("Bearer token", exact=True).fill(token)
                page.get_by_role("dialog").get_by_role(
                    "button", name="Connect", exact=True
                ).click()
            page.locator("h1").wait_for()

        def ref(collection, identity):
            return page.locator(f'a[href="#/{collection}/{identity}"]').first

        def capture(name):
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                # Project only visible text for a portable capture. Routes,
                # values and stored records remain intact; the next view reloads.
                page.evaluate(r"""() => {
                  document.getElementById('project-name').textContent = 'Example project';
                  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                  while (walker.nextNode()) {
                    const node = walker.currentNode;
                    if (node.parentElement.closest('script,style')) continue;
                    node.textContent = node.textContent
                      .replace(/(?:run|task|attempt|pipeline|definition|experiment|component)_[0-9a-f-]{36}/g, 'EXAMPLE_ID')
                      .replace(/\b[0-9a-f]{8}\b/g, 'ID')
                      .replace(/\b[0-9a-f]{6}\b/g, 'example');
                  }
                }""")
                page.screenshot(path=str(args.output / name))

        open_route("runs")
        expect(ref("runs", runs[0]["run_id"])).to_contain_text(pipeline_name)
        expect(ref("experiments", experiment["experiment_id"]).first).to_contain_text(
            experiment_name
        )
        expect(ref("definitions", definition["definition_id"]).first).to_contain_text(
            pipeline_name
        )
        assert not page.locator('img[src="x"]').count()
        assert runs[0]["run_id"] in ref("runs", runs[0]["run_id"]).get_attribute(
            "title"
        )
        checks.append(
            "Run list retains invocation labels and IDs beside pipeline and experiment names; markup remains text"
        )

        open_route("executions")
        expect(ref("attempts", attempt["attempt_id"])).to_contain_text(
            component["name"]
        )
        expect(ref("runs", runs[0]["run_id"]).first).to_contain_text(pipeline_name)
        expect(ref("tasks", task["task_id"]).first).to_contain_text(component["name"])
        capture("references-executions.png")
        open_route("attempts/" + attempt["attempt_id"])
        expect(
            page.locator(
                '.detail-meta [data-reference-id="' + attempt["attempt_id"] + '"]'
            )
        ).to_contain_text(component["name"])
        page.get_by_role("button", name="Delete execution", exact=True).click()
        expect(page.get_by_role("dialog")).to_contain_text(component["name"])
        page.keyboard.press("Escape")
        open_route("tasks/" + task["task_id"])
        expect(
            page.locator('[data-reference-id="' + task["task_id"] + '"]')
        ).to_contain_text(component["name"])
        expect(ref("attempts", attempt["attempt_id"])).to_contain_text(
            component["name"]
        )
        checks.append(
            "Execution/Task lists, detail headers, attempts and deletion context show component names with intact IDs"
        )

        open_route("runs/" + runs[0]["run_id"])
        expect(
            page.locator('.detail-meta [data-reference-id="' + runs[0]["run_id"] + '"]')
        ).to_contain_text(pipeline_name)
        page.get_by_role("button", name="Zoom in", exact=True).click()
        graph = page.locator(".graph").element_handle()
        viewport = page.locator(".graph").evaluate("node => node.captureViewport()")
        page.get_by_role("button", name=re.compile("^prepare:")).click()
        expect(page.locator(".step-panel")).to_contain_text(component["name"])
        page.locator(".step-panel").get_by_role(
            "tab", name="Attempts", exact=True
        ).click()
        expect(
            page.locator(".step-panel").locator(
                f'a[href="#/attempts/{attempt["attempt_id"]}"]'
            )
        ).to_contain_text(component["name"])
        assert page.evaluate("node => node === document.querySelector('.graph')", graph)
        assert (
            page.locator(".graph").evaluate("node => node.captureViewport()")
            == viewport
        )
        checks.append(
            "Graph inspector name/attempt updates preserve the graph node and viewport/zoom"
        )

        artifact_id = next(iter(task["outputs"].values()))
        open_route("artifacts/" + artifact_id + "?tab=Lineage")
        expect(ref("runs", runs[0]["run_id"])).to_contain_text(pipeline_name)
        expect(ref("attempts", attempt["attempt_id"])).to_contain_text(
            component["name"]
        )
        expect(ref("tasks", task["task_id"])).to_contain_text(component["name"])
        open_route("compare?runs=" + ",".join(run["run_id"] for run in runs))
        expect(ref("runs", runs[0]["run_id"])).to_contain_text(pipeline_name)
        checks.append(
            "Artifact producer/consumer lineage and Run comparison references show the same resolved context"
        )

        open_route("pipelines/" + catalog["pipeline_id"])
        expect(
            page.locator('[data-reference-id="' + catalog["pipeline_id"] + '"]')
        ).to_contain_text(catalog["name"])
        expect(
            page.locator('option[value="' + definition["definition_id"] + '"]')
        ).to_contain_text(pipeline_name)
        open_route("experiments/" + experiment["experiment_id"])
        page.get_by_text("Experiment details", exact=True).click()
        expect(
            page.locator('[data-reference-id="' + experiment["experiment_id"] + '"]')
        ).to_contain_text(experiment_name)
        open_route("runs/new?definition=" + definition["definition_id"])
        expect(page.locator(".reference-input-name").first).to_contain_text(
            pipeline_name
        )
        expect(page.get_by_label("Definition version", exact=True)).to_have_value(
            definition["definition_id"]
        )
        checks.append(
            "Catalog/version and experiment IDs, selectors and selected input hints retain names and exact values"
        )

        open_route("runs")
        page.route(
            "**/ui/reference-names",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body='{"error":{"message":"Unavailable"}}',
            ),
        )
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(ref("runs", runs[0]["run_id"])).to_contain_text("Name unavailable")
        page.unroute("**/ui/reference-names")
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(ref("runs", runs[0]["run_id"])).to_contain_text(pipeline_name)
        page.set_viewport_size({"width": 390, "height": 844})
        open_route("attempts/" + attempt["attempt_id"])
        expect(
            page.locator(
                '.detail-meta [data-reference-id="' + attempt["attempt_id"] + '"]'
            )
        ).to_contain_text(component["name"])
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        capture("references-narrow.png")
        checks.append(
            "Optional lookup failure keeps the screen usable, refresh recovers names and narrow layouts remain contained"
        )
        page.set_viewport_size({"width": 1440, "height": 1000})
        open_route("runs")
        expect(ref("runs", runs[0]["run_id"])).to_contain_text(pipeline_name)
        page.evaluate("""() => {
          const group = document.createElement('div'); group.id = 'batch-reference-probe';
          for (let i = 0; i < 205; i++) {
            const a = document.createElement('a'); a.href = '#/runs/run_' + crypto.randomUUID();
            a.textContent = 'Probe reference ' + i; group.append(a);
          }
          document.getElementById('content').append(group);
        }""")
        expect(
            page.locator('#batch-reference-probe [data-reference-state="unavailable"]')
        ).to_have_count(205)
        page.locator("#batch-reference-probe").evaluate("node => node.remove()")
        held = []

        def hold_first(route):
            if not held:
                held.append(route)
            else:
                route.continue_()

        page.route("**/ui/reference-names", hold_first)
        page.get_by_role("button", name="Refresh", exact=True).click()
        deadline = time.monotonic() + 5
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(20)
        assert held
        if token:
            page.get_by_role("button", name="Sign out", exact=True).click()
            expect(page.locator("#project-name")).to_have_text("Not connected")
        else:
            page.locator("nav").get_by_role(
                "link", name="Experiments", exact=True
            ).click()
            expect(
                page.get_by_role("heading", name="Experiments", exact=True)
            ).to_be_visible()
        old = held[0].request.post_data_json["references"]
        try:
            held[0].fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": [
                            {**item, "available": True, "name": "STALE REFERENCE NAME"}
                            for item in old
                        ]
                    }
                ),
            )
        except Exception:
            # Aborted requests can already be closed by Chromium after navigation.
            pass
        page.unroute("**/ui/reference-names", hold_first)
        expect(page.locator("#content")).not_to_contain_text("STALE REFERENCE NAME")
        checks.append(
            "More than 200 references use separate bounded batches; stale navigation/sign-out responses cannot overwrite current context"
        )
        browser.close()
    assert requests and all(1 <= len(item["references"]) <= 200 for item in requests)
    for item in requests:
        keys = [(ref["collection"], ref["id"]) for ref in item["references"]]
        assert len(keys) == len(set(keys))
    assert not errors, errors
    checks.append("Browser lookups are bounded/deduplicated and produce no page errors")
    result = {"browser": "Chromium", "checks": checks, "page_errors": errors}
    if args.output:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
