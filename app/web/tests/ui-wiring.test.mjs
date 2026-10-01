import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const page = readFileSync(new URL("../index.html", import.meta.url), "utf8");

// The tab buttons re-render the detail from the remembered payload. When
// ``renderDetail`` does not store it, the tabs only repaint the tab bar and the
// documents/history tabs (and therefore the PDF viewer entry point) never open.
test("the detail renderer remembers the payload the tabs re-render from", () => {
  assert.match(source, /state\.detail = process/u, "renderDetail must store the payload");
  assert.match(source, /if \(state\.detail\) renderDetail\(state\.detail\)/u);
});

test("opening another process clears the remembered payload", () => {
  const select = source.slice(source.indexOf("async function selectProcess"));
  const body = select.slice(0, select.indexOf("function debounce"));

  assert.match(body, /state\.detail = null/u);
});

test("the documents tab is where the viewer is opened from", () => {
  assert.match(page, /id="detail-tabs"/u);
  assert.match(page, /data-tab="documentos"/u);
  assert.match(source, /button\.source-link/u);
  assert.match(source, /openDocument\(document\.id/u);
});

test("the Mesa web UI has no manual extension pairing controls", () => {
  assert.doesNotMatch(page, /reset-pairing/u);
  assert.doesNotMatch(page, /renew-pairing/u);
  assert.doesNotMatch(page, /pairing-code/u);
  assert.doesNotMatch(page, /Reparear extensão/u);
  assert.doesNotMatch(source, /bridge\/pairing\/reset/u);
  assert.doesNotMatch(source, /bridge\/pairing\/renew/u);
});

test("session handoff remains independent from extension authentication", () => {
  assert.match(page, /id="handoff-session"/u);
  assert.match(page, /Copiar sessão para outro Chrome/u);
  assert.match(source, /\/api\/v1\/session\/handoff/u);
});

test("a paused acquisition is resumed instead of restarted", () => {
  assert.match(page, /id="resume-acquisition"/u);
  assert.ok(source.includes("/resume"));
  assert.ok(source.includes('addEventListener("click", resumeAcquisition)'));
  assert.ok(source.includes("setResumableJob(jobId)"), "a pausa mostra o retomar");
});

test("a partial fill renders changed, preserved, review counts and manual guidance", () => {
  assert.match(source, /function renderFillSummary\(request\)/u);
  assert.match(source, /Array\.isArray\(summary\.changed\)/u);
  assert.match(source, /Array\.isArray\(summary\.preserved\)/u);
  assert.match(source, /Array\.isArray\(summary\.unresolved\)/u);
  assert.match(source, /countLabel\(changed\.length/u);
  assert.match(source, /countLabel\(preserved\.length/u);
  assert.match(source, /countLabel\(unresolved\.length/u);
  assert.match(source, /Ato preenchido/u);
  assert.match(source, /conclua manualmente no portal/u);
});

test("fill warnings identify the field and the reason", () => {
  assert.match(source, /summary\?\.warnings/u);
  assert.match(source, /FIELD_LABELS\[field\]/u);
  assert.match(source, /fill-warnings/u);
});

test("a sidepanel fill result is rendered when process detail is reopened", () => {
  const detail = source.slice(source.indexOf("function renderDetail(process)"));
  const body = detail.slice(0, detail.indexOf("function archivePanel"));

  assert.match(body, /const fillResult = state\.fillResults\[process\.id\] \|\| process\.latest_fill_request/u);
  assert.match(body, /if \(fillResult\) renderFillSummary\(fillResult\)/u);
});

test("the fill action remains available for PRONTO and PREENCHIDO processes", () => {
  const panel = source.slice(source.indexOf("function fillPanel"));
  const body = panel.slice(0, panel.indexOf("function refreshTabBar"));

  assert.match(body, /FILLABLE_STATUSES\.has\(process\.status\)/u);
  assert.doesNotMatch(body, /request\.(?:state|error)/u);
});

test("a terminal fill refreshes both the process list and selected detail", () => {
  const fill = source.slice(source.indexOf("async function startFill"));
  const body = fill.slice(0, fill.indexOf("const state ="));

  assert.match(body, /await refreshProcesses\(\);[\s\S]*await selectProcess\(processId\)/u);
});

test("the Mesa does not add a submit, send or finalize action", () => {
  assert.doesNotMatch(page, /id="(?:submit|send|finalize|complement-act)[^"]*"/iu);
  assert.doesNotMatch(source, /AUTO_SUBMIT|COMPLEMENT_ACT|FINALIZE|\/api\/v1\/[^"`]*(?:submit|send|finalize)/iu);
});

test("a reload restores the active acquisition job from the Mesa", () => {
  assert.match(source, /plan\.active_job/u);
  assert.match(source, /active_job\.status/u);
  assert.match(source, /setResumableJob\(active_job\.id\)/u);
});

test("the storage panel says whether an external archive is configured", () => {
  assert.ok(source.includes("Arquivo externo"));
  assert.ok(source.includes("archive.external_root"));
});

test("area counters are cleared while a new analysis is in progress", () => {
  assert.match(source, /function clearAreaCounters\(\)/u);
  assert.match(source, /clearAreaCounters\(\);[\s\S]*postJson\("\/api\/v1\/area\/analyze"/u);
  assert.match(source, /placeholder \? "—"/u);
});

test("area analysis allows slow legacy page navigation to finish", () => {
  assert.match(source, /const deadline = Date\.now\(\) \+ 900000/u);
  assert.match(source, /A análise não respondeu em 15 minutos/u);
});

test("acquisition tells the operator to prepare e-Contas before downloading", () => {
  assert.match(source, /Abrindo o e-Contas para login e preparando o download/u);
  assert.match(source, /Faça login no e-Contas, deixe a tela correta e o marcador selecionado/u);
});

test("fill completion renders changed, preserved and review counts", () => {
  assert.match(source, /const changed = Array\.isArray\(summary\.changed\)/u);
  assert.match(source, /const preserved = Array\.isArray\(summary\.preserved\)/u);
  assert.match(source, /const unresolved = Array\.isArray\(summary\.unresolved\)/u);
  assert.match(source, /countLabel\(changed\.length/u);
  assert.match(source, /countLabel\(preserved\.length/u);
  assert.match(source, /countLabel\(unresolved\.length/u);
  assert.ok(source.includes("Confira o formulário e conclua manualmente no portal"));
});

test("fill warnings identify the affected field and its review reason", () => {
  assert.ok(source.includes("summary.unresolved"));
  assert.ok(source.includes("FIELD_LABELS"));
  assert.ok(source.includes("summary.warnings"));
});

test("fillable processes retain the fill action for retry regardless of prior request state", () => {
  const panel = source.slice(source.indexOf("function fillPanel"));
  const body = panel.slice(0, panel.indexOf("function refreshTabBar"));

  assert.match(body, /FILLABLE_STATUSES\.has\(process\.status\)/u);
  assert.doesNotMatch(body, /request\.state|ERRO|BLOQUEADO/u);
});

test("fill summary survives the detail refresh and never adds a submit action", () => {
  assert.match(source, /state\.fillResults\[processId\] = request/u);
  assert.match(source, /state\.fillResults\[process\.id\] \|\| process\.latest_fill_request/u);
  assert.match(source, /function renderFillSummary\(request\)/u);
  assert.doesNotMatch(source + page, /id="(?:submit|send|finalize|complement-act)"/iu);
});

test("the Mesa exposes a disabled next-process action and live status text", () => {
  assert.match(page, /id="next-process"[^>]*disabled/u);
  assert.match(page, /Próximo processo →/u);
  assert.match(page, /id="next-process-status"[^>]*aria-live="polite"/u);
});

test("the Mesa requests by selected process and selects only the confirmed target", () => {
  const start = source.indexOf("async function startNextProcess");
  assert.notEqual(start, -1, "the Mesa owns a dedicated next-process action");
  const end = source.indexOf("\n  function element", start);
  const body = source.slice(start, end === -1 ? undefined : end);

  assert.match(body, /const processId = state\.selectedId/u);
  assert.match(body, /const numericProcessId = Number\(processId\)/u);
  assert.match(body, /postJson\("\/api\/v1\/portal\/next-act",\s*\{\s*process_id: numericProcessId\s*\}\)/u);
  assert.match(body, /end_of_queue/u);
  assert.match(body, /Abrindo próximo…/u);
  assert.match(body, /const commandId = Number\(created\.command_id\)/u);
  assert.match(body, /\/api\/v1\/extension\/commands\/\$\{commandId\}/u);
  assert.match(body, /command\.state === "SUCCEEDED"/u);
  assert.match(body, /const targetProcessId = Number\(created\.target_process_id\)/u);
  assert.match(body, /selectProcess\(targetProcessId\)/u);
  assert.match(body, /Formulário pronto/u);
  assert.doesNotMatch(body, /\/api\/v1\/processes\/[^`]*\/fill/u);
});

test("a coded next-process refusal remains retryable and asks for a fresh analysis", () => {
  const start = source.indexOf("async function startNextProcess");
  const end = source.indexOf("\n  function element", start);
  const body = source.slice(start, end === -1 ? undefined : end);

  assert.ok(source.includes("error.status = response.status"), "postJson preserves the HTTP status");
  assert.ok(source.includes("error.payload = payload"), "postJson preserves the refusal code");
  assert.ok(
    body.includes('error?.status === 409 && error?.payload?.error === "next_act_refused"'),
    "the Mesa recognizes a definitive next-act refusal"
  );
  assert.ok(body.includes("!isDefinitiveRefusal"), "a refusal does not trip the uncertain-result lock");
  assert.ok(body.includes("Atualize a Área Restrita e tente novamente"), "the operator gets a retry instruction");
});

test("the Mesa does not offer next-process while the capability is unqualified", () => {
  const start = source.indexOf("function updateNextProcessButton");
  const end = source.indexOf("async function startNextProcess");
  assert.notEqual(start, -1, "the Mesa owns a next-process button updater");
  assert.notEqual(end, -1, "the updater precedes the next-process action");
  const body = source.slice(start, end);

  assert.match(body, /button\.disabled = true/u, "Phase 1 keeps the action disabled");
  assert.doesNotMatch(
    body,
    /!state\.selectedId/u,
    "selecting a process must not enable an unqualified capability"
  );
});

test("the Mesa follows the current portal form and can pause the follow", () => {
  assert.match(page, /data-tab="portal"/u);
  assert.match(page, /id="portal-follow-toggle"/u);
  assert.match(page, /id="portal-follow-status"/u);
  assert.match(page, /Portal atual/u);
  assert.match(source, /state\.followPortal/u);
  assert.match(source, /state\.portalProcessId/u);
  assert.match(source, /function refreshPortalSelection/u);
  assert.match(source, /PORTAL_SELECTION_POLL_MS/u);
  assert.match(source, /portalPollRunning/u);
  assert.match(source, /Acompanhando portal/u);
  assert.match(source, /Pausar acompanhamento/u);
  assert.match(source, /Acompanhamento pausado/u);
  assert.match(source, /Retomar acompanhamento/u);
});

test("the follow polls every second and cannot overlap itself", () => {
  assert.match(source, /PORTAL_SELECTION_POLL_MS,\s*\n?\s*window\.setInterval|setInterval\(refreshPortalSelection/u);
  assert.match(source, /if \(state\.portalPollRunning\) return/u);
  assert.match(source, /state\.portalPollRunning = false/u);
});

test("a manual selection pauses the follow while a portal selection does not", () => {
  const select = source.slice(source.indexOf("async function selectProcess"));
  const body = select.slice(0, select.indexOf("function debounce"));

  assert.match(body, /source = "manual"/u);
  assert.match(body, /state\.followPortal = false/u);
  assert.match(body, /source === "manual"/u);
  assert.match(body, /selectProcess\(decision\.selectProcessId|openTab/u);
});

test("the follow decision comes from the pure helpers, not from inline rules", () => {
  assert.match(source, /import \{[\s\S]*followAction[\s\S]*\} from "\/portal-current\.js"/u);
  assert.match(source, /followAction\(/u);
  assert.match(source, /classifyPortalProcess\(/u);
  assert.match(source, /portalFieldModels\(/u);
});

test("the portal tab reuses the single PDF viewer inside a two-column workspace", () => {
  assert.match(source, /detail-workspace/u);
  assert.match(source, /portal-layout/u);
  assert.match(page, /id="viewer-home"/u);
  assert.equal(
    (page.match(/id="viewer-canvas"/gu) || []).length,
    1,
    "there must never be a second PDF renderer"
  );
  assert.match(source, /function renderPortalCurrent\(process\)/u);
  assert.match(source, /getElementById\("pdf-viewer"\)/u);
});

test("a found field offers copy and evidence, a pending one offers nothing", () => {
  assert.match(source, /navigator\.clipboard\.writeText\(/u);
  assert.match(source, /openFieldEvidence\(process\.id, model\.name\)/u);
  assert.match(source, /Copiar valor/u);
  assert.match(source, /Ver evidência/u);

  const card = source.slice(source.indexOf("function portalFieldCard"));
  const body = card.slice(0, card.indexOf("function renderPortalCurrent"));
  assert.match(body, /model\.verdict === "ENCONTRADO"/u);
  assert.doesNotMatch(body, /PENDENTE[\s\S]{0,200}clipboard/u);
});

test("the current fill uses only the transient selection route", () => {
  const start = source.indexOf("async function startCurrentPortalFill");
  assert.notEqual(start, -1, "the portal tab owns its own fill action");
  const body = source.slice(start, source.indexOf("const state = {", start));

  assert.match(body, /postJson\("\/api\/v1\/portal\/current-selection\/fill",\s*\{\s*\}\)/u);
  assert.doesNotMatch(body, /\/api\/v1\/processes\/[^`]*\/fill/u);
  assert.doesNotMatch(body, /next-act|openAct|OPEN_ACT/u);
  assert.match(body, /followFillRequest\(/u);
  assert.match(source, /Preencher dados encontrados/u);
});

test("both fill entry points share one follow loop", () => {
  assert.match(
    source,
    /async function followFillRequest\(processId, fillRequestId, status\)/u
  );
  const auto = source.slice(
    source.indexOf("async function startFill"),
    source.indexOf("async function startCurrentPortalFill")
  );
  assert.match(auto, /followFillRequest\(processId, created\.fill_request_id/u);
  assert.match(source, /renderFillSummary\(request\)/u);
  assert.match(source, /para revisar/u);
});

test("the current fill button is hidden whenever the observation is not fillable", () => {
  assert.match(source, /currentFillAvailability\(state\.portalObservation, process\.id\)/u);
  assert.match(source, /availability\.available/u);
  assert.match(source, /fillButton\.hidden = true/u);
  assert.match(source, /availability\.message/u);
  assert.match(source, /attrs: \{ type: "button", id: "portal-fill" \}/u);
});
