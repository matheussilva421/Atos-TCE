import test from "node:test";
import assert from "node:assert/strict";

import { createSerialQueue } from "../sidepanel/operation-queue.js";

test("a new pairing waits for stale-token cleanup to finish", async () => {
  const queue = createSerialQueue();
  const events = [];
  let releaseCleanup;
  const cleanupPaused = new Promise((resolve) => {
    releaseCleanup = resolve;
  });

  const cleanup = queue.run(async () => {
    events.push("cleanup-start");
    await cleanupPaused;
    events.push("cleanup-end");
  });
  const pairing = queue.run(async () => {
    events.push("pairing");
  });

  await Promise.resolve();
  assert.deepEqual(events, ["cleanup-start"]);
  releaseCleanup();
  await Promise.all([cleanup, pairing]);

  assert.deepEqual(events, ["cleanup-start", "cleanup-end", "pairing"]);
});
