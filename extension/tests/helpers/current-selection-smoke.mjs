import { readFileSync } from "node:fs";
import { createApi, STORAGE_KEYS } from "../../lib/api.js";
import { installRouter } from "../../background/router.js";
import { ACT_FIELD_IDS, FakeDocument, FakeElement } from "../fake-dom.mjs";
import { fakeChrome } from "../helpers.mjs";

const argv = process.argv.slice(2);
const fillOnly = argv[0] === "fill";
const [baseUrl, clientId, token, extensionId] = fillOnly ? [] : argv;
if (!fillOnly && ![baseUrl, clientId, token, extensionId].every(Boolean)) {
  throw new Error("usage: current-selection-smoke.mjs BASE CLIENT TOKEN EXTENSION_ID");
}

const contentListeners = [];
// Separate Node invocations stand in for one retained synthetic browser
// document/worker in this fixture; deterministically pin document and publisher
// randomness here, only for this test helper.
Object.defineProperty(globalThis, "crypto", {
  configurable: true,
  value: {
    getRandomValues(bytes) {
      bytes.set(bytes.map((_value, index) => index));
      return bytes;
    },
  },
});
globalThis.chrome = {
  runtime: {
    id: extensionId,
    onMessage: { addListener: (listener) => contentListeners.push(listener) },
  },
};
await import("../../lib/area-snapshot.js");
await import("../../content/detect-form.js");
if (contentListeners.length !== 1) throw new Error("content detector listener was not installed");

function actForm(documentRef, { processKey, interested, hidden = false }) {
  const root = new FakeElement("form", { id: "complementarAtoForm" });
  const [number, year] = processKey.split("/");
  root.append(
    new FakeElement("input", { id: "txtNumeroProcesso", value: number }),
    new FakeElement("input", { id: "txtAnoProcesso", value: year }),
  );
  for (const [name, id] of Object.entries(ACT_FIELD_IDS)) {
    if (name === "modalidade" || name === "fundamento_legal") {
      const select = new FakeElement("select", { id });
      const label = name === "modalidade"
        ? "aposentadoria voluntária"
        : "Art. 6º e art. 7º da Emenda Constitucional 41/2003";
      const option = new FakeElement("option", { value: name === "modalidade" ? "M" : "A", text: label });
      select.append(option);
      root.append(select);
    } else {
      root.append(new FakeElement("input", { id, value: "" }));
    }
  }
  const table = new FakeElement("table", { id: "PessoasAssociadas" });
  const row = new FakeElement("tr");
  const radio = new FakeElement("input", { attrs: { type: "radio" } });
  radio.checked = true;
  radio.setAttribute("data-interested-name", interested);
  row.append(new FakeElement("td", { text: interested }), radio);
  table.append(row);
  root.append(table);

  if (hidden) {
    const wrapper = new FakeElement("div", { attrs: { "aria-hidden": "true" } });
    wrapper.append(root);
    documentRef.body.append(wrapper);
  } else {
    documentRef.body.append(root);
  }
  return root;
}

const documentRef = new FakeDocument({ screen: "form" });
documentRef.defaultView = {
  location: { href: "https://novaarearestrita.tce.rn.gov.br/SISTEMAS/PROCESSO/ComplementarAto.asp" },
  frameElement: null,
  parent: null,
  getComputedStyle: () => ({}),
};
documentRef.defaultView.parent = documentRef.defaultView;
const oldForm = actForm(documentRef, { processKey: "999999/2025", interested: "Pessoa Antiga", hidden: true });
const currentForm = actForm(documentRef, { processKey: "102390/2026", interested: "Pessoa Exemplo" });

if (fillOnly) {
  const payload = JSON.parse(readFileSync(0, "utf8"));
  globalThis.document = documentRef;
  await import("../../content/fill-form.js");
  if (contentListeners.length !== 2) throw new Error("content filler listener was not installed");
  const result = await new Promise((resolve) => {
    contentListeners[1]({ type: "FILL_FORM", payload }, {}, resolve);
  });
  process.stdout.write(JSON.stringify({
    result,
    oldCargo: {
      value: oldForm.querySelector("#txtCargo").value,
      writeCount: oldForm.querySelector("#txtCargo").writeCount,
    },
    currentCargo: {
      value: currentForm.querySelector("#txtCargo").value,
      writeCount: currentForm.querySelector("#txtCargo").writeCount,
    },
  }));
  process.exit(0);
}

const api = createApi({
  baseUrl,
  extensionId,
  storage: {
    async get() {
      return {
        [STORAGE_KEYS.clientId]: clientId,
        [STORAGE_KEYS.token]: token,
        [STORAGE_KEYS.baseUrl]: baseUrl,
      };
    },
    async set() {},
  },
});
const publications = [];
const publish = api.publishCurrentSelection.bind(api);
api.publishCurrentSelection = async (observation) => {
  const result = await publish(observation);
  publications.push({ observation, result });
  return result;
};

const chromeApi = fakeChrome({
  tabs: [{ id: 7, active: true, lastFocusedWindow: true, url: documentRef.defaultView.location.href }],
  frames: { 7: [{ frameId: 0, url: documentRef.defaultView.location.href }] },
  onMessage: (message) => new Promise((resolve) => {
    globalThis.document = documentRef;
    contentListeners[0](message, { tab: { id: 7 }, frameId: 0 }, resolve);
  }),
});
const router = installRouter({ api, chromeApi });
const poll = await router.poll();

process.stdout.write(JSON.stringify({ poll, publications }));
