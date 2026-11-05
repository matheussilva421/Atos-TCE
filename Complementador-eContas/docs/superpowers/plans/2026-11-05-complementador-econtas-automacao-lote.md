# Complementador e-Contas — Batch Automation Implementation Plan

For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

Goal: Acrescentar ao Complementador e-Contas existente uma automação em lote sequencial, com salvamento comprovado, limites estritos, recuperação sem duplicidade e homologação progressiva, preservando o preenchimento individual.

Architecture: Uma única extensão Chrome Manifest V3; service worker coordena execução e checkpoints em chrome.storage.local, content scripts inspecionam/operam o portal e painel compacto na listagem solicita comandos. Cada processo com exatamente um interessado representa um único ato; a fila da página atual é congelada e revalidada continuamente. Operações de salvamento são tratadas como potencialmente irreversíveis: checkpoint pré-clique, tentativa única e reconciliação se incerto.

Tech Stack: JavaScript ESM, Node.js node:test, jsdom, Playwright, esbuild, Chrome MV3 (minimum_chrome_version: 110), APIs chrome.tabs, chrome.runtime, chrome.storage, chrome.alarms apenas se necessário e justificado. Sem servidores, dependências de autenticação, serviço externo nem CI obrigatório.

Spec: docs/superpowers/specs/2026-11-05-complementador-econtas-lote-v0.1.md (aprovada, conteúdo consolidado a partir da conversa). Decisões: D01–D33, corrigidas pela regra final de um ato por processo com interessado único. Reference repository: matheussilva421/Atos-TCE, branch codex/complementador-e-contas, subtree Complementador-eContas/, baseline identificada como v0.1.1.

Status: PLANEJAMENTO APENAS — NÃO AUTORIZADO PARA EXECUÇÃO. Este arquivo foi produzido fora do repositório; seus caminhos são relativos a Complementador-eContas/, exceto docs/superpowers/..., que deverá ser incluído sob essa mesma pasta se o usuário autorizar futura execução. A inspeção prévia da branch confirmou os arquivos citados abaixo, mas não executou testes, não inspecionou o portal autenticado e não verificou que os seletores futuros existem.
Global Constraints
- Sem implementar agora: aprovação da spec permite escrever este plano; execução depende de autorização posterior e específica.
- Sem salvar atos reais durante T00–T21 ou no gate H1: nenhum teste sintético, inspect ou REA/RHEA autoriza o clique real em Complementar ato.
- H2 e H3 exigem autorizações próprias, separadas: H2 para exatamente um salvamento real controlado; H3 para um pequeno lote supervisionado; uso autônomo real exige aceite posterior.
- Um interessado = um ato; mais de um interessado ou cardinalidade incerta = ignorar o processo. Não reintroduzir múltiplos atos por interessado (correção D30–D32).
- Dois limites estritos: máximo de processos efetivamente examinados e máximo de atos confirmados; capturados/pré-excluídos não gastam cota.
- Fila congelada somente da página atual: sem paginação e sem reordenar ao longo do lote; alteração de filtro/marcador suspende.
- Uma extensão, duas abas de trabalho reutilizadas, um processo por vez, um lote ativo por perfil. Aba original da listagem intacta.
- Cinco campos: modalidade, dataDoeEstado, cargo, matricula, dataNascimento; data DOE = data da resolução administrativa por convenção operacional, com anotação da origem.
- Salvamento de resultado incerto: NUNCA repetir clique antes de reconciliação inequívoca; se persistir a dúvida, suspender e pedir intervenção, não presumir falha ou sucesso.
- Sem armazenar informações pessoais extraídas, PDFs ou textos: o diário contém somente IDs indispensáveis, estados, contadores e razões sanitizadas. Não registrar URL assinada, CPF, nome, matrícula, nascimento, cookies, tokens nem payload documental.
- Não alterar main, nem instalar automaticamente no perfil profissional, nem efetuar push, merge ou publicar release sem autorização. Evitar novas branches/PRs ou pipelines desnecessários; usar ramo de trabalho autorizado e commits pequenos após ciclos verdes.
- Preservar modo individual (v0.1.1): o botão individual preenche, não salva; a mudança de comportamento aplica-se ao novo modo de lote.
- Compatibilidade mínima Chrome/Edge 110: se usar chrome.alarms, respeitar os intervalos suportados nas versões declaradas. Não usar keep-alive artificial para contornar o ciclo MV3.
- DOM do e-Contas é uma incógnita até G1: seletores, rotas da listagem, classes de status, diálogo e evidência de save devem ser extraídos do portal real; se ausentes, parada documentada, não inventar comportamento.
Review Focus — testes obrigatórios dos cinco riscos mais prováveis
1. Lista paginada com item oculto/duplicado e filtro alterado → capturar apenas visíveis, deduplicar IDs, excluir concluídos, pausar em filtro diferente. Testes: batch_list_excludes_hidden_and_duplicates, batch_context_change_pauses (T02, T14).
2. Um único interessado versus dois, zero, cartão não carregado ou seleção prévia incorreta → somente selecionar e salvar se cardinalidade real = 1 e identidade estável. Testes: interested_count_not_exactly_one_never_saves, selected_identity_changes_blocks_save (T08, T12).
3. Campo preexistente divergente, modalidade já escolhida, datas em formatos diferentes → bloquear divergentes, comparar semanticamente equivalentes, não sobrescrever e não alterar o modo manual. Testes: batch_existing_conflict_blocks_submit, manual_fill_preserves_existing (T10, T20).
4. Chrome encerra worker/deixa aba após clique e antes do ACK → reconciliar portal, manter SAVE_UNCERTAIN, não emitir segundo clique mesmo após restart/reload. Testes: crash_after_click_without_ack_never_reclicks, uncertain_save_survives_restart (T13, T16, T21).
5. Dois eventos de Iniciar, outra janela, ou limite 1 quando dois processos estão disponíveis → um motor, um salvamento confirmado no máximo, contadores corretos. Testes: double_start_creates_one_batch, max_saved_one_never_submits_second (T06, T17, T19).
0. Evidence and file map (verified vs planned)
Existing files confirmed by read-only GitHub fetch:
- package.json — scripts npm test, npm run test:browser, npm run build, npm run build:test, npm run benchmark; ESM, node:test, jsdom, Playwright, esbuild.
- extension/manifest.json — MV3 v0.1.1, Chrome 110+, storage permission, content scripts on portal, background background.js.
- scripts/build.mjs — bundles src/background/index.mjs, src/form/content.mjs, src/autos/content.mjs.
- src/background/index.mjs — message router/`TransactionManager`, cache de sessão, diagnósticos e PDF fetch.
- src/background/bridge.mjs — runFillTransaction, runDocumentDiagnostic, resolução dos documentos e processo.
- src/shared/protocol.mjs, src/shared/routes.mjs — mensagens, IDs e roteamento de Autos/Formulário.
- src/form/content.mjs, src/form/form-reader.mjs, src/form/form-writer.mjs — botão individual, leitura de formulário e escrita com readback.
- src/autos/content.mjs — descoberta/leitura de eventos e restauração da seleção.
- tests/unit/bridge.test.mjs, README.md — testes do fluxo anterior e restrição atual explícita de nenhum salvamento.
Important discovered constraint: createFillPlan() preserva valores existentes, inclusive divergentes (reason: EXISTING_VALUE), enquanto readForm() exige uma seleção prévia do interessado. O modo de lote terá validação de conflitos e seleção automática próprias, sem trocar o contrato do modo manual.

Files to create (planned; verify against G0 repository tree before execution):
File	Sole responsibility
src/list/list-reader.mjs	Capturar/validar IDs, visibilidade, status e contexto da listagem
src/list/content.mjs	Painel compacto, eventos confiáveis e apresentação de progresso
src/list/list-ui.mjs	Renderização pura de estado/resumo, desacoplada do portal
src/batch/queue.mjs	Limites, fila congelada, exclusão de concluídos e contadores
src/batch/state-machine.mjs	Transições e invariantes lote/processo
src/batch/journal.mjs	Persistência local sanitizada, revisionamento e retenção
src/batch/runner.mjs	Coordenar uma etapa por vez a partir do background
src/batch/workspace.mjs	Criar/reutilizar/verificar abas de trabalho e rotas
src/batch/recovery.mjs	Reconciliação de estado e reinício seguro
src/batch/waits.mjs	Esperas por condição, timeouts e classificador de falhas
src/batch/report.mjs	Sumários sanitizados, classificação de resultados
src/form/interested-selector.mjs	Identificar/selecionar exatamente um interessado
src/form/batch-validation.mjs	Comparar campos preexistentes e verificar pré-save
src/form/save-adapter.mjs	Clique único conhecido, diálogos permitidos e sinalização de resultado
tests/unit/batch-*.test.mjs	Testes unitários granulares com node:test/jsdom
tests/browser/batch-*.spec.mjs	Fluxos integrados sintéticos com Playwright
tests/fixtures/batch/	DOM/PDF sintético, lista, form e diálogos verificados/espelhados
docs/evidence/batch-f0-sanitized.md	Relatório sanitizado da inspeção, bloqueios e evidências
docs/evidence/batch-h1.md, batch-h2.md, batch-h3.md	Registro de gates com evidência verificável


Existing files to modify, narrowly: extension/manifest.json, scripts/build.mjs, src/shared/protocol.mjs, src/shared/routes.mjs, src/background/index.mjs, src/background/bridge.mjs (apenas se integração exigir), src/form/content.mjs, src/form/form-reader.mjs (somente extensões não regressivas), src/autos/content.mjs (apenas fallback D02 comprovadamente necessário), README.md e testes existentes conforme abrangência. Não redistribuir responsabilidades de módulos maduros sem causa demonstrada.
1. Interface contracts (one naming source for all tasks)
Use estes contratos entre as tarefas, em JavaScript ESM (tipos documentados por JSDoc e fixtures; não converter o projeto inteiro para TypeScript):
// list/list-reader.mjs
readVisibleList(document) -> {contextKey, entries:[{processId,processLabel,status:'pending'|'completed'|'unknown'}]}
readListContext(document) -> string | null

// batch/queue.mjs
validateLimits({maxExamined,maxSaved}) -> {maxExamined,maxSaved} | throws
createFrozenBatch({batchId,listTabId,contextKey,entries,limits,startedAt}) -> BatchRecord
nextEligibleProcess(batch) -> {processId,processLabel} | null
hasReachedLimit(batch) -> boolean

// batch/state-machine.mjs
reduceBatch(batch, event) -> BatchRecord | throws InvalidTransition

// batch/journal.mjs
loadBatch(storage) -> Promise<BatchRecord|null>
saveBatch(storage, batch) -> Promise<void>
compactJournal(storage, now, policy) -> Promise<{deleted:number}>

// form/interested-selector.mjs
selectSingleInterested(document, expectedProcessId) -> Promise<{ok:true, interestedKey, interestedCount:1}|{ok:false,code}>

// form/batch-validation.mjs
compareExistingFields(formSnapshot, proposals) -> {ok:boolean,conflicts:string[],unknown:string[]}
validateBatchReady(formSnapshot, processContext) -> {ok:boolean,code?:string}

// form/save-adapter.mjs
inspectSaveUi(document) -> {state:'ready'|'blocked'|'unknown',reason?:string}
clickComplementarAtoOnce(document, expected) -> Promise<{attempted:boolean,result:'ack'|'error'|'unknown',code?:string}>
observeSaveOutcome(document, expected) -> {status:'confirmed'|'not_saved'|'unknown',evidence:string[]}

// batch/recovery.mjs
classifyRecovery(batch, portalObservation) -> {action:'resume'|'pause'|'suspend'|'complete',reason?:string}

// batch/runner.mjs
runOneStep({batchId, dependencies}) -> Promise<{state:string,needsWake:boolean}>

// batch/report.mjs
buildBatchReport(batch) -> {totals,items}
BatchRecord minimal schema: {schemaVersion:1,batchId,revision,listTabId,contextKey,limits:{maxExamined,maxSaved},queue:[{processId,processLabel,status}],cursor,counters:{examined,saved},state,current:{processId,phase,saveAttemptId|null}|null,events:[{processId,code,at}],updatedAt}. Never persist interested name/key/CPF, PDF, field values, raw HTML, raw modal text, signed URLs or authentication material. A stored saveAttemptId is opaque and non-sensitive. status values must follow spec. Form identity exists transiently in messages, not journal.

Serialization invariant: all load → reduce → save mutations must be issued by a single in-service-worker coordinator with a promise-based per-batch lock; the revision detects stale callbacks, but chrome.storage.local is not an atomic CAS database. A new service worker must load and reconcile instead of assuming an old in-memory lock survived. Avoid claims of exactly-once execution across profiles; the only acceptable guarantee is no blind repetition plus portal revalidation.
2. Stage gates — stop conditions, evidence and authorization
Gate	Evidence/acceptance	On failure
G0 — Baseline	Original branch/commit, tests, build, ZIP or folder backup and hash; no mutations in protected branch	Stop: do not implement against unknown baseline
G1 — Read-only recognition	DOM/route/status/context contract sanitizado; no live submit, real-dialog behavior unknown until H2	Stop or keep only synthetic prototype; never guess selectors
G2 — Core TDD	Every affected unit test green, manual mode regression green, build/test bundle coherent	Fix failure within authorized task; no gate promotion
G3 — Synthetic browser E2E	Real browser + fixtures simulate one-click batch/save, limits, concurrency, errors; zero network to institutional save	Stop before any H2 request
G4/H1 — Full synthetic acceptance	CA-01–CA-20 covered by evidence where synthetically demonstrable, restart and pause tests, privacy inspection, 0 real saves	Do not mark REAL_SAVE_VERIFIED
G5/H2 — One real controlled save	Separate explicit human authorization, institutional suitability, one real record and readback proof	Block real saving; record unmet gate, do not synthesize success
G6/H3 — Small supervised real batch	Separate authorization after H2, multiple records, progress verified, no duplicates	Preserve H2 state; do not unleash unsupervised lots
G7 — Release/acceptance	User acceptance, verified build/ZIP checksum, release notes, rollback and backup, no unapproved publish	Remain candidate, don't claim completion


Fallback rule for blocked external gates: complete all safe synthetic/local tasks and present an accurate blocked/conditional state. Never fabricate credentials, simulate a live e-Contas result as real, request token extraction, perform unapproved submission or turn a blocked gate into implicit approval. Conversely, do not block local development merely because H2/H3 are unavailable.
3. Incremental tasks
Each implementation task follows TDD: write named failing test → run RED (failure for the expected missing behavior) → implement minimal change → run GREEN including nearest regression → review diff, capture evidence and commit the scoped change. Commands below are run from Complementador-eContas/; no commands in this document have been run.

T00 — Establish protected baseline and rollback point (G0)
Files: Verify package.json, extension/manifest.json, README.md; create docs/evidence/batch-baseline.md; do not touch application source.

Interfaces: Consumes approved spec and branch codex/complementador-e-contas; produces immutable baseline SHA, backup path, checksum list, selected execution branch.
- [ ] Step 1 — Inspect: git status --short, git branch --show-current, git rev-parse HEAD, inspect AGENTS.md/local repo instructions, npm ci only if dependencies are absent and installation is authorized. Do not reset unrelated changes.
- [ ] Step 2 — Verify baseline: npm test, npm run test:browser, npm run build; record exact pass/fail, avoid claiming counts from earlier reports as current.
- [ ] Step 3 — Backup: copy original Complementador-eContas/ source/config and built v0.1.1 artifact to approved safe local path, compute SHA-256 and test extraction/restoration of a sample; protect main and existing user profile.
- [ ] Step 4 — Record: docs/evidence/batch-baseline.md with commit, test output, hash, known pending gates; documentation-only commit to authorized work branch, no push.
T01 — Inspect actual list/portal without saving (G1)
Files: Create docs/evidence/batch-f0-sanitized.md; create sanitized fixtures tests/fixtures/batch/list.html, form.html, save-dialog.html only for structures actually observed. No product source required.

Interfaces: Produces exact selectors/attributes for list entries, stable process IDs, status state, context fingerprint, singleton interested card, known save button and observed modal structure. If save result requires a real click, mark it unverified until H2.
- [ ] Step 1 — Observe: with operator-prepared Chrome QA + correct filters, read-only inspect DOM/SPA navigation; REA/RHEA selectively if needed, without downloading/exposing credentials, cookies or document contents.
- [ ] Step 2 — Negative fixtures: create fixtures for hidden rows, duplicate ID, green/red visual indicators, unknown status, 0/1/2 interested, altered marker and blank page. Define expected classification in test descriptions, no code yet.
- [ ] Step 3 — Verify safety: run a read-only smoke via browser, prove zero submit requests or clicks; ensure report and fixtures are anonymized.
- [ ] Step 4 — Gate decision: document each selector with observed evidence and caveats; G1 cannot be marked passed if ID/status/filtro cannot be reliably identified. Documentation-only commit when authorized.
T02 — Read and freeze only visible pending list records
Files: Create src/list/list-reader.mjs; test tests/unit/batch-list-reader.test.mjs; modify src/shared/routes.mjs only to add verified list route recognition.

Interfaces: readVisibleList(document), readListContext(document); returns explicit pending|completed|unknown. Never use color alone, never read other pagination.
- [ ] Step 1 — RED: tests batch_list_excludes_hidden_and_duplicates, completed_and_unknown_are_distinct, only_current_page_is_captured, list_route_requires_verified_pattern, empty_list_fails_closed; assertions: hidden IDs absent, duplicates once, unknown never silently marked pending.
- [ ] Step 2 — Run: node --test tests/unit/batch-list-reader.test.mjs; expected FAIL on unimplemented exports.
- [ ] Step 3 — GREEN: implement selectors from T01 and id validation via existing isValidProcessId; no selector fallback by guessing.
- [ ] Step 4 — Verify/commit: targeted command PASS plus npm test; review that existing parseRoute Autos/Form remain unchanged; scoped commit feat(batch): read visible list safely.
T03 — Limits, queue and terminal accounting
Files: Create src/batch/queue.mjs; test tests/unit/batch-queue.test.mjs.

Interfaces: validateLimits, createFrozenBatch, nextEligibleProcess, hasReachedLimit; BatchRecord follows contract section.
- [ ] Step 1 — RED: tests limit_rejects_zero_negative_fraction_nan, precompleted_not_examined, captured_not_examined_until_started, max_saved_one_never_submits_second, freeze_preserves_initial_order, queue_exhaustion_stops, no_pagination.
- [ ] Step 2 — Run: node --test tests/unit/batch-queue.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: implement pure value objects, dedup, explicit counters and integer guards. No UI or network.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): enforce frozen queue and dual caps.
T04 — Pure lifecycle state machine
Files: Create src/batch/state-machine.mjs; test tests/unit/batch-state-machine.test.mjs.

Interfaces: reduceBatch(batch,event); event types START, BEGIN_PROCESS, ADVANCE_PHASE, SAVE_ARMED, SAVE_ACK, MARK_SKIPPED, MARK_REVIEW, MARK_FAILED, MARK_UNCERTAIN, REQUEST_PAUSE, REQUEST_STOP, PAUSE_SAFE, STOP_SAFE, COMPLETE, SUSPEND, RESUME_AUTHORIZED.
- [ ] Step 1 — RED: tests illegal_transition_rejected, save_uncertain_is_nonterminal_for_reconciliation, only_ack_increments_saved, begin_process_increments_examined_once, pause_request_stops_next_process, confirmed_id_cannot_confirm_twice.
- [ ] Step 2 — Run: node --test tests/unit/batch-state-machine.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: pure reducer with clone, revision increments, counters bounded by limits; never mark unknown as confirmed.
- [ ] Step 4 — Verify/commit: targeted PASS plus npm test; feat(batch): add safe execution state machine.
T05 — Persistent minimal journal and retention
Files: Create src/batch/journal.mjs; test tests/unit/batch-journal.test.mjs.

Interfaces: loadBatch, saveBatch, compactJournal. Use chrome.storage.local only from background; restrict access from content scripts with setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'}) when supported; fallback must not disclose raw journal to page or content scripts.
- [ ] Step 1 — RED: tests journal_survives_service_worker_restart, journal_drops_pdf_and_personal_values, corrupted_checkpoint_suspends, retention_preserves_uncertain_and_interrupted, quota_failure_fails_closed, schema_version_mismatch_suspends.
- [ ] Step 2 — Run: node --test tests/unit/batch-journal.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: schema validation, data minimization/sanitization and explicit storage errors; do not store raw error messages from portal.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): persist sanitized checkpoints.
T06 — Single active batch and trusted command protocol
Files: Modify src/shared/protocol.mjs, src/background/index.mjs; create tests/unit/batch-protocol.test.mjs.

Interfaces: messages BATCH_PREVIEW, BATCH_START, BATCH_STATUS, BATCH_PAUSE, BATCH_STOP, BATCH_RESUME, BATCH_LIST_SNAPSHOT, BATCH_UI_UPDATE; each mutating command has requestId and checked sender/listTabId. One serialized mutation path in background; avoid changing REQUEST_FILL.
- [ ] Step 1 — RED: tests double_start_creates_one_batch, untrusted_sender_rejected, wrong_list_tab_rejected, stale_batch_revision_rejected, manual_fill_still_works.
- [ ] Step 2 — Run: node --test tests/unit/batch-protocol.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: strict message parsing and sender.tab/route checks, global-in-worker command serialization, durable lock/state; no claim of cross-device lock.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): serialize trusted batch commands.
T07 — Dedicated Autos and Complementar Ato workspace
Files: Create src/batch/workspace.mjs; modify src/background/bridge.mjs only if necessary for explicit source tab selection; test tests/unit/batch-workspace.test.mjs.

Interfaces: openWorkspace({processId, previous, tabsApi}) -> {autosTabId,formTabId}; verifyWorkspace({processId,ids,tabsApi}) -> {ok,code?}; recoverWorkspaceOnce(...) for pre-save only.
- [ ] Step 1 — RED: tests list_tab_never_navigated, workspace_reuses_two_tabs, wrong_process_tab_fails_closed, closed_tab_recovers_once_before_save, no_recreate_after_save_attempt, manual_ambiguous_tab_behavior_preserved.
- [ ] Step 2 — Run: node --test tests/unit/batch-workspace.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: deterministic tab IDs tied to batch, route verification via parseRoute; prevent cross-tab / cross-process reads; no broad tab discovery heuristics.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): reuse isolated process tabs.
T08 — Select and validate exactly one interested person
Files: Create src/form/interested-selector.mjs; integrate minimally into src/form/content.mjs under batch-only message; test tests/unit/batch-interested.test.mjs.

Interfaces: selectSingleInterested(doc, expectedProcessId); returns only interestedKey transiently; existing readForm() untouched for manual workflow.
- [ ] Step 1 — RED: tests interested_count_not_exactly_one_never_saves, one_unselected_card_auto_selected, one_already_selected_no_reclick, selected_identity_changes_blocks_save, wrong_process_blocks_selection, card_not_loaded_is_not_zero_count.
- [ ] Step 2 — Run: node --test tests/unit/batch-interested.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: wait for known card load signal; verify exactly one, select only if needed and readback name/key; never persist personally identifying data.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): select single interested safely.
T09 — Reuse document extraction and targeted fallback
Files: Prefer integration src/background/bridge.mjs and src/autos/content.mjs, only narrow extension proven necessary; create tests/unit/batch-documents.test.mjs.

Interfaces: Existing runFillTransaction remains primary extractor; batch adapter must supply exact form/autos tab IDs and transient interested snapshot; on missing values, inspect further same-process PDFs as D02, with bounded search.
- [ ] Step 1 — RED: tests reuses_resolution_and_guia_discovery, missing_field_searches_other_same_process_document, ambiguous_values_mark_review, cross_process_document_never_used, pdf_cached_ids_not_reused_for_other_process, manual_fill_unchanged.
- [ ] Step 2 — Run: node --test tests/unit/batch-documents.test.mjs; expected FAIL for new behavior.
- [ ] Step 3 — GREEN: preserve proven chooseResolutionCandidate, chooseBirthCandidate and cache isolation; extend only if missing-field fallback is actually unsupported. Avoid repeated PDF scans.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): reuse same-process document extraction.
T10 — Preexisting values and field-level divergence checks
Files: Create src/form/batch-validation.mjs; may add read-only exports to src/form/form-reader.mjs; test tests/unit/batch-validation.test.mjs.

Interfaces: compareExistingFields(formSnapshot, proposals) and validateBatchReady(formSnapshot, processContext); no mutation of createFillPlan() manual policy.
- [ ] Step 1 — RED: tests batch_existing_conflict_blocks_submit, equivalent_normalized_date_is_preserved, existing_modality_mismatch_blocks, missing_expected_value_for_existing_field_routes_to_review, all_five_required, visible_form_error_blocks, wrong_identity_blocks.
- [ ] Step 2 — Run: node --test tests/unit/batch-validation.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: normalize based on known form/catalog conventions, distinguish modalidade from four text fields, no fuzzy guessing; propagate reason codes, no personal values.
- [ ] Step 4 — Verify/commit: targeted PASS, npm test; feat(batch): block divergent and incomplete forms.
T11 — Form readback and exact pre-save context
Files: Modify narrowly src/form/content.mjs; add tests/unit/batch-presave.test.mjs.

Interfaces: background sends BATCH_VALIDATE_FORM with expected process and one interested key; content returns only boolean/normalized reason codes plus necessary transient readback, not sensitive persisted output.
- [ ] Step 1 — RED: tests all_five_present_and_no_visible_errors_pass, readonly_incomplete_blocks, form_revision_changes_blocks, route_changes_blocks, pending_status_changes_blocks, manual_button_still_does_not_save.
- [ ] Step 2 — Run: node --test tests/unit/batch-presave.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: call T10 checks and existing readForm, revalidate interested identity and pending status in portal before arming save.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): revalidate before complementary save.
T12 — Recognize save UI and known confirmation dialogs (synthetic only)
Files: Create src/form/save-adapter.mjs; test tests/unit/batch-save-adapter.test.mjs; add real-approved selector evidence from T01, not invented strings.

Interfaces: inspectSaveUi, clickComplementarAtoOnce, observeSaveOutcome. clickComplementarAtoOnce MUST NOT be called unless T13 has persisted SAVE_PENDING/attempt ID and background has revalidated context. The adapter cannot issue retry on its own.
- [ ] Step 1 — RED: tests known_dialog_can_confirm_once, unknown_dialog_is_not_accepted, save_button_not_found_no_click, second_call_same_attempt_does_not_click, portal_error_is_not_success, different_process_identity_aborts.
- [ ] Step 2 — Run: node --test tests/unit/batch-save-adapter.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: implement only DOM behaviors observed at G1 or synthetic UI explicitly labeled as provisional; prohibit broad heuristics for textual dialogs.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): recognize controlled save dialog.
T13 — Arm, execute once, verify and reconcile potential saving
Files: Create src/batch/recovery.mjs; integrate src/batch/runner.mjs (introduced here, expanded T15–T18); tests tests/unit/batch-saving.test.mjs.

Interfaces: runOneStep, classifyRecovery; write durable SAVE_PENDING + opaque attempt ID before dispatching one click. After click, VERIFYING and only CONFIRMED on evidence tied to correct process/act; if no proof, SAVE_UNCERTAIN and SUSPENDED. No second click based on timeout alone.
- [ ] Step 1 — RED: tests checkpoint_precedes_actual_click, one_ack_counts_once, crash_after_click_without_ack_never_reclicks, green_other_process_does_not_confirm, unknown_timeout_suspends, portal_confirms_existing_save_on_reconcile, no_auto_save_after_unknown.
- [ ] Step 2 — Run: node --test tests/unit/batch-saving.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: wrap adapter behind injectable side-effect boundary; idempotent in-memory dispatch per attempt and durable journal-first transition. If read-only portal cannot prove a successful save after H1, mark H2 validation unresolved instead of weakening proof.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): checkpoint and reconcile save attempts.
T14 — Context drift, session expiration and controlled recovery
Files: Extend src/batch/recovery.mjs; test tests/unit/batch-recovery.test.mjs.

Interfaces: classifyRecovery(batch, portalObservation) distinguishes filter_changed, session_expired, tab_changed, browser_restart, save_uncertain, normal_worker_wake.
- [ ] Step 1 — RED: tests batch_context_change_pauses, session_expired_requires_human_login, relogin_does_not_auto_resume, browser_restart_requires_continue, normal_worker_wake_can_resume_safe_step, uncertain_save_survives_restart, no_wrong_tab_resume.
- [ ] Step 2 — Run: node --test tests/unit/batch-recovery.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: distinguish SW sleep vs full browser restart with durable state/session marker; only user command BATCH_RESUME authorizes interrupted batch; reconcile saved state first.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): reconcile interrupted contexts.
T15 — Condition waits, bounded retry and systemic failure circuit breaker
Files: Create src/batch/waits.mjs; test tests/unit/batch-waits.test.mjs.

Interfaces: waitForCondition(predicate,{timeoutMs,pollMs,signal}) -> Promise<boolean>; classifyFailure(stage,error,history) -> 'retry'|'review'|'pause'|'suspend'; exact retry ceilings calibrated to T01/QA evidence, not guessed for institutional environment.
- [ ] Step 1 — RED: tests condition_satisfied_exits_immediately, bounded_timeout_reports_failure, transient_read_retry_limited, repeated_systemic_failure_pauses, no_retry_for_save_unknown, abort_on_route_change.
- [ ] Step 2 — Run: node --test tests/unit/batch-waits.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: use observable DOM/navigation transitions, bounded timeouts and monotonic event history; no perpetual timers or generic aggressive reloads.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): add bounded wait and failure policy.
T16 — MV3 lifecycle: event reactivation, persistence and minimal watchdog
Files: Modify src/background/index.mjs, extension/manifest.json only if additional Chrome permission is justified; test tests/unit/batch-mv3.test.mjs.

Interfaces: background listeners for message/tab events and reactivation call runOneStep/T14 reconciliation; chrome.alarms may be used as a fallback watchdog only when needed, with 1-minute-or-greater interval compatible with Chrome 110 (Chrome 120 later supports 30 seconds). Avoid keep-alive tricks.
- [ ] Step 1 — RED: tests worker_reactivation_reads_durable_journal, no_duplicate_step_after_two_wake_events, crash_before_save_arms_only_once, crash_after_click_without_ack_never_reclicks, alarm_only_runs_when_batch_active, no_auto_restart_after_browser_restart.
- [ ] Step 2 — Run: node --test tests/unit/batch-mv3.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: event-driven stage runner, journal loaded before action, serialized listeners; add only minimal permission when proven necessary. chrome.storage.local write visibility restricted; no document polling loop that requires SW never stopping.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): survive service worker lifecycle.
T17 — Iniciar/Pausar/Parar/Continuar with safe boundaries
Files: Extend src/batch/runner.mjs, src/background/index.mjs; test tests/unit/batch-controls.test.mjs.

Interfaces: BATCH_START, BATCH_PAUSE, BATCH_STOP, BATCH_RESUME; state machine events from T04; requires requestId, batchId, matching listTabId and expected revision to reject stale operations.
- [ ] Step 1 — RED: tests double_start_creates_one_batch, pause_finishes_current_safe_process, stop_prevents_next_process, saving_in_progress_waits_for_reconciliation, resume_requires_matching_context, cap_reached_during_pause_still_completes.
- [ ] Step 2 — Run: node --test tests/unit/batch-controls.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: never start another process after pause/stop request, unless current already began; no user prompt per process; process-level mutex protects sender events.
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): add safe batch controls.
T18 — Compact panel and list integration
Files: Create src/list/content.mjs, src/list/list-ui.mjs, tests/unit/batch-list-ui.test.mjs; modify scripts/build.mjs, extension/manifest.json to emit/register list-content.js, using existing host permissions only if possible.

Interfaces: list panel sends sanitized BATCH_* commands and renders buildBatchReport/progress; no direct portal save from panel. Ensure content script identity checks and trusted user interaction for initial Start.
- [ ] Step 1 — RED: tests panel_only_visible_on_verified_list, limits_are_positive_integers, start_disabled_without_valid_context, progress_renders_known_states, pause_stop_continue_controls, screen_reader_labels_and_keyboard.
- [ ] Step 2 — Run: node --test tests/unit/batch-list-ui.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: shadow-root compact panel modeled after src/form/content.mjs, no overlay of native list controls; content script only interacts via messages; build emits fourth bundle.
- [ ] Step 4 — Verify/commit: targeted PASS, npm test, npm run build:test; feat(batch): add list control panel.
T19 — Report, reason codes and controlled retention
Files: Create src/batch/report.mjs, tests/unit/batch-report.test.mjs; extend src/batch/journal.mjs retention as necessary.

Interfaces: buildBatchReport(batch) outputs counts/rows {processId,processLabel,status,reasonCode}; links derive only from validated portal route/ID, not arbitrary URLs. Retention excludes active/suspended/uncertain batches.
- [ ] Step 1 — RED: tests report_reconciles_totals, preexcluded_not_examined, uncertain_not_counted_as_saved, reasons_are_sanitized, retention_does_not_delete_pending, no_pii_in_report, links_reject_untrusted_origin.
- [ ] Step 2 — Run: node --test tests/unit/batch-report.test.mjs; expected FAIL.
- [ ] Step 3 — GREEN: deterministic report and cleanup, no persistent copies of extracted documents; no default CSV or full-history dashboard (D18 B).
- [ ] Step 4 — Verify/commit: targeted PASS and npm test; feat(batch): add minimal result report.
T20 — Regression protection for existing individual flow
Files: Test tests/unit/batch-manual-regression.test.mjs; update existing test(s) only for proven compatibility; do not weaken assertions proving manual path never saves.

Interfaces: manual MESSAGE.REQUEST_FILL, runFillTransaction, createFillPlan, readForm, button ⚡ Preencher preserved.
- [ ] Step 1 — RED/guard: write tests manual_fill_preserves_existing, manual_fill_never_clicks_complementar, manual_diagnostic_still_read_only, batch_and_manual_do_not_share_stale_context, manual_untrusted_click_ignored; tests must catch an intentionally injected save regression, not simply pass vacuously.
- [ ] Step 2 — Run: node --test tests/unit/batch-manual-regression.test.mjs; verify new assertions exercise actual code and fail on deliberate regression fixture.
- [ ] Step 3 — GREEN: adjust integration only as needed to preserve 0.1.1 semantics.
- [ ] Step 4 — Verify/commit: npm test, npm run test:browser, npm run build; commit test(batch): lock manual mode regression contract.
T21 — Synthetic Playwright E2E, MV3 crash simulation and H1 gate (G3/G4)
Files: Create tests/browser/batch-flow.spec.mjs, tests/browser/batch-recovery.spec.mjs, fixtures under tests/fixtures/batch/, docs/evidence/batch-h1.md; update browser harness only where necessary.

Interfaces: synthetic portal must simulate list, Autos, form, known/unexpected dialogues, status mutation, filter changes, worker termination, mid-save interruption and independent duplicate triggers. Browser tests use test origin, never processos.tce.rn.gov.br.
- [ ] Step 1 — RED: cases synthetic_3_processes_one_completed_one_multi_interested, synthetic_max_examined_2, synthetic_max_saved_1, synthetic_valid_single_interested_saves, synthetic_existing_conflict_reviews, synthetic_unknown_modal_suspends, synthetic_duplicate_start, synthetic_worker_suspension, synthetic_browser_restart_requires_resume, synthetic_save_uncertain_never_reclicks, synthetic_session_expiry_and_relogin.
- [ ] Step 2 — Run: npm run build:test && npm run test:browser; expected RED for unimplemented cases, and then GREEN after T02–T20 integration.
- [ ] Step 3 — Verify: npm test, npm run test:browser, npm run build, npm run benchmark (record baseline vs candidate; no hard absolute latency claim). Inspect extension permissions, build artifacts, storage for sensitive data and network destinations.
- [ ] Step 4 — Evidence: docs/evidence/batch-h1.md: git SHA, environment, test counts, logs without PII, hash, CA-01–CA-20 synthetic matrix, explicit REAL_SAVE_NOT_TESTED; commit test(batch): verify synthetic H1 gate.
- [ ] Gate: H1 passes only with no failing relevant tests and documented gaps. If unsupported actual portal behavior remains, hold production save feature disabled and mark gate pending rather than inventing confirmations.
T22 — H2: one live save, separately authorized (G5)
Files: Create docs/evidence/batch-h2.md, revise src/form/save-adapter.mjs + tests only if observations justify it. No change of status without evidence.

Interfaces: One process authorized by user and eligible under institutional rules; preflight process/interest/fields/status; one permitted click; portal readback; no secret storage.
- [ ] Step 1 — Approval gate: request explicit authorization for this one real save and confirm target/context. Absence => mark H2 BLOCKED_AWAITING_HUMAN_AUTHORIZATION, do not act.
- [ ] Step 2 — Before: record sanitized process ID and pending state; capture user-approved backup/evidence; confirm no active concurrent lot. Stop on multi interested, ambiguity or form divergence.
- [ ] Step 3 — Perform once: operator-supervised one save with known modal; do not retry after uncertain result.
- [ ] Step 4 — Readback: confirm correct act updated; record SHA/test state/evidence sanitized; if uncertain, H2 FAIL/INCONCLUSIVE and suspend, no repeated click.
- [ ] Step 5 — Gate: user explicitly accepts H2 findings before H3. No claim of H2 PASS from synthetic tests.
T23 — H3: small supervised live batch, separately authorized (G6)
Files: Create docs/evidence/batch-h3.md, limited bugfix/test changes if separately authorized; no broad redesign.

Interfaces: Small user-authorized batch with both caps, one process at a time, per-process confirmation and report; stop on unknown save.
- [ ] Step 1 — Approval gate: confirm H2 accepted and receive new specific authorization with process scope and two limits. No implicit authorization based on H2 approval.
- [ ] Step 2 — Preflight: verify list page, marker/filter, pending IDs, no other batch active; record sanitized pre-state.
- [ ] Step 3 — Run: observe one full multi-process sequence; verify no cross-process data, count only confirmed saves, no duplication or unauthorized navigation.
- [ ] Step 4 — Evaluate: reconcile report with independent e-Contas readback; capture performance, skipped/review items and stop/resume behavior where safe to exercise.
- [ ] Step 5 — Gate: record explicit user acceptance or H3_NOT_ACCEPTED; unattended institutional batches stay disabled until accepted.
T24 — Release preparation, backup, rollback and final handoff (G7)
Files: Update README.md, project version/manifest only following approved release policy, docs/evidence/batch-release.md; produce candidate ZIP in designated local release folder. Do not publish without approval.

Interfaces: release package includes only approved extension bundles + manifest/vendor; audit no credentials, tests/docs traceability, installation instructions, H1/H2/H3 gate states.
- [ ] Step 1 — Regression: npm test, npm run test:browser, npm run build, inspect dist/manifest.json, compare hashes of build/ZIP extracted, preserve version 0.1.1 backup.
- [ ] Step 2 — Review: audit permissions, raw logging, disabled/unavailable H2/H3, original manual mode behavior, CA mapping and changed files; fix only verified issues.
- [ ] Step 3 — Rollback test: on synthetic/test profile, disable candidate, load backed-up 0.1.1, confirm manual fill still functions and no unexpected saves; document that rollback cannot undo an act already committed in e-Contas — that must follow institutional procedure.
- [ ] Step 4 — Deliver: docs/evidence/batch-release.md includes commits, test outputs, failures/limits, hashes, install/rollback, scope, link to spec/plan, status. No auto-update in professional Chrome.
- [ ] Step 5 — Gate: user reviews and accepts. Without H2/H3 approval, state is LOCAL_CODE_COMPLETE / REAL_SAVE_NOT_HOMOLOGATED, never ACCEPTED or READY_FOR_AUTONOMOUS_REAL_BATCH.
4. CA-to-task traceability
Acceptance	Tasks proving it	Minimum gate
CA-01 manual mode	T06, T09, T20, T21	H1
CA-02 only current page	T01, T02, T03, T21	H1
CA-03 exclude already done	T02, T03, T19, T21	H1
CA-04 multi interested ignored	T08, T11, T21	H1
CA-05 single interested selected	T08, T11, T21	H1
CA-06 correct documents	T09, T21	H1
CA-07 five fields	T09, T10, T11, T21	H1
CA-08 existing-field conflict	T10, T20, T21	H1
CA-09 hard dual limits	T03, T04, T17, T21	H1
CA-10 confirmed saves only	T12, T13, T19, T21; T22 verifies real	H1 + H2
CA-11 no blind retry	T12, T13, T16, T21	H1
CA-12 safe pause/stop	T04, T17, T21	H1
CA-13 SW suspension	T05, T14, T16, T21	H1
CA-14 session/relogin	T14, T17, T21	H1
CA-15 bounded waits/retries	T15, T21	H1
CA-16 single batch/profile	T05, T06, T17, T21	H1
CA-17 report/result reasons	T19, T21; T23 validates real	H1 + H3
CA-18 minimal storage	T05, T19, T21	H1
CA-19 real authorization gates	T21–T24	H1–H3
CA-20 consistent resume	T04, T05, T13, T14, T16, T21	H1


5. Final cross-cutting quality gates
- Security: process ID and trusted origin validated at each navigation/operation; no page-generated synthetic click may issue batch start; content scripts never store or expose journal; status readback tied to correct process; H2 and H3 separated.
- Latency: track first/cached/document-heavy runs; no hard performance claim beyond evidence; prefer existing cache and document discovery over repeated calls.
- User experience: panel small, nonintrusive, status meaningful, links correct, pause controls accessible, no repeated questions during an authorized batch.
- Privacy: inspect both chrome.storage.session and chrome.storage.local, console logs, error reports, screenshots and test fixtures for leaked institutional data.
- Development discipline: one independently testable deliverable per task, TDD RED/GREEN, small commits on an authorized branch, evidence before claiming success; no CI, auto-PR, force-push, destructive clean/reset or automatic merge.
- Rollback: return to frozen original extension build and local source commit; switching code versions does not reverse any confirmed operation on the institutional portal.
6. Self-review of this plan
- Spec coverage: every CA-01–CA-20 is mapped in section 4; D01–D33 semantics respected, including explicit D30–D32 correction.
- Interfaces consistency: all files and named functions are mapped in section 1; runOneStep and classifyRecovery are used consistently; no invented list selector is treated as established.
- Review Focus: five top risks each have named tests in owning tasks and at least one browser-level reproduction.
- Unknown real portal UI: G1 and H2 intentionally separate read-only discovery from irreversible action; absence of a verified success signal is a blocker to H2/H3, not an excuse to weaken verification.
- State honesty: this file is a plan; no tasks, tests, commits, real saves, releases or Chrome QA work were performed by preparing it.
7. Execution handoff (future, not authorized now)
Recommended implementation mode: Superpowers subagent-driven-development, with fresh reviewer per small task, followed by whole-branch audit. Because the current user intends a single autonomous Codex Desktop GOAL eventually, execution should respect that GOAL once the user separately approves this plan and authorizes implementation. No automatic branch merge, push, installation or institutional save without explicit permission.

Next user decision: review and approve this Writing Plans document; only then prepare the single, autonomous Codex GOAL referencing this spec, plan, decisions D01–D33 and all gates. GOAL preparation is not GOAL execution.
