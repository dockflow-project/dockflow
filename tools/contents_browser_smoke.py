"""Read-only Contents journeys on a disposable web_fixture --contents service.

Exercises real preview API reads; no catalog/storage mutation or execution occurs.
Optional screenshots mask project/resource identifiers. Receipts contain neutral
check descriptions. Requires optional Playwright tooling.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
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

    def api(path):
        with urlopen(
            Request(endpoint + "/dockflow/v1" + path, headers=headers)
        ) as response:
            return json.load(response)

    if not api("/capabilities")["project_id"].startswith("web-fixture-"):
        raise SystemExit("Use a disposable web_fixture --contents service")
    records = {item.get("version"): item for item in api("/artifacts")["items"]}
    checks, errors, external = [], [], []
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda req: external.append("external request")
            if urlsplit(req.url).netloc != urlsplit(endpoint).netloc
            and not req.url.startswith("data:")
            else None,
        )

        def open_artifact(label):
            page.goto(endpoint + "/ui/#/artifacts/" + records[label]["artifact_id"])
            if token:
                page.locator("h1,dialog[open]").first.wait_for()
                if page.get_by_label("Bearer token", exact=True).is_visible():
                    page.get_by_label("Bearer token", exact=True).fill(token)
                    page.get_by_role("dialog").get_by_role(
                        "button", name="Connect", exact=True
                    ).click()
            expect(
                page.get_by_role("tab", name="Contents", exact=True)
            ).to_have_attribute("aria-selected", "true")
            page.locator(".contents-status").wait_for()
            assert page.locator(".detail-header > .tabs .tab").all_text_contents() == [
                "Contents",
                "Overview",
                "Lineage",
            ]

        def capture(name):
            if args.output:
                page.screenshot(
                    path=str(args.output / name),
                    mask=[page.locator("#project-name"), page.locator(".detail-meta")],
                )

        def layout():
            region = page.locator(".list-content")
            assert region.get_attribute("aria-label") == "Artifact contents"
            assert region.bounding_box()["height"] > 120
            header = page.locator(".detail-header").bounding_box()
            region.evaluate("node => node.scrollTop=350")
            assert page.locator(".detail-header").bounding_box() == header
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            footer = page.locator(".list-footer").bounding_box()
            assert (
                abs(footer["y"] + footer["height"] - page.viewport_size["height"]) < 2
            )

        open_artifact("Preview CSV")
        expect(page.locator("tbody tr")).to_have_count(50)
        expect(page.locator("tbody tr").first.locator("td").first).to_have_text("0")
        assert records["Preview CSV"]["size_bytes"] > 10 * 1024 * 1024
        layout()
        head_top = page.locator(".list-content th").first.bounding_box()["y"]
        assert abs(head_top - page.locator(".list-content").bounding_box()["y"]) < 2
        with page.expect_response(
            lambda response: "/contents?" in response.url
        ) as fetched:
            page.get_by_role("button", name="Next", exact=True).click()
        data = fetched.value.json()
        assert len(data["rows"]) == 50 and data["first_row"] == 51
        assert len(fetched.value.body()) < 65536
        expect(page.locator(".list-footer")).to_contain_text("51–100")
        expect(page.locator("tbody tr").first.locator("td").first).to_have_text("50")
        page.get_by_role("button", name="Previous", exact=True).click()
        expect(page.locator(".list-footer")).to_contain_text("1–50")
        capture("contents-csv-desktop.png")
        checks.append(
            "Default first Contents tab and real large CSV dynamic pages, exact rows, bounded response and sticky headings"
        )

        open_artifact("Preview JSON")
        info = page.locator(".json-branch > summary").filter(has_text='"info"')
        info.click()
        expect(page.locator(".json-number").first).to_have_text("9007199254740993")
        expect(
            page.locator(".json-string").filter(has_text="<img src=x onerror=alert(1)>")
        ).to_have_count(1)
        assert page.locator(".json-tree img").count() == 0
        items = page.locator(".json-branch > summary").filter(has_text='"items"')
        items.click()
        branch = items.locator("..")
        expect(branch.locator(":scope > .json-children > .json-branch")).to_have_count(
            100
        )
        branch.get_by_role("button", name="Show next 100", exact=True).click()
        expect(branch.locator(":scope > .json-children > .json-branch")).to_have_count(
            200
        )
        page.locator(".list-content").evaluate("node => node.scrollTop=400")
        old = page.locator(".list-content").element_handle()
        page.get_by_role("button", name="Refresh", exact=True).click()
        page.wait_for_function("node => !node.isConnected", arg=old)
        expect(branch.locator(":scope > .json-children > .json-branch")).to_have_count(
            200
        )
        assert page.locator(".list-content").evaluate("node => node.scrollTop") == 400
        capture("contents-json-desktop.png")
        checks.append(
            "Highlighted JSON preserves exact large numbers and literal markup, lazily expands batches and retains expansion/scroll on refresh"
        )

        open_artifact("Preview image")
        page.wait_for_function(
            "() => document.querySelector('.artifact-image img')?.naturalWidth === 320"
        )
        image = page.locator(".artifact-image img")
        assert image.get_attribute("src").startswith("data:image/png;base64,")
        page.get_by_role("button", name="Actual size", exact=True).click()
        expect(image).to_have_class("natural-size")
        page.get_by_role("button", name="Fit to width", exact=True).click()
        capture("contents-image-desktop.png")
        checks.append(
            "Authenticated same-origin image read with raster data URL, decoded dimensions, actual-size and fit controls"
        )

        open_artifact("Preview directory")
        page.locator(".list-content").get_by_role(
            "link", name="▸ nested", exact=True
        ).click()
        page.locator(".list-content").get_by_role(
            "link", name="data.json", exact=True
        ).click()
        expect(page.locator(".json-tree")).to_be_visible()
        assert "path=nested%2Fdata.json" in page.url
        page.go_back()
        expect(
            page.locator(".list-content").get_by_role(
                "link", name="▸ tables", exact=True
            )
        ).to_be_visible()
        page.locator(".list-content").get_by_role(
            "link", name="▸ tables", exact=True
        ).click()
        page.locator(".list-content").get_by_role(
            "link", name="example.csv", exact=True
        ).click()
        expect(page.locator(".list-footer")).to_contain_text("1–50")
        page.locator(".contents-breadcrumb").get_by_role(
            "link", name="Artifact root", exact=True
        ).click()
        expect(
            page.locator(".list-content").get_by_role(
                "link", name="▸ empty", exact=True
            )
        ).to_be_visible()
        page.locator(".list-content").get_by_role(
            "link", name="▸ empty", exact=True
        ).click()
        expect(page.locator(".list-footer")).to_contain_text("0 entries")
        capture("contents-empty-directory.png")
        checks.append(
            "Recorded directory browser, nested JSON/CSV, breadcrumbs, back history and empty folders"
        )

        open_artifact("Preview directory")
        page.locator(".list-content").get_by_role(
            "link", name="unknown.bin", exact=True
        ).click()
        expect(page.locator(".list-content")).to_contain_text("No visual preview")
        page.locator(".contents-breadcrumb").get_by_role(
            "link", name="Artifact root", exact=True
        ).click()
        page.locator(".list-content").get_by_role(
            "link", name="▸ nested", exact=True
        ).click()
        page.locator(".list-content").get_by_role(
            "link", name="broken.json", exact=True
        ).click()
        expect(page.locator(".list-content .notice.error")).to_contain_text(
            "valid bounded JSON"
        )
        page.get_by_role("tab", name="Overview", exact=True).click()
        expect(page.get_by_role("heading", name="Artifact", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Lineage", exact=True).click()
        expect(
            page.get_by_role("heading", name="Consumer tasks", exact=True)
        ).to_be_visible()
        open_artifact("Preview text")
        expect(page.locator(".list-content")).to_contain_text("first 64 KiB")
        checks.append(
            "Unsupported/malformed files retain artifact context and Overview/Lineage; text truncation is explicit"
        )

        page.set_viewport_size({"width": 390, "height": 844})
        for label in [
            "Preview CSV",
            "Preview JSON",
            "Preview image",
            "Preview directory",
            "Preview text",
        ]:
            open_artifact(label)
            layout()
            page.locator(".list-content").focus()
            capture(label.replace(" ", "-").lower() + "-mobile.png")
        checks.append(
            "All five viewers preserve fixed context/controls/footer and scrolling on a narrow viewport"
        )
        assert not errors and not external, (
            "Browser page errors or external requests occurred"
        )
        result = {
            "browser": browser.version,
            "checks": checks,
            "page_errors": [],
            "external_requests": [],
        }
        if args.output:
            (args.output / "result.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
