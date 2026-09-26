import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

function readOption(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function requireOption(name) {
  const value = readOption(name);
  if (!value) throw new Error(`Missing required option: ${name}`);
  return value;
}

function validateUrl(value) {
  if (value === "about:blank") return value;
  const url = new URL(value);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname))) {
    throw new Error("QA URL must use HTTPS or loopback HTTP.");
  }
  return url.href;
}

async function waitForCdp(port) {
  const endpoint = `http://127.0.0.1:${port}/json/version`;
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(endpoint);
      if (response.ok) {
        const info = await response.json();
        if (typeof info.webSocketDebuggerUrl === "string" && info.webSocketDebuggerUrl.startsWith("ws://127.0.0.1:")) {
          return;
        }
      }
    } catch {
      // Chromium needs a short startup window before its loopback CDP endpoint answers.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error("Chromium did not expose the expected loopback CDP endpoint.");
}

async function main() {
  const extensionRoot = requireOption("--extension-root");
  const profileRoot = requireOption("--profile-root");
  const playwrightEntry = requireOption("--playwright-entry");
  const port = Number(requireOption("--port"));
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("CDP port must be an integer from 1 through 65535.");
  }
  const url = validateUrl(readOption("--url") ?? "about:blank");
  const manifest = JSON.parse(await readFile(join(extensionRoot, "manifest.json"), "utf8"));
  if (manifest.manifest_version !== 3 || !manifest.name || !manifest.version) {
    throw new Error("The QA extension must have a valid Manifest V3 name and version.");
  }

  const { chromium } = await import(pathToFileURL(playwrightEntry).href);
  let context;
  try {
    context = await chromium.launchPersistentContext(profileRoot, {
      channel: "chromium",
      headless: false,
      viewport: null,
      ignoreDefaultArgs: ["--disable-extensions"],
      args: [
        `--disable-extensions-except=${extensionRoot}`,
        `--load-extension=${extensionRoot}`,
        "--remote-debugging-address=127.0.0.1",
        `--remote-debugging-port=${port}`,
        "--no-first-run",
        "--no-default-browser-check",
      ],
    });

    let worker = context.serviceWorkers().find((candidate) => candidate.url().startsWith("chrome-extension://"));
    if (!worker) {
      worker = await context.waitForEvent("serviceworker", {
        timeout: 20_000,
        predicate: (candidate) => candidate.url().startsWith("chrome-extension://"),
      });
    }
    const extensionId = new URL(worker.url()).hostname;
    const loadedManifest = await worker.evaluate(() => chrome.runtime.getManifest());
    if (loadedManifest.name !== manifest.name || loadedManifest.version !== manifest.version) {
      throw new Error("The running extension does not match the selected QA source directory.");
    }

    await waitForCdp(port);
    const page = context.pages()[0] ?? await context.newPage();
    if (url !== "about:blank") {
      try {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45_000 });
      } catch {
        console.warn("QA browser opened; the requested page did not finish loading. Check its tab before continuing.");
      }
    }

    console.log(`QA_EXTENSION_READY id=${extensionId} name=${JSON.stringify(loadedManifest.name)} version=${loadedManifest.version}`);
    console.log(`CDP_READY http://127.0.0.1:${port}`);
    console.log(`QA_PROFILE ${profileRoot}`);
    await new Promise((resolve) => context.once("close", resolve));
  } finally {
    if (context) await context.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error(`QA_CHROMIUM_FAILED ${error?.message ?? "unknown error"}`);
  process.exitCode = 1;
});
