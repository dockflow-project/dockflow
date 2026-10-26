"""Authenticated autocomplete qualification on a disposable web_fixture service.

Creates anonymous experiments in the disposable fixture. Suggestion race/failure
cases are browser-local projections. Exported receipts contain no runtime IDs;
optional captures mask record/project text and should be discarded after review.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
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

    def api(path, body=None):
        with urlopen(
            Request(
                endpoint + "/dockflow/v1" + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={**headers, "Content-Type": "application/json"},
            )
        ) as response:
            return json.load(response)

    if not api("/capabilities")["project_id"].startswith("web-fixture-"):
        raise SystemExit("Use a disposable web_fixture service")
    existing = {
        item["display_name"]
        for item in api("/experiments?search=Autocomplete%20example")["items"]
    }
    for i in range(14):
        if f"Autocomplete example {i:02}" in existing:
            continue
        api(
            "/experiments",
            {"display_name": f"Autocomplete example {i:02}", "description": ""},
        )
    recent = api("/ui/filter-options?collection=experiments")
    expected = recent["items"]
    assert len(expected) == 10
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def open_page(route):
            page.goto(endpoint + "/ui/#/" + route)
            page.locator("h1,dialog[open]").first.wait_for()
            if token and page.get_by_label("Bearer token", exact=True).is_visible():
                page.get_by_label("Bearer token", exact=True).fill(token)
                page.get_by_role("dialog").get_by_role(
                    "button", name="Connect", exact=True
                ).click()
            page.locator("h1").wait_for()
            expect(page.locator("#content")).to_have_attribute("data-route", route)

        open_page("experiments")
        search = page.get_by_role("combobox", name="Search", exact=True)
        search.click()
        options = page.locator(".autocomplete-options:not([hidden])").get_by_role(
            "option"
        )
        expect(options).to_have_count(10)
        expect(page.locator(".autocomplete-more")).to_have_text(
            f"...and {recent['remaining_count']} more"
        )
        expect(page.locator(".autocomplete-more")).to_be_visible()
        before_height = page.locator(".list-header").bounding_box()["height"]
        assert [option.inner_text().split("\n")[-1] for option in options.all()] == [
            item["id"] for item in expected
        ]
        page.keyboard.press("ArrowUp")
        expect(options.last).to_have_attribute("aria-selected", "true")
        page.wait_for_function("""() => {
          const active = document.querySelector('.autocomplete-option[aria-selected="true"]').getBoundingClientRect();
          const footer = document.querySelector('.autocomplete-more').getBoundingClientRect();
          return active.bottom <= footer.top + 1;
        }""")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        expect(search).to_have_value(expected[0]["name"] + " · " + expected[0]["id"])
        assert (
            search.evaluate("node => node.dataset.selectedValue") == expected[0]["id"]
        )
        assert page.locator(".list-header").bounding_box()["height"] == before_height
        expect(page.locator(".reference-input-name")).to_have_count(0)
        expect(page.get_by_role("listbox")).to_be_hidden()
        page.get_by_role("button", name="Apply filters", exact=True).click()
        expect(page.locator("tbody tr")).to_have_count(1)
        checks.append(
            "Empty-field options show the newest ten; keyboard selection preserves ID and Apply filters restricts the list"
        )

        search = page.get_by_role("combobox", name="Search", exact=True)
        expect(search).to_have_value(expected[0]["name"] + " · " + expected[0]["id"])
        search.fill("eXaMpLe 05")
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_have_count(1)
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_contain_text("Autocomplete example 05")
        target = api("/ui/filter-options?collection=experiments&search=example%2005")[
            "items"
        ][0]
        search.fill(target["id"][-12:])
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_have_count(1)
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_contain_text(target["id"])
        page.locator(".autocomplete-options:not([hidden])").get_by_role(
            "option"
        ).click()
        expect(search).to_have_value(target["name"] + " · " + target["id"])
        search.click()
        expect(page.get_by_role("listbox")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.get_by_role("listbox")).to_be_hidden()
        search.fill("no-matching-option")
        expect(page.get_by_role("listbox")).to_contain_text("No matching options")
        checks.append(
            "Case-insensitive name and partial ID matching, mouse selection, reopening, Escape and empty results work"
        )

        pending = []

        def delayed(route):
            query = parse_qs(urlsplit(route.request.url).query)
            if query.get("search") == ["delayed-response"]:
                pending.append(route)
            else:
                route.continue_()

        page.route("**/dockflow/v1/ui/filter-options?*", delayed)
        with page.expect_request(
            lambda request: "search=delayed-response" in request.url
        ):
            search.fill("delayed-response")
        search.fill("example 05")
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_have_count(1)
        pending.pop().fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"items": [{"id": "stale", "name": "Stale reply", "value": "stale"}]}
            ),
        )
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_contain_text("Autocomplete example 05")
        page.unroute("**/dockflow/v1/ui/filter-options?*", delayed)
        page.route(
            "**/dockflow/v1/ui/filter-options?*",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body='{"error":{"message":"Unavailable"}}',
            ),
        )
        search.fill("failure")
        expect(page.get_by_role("listbox")).to_contain_text("Suggestions unavailable")
        expect(search).to_be_editable()
        page.unroute("**/dockflow/v1/ui/filter-options?*")
        search.fill("example 05")
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_have_count(1)
        checks.append(
            "Delayed old replies cannot replace new matches; failed suggestions leave manual entry usable and editing recovers"
        )

        for route in ("pipelines", "components", "runs", "attempts", "artifacts"):
            open_page("executions" if route == "attempts" else route)
            search = page.get_by_role(
                "combobox",
                name="Component ID" if route == "components" else "Search",
                exact=True,
            )
            search.click()
            expect(
                page.locator(".autocomplete-options:not([hidden])")
                .get_by_role("option")
                .first
            ).to_be_visible()
            assert (
                len(
                    page.locator(".autocomplete-options:not([hidden])")
                    .get_by_role("option")
                    .all()
                )
                <= 10
            )
            page.keyboard.press("Escape")
        for route, label in (
            ("runs", "Pipeline ID"),
            ("runs", "Experiment ID"),
            ("components", "Pipeline ID"),
            ("attempts", "Run ID"),
            ("attempts", "Task ID"),
            ("artifacts", "Type"),
            ("storage", "Artifact"),
        ):
            open_page("executions" if route == "attempts" else route)
            field = page.get_by_role("combobox", name=label, exact=True)
            field.click()
            expect(
                page.locator(".autocomplete-options:not([hidden])")
                .get_by_role("option")
                .first
            ).to_be_visible()
            page.locator(".autocomplete-options:not([hidden])").get_by_role(
                "option"
            ).first.click()
            assert field.input_value()
        checks.append(
            "Every resource list and related ID/type filter exposes suggestions while state/availability selects retain their meaning"
        )

        def field(label):
            return page.get_by_role("combobox", name=label, exact=True)

        def choose(label, identifier):
            control = field(label)
            control.fill(identifier)
            matches = page.locator(".autocomplete-options:not([hidden])").get_by_role(
                "option"
            )
            expect(matches).to_have_count(1)
            matches.click()
            assert control.evaluate("node => node.dataset.selectedValue") == identifier
            assert control.input_value().endswith(identifier)

        def ids():
            return [
                option.inner_text().split("\n")[-1]
                for option in page.locator(".autocomplete-options:not([hidden])")
                .get_by_role("option")
                .all()
            ]

        def order(labels):
            assert (
                page.locator("form.toolbar .field > label").all_text_contents()
                == labels
            )
            heights = page.locator(
                "form.toolbar input,form.toolbar select"
            ).evaluate_all(
                "nodes => nodes.map(node => node.getBoundingClientRect().height)"
            )
            assert len(set(heights)) == 1

        open_page("components")
        order(["Pipeline ID", "Component ID"])
        component = api("/components")["items"][0]
        choose("Pipeline ID", component["definition_id"])
        field("Component ID").click()
        scoped = api(
            "/ui/filter-options?collection=components&definition_id="
            + component["definition_id"]
        )["items"]
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_have_count(len(scoped))
        assert ids() == [item["id"] for item in scoped]
        page.keyboard.press("Escape")
        choose("Component ID", component["component_id"])
        height = page.locator(".list-header").bounding_box()["height"]
        expect(page.locator(".reference-input-name")).to_have_count(0)
        page.get_by_role("button", name="Apply filters", exact=True).click()
        expect(page.locator("tbody tr")).to_have_count(1)
        assert "search=" + component["component_id"] in page.url
        assert page.locator(".list-header").bounding_box()["height"] == height
        page.get_by_role("button", name="Clear Pipeline ID", exact=True).click()
        expect(field("Component ID")).to_have_value("")

        open_page("runs")
        order(["Search", "Experiment ID", "Pipeline ID", "State"])
        runs = api("/runs")["items"]
        run = runs[0]
        states = (
            page.get_by_label("State", exact=True).locator("option").all_text_contents()
        )
        choose("Experiment ID", run["experiment_id"])
        field("Pipeline ID").click()
        expected_definitions = api(
            "/ui/filter-options?collection=definitions&experiment_id="
            + run["experiment_id"]
        )["items"]
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_have_count(len(expected_definitions))
        assert ids() == [item["id"] for item in expected_definitions]
        page.keyboard.press("Escape")
        choose("Pipeline ID", run["definition_id"])
        assert (
            page.get_by_label("State", exact=True).locator("option").all_text_contents()
            == states
        )
        clear_experiment = page.get_by_role(
            "button", name="Clear Experiment ID", exact=True
        )
        clear_experiment.focus()
        clear_experiment.press("Enter")
        expect(field("Pipeline ID")).to_have_value("")

        open_page("executions")
        order(["Search", "Run ID", "Task ID", "State"])
        task = api("/tasks")["items"][0]
        choose("Run ID", task["run_id"])
        field("Task ID").click()
        expected_tasks = api(
            "/ui/filter-options?collection=tasks&run_id=" + task["run_id"]
        )["items"]
        expect(
            page.locator(".autocomplete-options:not([hidden])").get_by_role("option")
        ).to_have_count(len(expected_tasks))
        assert ids() == [item["id"] for item in expected_tasks]
        page.keyboard.press("Escape")
        choose("Task ID", task["task_id"])
        page.get_by_role("button", name="Clear Run ID", exact=True).click()
        expect(field("Task ID")).to_have_value("")
        checks.append(
            "Prescribed component/Run/execution order, live parent scoping, child resets, inline captions, canonical submission and equal control heights preserve header geometry"
        )

        for width, height in ((1440, 1000), (390, 844), (390, 500)):
            page.set_viewport_size({"width": width, "height": height})
            open_page("experiments")
            page.get_by_role("combobox", name="Search", exact=True).click()
            expect(
                page.locator(".autocomplete-options:not([hidden])").get_by_role(
                    "option"
                )
            ).to_have_count(10)
            assert page.evaluate("""() => {
              const r = document.querySelector('.autocomplete-options').getBoundingClientRect();
              return r.left >= document.querySelector('.sidebar').getBoundingClientRect().right && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight &&
                document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight;
            }""")
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                page.locator("#project-name").evaluate(
                    "node => { node.textContent = 'example-project'; node.title = 'example-project'; }"
                )
                page.locator(
                    ".id,.cell-main,.cell-detail,.autocomplete-option small"
                ).evaluate_all(
                    "nodes => nodes.forEach(node => { node.textContent = 'Example reference'; })"
                )
                page.screenshot(
                    path=str(args.output / f"autocomplete-{width}-{height}.png")
                )
        checks.append(
            "Dropdown stays inside desktop, narrow and short viewports without clipping or page overflow"
        )
        if token:
            page.locator("#connect").click()
            expect(page.get_by_role("listbox")).to_have_count(0)
            expect(page.locator("#project-name")).to_have_text("Not connected")
            checks.append("Sign-out clears the page and visible suggestions")
        assert not errors, errors
        browser.close()
    result = {"browser": "Chromium", "checks": checks, "page_errors": errors}
    if args.output:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
