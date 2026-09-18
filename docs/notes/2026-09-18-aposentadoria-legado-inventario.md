# Aposentadoria do legado — inventário e sequência (M6 tarefa 8)

**Data:** 2026-09-18 · **Branch:** `codex/mesa-local-refactor`

Este documento é o inventário que falta para autorizar a remoção. Ele não remove
nada: descreve o que existe, o que ainda é carga hoje, o que muda de contrato e a
sequência proposta.

## 1. Achado que decide a limpeza de `Versions/`

O ZIP `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14.zip`
não é uma cópia antiga do acervo atual: é uma **rodada anterior** de coleta.

| Medida | Valor |
|---|---|
| Pastas de processo no ZIP | 166 (`100064-2022`, `100087-2022`, `100090-2022`, …) |
| PDFs | 3.273, somando 1,414 GB descomprimidos |
| Pastas do ZIP com `process_key` no banco canônico | 0 de 166 |
| Pastas do ZIP presentes na árvore canônica | 0 de 166 |
| Nomes de documento iguais a títulos canônicos | 0 de 3.273 |

O importador já foi exercitado em **dry-run** sobre essa cópia extraída (somente
leitura, sem materializar nada): 166 processos, 3.273 documentos, 3.273 PDFs
únicos, 0 duplicados, 0 erros, 0 avisos, 1.414.007.810 bytes (1,41 GB) — dentro
do gate de espaço (`bytes_unique` + 2 GiB livres, com 52 GB livres hoje). No
caminho, o ensaio revelou um defeito no gate destrutivo: o dry-run do importador
também grava recibo em `data/logs/`, e o recibo mais novo venceria a checagem de
`acervo-tce`. Corrigido: a limpeza agora exige recibo com `mode=apply` e sem
erros (`migration_receipt_not_apply` / `migration_receipt_has_errors`), com
testes para os dois casos e para o dry-run mais novo.

Ou seja: esses bytes existem **apenas** nesse ZIP. O acervo canônico tem 739
processos (724 pastas) da rodada atual; o ZIP tem 166 processos de 2022 do
Setor 156. Enquanto eles não estiverem preservados em outro lugar, o auditor
recusa `Versions/` (10,6 GB) e a ferramenta de limpeza não toca nela — é o
comportamento correto.

Duas saídas possíveis, ambas explícitas:

1. **Importar** os 3.273 PDFs para o acervo canônico pelo importador já provado
   (`scripts/migrate-legacy.py`, o ZIP contém `acervo-tce/processos/...` no
   layout esperado). Isso cria 166 processos de 2022 fora do escopo atual do
   trabalho na Mesa e libera os 10,6 GB de `Versions/` na auditoria seguinte.
2. **Manter** o ZIP como única cópia e deixar `Versions/` bloqueado, sem
   reclamar os 10,6 GB.

## 2. Unidades de aposentadoria em `work/tce-extractor`

215 arquivos versionados, 6,40 MB (os diretórios privados `acervo-tce/`,
`dados-locais/`, `outputs/`, `work/` e `docs/` não são versionados e não entram
aqui).

| Unidade | Arquivos | Tamanho | O que é |
|---|---|---|---|
| U1 superfície do pacote legado | 104 | 4,91 MB | `portable/**`: menu PowerShell, serviço local, web gerada, extensão legada (content, sidepanel, automation controller), launchers, `runtime-manifest.json` e licenças (já promovidos para `packaging/`), guias |
| U2 gate legado | 21 | 0,24 MB | `verify-project.ps1` e `tests/Test-*.ps1` (599 comandos hoje) |
| U3 testes Python legados | 50 | 0,76 MB | `test_*.py` da raiz do extrator (inclui os das etapas 3, 5 e 6 do gate) |
| U4 engines antigos na raiz | 9 | 0,17 MB | `batch_runner.py`, `tce_extractor.py`, `html_generator.py`, `consolidate_results.py`, `organize_pdfs.py`, `process_collections.py`, `targeted_collection.py`, `probe_target_url.py`, `extension_exporter.py` — todos com cópia promovida em `app/` |
| U5 empacotadores e QA legados | 28 | 0,31 MB | `build-portable-runtime.ps1`, `empacotar-*.ps1`, `package_*.py`, `qa_*.py`, `coleta-*.ps1`, `probe-existing-chrome.ps1`, `real_portal_session.py`, `clean-local-workspace.ps1`, `requirements-qa.txt`, `QA-DEPENDENCIAS.md` |
| U6 docs internas do extrator | 1 | 0,02 MB | `docs/notes/...` da extração legada |
| U7 outros | 2 | <0,01 MB | `verify_new_batch_zip.py`, `verify_qa_release.py` |

## 3. Dependências que mudam o contrato

1. **U2 é o gate atual.** `AGENTS.md` (contrato do projeto) manda validar com
   `verify-project.ps1`, e esse script roda a extensão legada, a web legada, o
   `portable` e os testes PowerShell. Remover U1 quebra as etapas 1–3 desse gate,
   então a aposentadoria precisa mover o contrato de validação para os gates da
   raiz (suíte Python, `npm test` da extensão, `packaging/build-portable.ps1`,
   `packaging/verify-package.ps1` com smoke) — o que implica **editar
   `AGENTS.md`**, arquivo do usuário.
2. **U5 não é toda descartável.** `qa_portal_recorder.py`, `real_portal_session.py`,
   `qa_*.py`, `coleta-*.ps1`, `probe-*.ps1` são as ferramentas que produzem a
   evidência de portal real (M2, M3 e o preenchimento supervisionado de M5).
   Elas não são usadas pelo runtime novo — e não podem sair antes de os gates
   supervisionados rodarem.
3. **`scripts/scan-area-cdp.ps1` não é legado.** É ferramenta suportada do M2
   (usada por `app/area_restrita/cdp_fallback.py`) e fica.
4. As duas proveniências literais que sobraram em `app/`, `extension/` e
   `packaging/` já foram reescritas; a fronteira é verificada por
   `tests/test_no_legacy_paths.py`.

## 4. Sequência proposta (cada passo exige autorização)

**Etapa A — retirar o stack legado (U1, U2, U3, U4, U6, U7).**

1. `git tag pre-legacy-retirement` e push da tag (com remoto confirmado).
2. Gates antes: suíte Python da raiz, `npm test` da extensão, contrato do pacote
   e smoke de extração limpa — todos verdes (estado atual: 401, 86, 11 e verde).
3. `git rm -r` das unidades, um commit por unidade, com `git diff --check`.
4. Gates depois: os mesmos da raiz, mais `git diff --check`.
5. `git tag mesa-migration-complete`.

**Etapa B — depois dos gates supervisionados reais (M2, M3 e M5).**

1. Remover U5 (ferramentas de portal real) quando a evidência real estiver
   registrada.
2. `python scripts/cleanup-storage.py --audit data/logs/storage-audit.json --allow-legacy-archive --apply`
   para o acervo de origem (`acervo-tce`, 9,05 GB, já `safe_to_delete` com recibo
   de migração presente) — e, se a decisão for importar os 3.273 PDFs, reauditar
   e liberar `Versions/` (10,6 GB).

## 5. O que já está pronto e não depende de autorização

- padrão novo documentado (`README.md`, `docs/ESTRUTURA.md`) e fronteira verde;
- ZIP padrão sem acervo construído, verificado, com smoke e retenção de dois
  builds em `dist/`;
- auditoria de armazenamento, backup explícito e limpeza por recibo implementados
  e testados;
- recusas da limpeza documentadas por motivo (nada de remoção ampla).
