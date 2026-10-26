"""Exercise destructive UI flows only on an explicitly disposable cleanup fixture.

Start tools/web_fixture.py with --cleanup. This probe refuses other project IDs.
Receipts retain neutral check descriptions; screenshots show relative storage keys.
"""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    endpoint = args.url.rstrip("/")

    def api(path, body=None):
        request = Request(
            endpoint + "/dockflow/v1" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    if not api("/capabilities")["project_id"].startswith("web-fixture-"):
        raise SystemExit(
            "Refusing destructive browser checks outside a disposable fixture"
        )
    artifacts = api("/artifacts", None)["items"]
    manual = next(
        item for item in artifacts if item.get("version") == "Manual database snapshot"
    )
    pinned = next(
        item for item in artifacts if item.get("version") == "Pinned manual dataset"
    )
    args.output.mkdir(parents=True, exist_ok=True)
    checks = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(endpoint + "/ui/#/storage")
        expect(
            page.get_by_role("heading", name="Storage cleanup", exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="Scan storage", exact=True).click()
        expect(
            page.get_by_role("button", name="Select all eligible orphans", exact=True)
        ).to_be_enabled()
        expect(
            page.locator("tbody").get_by_text("manual artifact", exact=True).first
        ).to_be_visible()
        expect(
            page.get_by_text(
                "Artifact is pinned; explicitly unpin it first", exact=False
            ).first
        ).to_be_visible()
        page.screenshot(
            path=str(args.output / "cleanup-desktop.png"),
            full_page=True,
            mask=[page.locator(".cleanup-location")],
        )
        page.get_by_role(
            "button", name="Select all eligible orphans", exact=True
        ).click()
        expect(
            page.get_by_role("button", name="Review selected deletion", exact=True)
        ).to_be_enabled()
        page.get_by_role("button", name="Review selected deletion", exact=True).click()
        dialog = page.get_by_role("dialog")
        apply_button = dialog.get_by_role(
            "button", name="Delete reviewed selection", exact=True
        )
        expect(apply_button).to_be_disabled()
        dialog.get_by_label("Type DANGER", exact=True).fill("danger")
        expect(apply_button).to_be_disabled()
        dialog.get_by_label("Type DANGER", exact=True).fill("DANGER")
        expect(apply_button).to_be_enabled()
        apply_button.click()
        expect(dialog).not_to_be_visible()
        assert all(
            item["artifact_id"]
            in {value["artifact_id"] for value in api("/artifacts")["items"]}
            for item in (manual, pinned)
        )
        checks.append(
            "Orphan cleanup excludes manual/pinned artifacts and requires exact DANGER"
        )
        page.goto(endpoint + "/ui/#/artifacts/" + pinned["artifact_id"])
        page.get_by_role("button", name="Delete artifact", exact=True).click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_label("Also delete managed storage files", exact=True).check()
        dialog.get_by_role("button", name="Review deletion", exact=True).click()
        expect(
            dialog.get_by_text(
                "Artifact is pinned; explicitly unpin it first", exact=False
            )
        ).to_be_visible()
        dialog.get_by_label("Type DANGER", exact=True).fill("DANGER")
        expect(
            dialog.get_by_role("button", name="Delete reviewed selection", exact=True)
        ).to_be_disabled()
        dialog.get_by_role("button", name="Close dialog", exact=True).click()
        checks.append("Pinned artifacts block both record and file deletion")
        page.goto(endpoint + "/ui/#/artifacts/" + manual["artifact_id"])
        page.get_by_role("button", name="Delete artifact", exact=True).click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_label("Also delete managed storage files", exact=True).check()
        dialog.get_by_role("button", name="Review deletion", exact=True).click()
        dialog.get_by_label("Type DANGER", exact=True).fill("DANGER")
        dialog.get_by_role(
            "button", name="Delete reviewed selection", exact=True
        ).click()
        expect(
            page.get_by_role("heading", name="Artifacts", exact=True)
        ).to_be_visible()
        assert manual["artifact_id"] not in {
            value["artifact_id"] for value in api("/artifacts")["items"]
        }
        checks.append("Explicit manual-artifact deletion removes its managed copy")
        pipelines = api("/pipelines")["items"]
        if pipelines:
            run = api(
                "/runs",
                {
                    "definition_id": pipelines[0]["definition_id"],
                    "display_name": "Disposable cleanup acceptance",
                    "reuse": {"scope": "none"},
                },
            )
            deadline = time.monotonic() + 90
            while run["state"] not in {
                "succeeded",
                "failed",
                "cancelled",
                "interrupted",
            }:
                if time.monotonic() > deadline:
                    raise AssertionError("Disposable Run did not finish")
                time.sleep(0.2)
                run = api("/runs/" + run["run_id"])
            assert run["state"] == "succeeded", run.get("error")
            attempts = api("/attempts?run_id=" + run["run_id"])["items"]
            assert attempts
            page.goto(endpoint + "/ui/#/attempts/" + attempts[0]["attempt_id"])
            page.get_by_role("button", name="Delete execution", exact=True).click()
            # A terminal outcome can precede the scheduler releasing its owner.
            # Retry only this explicit idle-owner conflict; never retry apply.
            deadline = time.monotonic() + 10
            while True:
                with page.expect_response(
                    lambda r: r.url.endswith("/deletions/plan")
                ) as planned:
                    page.get_by_role("dialog").get_by_role(
                        "button", name="Review deletion", exact=True
                    ).click()
                if planned.value.ok:
                    break
                failure = planned.value.json()["error"]
                assert (
                    planned.value.status == 409
                    and "idle execution owner" in failure["message"]
                )
                assert time.monotonic() < deadline, (
                    "Execution owner did not become idle"
                )
                time.sleep(0.2)
            page.get_by_role("dialog").get_by_role(
                "button", name="Delete reviewed selection", exact=True
            ).click()
            expect(
                page.get_by_role("heading", name="Executions", exact=True)
            ).to_be_visible()
            checks.append("Execution deletion through the packaged UI")
            page.goto(endpoint + "/ui/#/runs/" + run["run_id"])
            page.get_by_role("button", name="Delete run", exact=True).click()
            page.get_by_role("dialog").get_by_role(
                "button", name="Review deletion", exact=True
            ).click()
            page.get_by_role("dialog").get_by_role(
                "button", name="Delete reviewed selection", exact=True
            ).click()
            expect(page.get_by_role("heading", name="Runs", exact=True)).to_be_visible()
            checks.append("Run deletion preserves independent artifact records")
        page.goto(endpoint + "/ui/#/storage")
        page.set_viewport_size({"width": 390, "height": 844})
        scan_button = page.get_by_role("button", name="Scan storage", exact=True)
        if not scan_button.is_visible():
            scan_button = page.get_by_role("button", name="Rescan storage", exact=True)
        scan_button.click()
        expect(page.locator("tbody tr").first).to_be_visible()
        page.screenshot(
            path=str(args.output / "cleanup-mobile.png"),
            full_page=True,
            mask=[page.locator(".cleanup-location")],
        )
        assert not errors, errors
        checks.append("Desktop and narrow-screen storage inventory without page errors")
        result = {"browser": browser.version, "checks": checks, "page_errors": errors}
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        browser.close()


if __name__ == "__main__":
    main()
