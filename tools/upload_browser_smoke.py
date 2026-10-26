"""Upload files and both ZIP modes on a disposable web_fixture service.

Creates manual artifacts only in an explicitly identified fixture. Does not reset
data or execute Runs. Optional captures mask resource identifiers; review/discard
them before retaining the neutral result receipt. Requires optional Playwright.
"""

import argparse
import io
import json
import zipfile
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
        raise SystemExit("Use a disposable web_fixture service")
    before = api("/artifacts")["items"]
    before_runs = api("/runs")["items"]
    checks, errors, external = [], [], []
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("nested/table.csv", "id,value\n1,uploaded\n")
        archive.writestr("empty/", b"")
        archive.writestr("data.json", '{"literal":"<script>"}')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        submissions = []

        def upload_request(route):
            expect(
                page.get_by_role("dialog").get_by_role(
                    "button", name="Working…", exact=True
                )
            ).to_be_disabled()
            submissions.append("one submission")
            route.continue_()

        page.route("**/dockflow/v1/artifacts/upload", upload_request)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: external.append("external request")
            if urlsplit(request.url).netloc != urlsplit(endpoint).netloc
            and not request.url.startswith("data:")
            else None,
        )
        page.goto(endpoint + "/ui/#/artifacts")
        if token:
            page.get_by_label("Bearer token", exact=True).fill(token)
            page.get_by_role("dialog").get_by_role(
                "button", name="Connect", exact=True
            ).click()
        expect(
            page.get_by_role("heading", name="Artifacts", exact=True)
        ).to_be_visible()

        def open_form(name, content, mime="application/octet-stream"):
            page.locator("nav").get_by_role(
                "link", name="Artifacts", exact=True
            ).click()
            page.get_by_role("button", name="Upload artifact", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_label("File", exact=True).set_input_files(
                {"name": name, "mimeType": mime, "buffer": content}
            )
            return dialog

        def submit(dialog):
            with page.expect_response(
                lambda response: response.url.endswith("/artifacts/upload")
            ) as pending:
                dialog.get_by_role(
                    "button", name="Upload and register", exact=True
                ).click()
            response = pending.value
            assert response.status == 201, response.text()
            expect(dialog).not_to_be_visible()
            expect(
                page.get_by_role("tab", name="Contents", exact=True)
            ).to_have_attribute("aria-selected", "true")
            return response.json()

        def capture(name):
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=str(args.output / name),
                    mask=[
                        page.locator("#project-name"),
                        page.locator(".detail-meta"),
                        page.locator(".list-content .subtle"),
                        page.locator(".id, .cell-detail"),
                    ],
                )

        dialog = open_form(
            "uploaded.csv", b"id,value\n1,hello\n2,caf\xc3\xa9\n", "text/csv"
        )
        expect(dialog.get_by_label("ZIP handling", exact=True)).not_to_be_visible()
        dialog.get_by_label("Metadata (JSON object)", exact=True).fill(
            '{"description":"Uploaded dataset"}'
        )
        capture("upload-form-desktop.png")
        record = submit(dialog)
        expect(page.locator("tbody tr")).to_have_count(2)
        expect(page.locator(".detail-title")).to_contain_text("uploaded.csv")
        assert record["creation_origin"] == "manual" and record["producer"] is None
        assert record["metadata"] == {"description": "Uploaded dataset"}
        checks.append(
            "Browser file upload registers a manual managed artifact and opens its CSV Contents"
        )

        dialog = open_form("bundle.zip", data.getvalue())
        expect(dialog.get_by_label("ZIP handling", exact=True)).to_have_value("keep")
        kept = submit(dialog)
        assert kept["payload_kind"] == "file" and kept["size_bytes"] == len(
            data.getvalue()
        )
        expect(page.locator(".list-content")).to_contain_text("preview")
        checks.append("ZIP default keeps the archive bytes as a file artifact")

        dialog = open_form("bundle.zip", data.getvalue())
        dialog.get_by_label("ZIP handling", exact=True).select_option("extract")
        capture("upload-zip-desktop.png")
        extracted = submit(dialog)
        assert extracted["payload_kind"] == "directory"
        page.get_by_role("link", name="▸ nested", exact=True).click()
        page.get_by_role("link", name="table.csv", exact=True).click()
        expect(page.locator("tbody tr")).to_have_count(1)
        expect(page.locator("tbody")).to_contain_text("uploaded")
        checks.append(
            "ZIP extraction registers a directory artifact with nested CSV and empty-folder inventory"
        )

        dialog = open_form("broken.zip", b"not a zip")
        dialog.get_by_label("ZIP handling", exact=True).select_option("extract")
        dialog.get_by_label("Data revision", exact=True).fill("Keep form on error")
        with page.expect_response(
            lambda response: response.url.endswith("/artifacts/upload")
        ) as pending:
            dialog.get_by_role("button", name="Upload and register", exact=True).click()
        assert pending.value.status == 400
        expect(dialog).to_be_visible()
        expect(dialog.get_by_label("Data revision", exact=True)).to_have_value(
            "Keep form on error"
        )
        assert (
            dialog.get_by_label("File", exact=True).evaluate(
                "node => node.files[0].name"
            )
            == "broken.zip"
        )
        expect(
            dialog.get_by_role("button", name="Upload and register", exact=True)
        ).to_be_enabled()
        dialog.get_by_label("File", exact=True).set_input_files(
            {"name": "replacement.csv", "mimeType": "text/csv", "buffer": b"a,b\n1,2\n"}
        )
        expect(dialog.get_by_label("ZIP handling", exact=True)).not_to_be_visible()
        # Re-selecting ZIP after CSV resets the mode to keep.
        dialog.get_by_label("File", exact=True).set_input_files(
            {
                "name": "replacement.zip",
                "mimeType": "application/zip",
                "buffer": data.getvalue(),
            }
        )
        expect(dialog.get_by_label("ZIP handling", exact=True)).to_have_value("keep")
        page.keyboard.press("Escape")
        checks.append(
            "Invalid ZIP preserves the form and recovery controls; switching file type resets ZIP mode"
        )

        page.set_viewport_size({"width": 390, "height": 844})
        dialog = open_form("mobile.zip", data.getvalue())
        dialog.get_by_label("ZIP handling", exact=True).select_option("extract")
        dialog.get_by_role(
            "button", name="Upload and register", exact=True
        ).scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        capture("upload-form-narrow.png")
        submit(dialog)
        expect(page.get_by_role("link", name="▸ empty", exact=True)).to_be_visible()
        page.get_by_role("link", name="▸ empty", exact=True).click()
        expect(page.locator(".list-content")).to_contain_text("empty")
        checks.append(
            "Narrow upload form scrolls to its controls and extracted empty folders remain browsable"
        )
        browser.close()
    after = api("/artifacts")["items"]
    assert len(after) == len(before) + 4
    assert {record["artifact_id"] for record in before} <= {
        record["artifact_id"] for record in after
    }
    assert api("/runs")["items"] == before_runs
    assert len(submissions) == 5
    assert not errors and not external, (errors, external)
    checks.append(
        "Exactly four uploads were registered; failed upload created none; existing records and Runs were preserved"
    )
    result = {
        "checks": checks,
        "browser": "Chromium",
        "errors": errors,
        "external": external,
    }
    if args.output:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
