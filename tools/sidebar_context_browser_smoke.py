"""Read-only sidebar context, full-height workspace and connection journeys.

Requires optional Playwright and a disposable web_fixture service. Authentication
changes only the browser session. Long identity/status cases are local browser
projections; no records or storage are changed. Captures redact runtime IDs and
are for visual review/discard; receipts contain neutral check descriptions.
"""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    endpoint = args.url.rstrip("/")
    token = args.token_file.read_text().strip() if args.token_file else ""
    headers = {"Authorization": "Bearer " + token} if token else {}
    with urlopen(
        Request(endpoint + "/dockflow/v1/capabilities", headers=headers)
    ) as response:
        project = json.load(response)["project_id"]
    if not project.startswith("web-fixture-"):
        raise SystemExit("Use a disposable web_fixture service")
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def connect():
            page.locator("h1,dialog[open]").first.wait_for()
            if token and page.get_by_label("Bearer token", exact=True).is_visible():
                page.get_by_label("Bearer token", exact=True).fill(token)
                page.get_by_role("dialog").get_by_role(
                    "button", name="Connect", exact=True
                ).click()
            expect(
                page.get_by_role("heading", name="Artifacts", exact=True)
            ).to_be_visible()

        def frame():
            assert page.evaluate("""() => {
              const rect = selector => document.querySelector(selector).getBoundingClientRect();
              const sidebar = rect('.sidebar'), brand = rect('.brand'), context = rect('.sidebar-context');
              const main = rect('#content'), footer = rect('.list-footer'), button = rect('#connect');
              const utilities = rect('.sidebar-footer'), actions = rect('.sidebar-context-actions');
              const links = rect('.sidebar-utilities'), nav = rect('#navigation');
              const style = getComputedStyle(document.querySelector('.sidebar-context'));
              return !document.querySelector('.topbar') && main.top === 0 && main.bottom === innerHeight &&
                main.left === sidebar.right && context.top >= brand.bottom && context.right <= sidebar.right &&
                style.backgroundColor === 'rgba(0, 0, 0, 0)' && style.borderTopWidth === '0px' &&
                document.querySelector('.sidebar-context').innerText === document.querySelector('#project-name').innerText &&
                actions.top >= links.bottom && links.top >= utilities.top && nav.bottom <= utilities.top &&
                actions.bottom === innerHeight && getComputedStyle(document.querySelector('.sidebar-footer')).borderTopWidth === '1px' &&
                getComputedStyle(document.querySelector('.sidebar-context-actions')).borderTopWidth === '1px' &&
                utilities.bottom === innerHeight && button.left >= sidebar.left && button.right <= sidebar.right && button.bottom <= innerHeight &&
                Math.abs(footer.bottom - innerHeight) < 2 && document.documentElement.scrollWidth <= innerWidth &&
                document.documentElement.scrollHeight <= innerHeight;
            }""")

        def capture(name):
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=str(args.output / name),
                    mask=[page.locator(".id,.cell-detail,.cell-main")],
                )

        page.goto(endpoint + "/ui/#/artifacts")
        connect()
        expect(page.locator(".sidebar-context #project-name")).to_have_text(project)
        expect(page.locator("#project-name")).to_have_attribute("title", project)
        expect(page.locator(".sidebar-footer #connection")).to_have_text(
            "Service ready"
        )
        expect(page.locator(".sidebar-footer #connect")).to_have_text(
            "Sign out" if token else "Connect"
        )
        frame()
        checks.append(
            "Plain project name is beneath the logo; utilities sit between dividers above status/connection at the very bottom of the fixed footer; list uses the full height"
        )

        for width, height in [(1440, 1000), (390, 844), (390, 500)]:
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#project-name").evaluate(
                "node => { node.textContent = 'example-project-' + 'x'.repeat(112); node.title = node.textContent; }"
            )
            frame()
            context = page.locator(".sidebar-context").bounding_box()
            project_name = page.locator("#project-name")
            project_name.focus()
            expect(project_name).to_be_focused()
            if width < 760:
                assert project_name.evaluate(
                    "node => node.scrollHeight > node.clientHeight"
                )
                page.keyboard.press("End")
                page.wait_for_function(
                    "node => node.scrollTop >= node.scrollHeight - node.clientHeight - 1",
                    arg=project_name.element_handle(),
                )
                page.keyboard.press("Home")
                page.wait_for_function(
                    "node => node.scrollTop === 0", arg=project_name.element_handle()
                )
            page.locator("nav").get_by_role("link", name="Cleanup", exact=True).focus()
            assert page.locator(".sidebar-context").bounding_box() == context
            expect(page.locator("#connect")).to_be_visible()
            if height == 500:
                assert page.locator("#navigation").evaluate(
                    "node => node.scrollTop > 0"
                )
            page.locator("#navigation").evaluate("node => node.scrollTop = 0")
            capture(f"sidebar-{width}-{height}.png")
        checks.append(
            "Long project IDs remain readable/focusable with bounded scrolling; short/narrow navigation scrolls independently while context stays reachable"
        )

        page.route(
            "**/health/ready",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body='{"error":{"message":"Unavailable"}}',
            ),
        )
        page.goto(endpoint + "/ui/#/service")
        if token:
            page.locator("h1,dialog[open]").first.wait_for()
            if page.get_by_label("Bearer token", exact=True).is_visible():
                page.get_by_label("Bearer token", exact=True).fill(token)
                page.get_by_role("dialog").get_by_role(
                    "button", name="Connect", exact=True
                ).click()
        expect(page.locator(".sidebar-footer #connection")).to_have_text(
            "Recovery / unavailable"
        )
        expect(page.locator(".sidebar-footer #connect")).to_be_enabled()
        page.unroute("**/health/ready")
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(page.locator("#connection")).to_have_text("Service ready")
        page.goto(endpoint + "/ui/#/artifacts")
        connect()
        expect(page.locator("#connection")).to_have_text("Service ready")
        checks.append(
            "Unavailable and recovered readiness states use the sidebar status without disabling connection controls"
        )

        if token:
            page.locator(".sidebar-footer #connect").click()
            expect(page.locator("#project-name")).to_have_text("Not connected")
            assert page.locator("#project-name").get_attribute("title") is None
            expect(page.locator("#connection")).to_have_text("Not connected")
            expect(page.locator("#connect")).to_have_text("Connect")
            page.locator(".sidebar-footer #connect").click()
            page.get_by_label("Bearer token", exact=True).fill(token)
            page.get_by_role("dialog").get_by_role(
                "button", name="Connect", exact=True
            ).click()
            expect(page.locator("#project-name")).to_have_text(project)
            expect(page.locator("#connect")).to_have_text("Sign out")
            checks.append(
                "Sidebar sign-out clears token/project/title/status and Connect restores authenticated access"
            )
        assert not errors, errors
        browser.close()
    result = {"browser": "Chromium", "checks": checks, "page_errors": errors}
    if args.output:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
