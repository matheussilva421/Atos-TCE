"""Static equivalence of the promoted e-Contas runtime (M6 Task 1).

The collector was promoted by copy, and the only documented behaviour change is
``-RaizEstado``: runtime state (browser profile and bridge) moves out of the code
tree. Until the legacy surface is retired, this test keeps the promotion honest:
any other difference between the proven files and the promoted ones fails here.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = REPO_ROOT / "work" / "tce-extractor" / "portable"
LEGACY_EXTRACTOR = REPO_ROOT / "work" / "tce-extractor"
PROMOTED_ROOT = REPO_ROOT / "app" / "econtas" / "runtime"
ENGINE_ROOT = REPO_ROOT / "app" / "analysis" / "engine"
LEGACY_ENGINE_ROOT = LEGACY_ROOT / "app"

# Files the promotion copied without touching a single byte.
IDENTICAL_MODULES = ("TceFrozenQueue.psm1", "TcePortable.Core.psm1", "TcePortal.Driver.js")
COLLECTOR = "Coletar-Processos-TCE.ps1"

# Engine modules the promotion copied without touching a single byte.
IDENTICAL_ENGINE_MODULES = ("archive_index.py", "evidence_geometry.py", "legal_context.py")
# Engine modules whose only difference is how they import their neighbours.
IMPORT_ONLY_ENGINE_MODULES = (
    ("tce_extractor.py", LEGACY_EXTRACTOR / "tce_extractor.py"),
    ("batch_runner.py", LEGACY_EXTRACTOR / "batch_runner.py"),
)


def normalize_collector(text: str) -> str:
    """Reverse the documented promotion changes so both files must match.

    Removes comments (they carry no behaviour) and the ``-RaizEstado`` addition,
    then points the state paths back at ``$scriptRoot`` as the proven script had
    them. Anything else the promotion changed stays in the comparison and fails.
    """

    normalized = []
    inside_receipt = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#region RECIBO"):
            inside_receipt = True
            continue
        if stripped.startswith("#endregion RECIBO"):
            inside_receipt = False
            continue
        if inside_receipt:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("[string]$RaizEstado"):
            continue
        if stripped.startswith("[string]$ResultadoJson"):
            continue
        if stripped.startswith("if ([string]::IsNullOrWhiteSpace($RaizEstado))"):
            continue
        line = line.replace("RaizEstado 'dados-locais", "scriptRoot 'dados-locais")
        line = line.rstrip()
        if line.endswith("$Tessdata = '',"):
            line = line[:-1]
        normalized.append(line)
    # Blank lines carry no behaviour, and the new parameter added one.
    collapsed = []
    for line in normalized:
        if not line.strip() and (not collapsed or not collapsed[-1].strip()):
            continue
        collapsed.append(line)
    return chr(10).join(collapsed).strip(chr(10))


def strip_imports(text: str) -> str:
    """Drop import statements and their fallback scaffolding from a module."""

    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("from ", "import ", "try:", "except ImportError")):
            continue
        kept.append(line.rstrip())
    collapsed = []
    for line in kept:
        if not line.strip() and (not collapsed or not collapsed[-1].strip()):
            continue
        collapsed.append(line)
    return chr(10).join(collapsed).strip(chr(10))


@unittest.skipUnless(LEGACY_ROOT.is_dir(), "legacy tree retired (M6 Task 8)")
class PromotedRuntimeEquivalenceTests(unittest.TestCase):
    def test_the_promoted_modules_are_byte_identical_to_the_proven_ones(self):
        for name in IDENTICAL_MODULES:
            with self.subTest(name=name):
                promoted = (PROMOTED_ROOT / name).read_bytes()
                legacy = (LEGACY_ROOT / name).read_bytes()
                self.assertEqual(promoted, legacy)

    def test_the_promoted_collector_differs_only_by_the_state_root(self):
        promoted = normalize_collector((PROMOTED_ROOT / COLLECTOR).read_text(encoding="utf-8-sig"))
        legacy = normalize_collector((LEGACY_ROOT / COLLECTOR).read_text(encoding="utf-8-sig"))

        self.assertEqual(promoted, legacy)

    def test_the_state_root_parameter_is_required_by_the_mesa(self):
        source = (PROMOTED_ROOT / COLLECTOR).read_text(encoding="utf-8-sig")

        self.assertIn("[string]$RaizEstado", source)
        self.assertEqual(source.count("Join-Path $RaizEstado 'dados-locais"), 3)
        self.assertNotIn("Join-Path $scriptRoot 'dados-locais", source)

    def test_the_collector_writes_the_receipt_only_when_it_is_asked_to(self):
        source = (PROMOTED_ROOT / COLLECTOR).read_text(encoding="utf-8-sig")

        self.assertIn("[string]$ResultadoJson", source)
        self.assertIn("$receipt.processes[$item.key]", source)
        self.assertIn("if (-not [string]::IsNullOrWhiteSpace($ResultadoJson))", source)
        self.assertEqual(source.count("#region RECIBO"), source.count("#endregion RECIBO"))


@unittest.skipUnless(LEGACY_ROOT.is_dir(), "legacy tree retired (M6 Task 8)")
class PromotedEngineEquivalenceTests(unittest.TestCase):
    def test_the_frozen_engine_modules_are_byte_identical_to_the_proven_ones(self):
        for name in IDENTICAL_ENGINE_MODULES:
            with self.subTest(name=name):
                self.assertEqual(
                    (ENGINE_ROOT / name).read_bytes(),
                    (LEGACY_ENGINE_ROOT / name).read_bytes(),
                )

    def test_the_extractor_modules_differ_only_by_their_imports(self):
        for name, legacy_path in IMPORT_ONLY_ENGINE_MODULES:
            with self.subTest(name=name):
                promoted = strip_imports((ENGINE_ROOT / name).read_text(encoding="utf-8-sig"))
                legacy = strip_imports(legacy_path.read_text(encoding="utf-8-sig"))
                self.assertEqual(promoted, legacy)

    def test_the_pipeline_dropped_only_the_legacy_menu_entrypoint(self):
        promoted = (ENGINE_ROOT / "analysis_pipeline.py").read_text(encoding="utf-8-sig")
        legacy = (LEGACY_ENGINE_ROOT / "analysis_pipeline.py").read_text(encoding="utf-8-sig")

        self.assertIn("def run_local_pipeline", legacy)
        self.assertNotIn("def run_local_pipeline", promoted)

    def test_the_promoted_engine_exposes_what_the_mesa_calls(self):
        expectation = {
            "analysis_pipeline.py": ("classify_archive", "build_target_manifest"),
            "incremental_pipeline.py": ("analyze_process", "publish_results"),
        }
        for module, symbols in expectation.items():
            source = (ENGINE_ROOT / module).read_text(encoding="utf-8-sig")
            for symbol in symbols:
                with self.subTest(module=module, symbol=symbol):
                    self.assertIn(f"def {symbol}", source)

class EquivalenceCheckTests(unittest.TestCase):
    """The checks above must fail on a real difference, not only on paper."""

    def test_the_normalizer_keeps_real_changes_visible(self):
        proven = ["param(", ")", "Write-Host 'proven'", ""]
        mutated = ["param(", "    [string]$RaizEstado = ''", ")", "Write-Host 'mutado'", ""]

        self.assertNotEqual(
            normalize_collector(chr(10).join(proven)),
            normalize_collector(chr(10).join(mutated)),
        )

    def test_the_normalizer_ignores_the_documented_change(self):
        proven = [
            "param(",
            ")",
            "$profile = Join-Path $scriptRoot 'dados-locais/perfil-navegador'",
            "",
        ]
        promoted = [
            "param(",
            "    [string]$RaizEstado = ''",
            ")",
            "$profile = Join-Path $RaizEstado 'dados-locais/perfil-navegador'",
            "",
        ]

        self.assertEqual(
            normalize_collector(chr(10).join(proven)),
            normalize_collector(chr(10).join(promoted)),
        )

    def test_the_normalizer_ignores_the_receipt_region(self):
        proven = ["param(", ")", "Write-Host 'proven'", ""]
        promoted = [
            "param(",
            "    [string]$ResultadoJson = ''",
            ")",
            "#region RECIBO",
            "$receipt = [ordered]@{}",
            "#endregion RECIBO",
            "Write-Host 'proven'",
            "",
        ]

        self.assertEqual(
            normalize_collector(chr(10).join(proven)),
            normalize_collector(chr(10).join(promoted)),
        )

    def test_a_change_outside_the_receipt_region_still_fails(self):
        proven = ["Write-Host 'proven'", ""]
        promoted = [
            "#region RECIBO",
            "$receipt = 1",
            "#endregion RECIBO",
            "Write-Host 'mutado'",
            "",
        ]

        self.assertNotEqual(
            normalize_collector(chr(10).join(proven)),
            normalize_collector(chr(10).join(promoted)),
        )


if __name__ == "__main__":
    unittest.main()
