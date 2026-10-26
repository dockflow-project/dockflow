"""Check list workspaces with read-only fixture data and browser-local projections.

Requires optional Playwright tooling. Projected cursor pages, empty/error replies
and cleanup inventory stay in the browser; no storage or resource mutation occurs.
Only neutral check descriptions are printed.
"""

import argparse
import copy
import json
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


def workspace(page):
    """Check actual independent scrolling, fixed controls and sticky headings."""
    content = page.locator(".list-content")
    expect(content).to_be_visible()
    assert content.get_attribute("aria-label")
    assert content.get_attribute("tabindex") == "0"
    geometry = page.locator(".list-screen").evaluate("""node => {
      const rect = n => {const r = n.getBoundingClientRect();
        return {top:r.top, bottom:r.bottom, height:r.height};};
      return {header:rect(node.querySelector('.list-header')),
        footer:rect(node.querySelector('.list-footer')),
        list:rect(node.querySelector('.list-content')),
        documentOverflow:document.documentElement.scrollWidth > innerWidth,
        pageScroll:document.querySelector('#content').scrollTop};
    }""")
    assert geometry["list"]["height"] > 100, geometry
    assert geometry["footer"]["bottom"] <= page.viewport_size["height"] + 1
    assert not geometry["documentOverflow"] and geometry["pageScroll"] == 0
    content.evaluate("node => {node.scrollTop=500; node.scrollLeft=100;}")
    top = content.evaluate("node => node.getBoundingClientRect().top")
    head = page.locator(".list-content th").first
    assert abs(head.bounding_box()["y"] - top) < 2
    for selector, key in [(".list-header", "header"), (".list-footer", "footer")]:
        actual = page.locator(selector).bounding_box()
        assert abs(actual["y"] - geometry[key]["top"]) < 1
    content.focus()
    content.evaluate("node => node.scrollTop=0")
    page.keyboard.press("PageDown")
    page.wait_for_function(
        "() => document.querySelector('.list-content').scrollTop > 0"
    )
    content.evaluate("""node => new Promise(resolve => {
      let last = node.scrollTop, stable = 0;
      function frame() {
        stable = node.scrollTop === last ? stable + 1 : 0;
        last = node.scrollTop;
        if (stable >= 5) resolve(); else requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    })""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    endpoint = args.url.rstrip("/")

    def api(path):
        with urlopen(endpoint + "/dockflow/v1" + path, timeout=30) as response:
            return json.load(response)

    if not api("/capabilities")["project_id"].startswith("web-fixture-"):
        raise SystemExit("Use an explicitly disposable web_fixture service")
    catalog = {
        name: api("/" + name)
        for name in [
            "pipelines",
            "components",
            "experiments",
            "runs",
            "attempts",
            "artifacts",
        ]
    }
    assert all(value["items"] for value in catalog.values())
    checks, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        mode = {"value": "normal"}

        def projection(route):
            parsed = urlsplit(route.request.url)
            kind = parsed.path.removeprefix("/dockflow/v1/")
            if kind not in catalog or route.request.method != "GET":
                route.continue_()
                return
            if mode["value"] == "error":
                route.fulfill(
                    status=503,
                    json={"error": {"message": "Fixture refresh unavailable"}},
                )
                return
            query = parse_qs(parsed.query)
            second = "page_token" in query
            count = 0 if mode["value"] == "empty" else (7 if second else 50)
            data = copy.deepcopy(catalog[kind])
            data["items"] = [
                copy.deepcopy(data["items"][i % len(data["items"])])
                for i in range(count)
            ]
            data["next_page_token"] = "browser-cursor" if count and not second else None
            route.fulfill(json=data)

        page.route("**/dockflow/v1/**", projection)
        for kind in catalog:
            route_name = "executions" if kind == "attempts" else kind
            page.goto(endpoint + "/ui/#/" + route_name)
            expect(page.locator(".list-footer")).to_contain_text("50 records")
            workspace(page)
            before = page.locator(".list-content").evaluate(
                "node => node.scrollTop=500"
            )
            previous = page.locator(".list-content").element_handle()
            page.get_by_role("button", name="Refresh", exact=True).click()
            page.wait_for_function("node => !node.isConnected", arg=previous)
            expect(page.locator(".list-footer")).to_contain_text("50 records")
            page.wait_for_function(
                "value => document.querySelector('.list-content').scrollTop === value",
                arg=before,
            )
            page.get_by_role("button", name="Next", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("7 records")
            assert page.locator(".list-content").evaluate("node => node.scrollTop") == 0
            expect(page.get_by_role("button", name="Next", exact=True)).to_be_disabled()
            page.get_by_role("button", name="Previous", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("50 records")
            page.get_by_role("button", name="Next", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("7 records")
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("50 records")
            assert "page_token" not in page.url
            page.set_viewport_size({"width": 390, "height": 844})
            workspace(page)
            mode["value"] = "empty"
            page.get_by_role("button", name="Refresh", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("0 records")
            expect(page.locator("thead")).to_be_visible()
            expect(
                page.get_by_role("button", name="Previous", exact=True)
            ).to_be_disabled()
            mode["value"] = "normal"
            page.get_by_role("button", name="Refresh", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("50 records")
            mode["value"] = "error"
            page.get_by_role("button", name="Refresh", exact=True).click()
            expect(page.locator(".list-header .refresh-error")).to_contain_text(
                "Fixture refresh unavailable"
            )
            expect(page.locator(".list-footer")).to_contain_text("50 records")
            mode["value"] = "normal"
            page.get_by_role("button", name="Try again", exact=True).click()
            expect(page.locator(".refresh-error")).to_have_count(0)
            page.set_viewport_size({"width": 1440, "height": 1000})
            checks.append(
                f"{route_name}: fixed regions, sticky columns, cursor/filter/reset, refresh, keyboard, narrow, empty and error recovery"
            )

        experiment = catalog["experiments"]["items"][0]["experiment_id"]
        page.goto(endpoint + "/ui/#/experiments/" + experiment)
        expect(page.locator(".list-footer")).to_contain_text("50 records")
        workspace(page)
        checks.append("Experiment Run list uses the shared workspace")

        page.unroute("**/dockflow/v1/**", projection)
        artifact = catalog["artifacts"]["items"][0]["artifact_id"]
        lineage_path = "/artifacts/" + artifact + "/lineage"
        lineage = api(lineage_path)
        task = api("/tasks?run_id=" + catalog["runs"]["items"][0]["run_id"])["items"][0]
        lineage["items"] = [task] * 50
        lineage["next_page_token"] = None
        page.route(
            "**/dockflow/v1" + lineage_path + "*",
            lambda route: route.fulfill(json=lineage),
        )
        page.goto(endpoint + "/ui/#/artifacts/" + artifact + "?tab=Lineage")
        expect(page.locator(".list-footer")).to_contain_text("50 records")
        workspace(page)
        page.set_viewport_size({"width": 390, "height": 844})
        workspace(page)
        page.set_viewport_size({"width": 1440, "height": 1000})
        checks.append(
            "Artifact consumers retain resource tabs and independent list scrolling"
        )

        run_ids = [item["run_id"] for item in catalog["runs"]["items"][:2]]
        run = next(
            (
                rid
                for rid in run_ids
                if len(api("/tasks?run_id=" + rid + "&page_size=200")["items"]) > 50
            ),
            None,
        )
        assert run, "Provide a fixture with a Run of more than 50 tasks"
        for destination in [
            "runs/" + run + "?tab=Artifacts",
            "compare?runs=" + ",".join(run_ids),
        ]:
            page.goto(endpoint + "/ui/#/" + destination)
            expect(page.locator(".list-footer")).to_contain_text("50 rows on page 1")
            workspace(page)
            page.get_by_role("button", name="Next", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("page 2")
            expect(page.locator(".list-footer")).to_contain_text("loaded")
            if destination.startswith("runs/"):
                page.locator(".list-content").evaluate("node => node.scrollTop=200")
                previous = page.locator(".list-content").element_handle()
                page.get_by_role("button", name="Refresh", exact=True).click()
                page.wait_for_function("node => !node.isConnected", arg=previous)
                expect(page.locator(".list-footer")).to_contain_text("page 2")
                page.wait_for_function(
                    "() => document.querySelector('.list-content').scrollTop === 200"
                )
            page.get_by_role("button", name="Previous", exact=True).click()
            expect(page.locator(".list-footer")).to_contain_text("page 1")
            page.set_viewport_size({"width": 390, "height": 844})
            workspace(page)
            page.set_viewport_size({"width": 1440, "height": 1000})
        checks.append(
            "Run task results and comparisons page loaded rows locally and preserve refresh position"
        )

        def truncated_tasks(route):
            route.fulfill(json={"items": [task] * 200, "next_page_token": "more"})

        page.route("**/dockflow/v1/tasks?*", truncated_tasks)
        page.goto(endpoint + "/ui/#/runs/" + run + "?tab=Artifacts")
        expect(page.locator(".list-footer")).to_contain_text(
            "2000 loaded · truncated subset"
        )
        page.unroute("**/dockflow/v1/tasks?*", truncated_tasks)
        checks.append(
            "Bounded task results explicitly label loaded rows as a truncated subset"
        )

        def storage(route):
            body = route.request.post_data_json
            if route.request.url.endswith("/storage/scan"):
                route.fulfill(json={"scan_id": "browser-scan"})
                return
            selected = body.get("selected", [])
            if body.get("orphans"):
                selected = [f"row-{i}" for i in range(1, 57)]
            second = bool(body.get("page_token"))
            items = [
                {
                    "id": f"row-{i}",
                    "path": f"example/file-{i}.bin",
                    "size_bytes": 1024,
                    "classification": "orphan" if i else "protected",
                    "artifact_ids": [],
                    "eligible": bool(i),
                    "blockers": [] if i else ["Protected metadata"],
                }
                for i in (range(50, 57) if second else range(50))
            ]
            route.fulfill(
                json={
                    "scan_id": "browser-scan",
                    "state": "completed",
                    "created_at": "2026-10-25T12:00:00Z",
                    "location": "managed/example",
                    "items": items,
                    "selected_ids": selected,
                    "selection_groups": {},
                    "next_page_token": None if second else "browser-cursor",
                    "retention": {"days": -1, "interval_seconds": 3600},
                    "totals": {
                        "selected_bytes": len(selected) * 1024,
                        "orphan_bytes": 56 * 1024,
                        "artifact_bytes": 0,
                        "protected_artifact_bytes": 0,
                        "file_count": 57,
                    },
                }
            )

        page.route("**/dockflow/v1/storage/**", storage)
        page.goto(endpoint + "/ui/#/storage")
        page.get_by_role("button", name="Scan storage", exact=True).click()
        expect(page.locator(".list-footer")).to_contain_text("50 files on this page")
        workspace(page)
        expect(
            page.get_by_label("Select example/file-0.bin", exact=True)
        ).to_be_disabled()
        expect(page.locator(".cleanup-metrics")).to_be_visible()
        page.get_by_role(
            "button", name="Select all eligible orphans", exact=True
        ).click()
        expect(page.locator(".cleanup-metrics").first).to_contain_text("56.00 KiB")
        page.get_by_role("button", name="Next", exact=True).click()
        expect(page.locator(".list-footer")).to_contain_text("7 files on this page")
        page.get_by_role("button", name="Previous", exact=True).click()
        expect(page.locator(".list-footer")).to_contain_text("50 files on this page")
        page.get_by_role(
            "button", name="Explain storage classifications", exact=True
        ).click()
        expect(page.get_by_role("dialog")).to_contain_text("Retained file")
        page.get_by_role("button", name="Close dialog", exact=True).click()
        page.get_by_role("button", name="Deletion jobs", exact=True).click()
        expect(page.get_by_label("Plan ID", exact=True)).to_be_visible()
        page.get_by_role("button", name="Close dialog", exact=True).click()
        page.get_by_role("button", name="Preview retention", exact=True).click()
        expect(page.get_by_role("dialog")).to_contain_text("Deployment retention")
        page.get_by_role("button", name="Close dialog", exact=True).click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.reload()
        expect(page.locator(".list-footer")).to_contain_text("No completed scan")
        page.get_by_role("button", name="Scan storage", exact=True).click()
        expect(page.locator(".list-footer")).to_contain_text("50 files on this page")
        workspace(page)
        expect(page.locator(".cleanup-metrics")).to_be_visible()
        assert not page.locator(".list-header details").evaluate("node => node.open")
        page.locator(".list-header summary").click()
        expect(
            page.get_by_role(
                "button", name="Explain storage classifications", exact=True
            )
        ).to_be_visible()
        checks.append(
            "Cleanup fixed estimates/pagination, protected rows, bulk selection, secondary dialogs and narrow options"
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
