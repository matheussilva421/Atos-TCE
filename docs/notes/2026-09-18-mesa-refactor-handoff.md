# Handoff — Refatoração da Mesa Local (M1 → M6)

**Data:** 2026-09-18
**Branch:** `codex/mesa-local-refactor`
**Planos de referência:**
- `docs/superpowers/plans/2026-09-18-atos-tce-plano-completo.md`
- `docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md`

## 1. Objetivo

Transformar a Mesa Local no único centro de workflow e estado do sistema,
substituindo gradualmente menu PowerShell, serviço local, HTML gerado e
sidepanel. A migração é um *strangler refactor*: o fluxo legado continua
operacional como fallback até o último marco. O clique final de complementação
do ato permanece humano em todos os marcos (`autoSubmit=false`,
`real_send_enabled=false`).

## 2. Decisões técnicas já tomadas

| Decisão | Motivo |
|---|---|
| Trabalhar na branch `codex/mesa-local-refactor` no checkout principal, não em worktree | Os dados privados ignorados (`work/tce-extractor/acervo-tce`, `Versions/`, `outputs/`, `dados-locais/`) só existem neste checkout; M1 Task 6 e M6 auditam esses caminhos |
| `data/` na raiz como raiz de runtime, ignorada pelo Git | Separação código / dados / distribuição exigida pelo design (§10) |
| Blob canônico = cópia verificada de bytes; visão de processo = hardlink ao blob | É o texto do plano (M1 Task 3, Step 3 e Step 4) e o gate de espaço livre pressupõe uma cópia real |
| `documents.relative_path` é relativo à `data_root` (`archive/processos/...`) | Deixa a resolução da API inequívoca e sempre sob `data_root` |
| Processos importados em M1 nascem `PENDENTE` | O estado real vem da varredura da Área Restrita (M2) e da análise (M4). Evita o risco de um `PRONTO` local bloquear a regra fail-closed de M2 (`PRECISA_COMPLEMENTAR -> PENDENTE`, salvo estado mais avançado) |
| Status legado do registro (`partial`) é preservado no evento `legacy_import`, não como status novo | Conserva informação sem inventar política de workflow antes de M4 |
| Normalização canônica de interessado em `app/core/identity.py` | A chave natural `(process_key, interested_normalized)` precisa ser idêntica no importador Python e no scanner JS; a regra vem de `analysis_pipeline._normalise_interested` / `automation-schema.js` |
| Nomes truncados com acento usam forma canônica recalculada; divergência vira aviso no recibo | Garante que a identidade do importador casa com a identidade que a extensão vai produzir em M2 |
| Documentos são vinculados a cada linha `(process_key, interested)` do processo | 724 pastas e 739 registros: 15 chaves têm mais de um interessado e cada linha precisa ser autocontida para o preenchimento |
| Servidor HTTP só aceita bind em loopback | Invariante de segurança do master plan ("local write APIs require an authenticated Mesa loopback session") |

## 3. Estado das tarefas

### M1 — Foundation, SQLite and Read-Only Mesa

| Tarefa | Estado | Commit |
|---|---|---|
| 1. Root layout and Git safety | concluída | `46d37c4` |
| 2. SQLite schema v1 | concluída | `3d899b4` |
| 3. Safe legacy archive import + SHA-256 dedup | concluída | `0c454cd` |
| 4. Read-only Mesa API | concluída | `330968d` |
| 5. Read-only Mesa UI and launcher | concluída | `465cd11` |
| 6. Real archive migration rehearsal | em andamento | — |

### M2 a M6

Não iniciados. Não avançar sem o Exit Gate do marco anterior verde.

## 4. Arquivos criados/alterados

**Código novo (raiz, todos dentro do allowlist do `.gitignore`):**

- `app/__init__.py`, `app/core/__init__.py`, `app/archive/__init__.py`, `app/api/__init__.py`
- `app/core/identity.py` — normalização canônica de interessado (dono único da regra)
- `app/core/models.py` — `ProcessRecord`, `DocumentRecord`, `FieldRecord` congelados
- `app/core/store.py` — SQLite schema v1, migrações transacionais, upsert/leitura
- `app/archive/legacy_import.py` — `scan_legacy_archive`, `import_legacy_archive`, `canonicalize_process_tree`, `sha256_file`
- `app/api/views.py` — view models de leitura + `safe_join` + `resolve_document_file`
- `app/api/server.py` — `serve`, rotas explícitas, sem rota genérica de arquivo
- `app/web/index.html`, `app/web/app.js`, `app/web/app.css` — Mesa somente leitura
- `app/main.py` — launcher (`python -m app.main`)
- `scripts/migrate-legacy.py` — CLI de migração (dry-run por padrão)
- `START.cmd` — encaminha para `python -m app.main`
- `tests/test_store.py`, `tests/test_legacy_import.py`, `tests/test_api_server.py`

**Alterados:** `.gitignore` (allowlist de raiz + `/data/`, `/dist/`, `/tmp/`), `README.md` (seção "Mesa Local").

**Nada de `work/tce-extractor/` foi alterado em M1** (exigência do marco).

## 5. Testes executados

```
python -m unittest tests.test_store tests.test_legacy_import tests.test_api_server
```

- 50 testes, 50 aprovados, 0 falharam (antes do Task 6, que não tem teste próprio).
- Destaques: dedup por SHA-256 (1 blob para 2 cópias), acervo de origem intacto
  (hash + mtime), dry-run não materializa nada, hardlink real entre visão de
  processo e blob, reparse point/junction não seguido, CLI em dry-run,
  API sem rota genérica de arquivo e sem escape de `data_root`,
  launcher sobe `/api/v1/health` de verdade em subprocesso.

## 6. Como retomar

1. `git status` / `git log --oneline -8` na branch `codex/mesa-local-refactor`.
2. Conferir se `data/` já tem o resultado do ensaio real (M1 Task 6).
3. Rodar a suíte: `python -m unittest tests.test_store tests.test_legacy_import tests.test_api_server`.
4. Seguir para o Exit Gate de M1 e só então iniciar M2.

Gate de validação do projeto (inalterado, ainda roda o legado):

```
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
```

## 7. Pendências e riscos

- M1 Task 6 depende de espaço em disco: são ~8,4 GB de PDFs de origem e o gate
  exige `bytes_unique + 2 GiB` livres (56,9 GB livres no início do ensaio).
- `tests/fixtures/legacy-archive` citado no plano não é versionado porque
  `**/*.pdf` é ignorado; as fixtures são construídas em teste e o ensaio real
  usa `work/tce-extractor/acervo-tce`.
- O `.git` está somente-leitura dentro do sandbox: `git add`/`git commit` exigem
  aprovação de escalonamento.
- M6 depende de aprovação explícita do usuário antes de qualquer remoção de
  legado ou limpeza de armazenamento (o plano exige tag de segurança, recibos e
  auditoria de SHA antes).

## 8. Fronteiras preservadas

- Nenhum auto-submit foi adicionado; o protocolo novo ainda não existe (M5).
- Login em Área Restrita e e-Contas continua humano.
- `Versions/`, `outputs/`, `dados-locais/` e o acervo privado não foram tocados.
