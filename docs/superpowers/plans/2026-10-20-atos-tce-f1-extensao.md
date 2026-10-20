# Atos-TCE F1 — JSON-First MV3 Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar e utilizar um lote JSON v2 de forma local, atômica e segura para preencher cinco campos mediante clique humano, com a Mesa desligada.

**Architecture:** Bibliotecas JS puras separam validação, armazenamento, resolução exata e planejamento; somente `fill-form.js` escreve no DOM, e o painel apenas inicia essa operação. O fallback excepcional é integrado por F2, não pode ser usado para completar registro parcial.

**Tech Stack:** Chrome/Edge MV3, JavaScript ES modules, Node `node:test`, `chrome.storage.local` e contratos MV3 atuais.

**Spec:** `docs/superpowers/specs/2026-10-20-atos-tce-mesa-extensao-json-portal-lab-design.md` §§6–10. Requer F0.

## Global Constraints
- Só cinco campos graváveis; `fundamento_legal`, `genero` e `tipo_processo` nunca entram no write payload.
- Nenhum submit, assinatura, tramitação ou login automático; operador clica `Preencher campos` e conclui separadamente no portal.
- Lote único ACTIVE; importação v2 validada completamente; lote inválido mantém anterior, importação durante fill fica STAGED.
- Lote é snapshot imutável: alterações da Mesa exigem reexportação e reimportação manuais.
- Sem Mesa, registros presentes no JSON devem continuar funcionais. Sem registro exato e sem Mesa, bloquear — não fabricar valores.
- TDD RED/GREEN + commit independente + fresh reviewer por task; qualificação Reliability Reset preservada.

## Review Focus
1. Reinício do worker durante fill pendente jamais promove lote staged automaticamente (T2).
2. Processo presente e interessado ausente retorna NEEDS_MESA; processo presente + interessado parcial retorna EXACT_JSON (T3).
3. Divergência em campo já preenchido bloqueia todo o plano antes da primeira escrita (T4).
4. Um select com duas opções equivalentes ou valor não cadastrado nunca escolhe por índice (T4/T5).
5. O controle txtFundamentoLegal pode existir como sentinela estrutural sem ser lido para preencher ou escrito (T5).

---

### Task F1-T1: Validação e SHA canônico do lote v2

**Files:** Create `extension/lib/batch-v2.js`, `extension/tests/batch-v2.test.mjs`, `extension/tests/batch-v2-golden.test.mjs`.

**Interfaces:** `validateBatchV2(raw) -> {ok, batch?, errors?}`, `canonicalBatchV2(batch) -> Uint8Array`, `checksumBatchV2(batch) -> Promise<string>`.

- [ ] **Step 1 — RED:** Escrever testes `rejects_v1_and_duplicate_records` e `matches_python_sha256_golden`: assert.equal(validateBatchV2(v1).ok,false); assert.equal(validateBatchV2(duplicate).ok,false); assert.equal(await checksumBatchV2(golden), golden.sha256).
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/batch-v2.test.mjs extension/tests/batch-v2-golden.test.mjs`; funções ausentes ou asserções devem falhar.
- [ ] **Step 3 — GREEN mínimo:** Validar unicidade, tipos, referências, versão, caracteres e limites, sem coerção numérica dos IDs; reproduzir canonicalização F0-T4 com WebCrypto.
- [ ] **Step 4 — Verificar:** Testes focados PASS; `(cd extension && node --test)` PASS; paridade SHA Python/JS registrada no handoff.
- [ ] **Step 5 — Commit:** `git add extension/lib/batch-v2.js extension/tests/batch-v2*.test.mjs && git commit -m "feat: validate immutable JSON batch v2 in MV3"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica SHA, duplicidade, Unicode, casos com zero interessados e rejeição de v1.

### Task F1-T2: Importação atômica, staging e recuperação pós-crash

**Files:** Create `extension/lib/batch-storage.js`, `extension/tests/batch-storage.test.mjs`.

**Interfaces:** `importValidatedBatch(store, raw, fillLease) -> Promise<{state:'ACTIVE'|'STAGED'|'REJECTED'}>`, `reconcileStagedBatch(store, leaseId) -> Promise<object>`.

- [ ] **Step 1 — RED:** `invalid_import_preserves_active`, `import_during_fill_is_staged`, `worker_restart_requires_reconciliation`: assert.equal(outcome.state,"STAGED") durante lease; a leitura do lote ACTIVE antes e depois da reinicialização mantém SHA anterior.
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/batch-storage.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Usar staging, generation, commit pointer e lease explícitos; `chrome.storage.local` não oferece transação multi-key; leitura ativa considera commit pointer consistente, e lease interrompido permanece incerto até reconciliação do formulário.
- [ ] **Step 4 — Verificar:** Focado PASS, `(cd extension && node --test)` PASS; simular falha após gravar staged e antes do switch.
- [ ] **Step 5 — Commit:** `git add extension/lib/batch-storage.js extension/tests/batch-storage.test.mjs && git commit -m "feat: stage MV3 batch imports atomically"`.
- [ ] **Step 6 — Review:** Fresh reviewer valida estados de crash, corrupção, races entre cliques e limite de armazenamento.

### Task F1-T3: Resolver registro por identidade exata

**Files:** Create `extension/lib/record-resolver.js`, `extension/tests/record-resolver.test.mjs`.

**Interfaces:** `resolveRecord(batch, identity) -> {kind:'EXACT_JSON'|'NEEDS_MESA'|'BLOCKED', record?, reason?}`; não chama endpoint.

- [ ] **Step 1 — RED:** `partial_json_record_never_uses_mesa`: assert.equal(resolveRecord(batchWithPartial,exact).kind,"EXACT_JSON"); `missing_interested_needs_mesa`: assert.equal(resolveRecord(batch,absent).kind,"NEEDS_MESA").
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/record-resolver.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Match processo/interessado como identidade textual composta, recusando homônimos/ambiguidade e decisões por posição. Só ausências elegíveis retornam NEEDS_MESA.
- [ ] **Step 4 — Verificar:** Focado PASS, `(cd extension && node --test)` PASS.
- [ ] **Step 5 — Commit:** `git add extension/lib/record-resolver.js extension/tests/record-resolver.test.mjs && git commit -m "feat: resolve exact JSON interested records"`.
- [ ] **Step 6 — Review:** Reviewer verifica normalização, ambiguidades e que campos incompletos não invocam fallback.

### Task F1-T4: Planejamento seguro antes da escrita

**Files:** Create `extension/lib/fill-plan-v2.js`, `extension/tests/fill-plan-v2.test.mjs`.

**Interfaces:** `buildLocalFillPlan(snapshot, record) -> {state:'READY'|'BLOCKED', fields, missing, preserved, conflicts}`.

- [ ] **Step 1 — RED:** `divergent_existing_field_blocks_entire_operation`: assert.equal(plan.state,"BLOCKED"); assert.deepEqual(plan.fields,{}). `valid_partial_fills_independent_fields`: READY contém só campos presentes e elegíveis.
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/fill-plan-v2.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Comparar cinco campos antes de escrever; equivalência canônica é no-op; qualquer divergência real bloqueia tudo e gera lista side-by-side só no conflito; select usa catálogo atual e nunca ranking arbitrário.
- [ ] **Step 4 — Verificar:** Focado PASS e `(cd extension && node --test)` PASS; testes incluem placeholder, sem select, data malformatada e opção homônima.
- [ ] **Step 5 — Commit:** `git add extension/lib/fill-plan-v2.js extension/tests/fill-plan-v2.test.mjs && git commit -m "feat: block all writes on portal value divergence"`.
- [ ] **Step 6 — Review:** Reviewer adversarial examina zero-write-before-preflight, controle disabled, geração e coerção de data.

### Task F1-T5: Writer com allowlist terminal e readback

**Files:** Modify `extension/content/detect-form.js`, `extension/content/fill-form.js`; Create `extension/tests/five-field-fill.test.mjs`.

**Interfaces:** reader expõe formulário com identity/documentNonce/generation; writer aceita apenas `fill-plan-v2` READY, recusa campos fora da allowlist e reporta changed/preserved/missing/failed com leitura posterior.

- [ ] **Step 1 — RED:** `never_writes_legal_gender_or_classification`, `stale_form_blocks_all_writes`, `partial_failure_rereads_actual_dom`: observar chamados de setter; assert.equal(legalSetterCalls,0); assert.equal(genderSetterCalls,0); erro não finge rollback.
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/five-field-fill.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Aplicar allowlist na última fronteira de escrita, validar nonce/generation em todas as etapas; manter `txtFundamentoLegal` apenas em sentinelas estruturais já comprovadas, sem preenchimento ou preflight obrigatório.
- [ ] **Step 4 — Verificar:** Focado PASS e `(cd extension && node --test)` PASS; `extension/lib/protocol.js` ainda proíbe SUBMIT/SEND/FINALIZE.
- [ ] **Step 5 — Commit:** `git add extension/content/detect-form.js extension/content/fill-form.js extension/tests/five-field-fill.test.mjs && git commit -m "fix: enforce five-field DOM write boundary"`.
- [ ] **Step 6 — Review:** Reviewer verifica writes indiretos, DOM parcial, eventos nativos, frames falsos e nenhuma ação final.

### Task F1-T6: Painel compacto, importação e clique humano

**Files:** Modify `extension/sidepanel/panel.js`, `extension/sidepanel/panel.html`, `extension/background/router.js`; Create `extension/tests/json-first-sidepanel.test.mjs`.

**Interfaces:** botão `Preencher campos` inicia apenas para EXACT_JSON ou fallback validado (F2); importação nunca preenche; status JSON/MESA/BLOCKED explícito.

- [ ] **Step 1 — RED:** `json_record_fills_without_mesa_connection`, `import_does_not_fill`, `needs_mesa_is_blocked_until_f2`: assert.equal(apiCallsToMesa,0) no exato JSON; assert.equal(submitCalls,0).
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/json-first-sidepanel.test.mjs` FAIL.
- [ ] **Step 3 — GREEN mínimo:** Reorganizar sidepanel em painel único com botão principal e controles secundários; rotear por `batch-storage` + `record-resolver` + `fill-plan-v2`; não presumir endpoint novo da Mesa.
- [ ] **Step 4 — Verificar:** Focado PASS, `(cd extension && node --test)` PASS e revisão do protocolo de comandos proibidos; nenhum controle de auto-submit.
- [ ] **Step 5 — Commit:** `git add extension/sidepanel/panel.js extension/sidepanel/panel.html extension/background/router.js extension/tests/json-first-sidepanel.test.mjs && git commit -m "feat: make MV3 panel JSON-first and operator-driven"`.
- [ ] **Step 6 — Review:** Reviewer reproduz Mesa offline, JSON inválido, formulário ausente e alternância rápida de abas.

## F1 exit gate
- [ ] SHA Python/JS golden idêntico e importação atômica demonstrada mesmo com restart.
- [ ] JSON-first com a Mesa desligada; fallback NEEDS_MESA permanece bloqueado até F2.
- [ ] Documentar cada commit, RED/GREEN, reviewer, suítes da extensão e handoff.
- [ ] Reliability Reset ainda governa a ativação em produção; nenhum L3; nenhuma release.
