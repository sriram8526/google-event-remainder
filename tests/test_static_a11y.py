"""Static accessibility checks on the HTML shell (labels, landmarks, live regions, CSP-safety)."""

from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.label_for: set[str] = set()
        self._label_depth = 0
        self.wrapped_inputs: set[int] = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "label":
            self._label_depth += 1
            if "for" in attributes:
                self.label_for.add(attributes["for"])
        if tag in {"input", "select", "textarea"} and self._label_depth:
            self.wrapped_inputs.add(len(self.tags))
        self.tags.append((tag, attributes))

    def handle_endtag(self, tag):
        if tag == "label":
            self._label_depth -= 1


def parse():
    page = Page()
    page.feed((STATIC / "index.html").read_text())
    return page


def test_document_language_and_landmarks():
    page = parse()
    assert any(t == "html" and a.get("lang") == "en" for t, a in page.tags)
    assert any(t == "main" for t, _ in page.tags)
    assert sum(1 for t, _ in page.tags if t == "h1") == 1


def test_every_form_control_has_an_accessible_name():
    page = parse()
    for index, (tag, attrs) in enumerate(page.tags):
        if tag in {"input", "select"} and attrs.get("type") != "submit":
            named = (
                attrs.get("id") in page.label_for
                or index in page.wrapped_inputs
                or attrs.get("aria-label")
            )
            assert named, f"unlabelled control: {attrs}"


def test_announcer_region_is_mounted_in_the_static_html():
    page = parse()
    announcers = [a for t, a in page.tags if a.get("id") == "announcer"]
    assert (
        announcers and announcers[0]["role"] == "status" and announcers[0]["aria-live"] == "polite"
    )


def test_results_container_is_not_itself_a_live_region():
    page = parse()
    results = next(a for _, a in page.tags if a.get("id") == "results")
    assert "aria-live" not in results and results.get("tabindex") == "-1"


def test_skip_link_and_no_inline_script_or_style():
    page = parse()
    assert any(t == "a" and a.get("class") == "skip" for t, a in page.tags)
    assert not any(t == "script" and "src" not in a for t, a in page.tags)
    assert not any(a.get("style") for _, a in page.tags) and not any(
        t == "style" for t, _ in page.tags
    )


def test_javascript_never_uses_innerhtml_or_eval():
    source = (STATIC / "app.js").read_text()
    assert "innerHTML" not in source and "eval(" not in source and "document.write" not in source
