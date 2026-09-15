# Task 5 — relatório de fechamento QA, documentação e regressão

Data: 15/09/2026
Checkout: `C:\Users\slvma\Downloads\Github\Atos-TCE`
Branch: `main` compartilhada
Base da execução: `499fb34`
Push do código: realizado com sucesso para `https://github.com/matheussilva421/Atos-TCE.git`; `main` e `origin/main` alinhadas em `e899dcb` (`c84bced..e899dcb`).

## Escopo e segurança

Task 5 fechou a documentação e os gates seguros do plano
`docs/notes/2026-09-15-corrigir-achados-qa-plano.md`. Não houve login, rede
portal, envio, tramitação, lote real ou execução em `Versions/`. O pacote de
referência permaneceu byte a byte fora do diff Git.

## Causa confirmada e correção

O Task 1 tornou `process_list.py` e `register_process_list.py` módulos
autoritativos do pacote. O auditor valida esses quatro módulos quando a árvore
possui `app/`. Os fixtures de `package_complete_archive.py` ainda criavam
árvores com apenas `extension_exporter.py` e `package_complete_archive.py`,
causando `app_file_missing` antes de qualquer ZIP ser produzido.

Arquivos Task 5 alterados:

- `work/tce-extractor/test_package_complete_archive.py`
  - fixture agora contém os dois módulos autoritativos;
  - teste do ZIP verifica explicitamente ambos os membros.
- `work/tce-extractor/test_portable_end_to_end.py`
  - fixture end-to-end copia os dois módulos do runtime-fonte para `app/`.

Essas alterações são somente de teste/fixture. Não alteram produção,
auditoria, allowlists, conteúdo privado ou regras de segurança.

## TDD e regressão confirmada

RED antes do ajuste dos fixtures:

```text
python -m unittest test_package_complete_archive.CompleteArchivePackageTests.test_private_zip_audits_filtered_inventory_and_omits_extension_tests -v
1 teste executado, 1 erro
causa: auditoria private reprovada por app/process_list.py e app/register_process_list.py ausentes
```

GREEN após o ajuste mínimo:

```text
python -m unittest test_package_complete_archive.CompleteArchivePackageTests.test_private_zip_audits_filtered_inventory_and_omits_extension_tests -v
1 executado, 1 aprovado, 0 falhas
```

Regressão selecionada após GREEN:

```text
python -m unittest test_area_restrita_analysis test_materialize_area_analysis test_local_service test_package_audit test_extension_zip_packager test_package_complete_archive test_prepare_transfer -q
118 executados, 115 aprovados, 0 falhas, 3 ignorados
```

O primeiro passe dessa regressão, antes do ajuste, teve `18 erros/118`, todos
com a mesma causa de fixture/auditoria. Não há defeito de produção reproduzido
nesta rodada.

## Gates seguros obtidos

| Gate | Comando | Resultado | Classificação/limite |
|---|---|---:|---|
| Python selecionado | `python -m unittest ...` | 118 exec., 115 pass, 0 fail, 3 skip | verde selecionado |
| Python `portable` | `python -m unittest discover -s portable -p 'test_*.py' -q` | 6/6 | parcial; não é a suíte completa |
| Python completo | `python -m unittest discover -s . -p 'test_*.py' -q` | interrompido após ~8 s | `NOT_TESTED` nesta tentativa; não promover |
| Extensão Node | `npm test` | 389/389 | `PASS_FIXTURE` |
| Web package | `npm test` | 6/6 | `PASS_FIXTURE` |
| PowerShell portátil | `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\tests\Test-TcePortable.ps1` | 136/136 | `PASS_FIXTURE` |
| Auditoria pública direta da referência | `python portable\app\package_audit.py ... --distribution public` | interrompida; achados de acervo privado observados | não é PASS_PACKAGE público |
| Empacotamento físico | `empacotar-coletor-portatil.ps1` | não executado | `BLOCKED`: falta `staging-task5-verified`/runtime verificado |
| `git diff --check` | executado no fechamento | verde | sem whitespace error |

Os gates de navegador externo/portal real continuam fora desta execução. Não
foram iniciados novos testes após a interrupção solicitada.

## Matriz QA comparativa

Matriz sanitizada por função, preservando o relatório inicial e sem promover
fixture/static a portal real:

| Estado | QA inicial 14/09 | QA final 14/09 | Fechamento Task 5 |
|---|---:|---:|---:|
| `PASS_REAL` | 0 | 0 | 0 |
| `PASS_PACKAGE` | 3 | 1 | 1 |
| `PASS_FIXTURE` | 2 | 24 | 24 |
| `FAIL_REPRODUCED` | 0 | 0 | 0 |
| `BLOCKED` | 5 | 5 | 5 |
| `NOT_TESTED` | 20 | 0 | 0 |
| Total | 30 | 30 | 30 |

O fechamento Task 5 não reclassifica a matriz final: a correção dos fixtures
fecha a regressão local de empacotamento, mas não cria evidência de portal real.
Os cinco gates `BLOCKED` continuam sendo `portal.observation`,
`portal.marker`, `portal.form`, `portal.reversible-fill` e `portal.send-gate`.

## Referência, validação manual e privacidade

- Referência: `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`.
- Hash de árvore registrado pela QA anterior: `aa847c5173ba0bfee0a9b75ee0b0374eabddca8036c707f4f11406ca2a9478cf`.
- Checagem Git realizada antes do fechamento: `git diff --quiet HEAD -- Versions` passou e `git status --porcelain -- Versions` retornou zero entradas.
- Validação manual anterior: Chromium QA em modo `observe_only`, 83 eventos
  estruturais, zero `submit_attempt`; sessão permaneceu `BLOCKED` por falhas de
  rede/console e não promoveu `PASS_REAL`.
- Limites preservados: sem perfil pessoal, cookies, tokens, PII, HAR,
  screenshots ou traces no Git; `auto_submit=false` e envio/finalização manuais.

## GitHub e retomada

- Antes do histórico publicado: `main` estava `ahead 10` de `origin/main`; remoto
  observado em `c84bced`.
- Conteúdo Task 5: `74646b6`; documentação: `7062766`, `8d3716d` e `c5dff4a`;
  correção P1: `e899dcb` (`fix: block conflicting identity preparation`).
- Push realizado com sucesso para `https://github.com/matheussilva421/Atos-TCE.git`,
  no intervalo `c84bced..e899dcb`.
- Para retomar: conferir `git status`, repetir a suíte Python completa com um
  timeout externo controlado se necessário, e só depois considerar o audit/
  empacotamento quando `staging-task5-verified` existir. Não alterar `Versions`
  nem iniciar gates de portal sem autorização e sessão humana isolada.

## Verificação final desta retomada (15/09)

- Estado Git antes da correção P1: `main` em `c5dff4a` (`HEAD`). A verificação
  pós-push confirmou `main` e `origin/main` alinhadas em `e899dcb`.
- Node extensão: `389/389`.
- Web: `6/6`.
- PowerShell `Test-TcePortable`: `136/136`.
- `git diff --check`: verde.
- `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`: sem alterações; referência preservada.
- Python focado: inconcluso/interrompido após warnings HTTP, sem contagem final.
- Esta seção consolida somente resultados já obtidos; a matriz não foi alterada e não foram produzidos novos resultados. Não houve portal/login/envio.

## Verificação pós-push (15/09)

- Remoto: `https://github.com/matheussilva421/Atos-TCE.git`.
- Push realizado com sucesso: `c84bced..e899dcb`.
- `git status --short --branch` foi verificado imediatamente após o push e
  mostrou `main...origin/main` alinhada; `HEAD` e `origin/main` estavam em
  `e899dcb`.
- Esta atualização posterior é somente documental; testes, matriz e código
  publicado não foram alterados.

## Correção P1 — conflito de identidade na execução/preparação (15/09)

Base observada antes deste fix: `c5dff4a` (`HEAD`), após o conteúdo do Task 5
em `74646b6` e as correções documentais em `7062766`, `8d3716d` e `c5dff4a`.

O finding era que `recordAreaObservations()` marcava conflito da mesma tupla
`(processKey, interestedNormalized)`, mas `collectSnapshot()` ainda podia
enfileirar a primeira observação e seguir até `APPLY_FIELDS`. O teste novo
percorre `start()`/preparação e verifica que o conflito não é congelado na fila
nem gera `APPLY_FIELDS`.

A correção mínima fail-closed ficou em `background/automation-controller.js`:
`collectSnapshot()` consulta a observação marcada antes de resolver/enfileirar
e remove uma identidade já enfileirada antes do congelamento. Identidade
ausente, fluxo sem conflito e análise permanecem preservados. Nenhum envio ou
`auto_submit` foi liberado.

TDD e gates desta correção:

```text
RED focado: 1 falha; pending obtido 0, esperado 1
GREEN focado: 1/1
automation-controller: 69/69
Node completo da extensão: 390/390
```

Arquivos desta correção: `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`,
`work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`,
este relatório, o ledger e `docs/notes/2026-09-15-qa-final-handoff.md`.
