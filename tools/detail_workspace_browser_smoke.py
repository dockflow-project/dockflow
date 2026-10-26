"""Read-only element detail layout checks against a disposable web_fixture.

Long component/task/attempt replies are browser-local projections. No resources,
executions or storage files are changed. Output contains neutral checks only.
Requires optional Playwright tooling and existing fixture catalog/Run records.
"""

import argparse
import copy
import json
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    endpoint = args.url.rstrip("/")

    def api(path):
        with urlopen(endpoint + "/dockflow/v1" + path, timeout=30) as response:
            return json.load(response)

    if not api("/capabilities")["project_id"].startswith("web-fixture-"):
        raise SystemExit("Use a disposable web_fixture service")
    component = api("/components")["items"][0]
    artifact = api("/artifacts")["items"][0]
    attempt = api("/attempts")["items"][0]
    task = api("/tasks/" + attempt["task_id"])
    run = api("/runs/" + attempt["run_id"])
    component = api("/components/" + component["component_id"])
    paths = {
        "components/" + component["component_id"]: component,
        "tasks/" + task["task_id"]: task,
        "attempts/" + attempt["attempt_id"]: attempt,
    }
    checks, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        failing = False

        def project(route):
            path = route.request.url.split("/dockflow/v1/", 1)[1].split("?", 1)[0]
            if path not in paths or route.request.method != "GET":
                route.continue_()
                return
            if failing:
                route.fulfill(
                    status=503,
                    json={"error": {"message": "Detail refresh unavailable"}},
                )
                return
            data = copy.deepcopy(paths[path])
            data["name"] = "Long example " * 20
            if path.startswith("components/"):
                data["compiled"]["inputDefinitions"] = {
                    "parameters": {
                        f"example_{i}": {"parameterType": "STRING"} for i in range(100)
                    }
                }
                data["executor"]["example_details"] = ["Long example content"] * 100
            else:
                data["parameters"] = {f"example_{i}": i for i in range(100)}
                data["image"] = {
                    f"example_{i}": "Retained image details" for i in range(100)
                }
            route.fulfill(json=data)

        page.route("**/dockflow/v1/**", project)

        def layout():
            body = page.locator(".detail-body")
            expect(body).to_be_visible()
            assert body.get_attribute("aria-label")
            assert body.get_attribute("tabindex") == "0"
            header = page.locator(".detail-header").bounding_box()
            bounds = body.bounding_box()
            assert bounds["height"] > 120
            assert abs(bounds["y"] - header["y"] - header["height"]) < 2
            assert (
                abs(bounds["y"] + bounds["height"] - page.viewport_size["height"]) < 2
            )
            body.evaluate("node => node.scrollTop=400")
            assert page.locator(".detail-header").bounding_box() == header
            assert page.locator("#content").evaluate("node => node.scrollTop") == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            tabs = page.locator(".detail-header > .tabs")
            if tabs.count():
                tab_bounds = tabs.bounding_box()
                assert (
                    abs(
                        tab_bounds["y"]
                        + tab_bounds["height"]
                        - header["y"]
                        - header["height"]
                    )
                    < 2
                )
            return body

        cases = [
            (
                "components/" + component["component_id"],
                ["Overview", "Interface", "Executor", "Source"],
            ),
            (
                "tasks/" + task["task_id"],
                ["Overview", "Inputs / outputs", "Logs", "Record"],
            ),
            (
                "attempts/" + attempt["attempt_id"],
                ["Overview", "Inputs / outputs", "Logs", "Record"],
            ),
            ("artifacts/" + artifact["artifact_id"], ["Overview"]),
            ("definitions/" + run["definition_id"], ["Summary", "Source"]),
            ("runs/" + run["run_id"], ["Details", "Logs"]),
            ("service", []),
        ]
        for path, names in cases:
            for width, height in [(1440, 1000), (390, 844)]:
                page.set_viewport_size({"width": width, "height": height})
                page.goto(
                    endpoint + "/ui/#/" + path + ("?tab=" + names[0] if names else "")
                )
                page.locator(".information-screen .detail-body").wait_for()
                for name in names or [None]:
                    if name:
                        selected = page.get_by_role("tab", name=name, exact=True)
                        if selected.get_attribute("aria-selected") != "true":
                            old = page.locator(".detail-body").element_handle()
                            selected.click()
                            page.wait_for_function("node => !node.isConnected", arg=old)
                        expect(selected).to_have_attribute("aria-selected", "true")
                        assert "tab=" in page.url
                    body = layout()
                    if body.evaluate(
                        "node => node.scrollHeight > node.clientHeight+100"
                    ):
                        body.focus()
                        body.evaluate("node => node.scrollTop=0")
                        page.keyboard.press("PageDown")
                        page.wait_for_function(
                            "() => document.querySelector('.detail-body').scrollTop > 0"
                        )
                if path.startswith("components/"):
                    page.go_back()
                    expect(
                        page.get_by_role("tab", name="Executor", exact=True)
                    ).to_have_attribute("aria-selected", "true")
                    page.go_forward()
                    expect(
                        page.get_by_role("tab", name="Source", exact=True)
                    ).to_have_attribute("aria-selected", "true")
            checks.append(
                path.split("/")[0]
                + ": fixed context/bottom tabs, desktop/narrow body scrolling, keyboard and tab navigation"
            )

        page.set_viewport_size({"width": 1440, "height": 1000})
        component_path = "components/" + component["component_id"] + "?tab=Source"
        page.goto(endpoint + "/ui/#/" + component_path)
        body = page.locator(".detail-body")
        expect(body).to_contain_text("Compiled contract")
        body.evaluate("node => node.scrollTop=300")
        previous = body.element_handle()
        page.get_by_role("button", name="Refresh", exact=True).click()
        page.wait_for_function("node => !node.isConnected", arg=previous)
        assert body.evaluate("node => node.scrollTop") == 300
        failing = True
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(page.locator(".refresh-error")).to_contain_text(
            "Detail refresh unavailable"
        )
        expect(body).to_contain_text("Compiled contract")
        failing = False
        page.get_by_role("button", name="Try again", exact=True).click()
        expect(page.locator(".refresh-error")).to_have_count(0)
        checks.append(
            "Same element/tab refresh preserves body position; failed refresh retains data with retry"
        )

        page.unroute("**/dockflow/v1/**", project)
        page.goto(endpoint + "/ui/#/attempts/" + attempt["attempt_id"] + "?tab=Record")
        page.get_by_role("button", name="Delete execution", exact=True).click()
        expect(page.get_by_role("dialog")).to_contain_text(
            "Only terminal, reconciled records"
        )
        page.get_by_role("button", name="Close dialog", exact=True).click()
        page.get_by_role("button", name="Open in graph", exact=True).click()
        expect(page.locator(".graph-viewport")).to_be_visible()
        expect(page.locator(".graph-inspector")).to_be_visible()
        checks.append(
            "Fixed execution actions retain deletion review and selected-task graph navigation"
        )
        assert not errors, "Browser page errors occurred"
        print(
            json.dumps(
                {"browser": browser.version, "checks": checks, "page_errors": []},
                indent=2,
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
