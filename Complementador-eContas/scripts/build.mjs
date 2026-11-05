import { build } from 'esbuild';
import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

const testMode = process.argv.includes('--test');
const portalOrigin = testMode
  ? (process.env.TEST_PORTAL_ORIGIN || 'http://127.0.0.1:4173')
  : 'https://processos.tce.rn.gov.br';
const pdfOrigin = testMode ? portalOrigin : 'https://novaarearestrita.tce.rn.gov.br';
const outdir = testMode ? 'dist-test' : 'dist';

await rm(outdir, { recursive: true, force: true });
await mkdir(path.join(outdir, 'vendor'), { recursive: true });

const manifest = JSON.parse(await readFile('extension/manifest.json', 'utf8'));
if (testMode) {
  const testUrl = new URL(portalOrigin);
  const testMatch = testUrl.protocol + '//' + testUrl.hostname + '/*';
  manifest.host_permissions = [testMatch];
  for (const script of manifest.content_scripts) {
    script.matches = [testMatch];
  }
  for (const resource of manifest.web_accessible_resources) {
    resource.matches = [testMatch];
  }
}
await writeFile(path.join(outdir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');

const define = {
  __PORTAL_ORIGIN__: JSON.stringify(portalOrigin),
  __PDF_ORIGIN__: JSON.stringify(pdfOrigin),
  __BATCH_EXECUTION__: JSON.stringify(process.env.BATCH_EXECUTION === '1'),
};
const common = {
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: 'chrome110',
  define,
  logLevel: 'silent',
  legalComments: 'none',
  charset: 'utf8',
};

await build({ ...common, entryPoints: ['src/background/index.mjs'], outfile: path.join(outdir, 'background.js') });
await build({ ...common, entryPoints: ['src/form/content.mjs'], outfile: path.join(outdir, 'form-content.js') });
await build({ ...common, entryPoints: ['src/autos/content.mjs'], outfile: path.join(outdir, 'autos-content.js') });
await build({ ...common, entryPoints: ['src/list/content.mjs'], outfile: path.join(outdir, 'list-content.js') });
await cp('node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs', path.join(outdir, 'vendor', 'pdf.worker.mjs'));

const entries = ['background.js', 'form-content.js', 'autos-content.js', 'list-content.js', 'manifest.json'];
for (const entry of entries) {
  const stat = await import('node:fs/promises').then((fs) => fs.stat(path.join(outdir, entry)));
  process.stdout.write(entry + ': ' + stat.size + ' bytes\n');
}
process.stdout.write('build: ' + outdir + '\n');
