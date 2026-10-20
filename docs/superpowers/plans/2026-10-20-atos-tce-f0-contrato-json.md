# Atos-TCE F0 — Five-Field Contract & Batch V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar fundamento legal do preenchimento e publicar um lote JSON v2 completo, imutável e com integridade canônica compartilhada.

**Architecture:** Atualizar allowlist do fluxo operacional, mas preservar o SQLite histórico; exportador puro com inventário separado de interessados e checksum SHA-256. A extensão validará o mesmo contrato em F1.

**Tech Stack:** Python 3/unittest, SQLite, JS/Node node:test.

**Spec:** `docs/superpowers/specs/2026-10-20-atos-tce-mesa-extensao-json-portal-lab-design.md` §§5–7; master `docs/superpowers/plans/2026-10-20-atos-tce-master.md`.

## Global Constraints
- Apenas cinco campos graváveis: `modalidade`, `data_publicacao_doe`, `cargo`, `matricula`, `data_nascimento`; `tipo_processo` classificação; `fundamento_legal` e `genero` nunca escrita.
- Nunca apagar o histórico jurídico, executar migrations destrutivas ou ligar fallback à Mesa para completar JSON parcial.
- Inventário corresponde ao lote selecionado, não a filtros ativos de tela; processo sem interessado deve constar.
- JSON v1 não será convertido silenciosamente nem aceito no caminho v2. Preservar número e ano como strings e zeros significativos.
- Somente documentação nesta etapa. Na execução: RED, GREEN, commit/review por task; sem ações L3 de portal; gates Reliability Reset 20/20+20/20 não dispensados.

## Review Focus
1. `000123/2026` e `123/2026` não colidem nem são convertidos em floats (T3).
2. Zero interessados não remove processo selecionado do inventário (T3).
3. Reexecução de migração/read adapter não apaga `fundamento_legal` histórico (T2).
4. Unicode e ordem de arrays têm hash idêntico Python/JS; checksum exclui só a própria chave (T4).
5. Falta de um dos cinco campos não impede preenchimento dos demais no preflight (T2).

---

### Task F0-T1: Contrato operacional exato de cinco campos

**Files:** Modify `app/analysis/__init__.py`; Create `tests/test_five_fields_contract.py`.

**Interfaces:** `FILLABLE_FIELDS: tuple[str, ...]` é a allowlist única; `MANDATORY_FIELDS` preserva importadores antigos, mas não é regra bloqueadora do preenchimento parcial.

- [ ] **Step 1 — RED:** Adicionar `FiveFieldsContractTests.test_exact_five_fields` que importe `FILLABLE_FIELDS` e use `self.assertEqual(FILLABLE_FIELDS, ("modalidade", "data_publicacao_doe", "cargo", "matricula", "data_nascimento"))`; `self.assertNotIn("fundamento_legal", FILLABLE_FIELDS)`; idem gênero e tipo.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_five_fields_contract -v`; esperar falha na asserção/interface, não no ambiente.
- [ ] **Step 3 — GREEN mínimo:** Definir `FILLABLE_FIELDS` em `app/analysis/__init__.py`; adaptar aliases que existam após inventário de consumidores sem deletar dados legados.
- [ ] **Step 4 — Verificar:** Mesmo comando PASS; `python -m unittest discover -s tests -p "test_*.py" -q` sem novas falhas.
- [ ] **Step 5 — Commit:** `git add app/analysis/__init__.py tests/test_five_fields_contract.py && git commit -m "refactor: define five-field complement contract"`.
- [ ] **Step 6 — Review:** Reviewer independente verifica dependências legadas, imports e ausência de alteração de dados; corrigir P0/P1 antes de T2.

### Task F0-T2: Preflight sem fundamento legal e compatibilidade histórica

**Files:** Modify `app/area_restrita/preflight.py` e, apenas onde exigido, `app/area_restrita/fill_service.py`; Create `tests/test_five_field_preflight.py`.

**Interfaces:** `build_fill_plan(...)` mantém a assinatura pública existente, mas retorna plano com até cinco campos, sem `legal_decision` operacional nem consulta a `resolve_legal_foundation`.

- [ ] **Step 1 — RED:** Escrever `FiveFieldPreflightTests.test_legal_only_legacy_value_not_part_of_plan`: cinco campos elegíveis geram plano não bloqueado mesmo sem fundamento; campos ausentes ficam pendentes e os demais são elegíveis.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_five_field_preflight -v`; falha esperada no requisito de campo jurídico.
- [ ] **Step 3 — GREEN mínimo:** Remover dependência jurídica da preparação operacional e rejeitar fundamentos em payloads de escrita; conservar dados históricos e leitores destinados à auditoria, sem DELETE ou schema drop.
- [ ] **Step 4 — Verificar:** teste focado PASS; `python -m unittest tests.test_fill_service tests.test_api_server -q` PASS após atualizar contratos conflitantes com a spec.
- [ ] **Step 5 — Commit:** `git add app/area_restrita/preflight.py app/area_restrita/fill_service.py tests/test_five_field_preflight.py && git commit -m "fix: remove legal foundation from operational preflight"`.
- [ ] **Step 6 — Review:** Verificar ausência de caminhos de fallback legal e preservação histórica/idempotência; fresh reviewer, corrigir P0/P1.

### Task F0-T3: Exportação de inventário integral e interessados separados

**Files:** Create `app/exports/__init__.py`, `app/exports/batch_v2.py`, `tests/test_batch_v2_export.py`.

**Interfaces:** `export_batch_v2(processes: list[dict], interested: list[dict], batch_id: str, generated_at: str) -> dict`. Produz `schema_version=2`, `processes[]`, `interested[]`, metadados; exatamente cinco campos por registro, tipo_processo classificação.

- [ ] **Step 1 — RED:** Em `BatchV2ExportTests.test_selected_inventory_is_complete`, exportar processos `000123/2026` e `123/2026`, o primeiro com zero interessados; `self.assertEqual(len(batch["processes"]), 2)`, `self.assertNotEqual(batch["processes"][0]["process_key"],batch["processes"][1]["process_key"])`, `self.assertNotIn("fundamento_legal", str(batch))`.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_batch_v2_export -v`; função ausente/asserção falha.
- [ ] **Step 3 — GREEN mínimo:** Exportador puro verifica tipo e identidade, vínculo de interessado, unicidade e ausência de pessoas fictícias; falhar explicitamente em duplicação/corrupção.
- [ ] **Step 4 — Verificar:** Teste focado PASS; `python -m unittest discover -s tests -p "test_*.py" -q` PASS.
- [ ] **Step 5 — Commit:** `git add app/exports tests/test_batch_v2_export.py && git commit -m "feat: export full selected process batch v2"`.
- [ ] **Step 6 — Review:** Revisar filtros da Mesa versus lote, zeros, homônimos, dados sensíveis em logs e integridade referencial.

### Task F0-T4: Integridade canônica e vetores golden

**Files:** Create `app/exports/canonical_v2.py`, `tests/fixtures/batch_v2_golden.json`, `tests/test_batch_v2_canonical.py`; coordenação com F1-T1 para teste JS de paridade.

**Interfaces:** `canonical_bytes_v2(batch: dict) -> bytes`; `batch_sha256_v2(batch: dict) -> str`. UTF-8 e política de ordenação definida por este contrato e vetores golden; excluir somente `sha256` na serialização pré-hash.

- [ ] **Step 1 — RED:** `BatchCanonicalTests.test_hash_changes_on_interested_and_keeps_unicode`: `self.assertEqual(batch_sha256_v2(golden), golden["sha256"])`; alterar um único campo de interessado e exigir hash diferente; testar NFC/ordem de arrays conforme contrato congelado.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_batch_v2_canonical -v`; falha por ausência ou mismatch.
- [ ] **Step 3 — GREEN mínimo:** Implementar canonicalização explícita com `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",",":"))` **somente após** definir tratamento de Unicode NFC e ordenação de coleções do contrato; usar SHA-256 dos bytes; congelar fixture.
- [ ] **Step 4 — Verificar:** Teste focado PASS; em F1-T1 tornar obrigatória a paridade `node --test extension/tests/batch-v2-golden.test.mjs` antes da conclusão integrada de F0+F1.
- [ ] **Step 5 — Commit:** `git add app/exports/canonical_v2.py tests/fixtures/batch_v2_golden.json tests/test_batch_v2_canonical.py && git commit -m "test: freeze canonical batch v2 integrity vectors"`.
- [ ] **Step 6 — Review:** Examinar hash próprio, alteração de ordem de arrays, Unicode, data, checksum cross-language e não anunciar gate JS antes de F1.

### Task F0-T5: Mesa exibe somente cinco campos operacionais

**Files:** Modify `app/web/portal-current.js`, `app/web/tests/portal-current.test.mjs`.

**Interfaces:** `KNOWN_PORTAL_FIELDS`, `classifyPortalProcess(process)` e `portalFieldModels(process)` reportam cinco campos e estado parcial, sem fundamento/gênero. `tipo_processo` na ficha de classificação separada.

- [ ] **Step 1 — RED:** Alterar `portal-current.test.mjs`: `assert.equal(KNOWN_PORTAL_FIELDS.length, 5)`; `assert.equal(classifyPortalProcess(full).foundCount, 5)`; nenhuma entrada `fundamento_legal` ou `genero`.
- [ ] **Step 2 — Observar RED:** `node --test app/web/tests/portal-current.test.mjs`; testes antigos de sete campos falham.
- [ ] **Step 3 — GREEN mínimo:** Atualizar catálogo e contagem; remover premissas de fundamento das interações operacionais, sem alterar histórico do SQLite.
- [ ] **Step 4 — Verificar:** Mesmo teste PASS; `node --test app/web/tests/*.test.mjs` PASS.
- [ ] **Step 5 — Commit:** `git add app/web/portal-current.js app/web/tests/portal-current.test.mjs && git commit -m "refactor: show only five operational form fields"`.
- [ ] **Step 6 — Review:** Reviewer verifica consistência visual e funcional entre cartões, contadores e classificação.

### Task F0-T6: API autenticada para exportar lote completo

**Files:** Modify `app/api/server.py`; Create `tests/test_batch_v2_api.py`. Reuse `app/exports/batch_v2.py` and `canonical_v2.py`.

**Interfaces:** `POST /api/v1/exports/batch-v2` com `{scope:"selected",process_ids:[...]}` sob sessão Mesa autenticada. Resolve toda a seleção explícita, sem aplicar filtro visual.

- [ ] **Step 1 — RED:** `BatchV2ApiTests.test_selected_batch_ignores_ui_filter`: resposta para IDs A+B inclui ambos e interessados mesmo com filtro visual mostrando A; requisição não autenticada é rejeitada.
- [ ] **Step 2 — Confirm RED:** `python -m unittest tests.test_batch_v2_api -v` FAIL por rota ausente.
- [ ] **Step 3 — GREEN:** Resolver dados oficiais sob snapshot coerente, validar IDs, produzir JSON v2 e checksum por F0-T3/T4; lista vazia bloqueada.
- [ ] **Step 4 — Verify:** `python -m unittest tests.test_batch_v2_api tests.test_api_server -q` PASS; processo sem interessado consta.
- [ ] **Step 5 — Commit:** `git add app/api/server.py tests/test_batch_v2_api.py && git commit -m "feat: expose complete batch v2 export API"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica scope, sessão, acervo e nenhuma influência de filtros visuais.

## F0 exit gate
- [ ] Cada tarefa tem RED/GREEN, SHA e review independente aceito.
- [ ] Nenhuma migração destrutiva de dados históricos; nenhum valor jurídico no JSON v2.
- [ ] Schema v2 documentado e consumível; paridade JS é gate conjunto com F1-T1, não declarar compatibilidade antes dele.
- [ ] Suítes offline, diff e privacidade verdes; status Reliability Reset não promovido.
- [ ] Handoff datado; **nenhuma implementação autorizada pela redação deste plano**.
