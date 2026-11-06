# Baseline final — Complementador e-Contas (F0)

Data: 05/11/2026
Projeto: `C:\Users\slvma\Downloads\Github\Atos-TCE\Complementador-eContas`
Raiz Git: `C:\Users\slvma\Downloads\Github\Atos-TCE`
Branch: `codex/complementador-e-contas`

## Estado do Git

| Verificação | Resultado |
| --- | --- |
| HEAD local | `66febfb1b4c996f9ed79634ccd00ccd0a873bb37` |
| `origin/codex/complementador-e-contas` | `66febfb1b4c996f9ed79634ccd00ccd0a873bb37` |
| `main` | `6e1acd50e7be8895b415d40bae4376e169e05ee1` |
| `origin/main` | `6e1acd50e7be8895b415d40bae4376e169e05ee1` |
| `git status --short --branch` | limpo e sincronizado no início do F0 |
| `git diff --check` | PASS (sem saída) |

Últimos commits: `66febfb` (relatório final), `cb10b1a` (status e matriz CA), `90a1716` (H2/H3), `4fc8f76` (salvamento único), `ef41b1d` (4 preenchidos), `efb90cb` (BUSCAR automático).

## Testes e build do baseline

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **266 PASS**, 0 FAIL, 5,9 s |
| `npm run test:browser` | **23 PASS**, 0 FAIL, 34,6 s (Chromium 1248 headless) |
| `npm run build` | PASS — `background.js` 117.340 B, `form-content.js` 54.024 B, `autos-content.js` 984.438 B, `list-content.js` 27.656 B, `manifest.json` 1.196 B |

O build acima usa o padrão seguro: sem `BATCH_EXECUTION` e sem `BATCH_FILL_ONLY`. Os hashes SHA-256 coincidem com os registrados em `docs/evidence/final-report-2026-11-05.md`.

## Backup e restauração

| Item | Valor |
| --- | --- |
| Pasta | `work/batch-final-baseline-2026-11-05` |
| Conteúdo | `src`, `docs`, `tests`, `scripts`, `extension`, `dist`, `package.json`, `package-lock.json`, `README.md`, `.gitignore` |
| Arquivos | 128 |
| `SHA256SUMS.txt` | 128 linhas |
| ZIP | `work/batch-final-baseline-2026-11-05.zip` (915.327 bytes) |
| SHA-256 do ZIP | `2AAF8D1449C838D9DFC42669622A0F30163E26FFE50652E1352960EF25FA3C1E` |
| Extração de ensaio | `work/batch-final-baseline-2026-11-05-extract` |
| Divergências na extração | **0** |

O backup anterior (`work/batch-baseline-2026-11-05`) não foi alterado. Nenhum perfil de navegador, cookie ou credencial foi copiado.

## Documentação reconciliada antes do F1

O commit `66febfb` corrigiu as contradições apontadas no GOAL: `batch-ca-traceability.md`, `batch-release-candidate.md`, `batch-h1.md`, `README.md` e `docs/notes/handoff.md` agora distinguem `SUPERVISED_REAL_SAVE_VERIFIED (4/4)`, `AUTOMATED_SAVE_NOT_RUN` e `G7_PENDING`. O relatório consolidado está em `docs/evidence/final-report-2026-11-05.md`.

## Declaração

`BASELINE_PASS`. Árvore limpa, suítes verdes, build seguro reproduzível, backup íntegro com restauração conferida. As alterações de código do F1 começam a partir deste ponto.
