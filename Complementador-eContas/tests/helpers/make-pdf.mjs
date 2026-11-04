function escapePdfText(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}

function wrapText(value, width = 80) {
  const words = String(value).split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const word of words) {
    if (line.length === 0) {
      line = word;
    } else if (line.length + 1 + word.length <= width) {
      line += ' ' + word;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line.length > 0) {
    lines.push(line);
  }
  return lines.length > 0 ? lines : [''];
}

export function makePdf(pageTexts) {
  const pages = pageTexts.map((text) => String(text));
  const objects = [];
  const kids = [];
  for (let index = 0; index < pages.length; index += 1) {
    kids.push((4 + index * 2) + ' 0 R');
  }
  objects.push('<< /Type /Catalog /Pages 2 0 R >>');
  objects.push('<< /Type /Pages /Kids [' + kids.join(' ') + '] /Count ' + pages.length + ' >>');
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  for (let index = 0; index < pages.length; index += 1) {
    const contentId = 5 + index * 2;
    objects.push('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents ' + contentId + ' 0 R >>');
    const lines = wrapText(pages[index]);
    const commands = lines.map((line, lineIndex) => (lineIndex === 0 ? '' : 'T* ') + '(' + escapePdfText(line) + ') Tj').join(' ');
    const stream = 'BT /F1 12 Tf 14 TL 72 720 Td ' + commands + ' ET';
    objects.push('<< /Length ' + Buffer.byteLength(stream, 'utf8') + ' >>\nstream\n' + stream + '\nendstream');
  }

  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  for (let index = 0; index < objects.length; index += 1) {
    offsets.push(Buffer.byteLength(pdf, 'utf8'));
    pdf += (index + 1) + ' 0 obj\n' + objects[index] + '\nendobj\n';
  }
  const xrefOffset = Buffer.byteLength(pdf, 'utf8');
  const total = objects.length + 1;
  pdf += 'xref\n0 ' + total + '\n0000000000 65535 f \n';
  for (let index = 1; index < total; index += 1) {
    pdf += String(offsets[index]).padStart(10, '0') + ' 00000 n \n';
  }
  pdf += 'trailer\n<< /Size ' + total + ' /Root 1 0 R >>\nstartxref\n' + xrefOffset + '\n%%EOF\n';
  return new Uint8Array(Buffer.from(pdf, 'utf8'));
}