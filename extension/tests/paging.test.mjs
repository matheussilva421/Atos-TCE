import assert from "node:assert/strict";
import test from "node:test";
import { buildListDocument, FakeElement } from "./fake-dom.mjs";

await import("../lib/area-snapshot.js");

test("LIST_PAGE uses the safe legacy form path instead of clicking javascript links", async () => {
  const documentRef = buildListDocument({ page: "1", rows: [], hasNext: false });
  const form = new FakeElement("form", { id: "form1" });
  form.append(
    new FakeElement("input", { id: "NumeroPagina", value: "1", attrs: { type: "hidden" } }),
    new FakeElement("input", { id: "Paginacao", value: "", attrs: { type: "hidden" } }),
    new FakeElement("input", { id: "GrupoProcesso", value: "", attrs: { type: "hidden" } }),
  );
  let submitted = 0;
  form.submit = () => { submitted += 1; };
  const next = new FakeElement("a", {
    text: "Próxima >",
    attrs: {
      href: "javascript: form1.NumeroPagina.value=2; document.form1.Paginacao.value='S'; document.form1.GrupoProcesso.value='NS'; form1.submit();",
    },
  });
  next.click = () => { throw new Error("CSP blocked javascript URL"); };
  form.append(next);
  documentRef.body.append(form);

  const listeners = [];
  globalThis.chrome = { runtime: { onMessage: { addListener(listener) { listeners.push(listener); } } } };
  globalThis.document = documentRef;
  try {
    await import(`../content/paging.js?legacy-form-test=${Date.now()}`);
    assert.equal(listeners.length, 1);
    const response = await new Promise((resolve) => {
      listeners[0]({ type: "LIST_PAGE", payload: { action: "next" } }, {}, resolve);
    });

    assert.deepEqual(response, { ok: true, changed: true, page_before: 1, page_after: 2 });
    assert.equal(submitted, 1);
  } finally {
    delete globalThis.chrome;
    delete globalThis.document;
  }
});
