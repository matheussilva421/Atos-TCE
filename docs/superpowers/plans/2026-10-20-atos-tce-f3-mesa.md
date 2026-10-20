# Atos-TCE F3 — Mesa UI, PDF and Protected Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernizar a Mesa em duas colunas, permitir PDFs assíncronos e preservar rascunhos locais protegidos com merge seguro após mudanças oficiais.

**Architecture:** `app/web` controla apenas apresentação e troca de seleção; estado oficial continua em SQLite; drafts são persistidos em armazenamento local por computador e nunca exportados. PDF usa generation token para descartar respostas antigas.

**Tech Stack:** HTML/CSS/JavaScript, Node node:test, Python 3/unittest, Windows DPAPI/ACL, SQLite.

**Spec:** `docs/superpowers/specs/2026-10-20-atos-tce-mesa-extensao-json-portal-lab-design.md` §§11–12. Depende de F0 e F2.

## Global Constraints
- Preservar identidade visual do HTML `complementar-ato.html` (marinho/cobre/creme) com modernização, não reusar JavaScript legado.
- Tela principal PDF esquerda + ficha direita, divisor redimensionável, sem terceira coluna permanente; busca/seleção no cabeçalho.
- Áreas dedicadas Mesa/Aquisição/Lotes-JSON/Diagnósticos/Configurações; navegar não paralisa observação do formulário.
- Ficha e seleção atualizam antes do PDF; ao suspender acompanhamento manter o último documento com aviso.
- Draft protegido por computador, fora do workspace portátil, do JSON e das respostas de lookup da Mesa; preservar versão base e identidade exata.
- Nenhuma gravação oficial automática, mesmo durante troca de formulário. Merge de campos independentes requer salvar humano, conflito real requer escolha explícita.
- TDD, review independente, privacidade e Reliability Reset; não implementar código durante a preparação deste documento.

## Review Focus
1. PDF antigo termina depois de escolher outro processo: não substitui a renderização atual (T2).
2. Documento classificado como principal ambiguamente não abre primeiro arquivo por ordem (T2).
3. Draft não persistiu por disco cheio/DPAPI: UI não afirma protegido e avisa antes de trocar (T3).
4. Estado oficial muda entre proposta de merge e Salvar: CAS recusa, preservando draft (T4).
5. Navegação às áreas auxiliares não pausa o tracker nem perde PDF, ficha e scroll (T5).

---

### Task F3-T1: Estrutura visual principal e divisor

**Files:** Modify `app/web/index.html`, `app/web/app.css`; Create `app/web/tests/mesa-layout.test.mjs`.

**Interfaces:** DOM semântico `#mesa-pdf-pane`, `#mesa-review-pane`, `#mesa-divider`; controle de largura por `--mesa-pdf-width` ajustável via teclado/mouse.

- [ ] **Step 1 — RED:** `mesa_uses_exactly_two_primary_panes`: validar DOM HTML por fixture para contagem de painéis 2, labels acessíveis e divisor. `keyboard_resizes_and_persists_in_session`: faixa 25–75% sob viewport suportado.
- [ ] **Step 2 — Observar RED:** `node --test app/web/tests/mesa-layout.test.mjs`; teste deve falhar pelo DOM atual.
- [ ] **Step 3 — GREEN mínimo:** Reorganizar CSS e marcação com cabeçalho marinho/cobre e ficha creme, sem reconstruir legado; respeitar foco e semântica ARIA do splitter; preferências de largura durante sessão.
- [ ] **Step 4 — Verificar:** Focado PASS e `node --test app/web/tests/*.test.mjs` PASS; comparação manual de viewports com HTML de referência, evidência sanitizada.
- [ ] **Step 5 — Commit:** `git add app/web/index.html app/web/app.css app/web/tests/mesa-layout.test.mjs && git commit -m "feat: restore two-column Mesa visual architecture"`.
- [ ] **Step 6 — Review:** Fresh reviewer avalia contraste, overflow, acessibilidade, a fidelidade dos elementos visuais e regressões de ações existentes.

### Task F3-T2: Estado de PDF assíncrono, último visto e ambiguidade

**Files:** Create `app/web/document-viewer-state.js`, `app/web/tests/document-viewer-state.test.mjs`; Modify `app/web/app.js` e CSS/HTML somente se indispensável.

**Interfaces:** `chooseDocument({processId,available,lastSelected,principal}) -> {kind:'AUTO'|'ASK',documentId?}`; `acceptViewerResult(expectedGeneration,result) -> boolean`.

- [ ] **Step 1 — RED:** `late_pdf_result_cannot_replace_current`, `ambiguous_principal_requests_selection`, `last_selected_document_precedes_principal`: assert.equal(acceptViewerResult(11,{generation:10}),false); ambiguidade => ASK.
- [ ] **Step 2 — Observar RED:** `node --test app/web/tests/document-viewer-state.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Separar seleção da ficha do load PDF; usar generation/cancel para descarte de callbacks antigos, última escolha por processo somente na sessão e estado HOT/ARCHIVED/MISSING explícito.
- [ ] **Step 4 — Verificar:** Focado PASS, `node --test app/web/tests/*.test.mjs` PASS; confirmar que PDF não bloqueia troca rápida.
- [ ] **Step 5 — Commit:** `git add app/web/document-viewer-state.js app/web/tests/document-viewer-state.test.mjs app/web/app.js && git commit -m "feat: choose and load PDFs asynchronously without stale results"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica cancelar load, falha/arquivo ausente, documentos homônimos e fallback manual.

### Task F3-T3: Armazenamento local protegido de rascunhos

**Files:** Create `app/core/draft_store.py`, `tests/test_draft_store.py`; Modify `app/api/server.py` somente para endpoint autenticado de rascunho de usuário local.

**Interfaces:** `save_draft(key: DraftKey, base_revision: str, changes: dict) -> DraftReceipt`, `load_draft(key: DraftKey) -> Draft | None`; key é processo+interessado exatos.

- [ ] **Step 1 — RED:** `DraftStoreTests.test_persist_across_restart_on_same_machine`, `test_encrypted_at_rest`, `test_rejected_write_not_reported_saved`: assert que arquivo não contém texto claro dos campos; sem DPAPI/salvamento sucesso falso.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_draft_store -v` FAIL; fixtures usam identidades inventadas, testes Windows-only têm marcação explícita de ambiente.
- [ ] **Step 3 — GREEN mínimo:** Armazenamento em caminho por usuário fora do workspace portátil com ACL restritiva e DPAPI Windows (sem chave hardcoded); gravação temporária + replace atômico + recuperação de journal; não logar texto de campos.
- [ ] **Step 4 — Verificar:** Focado PASS nos Windows suportados; em outros ambientes testes dependentes de DPAPI são SKIP explícito, não PASS fictício. `python -m unittest discover -s tests -p "test_*.py" -q`.
- [ ] **Step 5 — Commit:** `git add app/core/draft_store.py app/api/server.py tests/test_draft_store.py && git commit -m "feat: persist protected local Mesa drafts"`.
- [ ] **Step 6 — Review:** Fresh reviewer confere permissões, falhas de disco, DPAPI, path traversal e ausência de rascunho em lookup/JSON.

### Task F3-T4: Merge de três versões e salvamento humano com CAS

**Files:** Create `app/core/draft_merge.py`, `tests/test_draft_merge.py`; Modify `app/core/store.py` e API local apenas por métodos existentes comprovados.

**Interfaces:** `merge_draft(base: dict, draft: dict, official: dict) -> MergeProposal`; `save_if_revision_matches(process_id, interested_id, expected_revision, values) -> bool`. Nenhuma atualização oficial sem ação explícita.

- [ ] **Step 1 — RED:** `DraftMergeTests.test_disjoint_changes_merge`, `test_same_field_conflict_requires_choice`, `test_revision_change_during_save_preserves_draft`: assertFalse(save_if_revision_matches(...,"rev-antiga",values)).
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_draft_merge -v` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Implementar base/draft/current por campo e conflito explícito; CAS transacional no SQLite no instante do clique Salvar; conflito não apaga draft.
- [ ] **Step 4 — Verificar:** Focado PASS, `python -m unittest discover -s tests -p "test_*.py" -q` PASS; testes de concorrência em processos distintos.
- [ ] **Step 5 — Commit:** `git add app/core/draft_merge.py app/core/store.py tests/test_draft_merge.py && git commit -m "feat: safely merge drafts with official revision checks"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica ABA/version collision, perdas de dados, idempotência de Save e ausência de autosave oficial.

### Task F3-T5: Áreas auxiliares e integração dos rascunhos à Mesa

**Files:** Modify `app/web/index.html`, `app/web/app.js`, `app/web/app.css`; Create `app/web/tests/mesa-navigation-drafts.test.mjs`.

**Interfaces:** `captureUnsavedDraftBeforeFollow(currentSelection) -> Promise<receipt>`, `restoreDraftOnReturn(processKey,interestedKey) -> Promise<draft|none>`; áreas no cabeçalho sem sidebar obrigatória.

- [ ] **Step 1 — RED:** `follow_switch_saves_draft_before_replacing_form`, `draft_save_failure_is_visible`, `auxiliary_navigation_preserves_selection_and_pdf`: assert que troca automática não declara proteção se receipt falhar; seleção permanece mesmo sem portal ativo, mas edição não se perde silenciosamente.
- [ ] **Step 2 — Observar RED:** `node --test app/web/tests/mesa-navigation-drafts.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Conectar UI às APIs de draft com mensagens claras, restaurar edições ao retornar, expor revisão de conflito e Save humano; menus para aquisição, lotes, diagnósticos e configurações sem suprimir observação de F2. Se a persistência protegida falhar, conservar edição na memória da sessão, emitir alerta destacado de risco e ainda acompanhar imediatamente o novo processo, sem indicar que o rascunho foi protegido.
- [ ] **Step 4 — Verificar:** Focado PASS, `node --test app/web/tests/*.test.mjs` PASS; navegador desktop/menor com foco/teclado e comparação visual.
- [ ] **Step 5 — Commit:** `git add app/web/index.html app/web/app.js app/web/app.css app/web/tests/mesa-navigation-drafts.test.mjs && git commit -m "feat: connect Mesa draft recovery and auxiliary workspaces"`.
- [ ] **Step 6 — Review:** Fresh reviewer avalia perda silenciosa de edição, navegação em múltiplas abas Mesa, áreas antigas e acessibilidade.

### Task F3-T6: Exportação manual na área Lotes/JSON

**Files:** Modify `app/web/app.js`, `app/web/index.html`; Create `app/web/tests/mesa-export-batch.test.mjs`.

**Interfaces:** `requestBatchV2Download(selectedProcessIds) -> Promise<{filename,sha256,processCount,interestedCount}>` usa API de F0-T6; não modifica automaticamente o JSON ativo da extensão.

- [ ] **Step 1 — RED:** `export_selected_lot_ignores_visual_filter` e `empty_selection_refuses_export`: selecionando A+B, o arquivo inclui A+B mesmo que busca visual mostre só A; lote vazio recusado.
- [ ] **Step 2 — Confirm RED:** `node --test app/web/tests/mesa-export-batch.test.mjs` FAIL.
- [ ] **Step 3 — GREEN:** Adicionar seleção explícita de lote, contagens e botão `Exportar JSON v2`; acionar somente rota F0-T6; reportar SHA e exigir reimportação manual na extensão.
- [ ] **Step 4 — Verify:** `node --test app/web/tests/mesa-export-batch.test.mjs` e `node --test app/web/tests/*.test.mjs` PASS, com zero interessados e arquivo validável por F1.
- [ ] **Step 5 — Commit:** `git add app/web/app.js app/web/index.html app/web/tests/mesa-export-batch.test.mjs && git commit -m "feat: download selected complete JSON batch from Mesa"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica integridade do lote, filtro desacoplado e nenhuma importação/fill automático.

## F3 exit gate
- [ ] Comparação visual com HTML antigo documentada; duas colunas e divisor acessível.
- [ ] Mudança de formulário durante edição não grava dados oficiais, nem perde draft sem aviso.
- [ ] PDFs atrasados descartados e documentos ambíguos pedem escolha.
- [ ] Testes Python/web, revisão independente e packaging do runtime verde.
- [ ] Nenhuma função da Área Restrita habilitada em produção sem 20/20+20/20.
