# Homologação 2.0 — tentativa real no Chrome QA

Data: 06/11/2026
Ambiente: Chrome QA isolado, build de homologação com salvamento habilitado
Perfil: QA dedicado; Chrome profissional não tocado
Autorização do operador: até 5 processos examinados

## Configuração usada

- Build QA: `work/qa-save-build-2026-11-05`, background SHA-256 `C69E92C062FE810F3C98F63CF8FDCCAC6F21FC2BE60C5F5EB23537B2A832CBDB`.
- Flags verificados no bundle: `BATCH_EXECUTION_ENABLED=true`, `BATCH_SAVE_ENABLED=true`, `BATCH_FILL_ONLY=false`.
- Filtros do operador: **Mutirão - Educação**; **ATO COMPLEMENTADO = Não**; **ProcessosNoSetor=true**; **semDistribuicao=true**.
- Página atual: 10 pendentes, 0 concluídos, 0 sem status no momento da captura.

## Execução 1 — 1 examinado / 1 salvo

| Item | Resultado |
| --- | --- |
| Processos examinados | 1 |
| Interessados | múltiplos |
| Preenchidos | 0 |
| Salvos | 0 |
| Estado final | `COMPLETED` |
| Motivo | `MULTIPLE_INTERESTED` |

O processo foi corretamente ignorado. Nenhum clique em “Complementar ato”.

## Execução 2 — 5 examinados / 5 salvos

A fila foi recapturada da página; o primeiro item é o mesmo da execução 1. Para contabilidade: **5 processos distintos** no total, **6 eventos `BEGIN_PROCESS`** (uma repetição de captura), sem ultrapassar os 5 processos autorizados em termos distintos.

| Item | Resultado |
| --- | --- |
| Capturados | 10 |
| Examinados | 5 |
| Múltiplos interessados | 4 |
| Documento não encontrado | 1 |
| Preenchidos | 0 |
| Salvos | 0 |
| Confirmados | 0 |
| Estado final | `COMPLETED` |
| Fila restante | 5 `QUEUED` |

Motivos sanitizados do diário:

- 4 × `MULTIPLE_INTERESTED`.
- 1 × `DOCUMENT_NOT_FOUND`, com campos ausentes `matricula` e `dataNascimento`.

O evento `SAVE_ARMED`, `SAVE_ACK` e `SAVE_UNCERTAIN` não apareceram. Não houve tentativa de salvamento.

## Validação independente

- Nenhum botão “Complementar ato” foi acionado pelo lote.
- O diário confirma `counters.saved = 0` e nenhum `saveAttemptId`.
- Não houve alteração de ato; a fila restante permaneceu intocada.
- A execução parou pelo limite autorizado, não por falha do motor.

## Testes e artefatos

- `node --test tests/unit/*.test.mjs`: **323 PASS**.
- `npm run test:browser`: **24 PASS** em um ciclo.
- `npm run build` / `build:test`: PASS.
- Candidato seguro 0.1.1: `release/Complementador-eContas-0.1.1-batch-safe.zip`, 645.040 bytes, SHA-256 `D820E4A9E32FB66F99C27D5B8B2E777E65E901153BC9076DE05EE154A8319E0C`.

## Veredito

`H2_ADAPTER_BLOCKED_NO_ELIGIBLE_PROCESS` · `H3_NOT_RUN` · `RELEASE_2.0_NOT_READY`

Não foi possível provar o primeiro salvamento automático dentro dos 5 processos autorizados: nenhum dos cinco tinha um único interessado elegível. Não há base para promover a versão 2.0.0 nem para declarar `RELEASE_2.0_READY`.

## Próximo passo

O operador pode autorizar mais 5 processos (limite total de 10 do GOAL) ou selecionar outro marcador/filtro com processos de interessado único. A fila atual tem 5 itens restantes, mas eles não podem ser tocados sem nova autorização. Se a próxima tentativa também não tiver ato elegível, o gate permanece bloqueado por ausência de processo apto, não por falha de código.
