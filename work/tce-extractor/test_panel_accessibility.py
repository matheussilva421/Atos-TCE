"""Static accessibility contracts for the production side panel.

The browser smoke test covers layout and keyboard interaction.  This focused
gate keeps the visual token and static HTML requirements executable without
requiring Chrome or an authenticated portal.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
PANEL = ROOT / "portable" / "extensao-complementar-ato" / "sidepanel"


class _IdAndLabelParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.labels_for: list[str] = []
        self.lang: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "html":
            self.lang = attributes.get("lang")
        if "id" in attributes and attributes["id"]:
            self.ids.append(attributes["id"])
        if tag == "label" and attributes.get("for"):
            self.labels_for.append(attributes["for"])


def _parse_tokens() -> dict[str, tuple[int, int, int]]:
    text = (PANEL / "panel-tokens.css").read_text(encoding="utf-8")
    tokens: dict[str, tuple[int, int, int]] = {}
    for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", text):
        tokens[name] = tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
    return tokens


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for channel in rgb:
        normalized = channel / 255
        channels.append(normalized / 12.92 if normalized <= 0.03928 else ((normalized + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    lighter = max(_relative_luminance(first), _relative_luminance(second))
    darker = min(_relative_luminance(first), _relative_luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


class PanelAccessibilityContractTests(unittest.TestCase):
    def test_text_status_accent_and_focus_tokens_meet_contrast_thresholds(self) -> None:
        tokens = _parse_tokens()
        white = (255, 255, 255)
        text_tokens = (
            "--text-primary",
            "--text-secondary",
            "--accent-primary",
            "--status-success",
            "--status-attention",
            "--status-error",
            "--focus-ring",
        )
        for name in text_tokens:
            with self.subTest(token=name):
                self.assertIn(name, tokens)
                self.assertGreaterEqual(_contrast_ratio(tokens[name], white), 4.5)

    def test_static_markup_has_language_unique_ids_and_label_targets(self) -> None:
        parser = _IdAndLabelParser()
        parser.feed((PANEL / "panel.html").read_text(encoding="utf-8"))
        self.assertEqual(parser.lang, "pt-BR")
        self.assertEqual(len(parser.ids), len(set(parser.ids)), "IDs estáticos devem ser únicos")
        self.assertTrue(parser.labels_for)
        for target in parser.labels_for:
            with self.subTest(target=target):
                self.assertIn(target, parser.ids)

    def test_safety_copy_remains_explicit_in_static_markup(self) -> None:
        markup = (PANEL / "panel.html").read_text(encoding="utf-8")
        self.assertIn("não envia o ato", markup)
        self.assertIn("não preenche nem envia atos", markup)


if __name__ == "__main__":
    unittest.main()
