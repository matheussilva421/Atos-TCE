# Handoff final QA — Task 5

Data: 15/09/2026
Checkout: `C:\Users\slvma\Downloads\Github\Atos-TCE`
Branch: `main` compartilhada
HEAD-base observado antes da correção P1: `c5dff4a` (`docs: record final Task 5 resumption verification`)
Histórico real: conteúdo Task 5 em `74646b6`; documentação em `7062766`, `8d3716d` e `c5dff4a`.
Push: não realizado

## Resumo

Task 5 fechou a regressão local de empacotamento descoberta após o Task 1 e
registrou a matriz QA final. A causa era de fixture: o auditor passou a exigir
`app/process_list.py` e `app/register_process_list.py`, mas dois fixtures do
empacotador completo não os incluíam. A produção já tinha o contrato correto.

No fechamento original do Task 5 foram alterados somente:

- `work/tce-extractor/test_package_complete_archive.py`;
- `work/tce-extractor/test_portable_end_to_end.py`;
- `.superpowers/sdd/2026-09-15-corrigir-achados-qa-plano/progress.md`;
- `.superpowers/sdd/2026-09-15-corrigir-achados-qa-plano/task-5-report.md`;
- este handoff.

Não houve alteração em `Versions/`, portal, login, envio, tramitação, lote
real, dados privados ou runtime de distribuição.

## Decisões técnicas

- Preservar o auditor fail-closed; não remover a exigência dos módulos.
- Corrigir fixtures para representar o inventário autoritativo real.
- Manter a classificação de portal separada de `PASS_FIXTURE` e
  `PASS_PACKAGE`.
- Não executar novamente o Python completo nem auditorias longas após a
  interrupção solicitada.

## Testes e gates

| Comando/gate | Evidência | Estado |
|---|---|---|
| RED focado de pacote | 1 erro por `app_file_missing` esperado | reproduzido antes da correção |
| GREEN focado de pacote | 1/1 | verde |
| Regressão Python selecionada | 118 exec., 115 pass, 0 fail, 3 skip | verde |
| Python `discover -s portable` | 6/6 | parcial, não suíte completa |
| Python completo | nova tentativa interrompida após ~8 s | inconcluso, `NOT_TESTED` |
| Extensão Node `npm test` | 389/389 | verde |
| Web `npm test` | 6/6 | verde |
| `Test-TcePortable.ps1` | 136/136 | verde |
| Auditoria pública longa da referência | interrompida, achados privados esperados | bloqueada/inconclusa |
| Empacotamento físico | runtime verificado ausente | `BLOCKED` |
| `git diff --check` | sem erros | verde |

Avisos observados na suíte Python foram `ResourceWarning` de fixtures HTTP e
depreciação da API `fitz`; não foram tratados como defeito de produção. O
gate completo não tem contagem final nesta execução e não deve ser reportado
como aprovado.

## Matriz comparativa preservada

| Estado | Inicial | Final anterior | Task 5 |
|---|---:|---:|---:|
| `PASS_REAL` | 0 | 0 | 0 |
| `PASS_PACKAGE` | 3 | 1 | 1 |
| `PASS_FIXTURE` | 2 | 24 | 24 |
| `FAIL_REPRODUCED` | 0 | 0 | 0 |
| `BLOCKED` | 5 | 5 | 5 |
| `NOT_TESTED` | 20 | 0 | 0 |
| Total | 30 | 30 | 30 |

Os cinco casos `BLOCKED` são os gates manuais do portal: observação, marcador,
formulário/preflight, preenchimento reversível e conclusão/envio. Não houve
`PASS_REAL`.

## Referência e validação manual prévia

- Pacote: `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`.
- Hash de árvore QA registrado: `aa847c5173ba0bfee0a9b75ee0b0374eabddca8036c707f4f11406ca2a9478cf`.
- `git diff --quiet HEAD -- Versions`: passou antes do fechamento.
- `git status --porcelain -- Versions`: zero entradas.
- QA manual anterior: Chromium isolado, `observe_only`, 83 eventos, zero
  `submit_attempt`; falhas de rede/console mantiveram `BLOCKED`.
- Nenhum login, credencial digitada, envio, conclusão, tramitação, lote real,
  perfil pessoal ou artefato bruto publicado.

## GitHub e retomada

Antes do commit, `main` estava `ahead 10` de `origin/main`, com remoto em
`c84bced`. O commit deste bloco é `74646b65c6270f0df2821bfe917c4c6359b55611`; não houve push.

Retomada segura:

1. conferir `git status` e o SHA do commit Task 5;
2. se necessário, rodar a suíte Python completa com timeout externo explícito;
3. somente com `staging-task5-verified` disponível, auditar/empacotar em destino
   temporário fora de `Versions`;
4. qualquer QA real exige sessão humana isolada e continua sem envio por padrão.

<oai-mem-citation>
<citation_entries>
MEMORY.md:1-10|note=[QA do pacote TCE exige usar a distribuicao exata e separar gates reais do portal]
MEMORY.md:28-36|note=[limites de QA manual e classificacao PASS_REAL/PASS_FIXTURE/PASS_PACKAGE]
</citation_entries>
<rollout_ids>
</rollout_ids>
</oai-mem-citation>

## Verificação final desta retomada (15/09)

- Estado Git antes da correção P1: `main` em `c5dff4a` (`HEAD`); não houve push.
- Node extensão: `389/389`.
- Web: `6/6`.
- PowerShell `Test-TcePortable`: `136/136`.
- `git diff --check`: verde.
- `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`: sem alterações; referência preservada.
- Python focado: inconcluso/interrompido após warnings HTTP, sem contagem final.
- Esta seção consolida somente resultados já obtidos; a matriz não foi alterada e não foram produzidos novos resultados. Não houve portal/login/envio.

## Correção P1 — conflito de identidade na execução/preparação (15/09)

- Finding reproduzido em `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`: `recordAreaObservations()` marcava conflito da mesma tupla `(processKey, interestedNormalized)`, mas `collectSnapshot()` ainda podia manter a identidade original na fila e levá-la à preparação.
- Correção mínima fail-closed: `collectSnapshot()` bloqueia a chave conflitante antes de resolver/enfileirar e remove uma ocorrência previamente enfileirada antes do congelamento. Fluxos sem conflito e identidade ausente permanecem inalterados; `auto_submit`/envio não foram liberados.
- Teste novo: `blocks a same-tuple area identity conflict before queue freeze and preparation`, percorrendo `start()` até a preparação e verificando fila congelada vazia e zero `APPLY_FIELDS`.
- TDD: RED focado `1 falha` (`pending: 0` em vez de `1`); GREEN focado `1/1`; suíte `automation-controller` `69/69`; Node completo da extensão `390/390`.
- Arquivos deste fix: `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`, `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`, este handoff e o ledger/relatório do Task 5.
- Não houve portal, login, `Versions/`, `auto_submit`, preenchimento real ou envio.
