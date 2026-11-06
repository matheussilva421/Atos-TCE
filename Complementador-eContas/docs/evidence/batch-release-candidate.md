# Candidato local de release — automação em lote

Data: 05/11/2026
Estado: `LOCAL_CANDIDATE` / `H1_INCOMPLETE` / `SUPERVISED_REAL_SAVE_VERIFIED (4/4)` / `AUTOMATED_SAVE_NOT_RUN` / `G7_PENDING`

Este documento prepara a entrega (T24) sem publicar, instalar em perfil profissional ou declarar homologação. A versão do manifesto permanece 0.1.1.

## Build candidato (dist)

Build gerado nesta data sem `BATCH_EXECUTION` e sem `BATCH_FILL_ONLY` (motor desligado).

| Arquivo | Bytes | SHA-256 |
| --- | --- | --- |
| manifest.json | 1.196 | `08F88EA93CFF23F23EC19A7A4C0DB6F1BC18EC79CAC9D54D55C4698E084E5B35` |
| background.js | 117.340 | `39B7E50868B6B0DEEE6A13A9FFAE3C9C5DF828FDBACE849B3C3C6B35FA675B6C` |
| form-content.js | 54.024 | `59CB52B8CAB83D88E0FCA867DD5AC15D8057BF01B7001538D2299340EC6D61DB` |
| autos-content.js | 984.438 | `EDF133B12EE42C0211B0398E3E9F16912410586BD9DC628FDA74D4BE32275A90` |
| list-content.js | 27.656 | `59D87C1EE022D3F3117FCBCF85AE67C55BDDAE42AC28A7B7A2C85DF587334DA1` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

## Backup e ensaio de rollback

- Backup imutável: `work/batch-baseline-2026-11-05` (59 arquivos de fonte/configuração + 5 do build v0.1.1).
- Inventário `SHA256SUMS.txt`: 64 hashes verificados nesta data, **0 divergências**.
- Restauração: desligar a extensão candidata, apontar para a pasta restaurada do backup e recarregar. Nenhum perfil profissional foi tocado no ensaio.
- Limite conhecido: reverter código não desfaz ato já gravado no e-Contas; reversão institucional segue o procedimento oficial.

## Instalação do candidato (quando autorizada)

1. Gerar/extrair o pacote apenas em diretório local de homologação.
2. Abrir `chrome://extensions`, ativar modo desenvolvedor, carregar a pasta extraída.
3. Confirmar que a versão exibida é 0.1.1 e que o painel aparece apenas na listagem de processos.
4. Manter `BATCH_EXECUTION_ENABLED = false` até a validação do salvamento automático e a autorização de um gate real.

Política institucional pode bloquear extensões não empacotadas; nesse caso, a instalação depende de aprovação interna e não deve ser contornada.

## O que está comprovado

- Preenchimento em lote no Chrome QA: 10 processos examinados, 4 `FILLED`, 6 `REVIEW_REQUIRED` por `MISSING_FIELDS`, 0 salvamentos automáticos.
- Quatro atos salvos de forma supervisionada pelo operador, com uma confirmação cada e verificação independente de 4/4.
- Diálogo real observado: título **Complementar ato**, confirmação **sim, complementar**, cancelamento **NÃO**.
- Filtros persistentes com BUSCAR automático e rota de Autos revalidada no QA.

## O que não está homologado

- Salvamento automático pelo adaptador (nunca executado de ponta a ponta).
- Verificação de resultado pós-salvamento pelo motor (`verify()` ainda devolve `unknown`).
- Recuperação de `SAVE_PENDING` após queda entre o checkpoint e o ACK.
- Suspensão real do service worker e reinício do navegador.
- Isolamento de cache entre dois processos reais e autosave do portal.
- Chrome profissional.
- G7: release com pacote, hashes de instalação/rollback e aceite formal.

`AUTOMATED_SAVE_NOT_RUN`. Este candidato não deve ser tratado como release aprovado.
