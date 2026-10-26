"""Verify graph workspace layout/state on a disposable web_fixture service.

Requires optional Playwright tooling. All API traffic is read-only. Long/nested
graphs and a running status are browser-local response projections; no records
are changed. Only neutral check descriptions are printed.
"""

import argparse
import copy
import json
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def check_background_pan(page):
    viewport = page.locator(".graph-viewport")

    def state():
        return page.locator(".graph").evaluate("node => node.captureViewport()")

    def background():
        return viewport.evaluate("""node => {
          const r = node.getBoundingClientRect();
          for (let y = r.top + 100; y < r.bottom - 30; y += 24)
            for (let x = r.left + 100; x < r.right - 30; x += 24) {
              const target = document.elementFromPoint(x, y);
              if (target?.closest('.graph-viewport') === node && !target.closest('.graph-node'))
                return {x, y};
            }
          throw Error('No visible background point');
        }""")

    def begin():
        point = background()
        page.mouse.move(point["x"], point["y"])
        viewport.evaluate("""node => node.addEventListener('pointerdown',
          event => { window.panPointerId = event.pointerId; }, {once: true})""")
        page.mouse.down()
        return point

    for zoom_button in ["Reset", "Zoom in"]:
        page.get_by_role("button", name=zoom_button, exact=True).click()
        viewport.evaluate("node => { node.scrollLeft = 250; node.scrollTop = 650; }")
        before = state()
        identity = page.locator(".graph").element_handle()
        point = begin()
        page.mouse.move(point["x"] - 60, point["y"] - 70, steps=5)
        expect(viewport).to_have_class("graph-viewport is-panning")
        assert viewport.evaluate("node => getComputedStyle(node).cursor") == "grabbing"
        after = state()
        assert after["left"] == before["left"] + 60
        assert after["top"] == before["top"] + 70
        assert after["zoom"] == before["zoom"]
        page.mouse.up()
        expect(viewport).to_have_class("graph-viewport")
        assert viewport.evaluate("node => getComputedStyle(node).cursor") == "grab"
        assert page.evaluate(
            'node => node === document.querySelector(".graph")', identity
        )
        point = begin()
        page.mouse.move(point["x"] + 40, point["y"] + 30, steps=4)
        page.mouse.up()
        assert state()["left"] == after["left"] - 40
        assert state()["top"] == after["top"] - 30

    # Tiny movement and secondary-button presses do not start a gesture.
    before = state()
    point = begin()
    page.mouse.move(point["x"] + 2, point["y"] + 1)
    page.mouse.up()
    assert state() == before
    point = background()
    page.mouse.move(point["x"], point["y"])
    page.mouse.down(button="right")
    page.mouse.move(point["x"] - 20, point["y"] - 20)
    page.mouse.up(button="right")
    page.keyboard.press("Escape")
    assert state() == before

    # Captured pointers still end cleanly after leaving the viewport.
    point = begin()
    bounds = viewport.bounding_box()
    page.mouse.move(bounds["x"] - 20, point["y"] - 30, steps=5)
    page.mouse.up()
    expect(viewport).to_have_class("graph-viewport")
    before = state()
    page.mouse.move(point["x"], point["y"])
    assert state() == before

    for end in ["cancel", "capture", "blur", "wheel"]:
        point = begin()
        page.mouse.move(point["x"] - 20, point["y"] - 20)
        if end == "cancel":
            viewport.dispatch_event(
                "pointercancel", {"pointerId": page.evaluate("panPointerId")}
            )
        elif end == "capture":
            viewport.evaluate("node => node.releasePointerCapture(window.panPointerId)")
            page.mouse.move(point["x"] - 21, point["y"] - 21)
        elif end == "blur":
            page.evaluate('window.dispatchEvent(new Event("blur"))')
        else:
            page.mouse.wheel(0, 40)
        expect(viewport).to_have_class("graph-viewport")
        page.mouse.up()
    viewport.evaluate("node => { node.scrollLeft = 0; node.scrollTop = 0; }")
    point = begin()
    page.mouse.move(point["x"] + 30, point["y"] + 30)
    page.mouse.up()
    assert state()["left"] == 0 and state()["top"] == 0
    viewport.evaluate("node => { node.scrollLeft = 1e9; node.scrollTop = 1e9; }")
    before = state()
    point = begin()
    page.mouse.move(point["x"] - 40, point["y"] - 40)
    page.mouse.up()
    assert state() == before
    viewport.evaluate("node => { node.scrollLeft = 0; node.scrollTop = 0; }")
    bounds = viewport.bounding_box()
    node = page.locator(".graph-node").first.bounding_box()
    page.mouse.move(node["x"] + 100, bounds["y"] + 16)
    page.mouse.down()
    page.mouse.move(node["x"] + 100, node["y"] + 30, steps=3)
    page.mouse.up()
    assert viewport.evaluate("node => getComputedStyle(node).touchAction") == "auto"
    expect(page.locator(".graph-inspector")).to_have_count(0)
    expect(page.locator(".graph-node.selected")).to_have_count(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file", type=Path)
    args = parser.parse_args()
    endpoint = args.url.rstrip("/")
    token = args.token_file.read_text().strip() if args.token_file else ""

    def api(path):
        with urlopen(
            Request(
                endpoint + "/dockflow/v1" + path,
                headers={"Authorization": "Bearer " + token} if token else {},
            ),
            timeout=30,
        ) as response:
            return json.load(response)

    if not api("/capabilities")["project_id"].startswith("web-fixture-"):
        raise SystemExit("Use a disposable web_fixture service")
    run = api("/runs")["items"][0]
    definition = api("/definitions/" + run["definition_id"])
    pipeline = api("/pipelines/" + definition["pipeline_id"])
    polling = False
    errors = []
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        def open_page(url):
            page.goto(url)
            if token:
                page.locator("h1,dialog[open]").first.wait_for()
                if page.get_by_label("Bearer token", exact=True).is_visible():
                    page.get_by_label("Bearer token", exact=True).fill(token)
                    page.get_by_role("dialog").get_by_role(
                        "button", name="Connect", exact=True
                    ).click()

        page.on("pageerror", lambda error: errors.append(str(error)))

        def definition_projection(route):
            response = route.fetch()
            value = response.json()
            spec = value["pipeline_spec"]
            tasks = spec["root"]["dag"]["tasks"]
            example = copy.deepcopy(next(iter(tasks.values())))
            previous = next(iter(tasks))
            for index in range(18):
                name = f"workspace-step-{index}"
                task = copy.deepcopy(example)
                task["dependentTasks"] = [previous]
                task["taskInfo"] = {"name": name}
                task.pop("inputs", None)
                task["workspace_fixture_lines"] = [
                    f"Fixture detail line {line}" for line in range(100)
                ]
                tasks[name] = task
                previous = name
            for index in range(8):
                peer = copy.deepcopy(example)
                peer.pop("inputs", None)
                peer.pop("dependentTasks", None)
                tasks[f"workspace-peer-{index}"] = peer
            spec["components"]["workspace-group"] = {
                "dag": {"tasks": {"child": copy.deepcopy(example)}}
            }
            tasks["workspace-group"] = {"componentRef": {"name": "workspace-group"}}
            route.fulfill(response=response, json=value)

        def run_projection(route):
            response = route.fetch()
            value = response.json()
            if polling:
                value["state"] = "running"
            route.fulfill(response=response, json=value)

        page.route("**/dockflow/v1/definitions/*", definition_projection)
        page.route("**/dockflow/v1/runs/" + run["run_id"], run_projection)

        def snapshot():
            return page.locator(".graph").evaluate("node => node.captureViewport()")

        def assert_workspace():
            assert page.evaluate("""() => {
              const rect = selector => document.querySelector(selector).getBoundingClientRect();
              const viewport = rect('.graph-viewport'), header = rect('.detail-header');
              const context = rect('.sidebar-context'), sidebar = rect('.sidebar'), brand = rect('.brand');
              return !document.querySelector('.topbar') && header.top === 0 &&
                context.top >= brand.bottom && context.right <= sidebar.right && sidebar.top === 0 &&
                sidebar.bottom === innerHeight && Math.abs(viewport.bottom - innerHeight) <= 1 &&
                viewport.height > innerHeight * .4 &&
                document.documentElement.scrollWidth <= innerWidth &&
                document.documentElement.scrollHeight <= innerHeight &&
                document.getElementById('content').scrollTop === 0;
            }""")

        for kind, identifier in [
            ("pipelines", pipeline["pipeline_id"]),
            ("runs", run["run_id"]),
        ]:
            for width, height in [(1440, 1000), (390, 844)]:
                page.set_viewport_size({"width": width, "height": height})
                open_page(endpoint + "/ui/#/" + kind + "/" + identifier)
                page.wait_for_function(
                    "path => document.querySelector('.detail-screen')?.detailView?.path === path",
                    arg=kind + "/" + identifier,
                )
                expect(page.locator(".graph-node")).to_have_count(29)
                assert_workspace()
                check_background_pan(page)
                page.get_by_role("button", name="Reset", exact=True).click()
                page.get_by_role("button", name="Zoom out", exact=True).click()
                page.locator(".graph-viewport").evaluate(
                    "node => { node.scrollLeft = 140; node.scrollTop = 650; }"
                )
                page.evaluate(
                    "window.workspaceGraph = document.querySelector('.graph')"
                )
                before = snapshot()
                requests = []

                def record_request(request, captured=requests):
                    if not request.url.endswith("/dockflow/v1/ui/reference-names"):
                        captured.append(request)

                page.on("request", record_request)
                for name in ["workspace-step-3", "workspace-step-4"]:
                    page.locator(
                        f'[data-node="{name}"] .graph-node-select'
                    ).dispatch_event("click")
                    expect(page.locator(".graph-inspector")).to_be_visible()
                    expect(
                        page.locator(f'[data-node="{name}"].selected')
                    ).to_have_count(1)
                    assert page.evaluate(
                        "workspaceGraph === document.querySelector('.graph')"
                    )
                    assert snapshot() == before
                page.remove_listener("request", record_request)
                assert not requests, "Selection must not refetch the graph/page"
                page.go_back()
                expect(
                    page.locator('[data-node="workspace-step-3"].selected')
                ).to_have_count(1)
                assert snapshot() == before
                assert page.evaluate(
                    "workspaceGraph === document.querySelector('.graph')"
                )
                if kind == "runs":
                    page.locator(".graph-inspector").get_by_role(
                        "tab", name="Attempts", exact=True
                    ).click()
                    expect(
                        page.locator(".graph-inspector").get_by_role(
                            "tab", name="Attempts", exact=True
                        )
                    ).to_have_attribute("aria-selected", "true")
                    assert snapshot() == before
                    assert page.evaluate(
                        "workspaceGraph === document.querySelector('.graph')"
                    )
                page.locator(".graph-inspector").evaluate(
                    "node => node.scrollTop = 400"
                )
                assert (
                    page.locator(".graph-inspector").evaluate("node => node.scrollTop")
                    > 0
                )
                assert snapshot() == before
                assert_workspace()
                page.locator(".graph-viewport").evaluate(
                    "node => node.scrollLeft = node.scrollWidth"
                )
                before_close = snapshot()
                page.get_by_role(
                    "button", name="Close step details", exact=True
                ).click()
                expect(page.locator(".graph-inspector")).to_have_count(0)
                assert snapshot() == before_close
                assert page.evaluate(
                    "workspaceGraph === document.querySelector('.graph')"
                )
                page.locator(".graph-viewport").focus()
                page.keyboard.press("PageDown")
                page.wait_for_timeout(250)
                assert snapshot()["top"] > before["top"]
                assert_workspace()
                if kind == "runs":
                    before = snapshot()
                    previous_graph = page.locator(".graph").element_handle()
                    page.get_by_role("button", name="Refresh", exact=True).click()
                    page.wait_for_function(
                        "previous => previous !== document.querySelector('.graph')",
                        arg=previous_graph,
                    )
                    expect(page.locator(".graph-toolbar")).to_contain_text("90%")
                    assert snapshot() == before
                    if width > 760:
                        page.evaluate("""() => {
                          const original = window.fetch;
                          window.fetch = async (...args) => {
                            const response = await original(...args);
                            if (String(args[0]).includes('/dockflow/v1/tasks?'))
                              await new Promise(resolve => { window.releaseWorkspaceRefresh = resolve; });
                            return response;
                          };
                          window.restoreWorkspaceFetch = () => { window.fetch = original; };
                        }""")
                        previous_graph = page.locator(".graph").element_handle()
                        page.get_by_role("button", name="Refresh", exact=True).click()
                        page.wait_for_function(
                            "() => typeof window.releaseWorkspaceRefresh === 'function'"
                        )
                        page.get_by_role("button", name="Zoom out", exact=True).click()
                        page.locator(".graph-viewport").evaluate(
                            "node => node.scrollTop = 850"
                        )
                        during_refresh = snapshot()
                        page.evaluate(
                            "releaseWorkspaceRefresh(); restoreWorkspaceFetch()"
                        )
                        page.wait_for_function(
                            "previous => previous !== document.querySelector('.graph')",
                            arg=previous_graph,
                        )
                        assert snapshot() == during_refresh
                checks.append(
                    f"{kind}: {'desktop' if width > 760 else 'narrow'} background drag/cancellation, layout, selection/history, inspector scroll/close, keyboard pan and viewport state"
                )

            page.set_viewport_size({"width": 1440, "height": 1000})
            page.get_by_role(
                "button", name="Open subpipeline workspace-group", exact=True
            ).dispatch_event("click")
            expect(page.locator(".graph-node")).to_have_count(1)
            assert snapshot()["zoom"] == 1 and snapshot()["top"] == 0
            viewport = page.locator(".graph-viewport")
            bounds = viewport.bounding_box()
            page.mouse.move(bounds["x"] + 16, bounds["y"] + 16)
            page.mouse.down()
            page.mouse.move(bounds["x"] + 8, bounds["y"] + 8, steps=2)
            expect(viewport).to_have_class("graph-viewport is-panning")
            page.mouse.up()
            expect(viewport).to_have_class("graph-viewport")
            page.get_by_role("button", name="Pipeline", exact=True).click()
            expect(page.locator(".graph-node")).to_have_count(29)
            page.get_by_role("button", name="All tasks", exact=True).click()
            expect(page.locator(".graph-node")).to_have_count(30)
            check_background_pan(page)
            checks.append(f"{kind}: focused scope and All tasks navigation/dragging")

        polling = True
        open_page(endpoint + "/ui/#/runs/" + run["run_id"])
        expect(page.get_by_label("Live updates every 3s")).to_be_checked()
        viewport = page.locator(".graph-viewport")
        bounds = viewport.bounding_box()
        previous_graph = page.locator(".graph").element_handle()
        page.mouse.move(bounds["x"] + 16, bounds["y"] + 16)
        page.mouse.down()
        page.mouse.move(bounds["x"] + 8, bounds["y"] + 8)
        expect(viewport).to_have_class("graph-viewport is-panning")
        page.wait_for_timeout(3300)
        assert page.evaluate(
            'node => node === document.querySelector(".graph")', previous_graph
        )
        expect(viewport).to_have_class("graph-viewport is-panning")
        page.mouse.up()
        page.get_by_role("button", name="Zoom out", exact=True).click()
        page.locator(".graph-viewport").evaluate("node => node.scrollTop = 700")
        before = snapshot()
        previous_graph = page.locator(".graph").element_handle()
        with page.expect_response(
            lambda response: response.url.endswith("/runs/" + run["run_id"]),
            timeout=10000,
        ):
            pass
        page.wait_for_function(
            "previous => previous !== document.querySelector('.graph')",
            arg=previous_graph,
        )
        expect(page.locator(".graph-toolbar")).to_contain_text("90%")
        assert snapshot() == before
        checks.append(
            "Live Run refresh preserves zoom and pan with browser-local running status"
        )
        page.get_by_role("tab", name="Details", exact=True).click()
        expect(page.locator(".detail-body h2").first).to_have_text("Invocation")
        page.locator(".detail-body").evaluate("node => node.scrollTop = 500")
        assert (
            page.locator(".detail-header").evaluate(
                "node => node.getBoundingClientRect().top"
            )
            == 0
        )
        page.get_by_role("tab", name="Graph", exact=True).click()
        expect(page.locator(".graph-node")).to_have_count(29)
        page.get_by_role("link", name="Artifacts", exact=True).click()
        expect(
            page.get_by_role("heading", name="Artifacts", exact=True)
        ).to_be_visible()
        assert page.locator("#content").evaluate(
            "node => !node.classList.contains('detail-mode')"
        )
        checks.append(
            "Fixed headers on non-Graph tabs and restored normal collection layout"
        )
        assert not errors, "Browser page errors occurred"
        browser.close()
    print(json.dumps({"checks": checks, "page_errors": []}, indent=2))


if __name__ == "__main__":
    main()
