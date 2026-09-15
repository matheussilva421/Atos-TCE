import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const DRIVER_PATH = fileURLToPath(new URL("../../TcePortal.Driver.js", import.meta.url));
const PROCESS_NUMBER = "12345";
const PROCESS_YEAR = 2026;

async function runManifest(processResponse, requestedNumber = PROCESS_NUMBER, requestedYear = PROCESS_YEAR) {
  const calls = [];
  const driver = await readFile(DRIVER_PATH, "utf8");
  try {
    const result = await vm.runInNewContext(`(${driver})(${JSON.stringify({
      operation: "manifest",
      number: requestedNumber,
      year: requestedYear,
    })})`, {
      localStorage: { getItem() { return null; } },
      fetch: async (path) => {
        calls.push(path);
        if (String(path).startsWith("/api/Processo?")) {
          return { ok: true, async json() { return processResponse; } };
        }
        if (String(path).includes("/eventos?")) {
          return { ok: true, async json() { return []; } };
        }
        throw new Error(`endpoint inesperado: ${path}`);
      },
    });
    return { result, calls };
  } catch (error) {
    error.calls = calls;
    throw error;
  }
}

async function captureManifest(processResponse) {
  try {
    return { value: await runManifest(processResponse) };
  } catch (error) {
    return { error };
  }
}

test("rejects a divergent process result before requesting its events", async () => {
  const outcome = await captureManifest([
    { numeroProcesso: "99999", anoProcesso: 2025, idProcesso: "wrong-process-id" },
  ]);

  assert.ok(outcome.error, "manifest deve rejeitar uma resposta sem correspondência exata");
  assert.match(outcome.error.message, /12345\/2026/);
  assert.deepEqual(outcome.error.calls, [
    "/api/Processo?numeroProcesso=12345&anoProcesso=2026",
  ]);
});

test("rejects an exact process result without idProcesso before requesting events", async () => {
  const outcome = await captureManifest([
    { numeroProcesso: PROCESS_NUMBER, anoProcesso: PROCESS_YEAR },
  ]);

  assert.ok(outcome.error, "manifest deve rejeitar processo exato sem idProcesso");
  assert.match(outcome.error.message, /12345\/2026/);
  assert.deepEqual(outcome.error.calls, [
    "/api/Processo?numeroProcesso=12345&anoProcesso=2026",
  ]);
});

test("builds the manifest from the exact process result", async () => {
  const { result, calls } = await runManifest([
    { numeroProcesso: "99999", anoProcesso: 2025, idProcesso: "wrong-process-id" },
    { numeroProcesso: PROCESS_NUMBER, anoProcesso: PROCESS_YEAR, idProcesso: "exact-process-id" },
  ]);

  assert.deepEqual(JSON.parse(JSON.stringify(result.process)), {
    key: "12345/2026",
    id: "exact-process-id",
    number: PROCESS_NUMBER,
    year: PROCESS_YEAR,
  });
  assert.deepEqual(calls, [
    "/api/Processo?numeroProcesso=12345&anoProcesso=2026",
    "/api/Processo/exact-process-id/eventos?sortDesc=false&trazerInativas=true",
  ]);
});
