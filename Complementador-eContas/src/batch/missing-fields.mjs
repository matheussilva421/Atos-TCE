const KNOWN_FIELDS = ['modalidade', 'dataDoeEstado', 'cargo', 'matricula', 'dataNascimento'];
const RESOLUTION_FIELDS = ['modalidade', 'dataDoeEstado', 'cargo', 'matricula'];

function normalizeFields(fields) {
  const source = Array.isArray(fields) ? fields : [];
  const seen = new Set();
  const result = [];
  for (const field of source) {
    if (typeof field !== 'string' || !KNOWN_FIELDS.includes(field) || seen.has(field)) {
      continue;
    }
    seen.add(field);
    result.push(field);
  }
  return result;
}

/**
 * Classifica a causa de um MISSING_FIELDS sem expor valores. Recebe apenas nomes
 * de campos e o diagnóstico sanitizado produzido pela transação documental.
 */
export function classifyMissingFields({ fields = [], diagnostics = {}, errorCode = '' } = {}) {
  const diag = diagnostics && typeof diagnostics === 'object' ? diagnostics : {};
  const status = diag.proposalStatus && typeof diag.proposalStatus === 'object'
    ? diag.proposalStatus
    : {};
  const derived = Object.entries(status)
    .filter(([field, value]) => KNOWN_FIELDS.includes(field) && value !== 'exact')
    .map(([field]) => field);
  const missing = normalizeFields(fields && fields.length > 0 ? fields : derived);
  const code = typeof errorCode === 'string' ? errorCode : '';

  if (code === 'INTERESTED_CHANGED' || code === 'INTERESTED_MISMATCH') {
    return { cause: 'INTERESTED_MISMATCH', fields: missing };
  }
  if (/TIMEOUT/.test(code)) {
    return { cause: 'TIMEOUT', fields: missing };
  }
  const documentCode = typeof diag.documentCode === 'string' ? diag.documentCode : '';
  if (/PDF_NOT_READABLE|DOCUMENT_NOT_READABLE/.test(documentCode)) {
    return { cause: 'PDF_NOT_READABLE', fields: missing };
  }
  if (/UNSUPPORTED_FORMAT/.test(documentCode)) {
    return { cause: 'UNSUPPORTED_FORMAT', fields: missing };
  }
  if (diag.resolutionFound === false && diag.guiaFound === false) {
    return { cause: 'DOCUMENT_NOT_FOUND', fields: missing };
  }
  if (missing.some((field) => status[field] === 'ambiguous')) {
    return { cause: 'AMBIGUOUS_VALUE', fields: missing };
  }
  if (missing.some((field) => RESOLUTION_FIELDS.includes(field)) && diag.resolutionFound === false) {
    return { cause: 'RESOLUTION_NOT_MATCHED', fields: missing };
  }
  if (missing.includes('dataNascimento') && diag.guiaFound === false) {
    return { cause: 'GUIA_NOT_MATCHED', fields: missing };
  }
  if (missing.length > 0) {
    return { cause: 'FIELD_NOT_PRESENT', fields: missing };
  }
  return { cause: 'OTHER', fields: [] };
}
