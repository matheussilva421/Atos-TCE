# Área Restrita Reliability Reset — Fonte de runtime (source of truth)

Data: 2026-09-30
Branch: `codex/area-restrita-reliability-reset`
HEAD na criação: `47c2e1884023b9325d7f475e34f2621b9bb17009`
Base da reconciliação: `origin/codex/area-restrita-reliability-reset-spec` (`9fa3465`), que já contém `origin/codex/atos-tce-unified` (`397553f`) mais o spec e o plano aprovados.

## Evidência executável (não inferida de handoff antigo)

`START.cmd` (raiz) executa o runtime empacotado, quando presente, e cai para o Python do sistema:

```text
set EMBEDDED=%~dp0runtime\python\python.exe
if exist "%EMBEDDED%" ( "%EMBEDDED%" -m app.main %* ) else ( python -m app.main %* )
```

Ou seja: `START.cmd -> python -m app.main`. O pacote de produção É a árvore raiz.

`packaging/build-portable.ps1` monta o ZIP portátil copiando, a partir da RAÍZ do repositório:

```text
app/                         -> app/
extension/                   -> extension/
START.cmd                    -> START.cmd
README.md                    -> README.md
LEIA-ME-OUTRO-PC.txt         -> LEIA-ME-OUTRO-PC.txt
scripts/scan-area-cdp.ps1    -> scripts/scan-area-cdp.ps1
staging-runtime/runtime      -> runtime/        (runtime fixo, pinado por runtime-manifest.json)
staging-runtime/licenses     -> licenses/
```

e exige, no staging: `app\main.py`, `extension\manifest.json`, `START.cmd`, `README.md`, `LEIA-ME-OUTRO-PC.txt`.

`packaging/verify-package.ps1` valida o mesmo contrato no ZIP portátil. Entre outras checagens, confirma que o `START.cmd` empacotado casa `app\.main`:

```text
if ($launcherText -notmatch 'app\.main') { throw 'START.cmd empacotado não inicia app.main' }
```

## Declaração

```text
Production source for Reliability Reset: root app/, extension/, tests/, packaging/, scripts/
work/tce-extractor: verifier/legacy compatibility tree for this goal unless an executable build input proves otherwise
No dual implementation of the same fix
```

Correções de runtime deste Reliability Reset são feitas em `app/`, `extension/`, `tests/` e `packaging/`. `work/tce-extractor/` permanece apenas como verificador legado (por exemplo `verify-project.ps1`); a mesma correção NÃO é replicada nas duas árvores.

## Baseline pré-mudança (2026-09-30, HEAD `47c2e18`)

```text
python -m unittest discover -s tests -p "test_*.py" -q  -> 677 testes, OK (0 falhas)
npm test --prefix extension                             -> 208/208 pass
node --test app/web/tests/*.test.mjs                     -> 33/33 pass
work\tce-extractor\verify-project.ps1                   -> 1260 executados, 1258 pass, 0 fail, 2 skip
git diff --check                                         -> limpo
```

Baseline verde. Nenhuma Task de runtime começou antes deste gate.

## Reconciliação documental — 2026-10-02

`AGENTS.md` foi alinhado a esta evidência: para o runtime portátil atual e o
Reliability Reset, a fonte de produção é `app/`, `extension/`, `tests/`,
`packaging/` e `scripts/`. `work/tce-extractor/` permanece como árvore legada de
compatibilidade/laboratório e abriga um verificador legado; não é local para
implementar isoladamente uma correção de produção.

Os SHAs e contagens em “Baseline pré-mudança” são registros históricos daquela
execução. O estado operacional vigente, os commits de correção e os gates do
Goal 02-10 estão no handoff
[`2026-09-30-area-restrita-reliability-reset-phase-1-handoff.md`](2026-09-30-area-restrita-reliability-reset-phase-1-handoff.md).

