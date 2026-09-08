import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from unittest.mock import patch

from tce_extractor import (
    CheckpointStore,
    Extraction,
    classify_document,
    extract_fields,
    extract_interested,
    extract_pdf_pages,
    _find_interested,
    merge_extractions,
    normalize_date,
    render_markdown,
)


class DocumentClassificationTests(unittest.TestCase):
    def test_extract_fields_preserves_original_quote_and_geometry_when_words_are_supplied(self):
        pages = [
            "RESOLUÇÃO ADMINISTRATIVA Nº 156\n"
            "Interessada: JOANA DA SILVA\n"
            "Cargo: PROFESSOR"
        ]
        page_words = [
            {
                "width": 200,
                "height": 100,
                "words": [
                    {"text": "Cargo:", "rect": [10, 20, 35, 30]},
                    {"text": "PROFESSOR", "rect": [40, 20, 100, 30]},
                ],
            }
        ]
        extraction = extract_fields(
            pages,
            process="103439/2023",
            event="6",
            document="resolucao.pdf",
            kind="resolucao_administrativa",
            page_words=page_words,
        )
        cargo = extraction.fields["cargo"]
        self.assertEqual(cargo.quote, "PROFESSOR")
        self.assertEqual(cargo.rects, ((0.2, 0.2, 0.5, 0.3),))
        self.assertEqual(cargo.method, "native")

    def test_classifies_priority_documents_without_relying_on_ellipsis(self):
        self.assertEqual(
            classify_document(
                "Documento_Processo_Portal_Gestor - RESOLUÇÃO ADMINISTRATIVA Nº 156",
                "CONCEDE APOSENTADORIA VOLUNTÁRIA",
            ),
            "resolucao_administrativa",
        )
        self.assertEqual(
            classify_document(
                "Guia Financeira / Taxação de Proventos",
                "guia financeira do benefício",
            ),
            "guia_financeira_taxacao",
        )

    def test_rejects_unrelated_tramitacao_document(self):
        self.assertIsNone(
            classify_document("Tramitacao_Processo_Administrativo", "encaminhado ao setor")
        )

    def test_classifies_pdf_text_with_legacy_replacement_characters(self):
        self.assertEqual(
            classify_document(
                "Documento_Processo_Portal_Gest...",
                "RESOLU��O ADMINISTRATIVA N� 156\nConcede aposentadoria volunt�ria",
            ),
            "resolucao_administrativa",
        )

    def test_rejects_documents_that_only_mention_a_resolution(self):
        self.assertIsNone(
            classify_document(
                "Documento_Processo_Portal_Gest...",
                "DESPACHO\nProvidenciada a Resolução Administrativa nº 435, "
                "publicada no Diário Oficial do Estado.",
            )
        )
        self.assertIsNone(
            classify_document(
                "Documento_Processo_Portal_Gest...",
                "PARECER\nO benefício foi concedido mediante Resolução "
                "Administrativa nº 435 e os proventos foram implantados.",
            )
        )


class FieldExtractionTests(unittest.TestCase):
    def test_extracts_fields_with_pdf_page_citations_and_normalized_date(self):
        pages = [
            "Capa do documento",
            "RESOLUÇÃO ADMINISTRATIVA Nº 156, DE 20 DE FEVEREIRO DE 2020\n"
            "Interessada: MAGNOLIA RAMALHO MACIEL PINTO LOPES\n"
            "CPF/CNPJ: 50348841434\n"
            "Modalidade: aposentadoria voluntária por tempo de contribuição\n"
            "Fundamento Legal: artigo 40, § 5º, da Constituição Federal\n"
            "Publicação no Diário Oficial do Estado: 20/02/2020\n"
            "Cargo: PROFESSOR PN-III\n"
            "Matrícula nº 103.870-2\n"
            "Data de Nascimento: 14/08/1965\n"
            "Gênero: Feminino",
        ]

        result = extract_fields(
            pages,
            process="103439/2023",
            event="9",
            document="RESOLUÇÃO ADMINISTRATIVA",
        )

        self.assertEqual(result.fields["modalidade"].value, "aposentadoria voluntária por tempo de contribuição")
        self.assertEqual(result.fields["data_publicacao_doe"].value, "20/02/2020")
        self.assertEqual(result.fields["matricula"].value, "103.870-2")
        self.assertEqual(result.fields["data_nascimento"].page, 2)
        self.assertEqual(result.fields["cargo"].citation, "Processo 103439/2023 · Evento 9 · p. 2")

    def test_does_not_infer_publication_date_from_event_date(self):
        result = extract_fields(
            ["Evento incluído em 28/04/2023\nData do ato: 07/02/2020"],
            process="103439/2023",
            event="9",
            document="RESOLUÇÃO ADMINISTRATIVA",
        )

        self.assertEqual(result.fields["data_publicacao_doe"].status, "missing")

    def test_uses_resolution_heading_date_as_doe_publication_date(self):
        result = extract_fields(
            [
                "Instituto de Previdência dos Servidores do Estado do Rio Grande do Norte\n"
                "RESOLUÇÃO ADMINISTRATIVA Nº 156, DE 07 DE FEVEREIRO DE 2020.\n"
                "Concede aposentadoria voluntária por tempo de contribuição."
            ],
            process="103439/2023",
            event="9",
            document="RESOLUÇÃO ADMINISTRATIVA",
        )

        publication = result.fields["data_publicacao_doe"]
        self.assertEqual(publication.value, "07/02/2020")
        self.assertEqual(publication.status, "found")
        self.assertEqual(publication.citation, "Processo 103439/2023 · Evento 9 · p. 1")

    def test_uses_resolution_heading_date_when_pdf_text_has_broken_accents(self):
        cases = (
            ("RESOLU��O ADMINISTRATIVA N� 496, DE 29 DE MAIO DE 2019.", "29/05/2019"),
            ("RESOLU��O ADMINISTRATIVA N� 828, DE 17 DE MAR�O DE 2017.", "17/03/2017"),
            ("RESOLU��O ADMINISTRATIVAN- 533, DE 16 DE OUTUBRO DE 2015.", "16/10/2015"),
        )
        for heading, expected in cases:
            with self.subTest(heading=heading):
                result = extract_fields(
                    [heading + "\nConcede aposentadoria voluntária."],
                    process="103484/2023",
                    event="6",
                    document="Documento_Processo_Portal_Gest...",
                )
                self.assertEqual(result.fields["data_publicacao_doe"].value, expected)

    def test_extracts_complete_cargo_with_class_from_resolution_narrative(self):
        result = extract_fields(
            [
                'RESOLUÇÃO ADMINISTRATIVA Nº 1234, DE 17 DE AGOSTO DE 2022.\n'
                'RESOLVE conceder aposentadoria a JOANA DA SILVA, no cargo de '
                'PROFESSOR PN - IV, Classe "J", matrícula nº 104.670-5/1.'
            ],
            process="103785/2023",
            event="16",
            document="RESOLUÇÃO ADMINISTRATIVA",
            kind="resolucao_administrativa",
        )

        cargo = result.fields["cargo"]
        self.assertEqual(cargo.value, 'PROFESSOR PN - IV, Classe "J"')
        self.assertEqual(cargo.citation, "Processo 103785/2023 · Evento 16 · p. 1")

    def test_normalizes_multiline_resolution_cargo_and_class_for_copying(self):
        result = extract_fields(
            [
                'RESOLVE conceder aposentadoria a JOANA DA SILVA, no cargo de '
                'PROFESSOR,\n PN-IV, Classe\n"E", matrícula nº 123.456-7/1.'
            ],
            process="103721/2023",
            event="19",
            document="RESOLUÇÃO ADMINISTRATIVA",
            kind="resolucao_administrativa",
        )

        self.assertEqual(
            result.fields["cargo"].value,
            'PROFESSOR PN - IV, Classe "E"',
        )

    def test_recovers_cargo_and_class_from_reordered_pdf_columns(self):
        cases = (
            (
                'integrais, a\n, no cargo de\n, Classe\n", matrícula nº\n'
                'MARIA ERTIMA DO REGO\nPROFESSOR PN-III\n"F\n104.544-0/1',
                'PROFESSOR PN - III, Classe "F"',
            ),
            (
                'integrais, a\n, no cargo de\nARLETE OLIVEIRA DO NASCIMENTO MELO\n'
                'PROFESSOR PN-IV\n, Classe\n, matrícula nº\n"D"\n104.670-5/1',
                'PROFESSOR PN - IV, Classe "D"',
            ),
        )
        for text, expected in cases:
            with self.subTest(expected=expected):
                result = extract_fields(
                    [text], process="103776/2023", event="3",
                    document="RESOLUÇÃO ADMINISTRATIVA",
                    kind="resolucao_administrativa",
                )
                self.assertEqual(result.fields["cargo"].value, expected)

    def test_cargo_is_taken_from_the_identified_person_in_multi_act_page(self):
        result = extract_fields(
            [
                'Outro ato menciona no cargo de PROFESSOR PN - IV, Classe "G".\n'
                'RESOLVE conceder aposentadoria voluntária a SONIA MARIA PEREIRA DE SOUSA, '
                'no cargo de AUXILIAR DE INFRAESTRUTURA, matrícula nº 87.137-0/1.'
            ],
            process="103788/2023", event="4", document="Diário Oficial",
            kind="resolucao_administrativa",
        )

        self.assertEqual(result.interested, "SONIA MARIA PEREIRA DE SOUSA")
        self.assertEqual(result.fields["cargo"].value, "AUXILIAR DE INFRAESTRUTURA")

    def test_multi_act_resolution_without_identified_person_does_not_guess_cargo(self):
        result = extract_fields(
            [
                'no cargo de PROFESSOR PN - IV, Classe "G"\n'
                'no cargo de TÉCNICO EM ENFERMAGEM, Classe "B"'
            ],
            process="103785/2023", event="7", document="Diário Oficial",
            kind="resolucao_administrativa",
        )

        self.assertIsNone(result.interested)
        self.assertEqual(result.fields["cargo"].status, "missing")

    def test_reordered_columns_with_blank_class_do_not_turn_name_into_cargo(self):
        result = extract_fields(
            [
                'integrais, a\n, no cargo de\n, VULPIANO BERNARDO DE OLIVEIRA\n'
                'PROFESSOR PN - III\nClasse " "\n, matrícula nº 12345'
            ],
            process="103773/2023", event="11", document="RESOLUÇÃO ADMINISTRATIVA",
            kind="resolucao_administrativa",
        )

        self.assertEqual(result.fields["cargo"].status, "missing")

    def test_normalize_date_rejects_ambiguous_dates(self):
        self.assertEqual(normalize_date("20-02-2020"), "20/02/2020")
        self.assertIsNone(normalize_date("2020"))

    def test_ocr_uses_the_workspace_tessdata_directory(self):
        try:
            import fitz
            from PIL import Image, ImageDraw
        except ImportError as error:  # pragma: no cover - environment guard
            self.skipTest(str(error))

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "scan.png"
            pdf_path = root / "scan.pdf"
            image = Image.new("RGB", (1200, 220), "white")
            ImageDraw.Draw(image).text((40, 80), "Cargo: PROFESSOR", fill="black")
            image.save(image_path)
            pdf = fitz.open()
            page = pdf.new_page(width=1200, height=220)
            page.insert_image(page.rect, filename=str(image_path))
            pdf.save(pdf_path)
            pdf.close()

            pages = extract_pdf_pages(
                pdf_path,
                tesseract=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                tessdata_dir=Path(__file__).parent.parent / "tessdata",
            )

            self.assertIn("PROFESSOR", " ".join(pages).upper())

    def test_ocr_geometry_comes_from_the_same_tsv_pass_as_text(self):
        try:
            import fitz
        except ImportError as error:  # pragma: no cover - environment gate
            self.skipTest(str(error))

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "scan.pdf"
            document = fitz.open()
            document.new_page(width=200, height=100)
            document.save(pdf_path)
            document.close()
            tsv = (
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\t"
                "top\twidth\theight\tconf\ttext\n"
                "5\t1\t1\t1\t1\t1\t10\t20\t60\t10\t95\tPROFESSOR\n"
            )
            with patch(
                "tce_extractor.subprocess.run",
                return_value=type("Completed", (), {"returncode": 0, "stdout": tsv.encode("utf-8")})(),
            ) as run:
                pages, geometry = extract_pdf_pages(
                    pdf_path,
                    tesseract="tesseract-fixture",
                    return_geometry=True,
                )

        self.assertEqual(pages, ["PROFESSOR"])
        self.assertEqual(run.call_count, 1)
        self.assertIn("tsv", run.call_args.args[0])
        self.assertEqual(geometry[0]["method"], "ocr")
        self.assertEqual(geometry[0]["words"][0]["text"], "PROFESSOR")
        self.assertTrue(all(0 <= value <= 1 for value in geometry[0]["words"][0]["rect"]))

    def test_extracts_resolution_narrative_without_form_labels(self):
        result = extract_fields(
            [
                "RESOLUÇÃO ADMINISTRATIVA Nº 156\n"
                "Concede aposentadoria voluntária por tempo de contribuição.\n"
                "RESOLVE conceder aposentadoria voluntária por tempo de contribuição, "
                "com proventos integrais, a JOANA DA SILVA, no cargo de PROFESSOR PN - III, "
                "Classe J, matrícula nº 103.870-2/1, nos termos do artigo 6º da Constituição Federal."
            ],
            "103439/2023",
            "9",
            "RESOLUÇÃO ADMINISTRATIVA",
        )

        self.assertEqual(result.fields["modalidade"].value, "aposentadoria voluntária por tempo de contribuição")
        self.assertEqual(result.fields["cargo"].value, 'PROFESSOR PN - III, Classe "J"')
        self.assertEqual(result.fields["matricula"].value, "103.870-2/1")
        self.assertEqual(extract_interested(result), "JOANA DA SILVA")

    def test_recomposes_resolution_registration_split_by_pdf_layout(self):
        cases = (
            "matrícula nº 103.870-2 / 1",
            "matrícula nº 103.870-2/\n1",
            "matrícula nº\n103.870-2 /\n1",
        )
        for registration_text in cases:
            with self.subTest(registration_text=registration_text):
                result = extract_fields(
                    [
                        "RESOLUÇÃO ADMINISTRATIVA Nº 156\n"
                        "RESOLVE conceder aposentadoria voluntária a JOANA DA SILVA, "
                        "no cargo de PROFESSOR PN - IV, Classe J, "
                        f"{registration_text}."
                    ],
                    process="103439/2023",
                    event="9",
                    document="RESOLUÇÃO ADMINISTRATIVA",
                    kind="resolucao_administrativa",
                )

                self.assertEqual(result.fields["matricula"].value, "103.870-2/1")

    def test_extracts_guide_layout_name_birth_and_effective_cargo(self):
        result = extract_fields(
            [
                "X\nAssunto:\nProporcional\nIntegral\nEspecial\n"
                "Segurado:\nCPF:\nRG:\nData de Nascimento:\nProcesso N°:\nRegra:\n"
                "1038702.1 - MAGNOLIA RAMALHO MACIEL PINTO LOPES\n"
                "NOVO FLUXO DE APOSENTADORIA POR TEMPO DE CONTRIBUIÇÃO\n"
                "REGRA DE TRANSIÇÃO DA EC 41 - ART. 6° - PROFESSOR\n"
                "50348841434\n822993 SSP\n30/04/1967\n03810033.003126/2019-01\n"
                "Guia Financeira/Taxação de Proventos\nCOMPOSIÇÃO DA REMUNERAÇÃO\n"
                "Fundamentação\nCargo Efetivo\nPROF PERM NIVEL - III (DEC JUD)\nValor",
            ],
            "103439/2023",
            "11",
            "Guia Financeira/Taxação de Proventos",
        )

        self.assertEqual(
            extract_interested(result), "MAGNOLIA RAMALHO MACIEL PINTO LOPES"
        )
        self.assertEqual(result.fields["data_nascimento"].value, "30/04/1967")
        self.assertEqual(result.fields["cargo"].value, "PROF PERM NIVEL - III (DEC JUD)")

    def test_ignores_other_publication_dates_and_keeps_legal_basis(self):
        result = extract_fields(
            [
                "RESOLUÇÃO ADMINISTRATIVA Nº 9\n"
                "RESOLVE conceder aposentadoria voluntária a JOANA DA SILVA, "
                "no cargo de PROFESSOR, matrícula nº 1, nos termos do artigo 6º "
                "da Emenda Constitucional nº 41/2003, com efeitos na data da sua publicação.\n"
                "Ato anterior publicado no Diário Oficial do Estado de 12 de outubro de 2018."
            ],
            "103439/2023",
            "19",
            "RESOLUÇÃO ADMINISTRATIVA",
        )

        self.assertIn("artigo 6º", result.fields["fundamento_legal"].value)
        self.assertEqual(result.fields["data_publicacao_doe"].status, "missing")

    def test_finds_multiline_person_name_and_ignores_agency_acronym(self):
        result = extract_fields(
            [
                "RESOLVE conceder aposentadoria voluntária, a SEEC., no cargo de "
                "PROFESSOR, e a MARIA ANGELITA DA\nSILVA DIAS, no cargo de "
                "PROFESSOR PN - IV, matrícula nº 104.444-3/1.\n"
                "2016 - SEEC."
            ],
            "103466/2023",
            "19",
            "RESOLUÇÃO ADMINISTRATIVA",
        )

        self.assertEqual(extract_interested(result), "MARIA ANGELITA DA SILVA DIAS")
        self.assertIsNone(_find_interested("2016 - SEEC."))


class MergeAndOutputTests(unittest.TestCase):
    def test_conflicting_sources_are_preserved_as_conflict(self):
        first = Extraction(
            process="103439/2023",
            event="9",
            document="RESOLUÇÃO ADMINISTRATIVA",
            fields=extract_fields(
                ["Cargo: PROFESSOR"], "103439/2023", "9", "RESOLUÇÃO ADMINISTRATIVA"
            ).fields,
        )
        second = Extraction(
            process="103439/2023",
            event="12",
            document="Guia Financeira / Taxação de Proventos",
            fields=extract_fields(
                ["Cargo: PROFESSOR II"],
                "103439/2023",
                "12",
                "Guia Financeira / Taxação de Proventos",
            ).fields,
        )

        merged = merge_extractions([first, second])

        self.assertEqual(merged["cargo"].status, "conflict")
        self.assertEqual(
            [candidate.value for candidate in merged["cargo"].candidates],
            ["PROFESSOR", "PROFESSOR II"],
        )

    def test_conflicting_geometry_keeps_each_candidate_identity_and_rects(self):
        first = extract_fields(
            ["Cargo: PROFESSOR"],
            "103439/2023",
            "9",
            "resolucao-9.pdf",
            page_words=[{
                "coordinates": "normalized",
                "method": "native",
                "words": [
                    {"text": "Cargo:", "rect": [0.1, 0.1, 0.2, 0.2]},
                    {"text": "PROFESSOR", "rect": [0.21, 0.1, 0.5, 0.2]},
                ],
            }],
        )
        second = extract_fields(
            ["Cargo: PROFESSOR II"],
            "103439/2023",
            "12",
            "resolucao-12.pdf",
            page_words=[{
                "coordinates": "normalized",
                "method": "ocr",
                "words": [
                    {"text": "Cargo:", "rect": [0.1, 0.6, 0.2, 0.7]},
                    {"text": "PROFESSOR", "rect": [0.21, 0.6, 0.5, 0.7]},
                    {"text": "II", "rect": [0.51, 0.6, 0.55, 0.7]},
                ],
            }],
        )

        merged = merge_extractions([first, second])

        self.assertEqual(merged["cargo"].status, "conflict")
        self.assertEqual(
            [(item.event, item.document, item.method, item.rects) for item in merged["cargo"].candidates],
            [
                ("9", "resolucao-9.pdf", "native", ((0.21, 0.1, 0.5, 0.2),)),
                ("12", "resolucao-12.pdf", "ocr", ((0.21, 0.6, 0.55, 0.7),)),
            ],
        )

    def test_markdown_contains_field_source_and_partial_pending(self):
        extraction = extract_fields(
            ["Modalidade: aposentadoria especial"],
            "103439/2023",
            "9",
            "RESOLUÇÃO ADMINISTRATIVA",
        )
        markdown = render_markdown(
            [
                {
                    "process": "103439/2023",
                    "status": "partial",
                    "interested": "MAGNOLIA RAMALHO MACIEL PINTO LOPES",
                    "fields": merge_extractions([extraction]),
                }
            ],
            run_id="test-run",
        )

        self.assertIn("## Processo 103439/2023", markdown)
        self.assertIn("Processo 103439/2023 · Evento 9 · p. 1", markdown)
        self.assertIn("Campo sem evidência segura", markdown)

    def test_checkpoint_updates_one_process_without_losing_other_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "checkpoint.json"
            store = CheckpointStore(path)
            store.initialize(["103439/2023", "103442/2023"], run_id="run-1")
            store.update_process("103439/2023", {"status": "partial", "event": "9"})

            saved = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(saved["run_id"], "run-1")
            self.assertEqual(saved["processes"]["103439/2023"]["status"], "partial")
            self.assertEqual(saved["processes"]["103442/2023"]["status"], "pending")

    def test_checkpoint_retries_transient_onedrive_replace_lock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "checkpoint.json"
            store = CheckpointStore(path)
            original_replace = Path.replace
            attempts = 0

            def transient_lock(target):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(5, "OneDrive transient lock")
                source = next(Path(temp_dir).glob(".checkpoint.json.*.tmp"))
                return original_replace(source, target)

            with (
                patch("tce_extractor.Path.replace", side_effect=transient_lock),
                patch("tce_extractor.time.sleep") as sleep,
            ):
                store.initialize(["103439/2023"], run_id="run-onedrive")

            self.assertEqual(attempts, 2)
            sleep.assert_called_once()
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["run_id"], "run-onedrive")
            self.assertEqual(list(Path(temp_dir).glob(".checkpoint.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
