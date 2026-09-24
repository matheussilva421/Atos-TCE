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

test("the fill action remains available according to PRONTO process status", () => {
  const panel = source.slice(source.indexOf("function fillPanel"));
  const body = panel.slice(0, panel.indexOf("function refreshTabBar"));

  assert.match(body, /process\.status !== "PRONTO"/u);
  assert.doesNotMatch(body, /request\.(?:state|error)/u);
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
  assert.ok(source.includes("summary.changed.length"));
  assert.ok(source.includes("summary.preserved.length"));
  assert.ok(source.includes("summary.unresolved.length"));
  assert.ok(source.includes("Confira o formulário e conclua manualmente no portal"));
});

test("fill warnings identify the affected field and its review reason", () => {
  assert.ok(source.includes("summary.unresolved"));
  assert.ok(source.includes("FIELD_LABELS"));
  assert.ok(source.includes("summary.warnings"));
});

test("a PRONTO process retains the fill action for retry regardless of prior request state", () => {
  const panel = source.slice(source.indexOf("function fillPanel"));
  const body = panel.slice(0, panel.indexOf("function refreshTabBar"));

  assert.match(body, /process\.status !== "PRONTO"/u);
  assert.doesNotMatch(body, /request\.state|ERRO|BLOQUEADO/u);
});

test("fill summary survives the detail refresh and never adds a submit action", () => {
  assert.ok(source.includes("renderFillStatus(refreshedStatus, lastRequest)"));
  assert.ok(source.includes("function renderFillSummary"));
  assert.doesNotMatch(source + page, /id="(?:submit|send|finalize|complement-act)"/iu);
});
