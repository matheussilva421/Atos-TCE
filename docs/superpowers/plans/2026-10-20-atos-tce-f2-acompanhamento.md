# Atos-TCE F2 — Portal Following and Exceptional Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acompanhar automaticamente a última aba com formulário real, atualizar a Mesa em baixa latência e realizar fallback somente se registro exato estiver ausente do JSON.

**Architecture:** Extensão MV3 determina aba/frame e publica observações deduplicadas no canal autenticado atual; Mesa projeta a seleção sem bloquear por PDFs; lookup excepcional responde dados oficiais, com cache single-flight apenas na memória da extensão.

**Tech Stack:** MV3 JavaScript, Node node:test, Python 3/unittest, API HTTP local autenticada, web JS.

**Spec:** `docs/superpowers/specs/2026-10-20-atos-tce-mesa-extensao-json-portal-lab-design.md` §§7–8; Master `docs/superpowers/plans/2026-10-20-atos-tce-master.md`. Depende de F0–F1.

## Global Constraints
- Acompanhamento somente quando **FORM aberto e visível**, não LIST/INTERESTED; last-used portal tab preservado quando foco vai para a Mesa.
- Identidade exata deve incorporar processo, interessado, ato quando disponível, frame, tab, nonce, generation; ambiguity ou stale = fail-closed.
- Mesa é observadora, não fonte de valores para registro existente no JSON. Lookup somente para processo/interessado ausente.
- Eventos de fill leves não persistem; não armazenar valores de campos na telemetria.
- Mesa segue automaticamente inclusive durante edição (que será salva em draft na F3); sem pause que viole decisão 1.
- Não automatizar conclusão nem login. RED/GREEN + review independente e gates Reliability Reset.

## Review Focus
1. Alternar de portal para Mesa não invalida formulário real nem escolhe outra aba profissional (T1).
2. Dois frames candidatos visíveis não podem ser desambiguados pelo primeiro da enumeração (T1).
3. Resposta de lookup chega depois de outro formulário ser selecionado: deve ser descartada (T4).
4. JSON parcial não aciona lookup sob qualquer estado da conexão (T4).
5. Observação expirada mantém a ficha mas sinaliza suspensão; PDF não participa do caminho rápido (T5).

---

### Task F2-T1: Última aba profissional e filtro de frames

**Files:** Create `extension/background/active-portal-tab.js`, `extension/tests/active-portal-tab.test.mjs`; Modify `extension/background/router.js`.

**Interfaces:** `choosePortalTab(tabs, previous, focusEvent) -> {status:'MATCHED'|'SUSPENDED'|'AMBIGUOUS',tabId?,frameRef?}`, que nunca retorna um candidato meramente pelo índice.

- [ ] **Step 1 — RED:** Testes `mesa_focus_retains_last_portal_tab`, `two_visible_candidates_are_ambiguous`, `hidden_old_frame_is_ignored`: `assert.equal(choosePortalTab([a,b],a,mesaFocus).tabId,a.id)`; múltiplos candidatos AMBIGUOUS.
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/active-portal-tab.test.mjs` falha por interface/asserção.
- [ ] **Step 3 — GREEN:** Implementar estado de último foco profissional e observação de frame atual; só `https://novaarearestrita.tce.rn.gov.br` e a aba confirmada são elegíveis. Não confiar na ordem de `chrome.tabs.query`.
- [ ] **Step 4 — Verificar:** Testes focados PASS e `(cd extension && node --test)` PASS; teste de foco em janela diferente.
- [ ] **Step 5 — Commit:** `git add extension/background/active-portal-tab.js extension/background/router.js extension/tests/active-portal-tab.test.mjs && git commit -m "feat: track last active portal form tab safely"`.
- [ ] **Step 6 — Review:** Reviewer avalia múltiplas janelas, perfis e perda de foco; P0/P1 exigem correção e nova rodada.

### Task F2-T2: Evento de observação e fallback periódico

**Files:** Create `extension/lib/form-observation.js`, `extension/tests/form-observation.test.mjs`; Modify `extension/background/router.js` e `extension/content/heartbeat.js`.

**Interfaces:** `observationTransition(previous,next) -> 'UPDATE'|'SUSPEND'|'NOOP'|'DROP_STALE'`; `observationKey({tabId,frameId,processKey,interestedNormalized,documentNonce,generation}) -> string`.

- [ ] **Step 1 — RED:** `duplicate_event_is_noop`, `generation_regression_drops` e `switching_to_mesa_does_not_suspend`: assert.equal(observationTransition(newer,older),"DROP_STALE").
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/form-observation.test.mjs` FAIL.
- [ ] **Step 3 — GREEN:** Disparar observações nas transições significativas; deduplicar; heartbeat apenas recovery e limites de frequência; sem capturar valores dos cinco campos e sem push de cookies.
- [ ] **Step 4 — Verificar:** Focado PASS e `(cd extension && node --test)` PASS, incluindo restart worker e evento repetido.
- [ ] **Step 5 — Commit:** `git add extension/lib/form-observation.js extension/tests/form-observation.test.mjs extension/background/router.js extension/content/heartbeat.js && git commit -m "feat: publish deduplicated portal observations"`.
- [ ] **Step 6 — Review:** Reviewer verifica replay, taxas excessivas, estado transitório/AMBIGUOUS e nenhuma navegação automática.

### Task F2-T3: API autenticada e projeção de observações

**Files:** Modify `app/area_restrita/current_selection.py`, `app/api/server.py`; Create `tests/test_portal_observation_events.py`.

**Interfaces:** `record_portal_observation(session, payload) -> {status,observation_id}` no tracker atual; payload mínimo `observation_id,state,identity,tab_ref,frame_ref,document_nonce,generation`. A rota exata seguirá as convenções autenticadas já existentes no `server.py`, documentada no teste da API.

- [ ] **Step 1 — RED:** `PortalObservationTests.test_authenticated_newer_selection_wins`: enviar evento válido e outro com generation anterior; assert status do evento antigo rejeitado e identity mais recente inalterada; sessão ausente não autoriza update.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_portal_observation_events -v` FAIL.
- [ ] **Step 3 — GREEN:** Implementar inserção idempotente com geração/TTL e revisão de origem e sessão; manter endpoint `/api/v1/portal/current-selection` retrocompatível; não persistir dados dos campos.
- [ ] **Step 4 — Verificar:** Focado PASS; `python -m unittest tests.test_api_server -q` PASS; auditoria de resposta/erro minimizado.
- [ ] **Step 5 — Commit:** `git add app/area_restrita/current_selection.py app/api/server.py tests/test_portal_observation_events.py && git commit -m "feat: accept authenticated current-form observations"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica replay, sessões falsas, TTL e privacidade.

### Task F2-T4: Lookup excepcional oficial e cache single-flight

**Files:** Create `app/area_restrita/exceptional_lookup.py`, `tests/test_exceptional_lookup.py`, `extension/lib/exceptional-lookup.js`, `extension/tests/exceptional-lookup.test.mjs`; Modify `app/api/server.py` e `extension/background/router.js`.

**Interfaces:** `lookup_official_record(store, identity: dict) -> dict | None`, `requestExceptionalLookup(formKey, lookupFn) -> Promise<record | null>`; TTL, timeout/backoff e invalidation por formKey. A chamada somente quando F1-T3 retorna NEEDS_MESA.

- [ ] **Step 1 — RED:** Python `test_never_return_unsaved_draft`, JS `partial_exact_json_must_not_lookup` e `stale_answer_cannot_fill_new_form`: assert.equal(mesaCalls,0) para JSON parcial; depois de invalidar geração, resposta retorna BLOCKED.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_exceptional_lookup -v` e `node --test extension/tests/exceptional-lookup.test.mjs` FAIL.
- [ ] **Step 3 — GREEN:** Adicionar API autenticada que lê dados oficiais apenas, sem rascunhos; cache em memória single-flight por identidade+nonce+generation, com descarte em troca de formulário e sem escrever no JSON.
- [ ] **Step 4 — Verificar:** Dois testes focados PASS; `python -m unittest tests.test_api_server -q` e `(cd extension && node --test)` PASS.
- [ ] **Step 5 — Commit:** `git add app/area_restrita/exceptional_lookup.py app/api/server.py tests/test_exceptional_lookup.py extension/lib/exceptional-lookup.js extension/tests/exceptional-lookup.test.mjs extension/background/router.js && git commit -m "feat: add missing-record only Mesa fallback"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica ausência versus incompletude, falha Mesa offline, identidade alterada e cache sem disco.

### Task F2-T5: Mesa segue e suspende sem perder contexto

**Files:** Modify `app/web/portal-current.js`, `app/web/app.js`, `app/web/tests/portal-current.test.mjs`; Create `app/web/tests/portal-follow-events.test.mjs`.

**Interfaces:** `followAction(...)` sempre seleciona MATCHED recente, sem pause; `portalFollowingView(observation,lastProcessId) -> {selectedId,suspended}`.

- [ ] **Step 1 — RED:** `follow_when_editing`, `expired_observation_keeps_last_selection`, `list_page_not_a_form`: assert.equal(portalFollowingView(expired,7).selectedId,7); assert.equal(portalFollowingView(expired,7).suspended,true).
- [ ] **Step 2 — Observar RED:** `node --test app/web/tests/portal-current.test.mjs app/web/tests/portal-follow-events.test.mjs` FAIL.
- [ ] **Step 3 — GREEN:** Separar seleção e estado de acompanhamento; atualizar ficha primeiro, PDF depois (F3); suportar draft save hook em F3; não selecionar com base em LIST/INTERESTED.
- [ ] **Step 4 — Verificar:** Focados PASS; `node --test app/web/tests/*.test.mjs` PASS; indicadores explicam suspensão.
- [ ] **Step 5 — Commit:** `git add app/web/portal-current.js app/web/app.js app/web/tests/portal-current.test.mjs app/web/tests/portal-follow-events.test.mjs && git commit -m "feat: always follow valid portal form and suspend safely"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica que seleção de formulário não dispara fill ou perda de edição; dependência de hooks drafts F3 identificada e testada quando ligada.

## F2 exit gate
- [ ] Todas as tasks RED/GREEN, commits e revisões independentes aceitos.
- [ ] Mesa desligada: JSON local continua funcional. Mesa indisponível com registro ausente: BLOCKED, sem valores inventados.
- [ ] Eventos mínimos sem dados dos campos; TTL e idempotência testados.
- [ ] Nenhum FORM foi assumido a partir de LIST/INTERESTED; testes completos Python/extension/web verdes.
- [ ] Reliability Reset não foi dispensado; nenhum teste L1/L2 ao vivo sem gate.
