/** Pure selection and layout state for the offline review desk. */

export function resolveDocument(documents, documentId) {
  if (!Array.isArray(documents) || typeof documentId !== 'string') return null;
  return documents.find((document) => document && document.id === documentId) ?? null;
}

export function setSelection(state, selection) {
  if (!selection || typeof selection.processKey !== 'string' || typeof selection.interestedNormalized !== 'string') {
    throw new TypeError('selection identity is required');
  }
  return {
    ...state,
    processKey: selection.processKey,
    interestedNormalized: selection.interestedNormalized,
    followPortal: false,
  };
}

export function setFollowPortal(state, enabled) {
  return { ...state, followPortal: enabled === true };
}

export function createReviewApp({ documents = [], initialState = {} } = {}) {
  let state = { followPortal: true, ...initialState };
  return {
    getState: () => ({ ...state }),
    resolveDocument: (documentId) => resolveDocument(documents, documentId),
    setSelection: (selection) => {
      state = setSelection(state, selection);
      return { ...state };
    },
    setFollowPortal: (enabled) => {
      state = setFollowPortal(state, enabled);
      return { ...state };
    },
  };
}

/**
 * Connect the tested state module to the served review document.  The large
 * inline renderer remains the offline fallback, while the local service gets
 * one shared module instance for selection/follow state.
 */
export function installReviewAppModule(documentRef = globalThis.document) {
  if (!documentRef) return null;
  const dataNode = documentRef.getElementById('app-data');
  let data = {};
  try {
    data = JSON.parse(dataNode?.textContent || '{}');
  } catch (_) {
    return null;
  }
  const documents = (Array.isArray(data.processes) ? data.processes : [])
    .flatMap((process) => Array.isArray(process?.all_documents)
      ? process.all_documents
      : (Array.isArray(process?.documents) ? process.documents : []));
  const app = createReviewApp({ documents });
  documentRef.body?.setAttribute('data-review-module', 'review-app');
  if (globalThis.window) globalThis.window.TceReviewApp = app;
  return app;
}

if (typeof document !== 'undefined') {
  const install = () => installReviewAppModule(document);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    install();
  }
}
