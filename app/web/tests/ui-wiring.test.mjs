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

test("the Mesa offers to re-pair an extension that lost its storage", () => {
  assert.match(page, /id="reset-pairing"/u);
  assert.match(source, /\/api\/v1\/bridge\/pairing\/reset/u);
  assert.match(source, /addEventListener\("click", resetPairing\)/u);
});

test("a paused acquisition is resumed instead of restarted", () => {
  assert.match(page, /id="resume-acquisition"/u);
  assert.ok(source.includes("/resume"));
  assert.ok(source.includes('addEventListener("click", resumeAcquisition)'));
  assert.ok(source.includes("setResumableJob(jobId)"), "a pausa mostra o retomar");
});

test("the storage panel says whether an external archive is configured", () => {
  assert.ok(source.includes("Arquivo externo"));
  assert.ok(source.includes("archive.external_root"));
});
