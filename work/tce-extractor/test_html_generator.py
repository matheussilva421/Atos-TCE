import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from html_generator import build_interface_payload, render_html


class HtmlGeneratorTests(unittest.TestCase):
    def _write_all_documents_fixture(self, root):
        archive_root = root / "acervo-tce"
        process_root = archive_root / "processos" / "103439-2023"
        files = [
            (9, "resolucao.pdf", "RESOLUÇÃO ADMINISTRATIVA"),
            (10, "guia financeira.pdf", "GUIA FINANCEIRA"),
            (11, "despacho.pdf", "DESPACHO"),
        ]
        events = []
        for event, filename, title in files:
            pdf = process_root / f"evento-{event:04d}" / filename
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(b"%PDF-1.7 fixture")
            events.append(
                {
                    "event": event,
                    "date": f"{event:02d}/05/2023",
                    "title": f"Evento {event}",
                    "documents": [
                        {
                            "title": title,
                            "relative_path": pdf.relative_to(archive_root).as_posix(),
                            "page_count": event - 7,
                            "classification": (
                                "guia_financeira_taxacao"
                                if event == 10
                                else "outro_documento"
                                if event == 9
                                else None
                            ),
                            "automatic_source": event == 10,
                            "classification_conflict": event == 10,
                        }
                    ],
                }
            )

        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "processes": [
                        {
                            "process": "103439/2023",
                            "documents": [
                                {
                                    "event": "9",
                                    "title": "RESOLUÇÃO ADMINISTRATIVA",
                                    "kind": "resolucao_administrativa",
                                    "classification": "resolucao_administrativa",
                                    "automatic_source": True,
                                    "relative_path": events[0]["documents"][0]["relative_path"],
                                    "pdf_path": str(
                                        archive_root
                                        / events[0]["documents"][0]["relative_path"]
                                    ),
                                },
                                {
                                    "event": "10",
                                    "title": "GUIA FINANCEIRA",
                                    "kind": "guia_financeira_taxacao",
                                    "classification": "guia_financeira_taxacao",
                                    "automatic_source": True,
                                    "relative_path": events[1]["documents"][0]["relative_path"],
                                    "pdf_path": str(
                                        archive_root
                                        / events[1]["documents"][0]["relative_path"]
                                    ),
                                },
                            ],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        checkpoint = root / "checkpoint.json"
        checkpoint.write_text(
            json.dumps(
                {
                    "processes": {
                        "103439/2023": {
                            "status": "partial",
                            "pendencias": ["Gênero"],
                            "documents": [
                                {
                                    "event": "9",
                                    "file": "resolucao.pdf",
                                    "pages": 2,
                                    "classification": "resolucao_administrativa",
                                }
                            ],
                            "result": {"blocks": []},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        index = root / "indice-local.json"
        index.write_text(
            json.dumps(
                {
                    "processes": [
                        {"key": "103439/2023", "events": events}
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return manifest, checkpoint, index

    def test_payload_lists_every_archive_file_with_relative_links_and_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest, checkpoint, index = self._write_all_documents_fixture(
                Path(temp_dir)
            )

            payload = build_interface_payload(
                manifest, checkpoint, archive_index_path=index
            )

            process = payload["processes"][0]
            self.assertEqual(len(process["documents"]), 2)
            self.assertEqual(len(process["all_documents"]), 3)
            self.assertEqual(
                {document["classification"] for document in process["all_documents"]},
                {
                    "resolucao_administrativa",
                    "guia_financeira_taxacao",
                    "outro_documento",
                },
            )
            self.assertEqual(
                [document["event"] for document in process["all_documents"]],
                ["9", "10", "11"],
            )
            self.assertEqual(
                [document["page_count"] for document in process["all_documents"]],
                [2, 3, 4],
            )
            self.assertTrue(process["all_documents"][0]["automatic_source"])
            self.assertTrue(process["all_documents"][1]["classification_conflict"])
            self.assertFalse(process["all_documents"][2]["automatic_source"])
            self.assertEqual(
                process["all_documents"][1]["pdf_url"],
                "processos/103439-2023/evento-0010/guia%20financeira.pdf",
            )
            self.assertEqual(payload["stats"]["priority_documents"], 2)
            self.assertEqual(payload["stats"]["all_documents"], 3)

    def test_priority_document_is_selected_before_earlier_cover_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, checkpoint, index = self._write_all_documents_fixture(root)
            archive = json.loads(index.read_text(encoding="utf-8"))
            cover = root / "acervo-tce" / "processos" / "103439-2023" / "evento-0000" / "capa.pdf"
            cover.parent.mkdir(parents=True, exist_ok=True)
            cover.write_bytes(b"%PDF-1.7 cover")
            archive["processes"][0]["events"].insert(
                0,
                {
                    "event": 0,
                    "title": "Capa",
                    "documents": [
                        {
                            "title": "Capa",
                            "relative_path": cover.relative_to(root / "acervo-tce").as_posix(),
                            "classification": "outro_documento",
                        }
                    ],
                },
            )
            index.write_text(json.dumps(archive), encoding="utf-8")

            payload = build_interface_payload(
                manifest, checkpoint, archive_index_path=index
            )

            documents = payload["processes"][0]["all_documents"]
            self.assertEqual(documents[0]["classification"], "resolucao_administrativa")
            self.assertEqual(documents[0]["event"], "9")
            self.assertEqual(documents[2]["event"], "0")

    def test_processes_with_priority_documents_appear_before_empty_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "resolucao.pdf"
            pdf.write_bytes(b"%PDF-1.7 fixture")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "processes": [
                            {"process": "100064/2022", "documents": []},
                            {
                                "process": "103487/2023",
                                "documents": [
                                    {
                                        "event": "5",
                                        "title": "RESOLUÇÃO ADMINISTRATIVA",
                                        "kind": "resolucao_administrativa",
                                        "pdf_path": str(pdf),
                                    }
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "processes": {
                            "100064/2022": {"result": {"blocks": []}},
                            "103487/2023": {"result": {"blocks": []}},
                        }
                    }
                ),
                encoding="utf-8",
            )

            payload = build_interface_payload(manifest, checkpoint)

            self.assertEqual(
                [item["process"] for item in payload["processes"]],
                ["103487/2023", "100064/2022"],
            )

    def test_rendered_html_has_document_badges_counters_and_preserves_controls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest, checkpoint, index = self._write_all_documents_fixture(
                Path(temp_dir)
            )
            html = render_html(
                build_interface_payload(
                    manifest, checkpoint, archive_index_path=index
                )
            )

            self.assertIn('data-kind="resolucao_administrativa"', html)
            self.assertIn('data-kind="guia_financeira_taxacao"', html)
            self.assertIn('data-kind="outro_documento"', html)
            for badge_class in (
                ".badge-resolution",
                ".badge-guide",
                ".badge-other",
                ".badge-conflict",
                ".badge-pending",
            ):
                self.assertIn(badge_class, html)
            self.assertIn("RESOLUÇÃO", html)
            self.assertIn("GUIA", html)
            self.assertIn("OUTRO", html)
            self.assertIn('id="stat-documents"', html)
            self.assertIn('id="stat-all-documents"', html)
            self.assertIn('id="stat-pending"', html)
            self.assertIn(
                "$('stat-all-documents').textContent = data.stats.all_documents",
                html,
            )
            self.assertIn("process.all_documents", html)
            self.assertIn('id="splitter"', html)
            self.assertIn("navigator.clipboard", html)
            self.assertIn('id="process-done"', html)
            self.assertNotIn("https://", html)
            self.assertNotIn("http://", html)

    def test_cli_accepts_archive_index_and_writes_only_requested_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, checkpoint, index = self._write_all_documents_fixture(root)
            output = root / "qa" / "fixture.html"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("html_generator.py")),
                    "--manifest",
                    str(manifest),
                    "--checkpoint",
                    str(checkpoint),
                    "--archive-index",
                    str(index),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.is_file())
            self.assertEqual(json.loads(completed.stdout)["all_documents"], 3)
            self.assertFalse((root / "complementar-ato.html").exists())

    def test_payload_merges_analysis_with_manifest_pdf_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "evento-0009-resolucao_administrativa.pdf"
            pdf.write_bytes(b"%PDF-1.7")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "9",
                                        "date": "28/04/2023",
                                        "title": "RESOLUÇÃO ADMINISTRATIVA",
                                        "kind": "resolucao_administrativa",
                                        "pdf_path": str(pdf),
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "processes": {
                            "103439/2023": {
                                "status": "partial",
                                "result": {
                                    "process": "103439/2023",
                                    "status": "partial",
                                    "blocks": [
                                        {
                                            "interested": "JOANA DA SILVA",
                                            "pending": ["Gênero"],
                                            "fields": {
                                                "cargo": {
                                                    "status": "found",
                                                    "value": "PROFESSORA",
                                                    "process": "103439/2023",
                                                    "event": "9",
                                                    "page": 1,
                                                    "citation": "Processo 103439/2023 · Evento 9 · p. 1",
                                                }
                                            },
                                        }
                                    ],
                                },
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = build_interface_payload(manifest, checkpoint)

            self.assertEqual(payload["processes"][0]["process"], "103439/2023")
            self.assertEqual(payload["processes"][0]["documents"][0]["event"], "9")
            self.assertEqual(payload["processes"][0]["documents"][0]["pdf_url"], "")
            self.assertEqual(
                payload["processes"][0]["blocks"][0]["fields"]["cargo"]["value"],
                "PROFESSORA",
            )

    def test_payload_can_use_relative_pdf_links_for_portable_zip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "evento-0009-resolucao_administrativa.pdf"
            pdf.write_bytes(b"%PDF-1.7")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "9",
                                        "title": "RESOLUÇÃO ADMINISTRATIVA",
                                        "kind": "resolucao_administrativa",
                                        "pdf_path": str(pdf),
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(
                json.dumps({"processes": {"103439/2023": {"status": "partial"}}}),
                encoding="utf-8",
            )

            payload = build_interface_payload(manifest, checkpoint, pdf_link_root="pdfs")

            self.assertEqual(
                payload["processes"][0]["documents"][0]["pdf_url"],
                "pdfs/103439-2023/evento-0009-resolucao_administrativa.pdf",
            )

    def test_priority_pdf_link_rejects_archive_escape_without_exposing_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outside = root / "outside.pdf"
            outside.write_bytes(b"%PDF-1.7")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "9",
                                        "title": "RESOLUÇÃO ADMINISTRATIVA",
                                        "kind": "resolucao_administrativa",
                                        "relative_path": "../outside.pdf",
                                        "pdf_path": str(outside),
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(
                json.dumps({"processes": {"103439/2023": {"status": "partial"}}}),
                encoding="utf-8",
            )

            payload = build_interface_payload(manifest, checkpoint)

            pdf_url = payload["processes"][0]["documents"][0]["pdf_url"]
            self.assertEqual(pdf_url, "")
            self.assertNotIn("file:", pdf_url)

    def test_rendered_html_is_offline_and_has_copy_and_pdf_controls(self):
        html = render_html(
            {
                "processes": [
                    {
                        "process": "103439/2023",
                        "status": "partial",
                        "documents": [],
                        "blocks": [],
                    }
                ],
                "stats": {"processes": 1, "documents": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn('id="app-data"', html)
        self.assertIn('id="pdf-frame"', html)
        self.assertIn("Copiar", html)
        self.assertIn("navigator.clipboard", html)
        self.assertNotIn("consultaprocessotemp", html)
        self.assertNotIn("qsIdProcesso=", html)

    def test_rendered_html_removes_external_urls_from_extracted_text(self):
        html = render_html(
            {
                "processes": [
                    {
                        "process": "103439/2023",
                        "status": "partial",
                        "documents": [],
                        "blocks": [
                            {
                                "interested": "JOANA DA SILVA",
                                "pending": [],
                                "fields": {
                                    "fundamento_legal": {
                                        "status": "found",
                                        "value": "Texto https://example.test/validacao?codigo=abc",
                                        "process": "103439/2023",
                                        "event": "9",
                                        "page": 1,
                                    }
                                },
                            }
                        ],
                    }
                ],
                "stats": {"processes": 1, "documents": 0, "found": 1, "conflicts": 0},
            }
        )

        self.assertNotIn("https://example.test", html)
        self.assertIn("Texto [endereço externo omitido]", html)

    def test_rendered_html_tracks_completed_processes_locally(self):
        html = render_html(
            {
                "processes": [
                    {
                        "process": "103439/2023",
                        "status": "partial",
                        "documents": [],
                        "blocks": [],
                    }
                ],
                "stats": {"processes": 1, "documents": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn('id="process-done"', html)
        self.assertIn('id="stat-done"', html)
        self.assertIn("tce-completed-processes-v1", html)
        self.assertIn("completedProcesses.has(process.process) ? '✓ '", html)
        self.assertIn("localStorage.setItem(COMPLETED_STORAGE_KEY", html)

    def test_packaging_script_declares_portable_pdf_bundle(self):
        script_path = Path(__file__).with_name("empacotar-complementar-ato.ps1")
        self.assertTrue(script_path.exists())
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("--pdf-link-root", script)
        self.assertIn("Compress-Archive", script)
        self.assertIn("pdfs", script)
        self.assertIn("README-USO.md", script)
        self.assertIn("[switch]$Force", script)
        self.assertIn("$temporaryZip", script)

    def test_rendered_html_has_compact_portrait_desktop_layout(self):
        html = render_html(
            {
                "processes": [],
                "stats": {"processes": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn("@media (min-width: 680px) and (max-width: 1080px)", html)
        self.assertIn("grid-template-columns: minmax(0, var(--viewer-size)) 18px minmax(0, 1fr)", html)
        self.assertIn(
            "grid-template-columns: minmax(170px, .6fr) minmax(0, 2.5fr) minmax(150px, 1fr)",
            html,
        )
        self.assertIn(".toolbar .follow-button { min-width: 116px; white-space: nowrap;", html)
        self.assertIn("height: 100vh;", html)
        self.assertIn("overflow: hidden;", html)
        self.assertIn("zoom=page-fit", html)
        self.assertIn('id="pdf-zoom-in"', html)
        self.assertIn('id="pdf-rotate"', html)

    def test_desktop_layout_confines_scrolling_and_mobile_restores_page_flow(self):
        html = render_html(
            {
                "processes": [],
                "stats": {"processes": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn(
            ".app-shell { height: 100vh; min-height: 0; display: flex;",
            html,
        )
        self.assertIn(
            ".app-shell { height: auto; min-height: 100vh; }",
            html,
        )

    def test_rendered_html_has_keyboard_accessible_resizable_splitter(self):
        html = render_html(
            {
                "processes": [],
                "stats": {"processes": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn('id="splitter"', html)
        self.assertIn('id="split-slider"', html)
        self.assertIn('type="range"', html)
        self.assertIn('aria-label="Ajustar largura dos painéis"', html)
        self.assertIn("--viewer-size", html)
        self.assertIn("localStorage.setItem('tce-split-percent'", html)
        self.assertIn("addEventListener('resize', updateSplitBounds)", html)

    def test_splitter_uses_compact_drag_handle_instead_of_wide_range_track(self):
        html = render_html(
            {
                "processes": [],
                "stats": {"processes": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn('class="splitter-handle"', html)
        self.assertIn("cursor: col-resize", html)
        self.assertIn("addEventListener('pointerdown'", html)
        self.assertNotIn("width: 132px", html)

    def test_splitter_applies_width_to_workspace_that_owns_responsive_variable(self):
        html = render_html(
            {
                "processes": [],
                "stats": {"processes": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn(
            "document.querySelector('.workspace').style.setProperty('--viewer-size'",
            html,
        )
        self.assertNotIn(
            "document.documentElement.style.setProperty('--viewer-size'", html
        )

    def test_splitter_uses_default_width_when_no_saved_preference_exists(self):
        html = render_html(
            {
                "processes": [],
                "stats": {"processes": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn("if (savedValue !== null)", html)

    def test_splitter_pointer_math_accounts_for_divider_center(self):
        html = render_html(
            {
                "processes": [],
                "stats": {"processes": 0, "found": 0, "conflicts": 0},
            }
        )

        self.assertIn("const dividerOffset = 9;", html)


if __name__ == "__main__":
    unittest.main()
