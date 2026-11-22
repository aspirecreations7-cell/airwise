from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

STATIC = Path(__file__).resolve().parent.parent / "static"
SETTINGS = Settings(
    gemini_api_key="", gemini_model="m", llm_timeout_seconds=1.0, openaq_api_key=""
)


class Audit(HTMLParser):
    """Collects facts about the page that matter for accessibility and CSP."""

    def __init__(self):
        super().__init__()
        self.lang = None
        self.h1_count = 0
        self.label_depth = 0
        self.label_targets = set()
        self.controls = []
        self.inline_attributes = []
        self.style_tags = 0
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.lang = attributes.get("lang")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "label":
            self.label_depth += 1
            if attributes.get("for"):
                self.label_targets.add(attributes["for"])
        elif tag in ("input", "select", "textarea"):
            self.controls.append((attributes.get("id"), self.label_depth > 0))
        elif tag == "style":
            self.style_tags += 1
        elif tag == "script":
            self.scripts.append(attributes)
        self.inline_attributes += [
            name for name in attributes if name.startswith("on") or name == "style"
        ]

    def handle_endtag(self, tag):
        if tag == "label":
            self.label_depth -= 1


def audit():
    parser = Audit()
    parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    return parser


def test_page_declares_language_and_has_one_h1():
    page = audit()
    assert page.lang == "en"
    assert page.h1_count == 1


def test_every_form_control_has_a_label():
    page = audit()
    assert page.controls
    for control_id, inside_label in page.controls:
        assert inside_label or control_id in page.label_targets, control_id


def test_page_works_under_the_content_security_policy():
    page = audit()
    assert page.style_tags == 0
    assert page.inline_attributes == []
    assert all(script.get("src") for script in page.scripts)


def test_skip_link_and_main_landmark_exist():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'href="#main"' in html
    assert 'id="main"' in html


def test_javascript_never_writes_html_from_api_data():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "outerHTML" not in script
    assert "document.write" not in script


def test_static_files_are_served():
    with TestClient(create_app(SETTINGS)) as client:
        for path in ("/", "/app.js", "/styles.css"):
            assert client.get(path).status_code == 200
