import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildFormDocument,
  buildInterestedDocument,
  buildListDocument,
  cell,
  FakeElement,
  greenComplementIcon,
  listRow,
  redComplementIcon,
} from "./fake-dom.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const extensionRoot = join(here, "..");

await import("../lib/area-snapshot.js");
const { scan } = globalThis.TCEAreaSnapshot;

test("a list page exposes scope, marker, page and rows", () => {
  const documentRef = buildListDocument({
    page: "1",
    markerLabel: "PROFESSOR - IPERN - 2 RUBRICAS",
    paginationLabels: [2, 3],
    sourceScope: "sector_finalistic",
    rows: [
      { processKey: "102390/2026", interested: "Pessoa Exemplo" },
      { processKey: "102391/2026", interested: "Outra Pessoa" },
    ],
  });

  const snapshot = scan(documentRef);

  assert.equal(snapshot.role, "list");
  assert.equal(snapshot.source_scope, "sector_finalistic");
  assert.deepEqual(snapshot.marker, {
    label: "PROFESSOR - IPERN - 2 RUBRICAS",
    value: "marker-2",
  });
  assert.equal(snapshot.page, 1);
  assert.equal(snapshot.total_pages, 3);
  assert.equal(snapshot.rows.length, 2);
  assert.equal(snapshot.rows[0].process_key, "102390/2026");
  assert.equal(snapshot.rows[0].interested, "Pessoa Exemplo");
  assert.equal(snapshot.rows[0].interested_normalized, "pessoa exemplo");
  assert.equal(snapshot.rows[0].classification, "PRECISA_COMPLEMENTAR");
  assert.equal(snapshot.rows[0].needs_complement, true);
  assert.equal(snapshot.rows[0].action_observed, "Complementar Ato");
});

test("a completed act becomes ATO_COMPLEMENTADO", () => {
  const documentRef = buildListDocument({
    rows: [{ processKey: "102390/2026", interested: "Pessoa Exemplo", icon: greenComplementIcon() }],
  });

  const row = scan(documentRef).rows[0];

  assert.equal(row.classification, "ATO_COMPLEMENTADO");
  assert.equal(row.needs_complement, false);
  assert.equal(row.action_observed, "Ato Complementado");
});

test("an unknown action becomes AMBIGUO", () => {
  const documentRef = buildListDocument({
    rows: [
      {
        processKey: "102390/2026",
        interested: "Pessoa Exemplo",
        icon: new FakeElement("img", { attrs: { alt: "Detalhes", src: "../images/info.png" } }),
      },
    ],
  });

  const row = scan(documentRef).rows[0];

  assert.equal(row.classification, "AMBIGUO");
  assert.equal(row.needs_complement, false);
  assert.equal(row.action_observed, null);
});

test("rows without a canonical identity are skipped and counted", () => {
  const documentRef = buildListDocument({
    rows: [
      { processKey: "102390/2026", interested: "Pessoa Exemplo" },
      { processKey: "103401/2023", interested: "" },
    ],
  });

  const snapshot = scan(documentRef);

  assert.equal(snapshot.rows.length, 1);
  assert.equal(snapshot.skipped_rows, 1);
});

test("the portal act id is read from the row when present", () => {
  const documentRef = buildListDocument({
    rows: [{ processKey: "102390/2026", interested: "Pessoa Exemplo", actId: "987654" }],
  });

  assert.equal(scan(documentRef).rows[0].portal_act_id, "987654");
});

test("interested names are normalized exactly like the Python owner", () => {
  const documentRef = buildListDocument({
    rows: [{ processKey: "102390/2026", interested: "  JOSÉ   D'ÁVILA Conceição " }],
  });

  assert.equal(scan(documentRef).rows[0].interested_normalized, "jose d'avila conceicao");
});

test("the scope falls back to the portal URL when no data attribute exists", () => {
  const sector = buildListDocument({ rows: [] });
  sector.defaultView.location.href = "https://novaarearestrita.tce.rn.gov.br/processonosetor.asp";
  assert.equal(scan(sector).source_scope, "sector_finalistic");

  const mine = buildListDocument({ rows: [] });
  mine.defaultView.location.href = "https://novaarearestrita.tce.rn.gov.br/meusprocessos.asp";
  assert.equal(scan(mine).source_scope, "my_processes");

  const unknown = buildListDocument({ rows: [] });
  unknown.defaultView.location.href = "https://example.invalid/home";
  assert.equal(scan(unknown).source_scope, null);
});

test("an unrecognised screen yields no rows and the unknown role", () => {
  const documentRef = buildListDocument({ rows: [] });
  documentRef.body.children = [cell("nada")];

  const snapshot = scan(documentRef);

  assert.equal(snapshot.role, "unknown");
  assert.deepEqual(snapshot.rows, []);
});

test("pagination without numeric labels estimates the total from the next control", () => {
  const withNext = buildListDocument({ page: "1", rows: [], hasNext: true });
  assert.equal(scan(withNext).total_pages, 2);

  const withoutNext = buildListDocument({ page: "1", rows: [], hasNext: false });
  assert.equal(scan(withoutNext).total_pages, 1);
});

test("legacy pagination reads the current page from NumeroPagina", () => {
  const documentRef = buildListDocument({ page: "1", rows: [], hasNext: true });
  const currentPageLink = documentRef.body.children.at(-1).children[0];
  delete currentPageLink.attributes["aria-current"];
  const currentPage = new FakeElement("select", { id: "NumeroPagina", value: "1" });
  documentRef.body.append(currentPage);

  assert.equal(scan(documentRef).page, 1);
  currentPage.value = "2";
  assert.equal(scan(documentRef).page, 2);
});

test("scanning never clicks, submits or mutates the page", () => {
  const row = listRow({ processKey: "102390/2026", interested: "Pessoa Exemplo" });
  const link = row.children[3];
  const documentRef = buildListDocument({ rows: [] });
  documentRef.body.children[0].children[0].append(row);

  scan(documentRef);
  scan(documentRef);

  assert.equal(link.clickCount, 0);
  assert.equal(documentRef.body.children.length, 2);
  assert.equal(documentRef.body.children[0].children.length, 1);
});

test("a form screen and an interested screen report their own role", () => {
  assert.equal(scan(buildFormDocument()).role, "form");
  assert.equal(scan(buildInterestedDocument({ people: ["Pessoa Exemplo"] })).role, "interested");
});

test("the scanner never touches cookies, storage or credentials", () => {
  const sources = ["lib/area-snapshot.js", "content/scan-area.js"].map((relative) =>
    readFileSync(join(extensionRoot, relative), "utf8")
  );

  for (const source of sources) {
    for (const forbidden of [
      "document.cookie",
      "localStorage",
      "sessionStorage",
      "indexedDB",
      "chrome.cookies",
      "password",
      "fetch(",
    ]) {
      assert.equal(source.includes(forbidden), false, `unexpected ${forbidden}`);
    }
  }
});

test("the scanner ignores a document whose storage accessors would throw", () => {
  const documentRef = buildListDocument({
    rows: [{ processKey: "102390/2026", interested: "Pessoa Exemplo" }],
  });
  Object.defineProperty(documentRef, "cookie", {
    get() {
      throw new Error("cookie access is forbidden");
    },
  });

  assert.equal(scan(documentRef).rows.length, 1);
});

test("every module in lib and content is free of credential access", () => {
  const files = [];
  for (const folder of ["lib", "content"]) {
    for (const name of readdirSync(join(extensionRoot, folder))) {
      if (name.endsWith(".js")) files.push(join(extensionRoot, folder, name));
    }
  }
  assert.ok(files.length > 0);
  for (const file of files) {
    const source = readFileSync(file, "utf8");
    assert.equal(source.includes("document.cookie"), false, file);
    assert.equal(source.includes("localStorage"), false, file);
    assert.equal(source.includes("sessionStorage"), false, file);
  }
});

test("old and new complement-icon fixtures stay recognisable", () => {
  const red = redComplementIcon();
  const green = greenComplementIcon();
  assert.match(red.getAttribute("src"), /vermelh/u);
  assert.match(green.getAttribute("alt"), /Ato Complementado/u);

  const row = listRow({ processKey: "1/2026", interested: "Pessoa", icon: red });
  assert.equal(row.children.length, 4);
});
