# Relatório final — Complementador e-Contas

> Atualização 05/11/2026 (pós-F1–F6): os itens 1–6 da seção "O que falta" foram implementados e testados; consulte `batch-final-tests.md`, `batch-final-diagnostics.md`, `batch-final-security.md` e `batch-final-release.md`. O release continua candidato seguro; F7/F8/F9 não foram executados.

Data: 05/11/2026
Branch: `codex/complementador-e-contas`
Versão: 0.1.1
Escopo: extensão Chrome MV3 em `Complementador-eContas/`, no repositório `matheussilva421/Atos-TCE`.

## Veredito

`BATCH_FILL_VERIFIED_REAL` · `SUPERVISED_REAL_SAVE_VERIFIED_4_OF_4` · `AUTOMATED_SAVE_NOT_RUN` · `MV3_ENDURANCE_NOT_RUN` · `PROFESSIONAL_BROWSER_NOT_RUN` · `G7_PENDING`

O preenchimento em lote está funcional e foi exercitado no portal real: 10 processos examinados, 4 preenchidos com os cinco campos e 6 em revisão por campos ausentes, sem nenhum salvamento automático. Os únicos salvamentos reais foram quatro atos confirmados um a um pelo operador, com verificação independente de 4/4. O adaptador automático de salvamento existe e está testado, mas nunca foi executado de ponta a ponta no portal; permanece desligado por padrão.

## 1. Repositório

| Item | Valor |
| --- | --- |
| Caminho local | `C:\Users\slvma\Downloads\Github\Atos-TCE` |
| Subpasta do projeto | `Complementador-eContas/` |
| Branch de trabalho | `codex/complementador-e-contas` |
| HEAD na coleta | `cb10b1a` |
| `main` / `origin/main` | `6e1acd5` (intocadas) |
| Remoto | `https://github.com/matheussilva421/Atos-TCE.git` |
| Árvore | limpa antes deste relatório |

O commit deste relatório é o commit de documentação imediatamente seguinte a `cb10b1a` na mesma branch. Nenhum merge, force-push ou alteração em `main` foi feito.

## 2. O que foi entregue

- Painel compacto na listagem de processos com pré-visualizar, iniciar, pausar, parar, continuar, salvar filtros e restaurar filtros.
- Fila congelada da página atual, sem paginação, com deduplicação, exclusão de já complementados e dois limites independentes (examinados e salvos).
- Máquina de estados do lote e do processo, incluindo `SAVE_PENDING`, `SAVE_NOT_DISPATCHED`, `MARK_FILLED` e recusa de transições ilegais.
- Diário local sanitizado em `chrome.storage.local`, com falha fechada em corrupção, quota e schema; sem PDFs, nomes, CPF, matrícula, nascimento ou URLs assinadas.
- Fluxo por processo com abas dedicadas, verificação de identidade, interessado único, preenchimento, validação e gate de salvamento.
- Descoberta automática de Resolução Administrativa e Guia Financeira/Taxação de Proventos nos cartões de evento, com correlação de nascimento ao interessado e restauração do documento original.
- Filtros persistentes com aplicação e BUSCAR automáticos em sessão nova, sem laço de recarga.
- Modo estruturalmente só-preenchimento (`BATCH_FILL_ONLY=1`), no qual o caminho de salvamento é impossível por construção.
- Adaptador de salvamento com clique único, diálogo desconhecido falhando fechado e aprendizado do diálogo real.
- Build de entrega com o motor desligado (`BATCH_EXECUTION_ENABLED=false`).

## 3. Evidência real no Chrome QA

| Verificação | Resultado |
| --- | --- |
| Listagem e status por classe | PASS — 10 linhas, status lido pela classe, sem paginar |
| Rota de Autos | PASS — `#ifrm`, 54 cartões, content script ativo |
| Filtros salvos + BUSCAR automático | PASS — chips confirmam o marcador do operador |
| Lote 10/1 só-preenchimento | 10 examinados, 4 `FILLED`, 6 `REVIEW_REQUIRED` (`MISSING_FIELDS`), 0 salvos |
| Campos nas 4 abas | PASS — modalidade + quatro campos em todas |
| Salvamento real | 4 atos, uma confirmação por ato, autorização explícita do operador |
| Verificação pós-salvamento | PASS — 4 de 4 sem o botão “Complementar ato” ao reabrir |
| Diálogo real | título **Complementar ato**, confirmação **sim, complementar**, cancelamento **NÃO** |

Os seis processos restantes não foram tocados. Não há dado pessoal nesta evidência; identificadores aparecem apenas de forma sanitizada nos documentos internos.

## 4. Testes e build executados nesta data

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **266 PASS**, 0 FAIL (6,9 s) |
| `npm run test:browser` | **23 PASS**, 0 FAIL (41,7 s, Chromium 1248 headless) |
| `npm run build` | PASS — `dist` gerado com o motor desligado |
| `git diff --check` | PASS (sem alterações pendentes antes deste relatório) |

Build de referência (sem `BATCH_EXECUTION` e sem `BATCH_FILL_ONLY`):

| Arquivo | Bytes | SHA-256 |
| --- | --- | --- |
| manifest.json | 1.196 | `08F88EA93CFF23F23EC19A7A4C0DB6F1BC18EC79CAC9D54D55C4698E084E5B35` |
| background.js | 117.340 | `39B7E50868B6B0DEEE6A13A9FFAE3C9C5DF828FDBACE849B3C3C6B35FA675B6C` |
| form-content.js | 54.024 | `59CB52B8CAB83D88E0FCA867DD5AC15D8057BF01B7001538D2299340EC6D61DB` |
| autos-content.js | 984.438 | `EDF133B12EE42C0211B0398E3E9F16912410586BD9DC628FDA74D4BE32275A90` |
| list-content.js | 27.656 | `59D87C1EE022D3F3117FCBCF85AE67C55BDDAE42AC28A7B7A2C85DF587334DA1` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

## 5. Critérios de aceite

| CA | Estado | Evidência |
| --- | --- | --- |
| CA-01 modo individual | PASS sintético + navegador | `batch-manual-regression.test.mjs`; suíte manual |
| CA-02 página atual | PASS real | 10 linhas capturadas sem paginar |
| CA-03 concluídos excluídos | PASS sintético | `batch-queue.test.mjs` |
| CA-04 múltiplos interessados | PASS sintético + real | recusas observadas em execuções anteriores; nenhum salvo |
| CA-05 interessado único | PASS real | 4 abas com um interessado selecionado |
| CA-06 documentos corretos | PARCIAL | 4 preenchidos; causa dos 6 `MISSING_FIELDS` não isolada |
| CA-07 cinco campos | PASS real | modalidade + quatro campos nas 4 abas |
| CA-08 preexistentes/divergentes | PASS sintético | `batch-validation.test.mjs` |
| CA-09 dois limites | PASS real | 10/1 respeitado |
| CA-10 só salvamentos comprovados | PASS supervisionado | 4/4 verificados; 0 contados pelo motor |
| CA-11 não repetir incerto | PASS sintético + supervisionado | uma confirmação por ato |
| CA-12 pausa/parada seguras | PASS sintético | `batch-state-machine.test.mjs` |
| CA-13 suspensão MV3 | PARCIAL | sem suspensão real do service worker |
| CA-14 expiração/relogin | PASS sintético | `batch-recovery.test.mjs` |
| CA-15 esperas limitadas | PASS sintético | `batch-waits.test.mjs` |
| CA-16 um lote por perfil | PASS sintético | `batch-protocol.test.mjs` |
| CA-17 relatório por processo | PASS sintético | `batch-report.test.mjs` |
| CA-18 diário sem dados pessoais | PASS | `batch-journal.test.mjs`; auditoria |
| CA-19 autorização de salvamento | PASS | H2/H3 com autorização explícita e limite de 4 |
| CA-20 retomada consistente | PARCIAL | `batch-recovery.test.mjs`; falta o caminho `SAVE_PENDING` |

## 6. O que falta

1. **Ligar o salvamento ao driver.** `src/background/index.mjs:68` chama `createBatchDriver` sem `saveEnabled`; o padrão é `false`. Mesmo com `BATCH_EXECUTION=1`, o runner cai em `MARK_FILLED` e não salva.
2. **Verificação pós-salvamento real.** `src/batch/deps.mjs:117` devolve `{ status: 'unknown' }`. Como o runner só confirma com `confirmed`, o caminho automático terminaria em `SAVE_UNCERTAIN`/`SUSPENDED` mesmo após um ACK.
3. **Recuperação de `SAVE_PENDING`.** `src/batch/runner.mjs:53` trata `SUSPENDED`, mas não um lote `RUNNING` com fase `SAVE_PENDING`; após queda entre o checkpoint e o ACK, o lote fica parado.
4. **Catch da fase `VALIDATING`.** `src/batch/runner.mjs:158` usa o `batch` anterior ao `SAVE_ARMED`; uma exceção depois do clique pode lançar `INVALID_TRANSITION` em vez de registrar `SAVE_UNCERTAIN`.
5. **Transição `SUSPENDED` → `RUNNING`.** `src/batch/state-machine.mjs:120` permite `SAVE_ACK` reativar o lote automaticamente; decidir se a retomada após incerteza exige `Continuar`.
6. **Diálogo com identificação estrutural.** `src/form/save-adapter.mjs:22` compara apenas título e texto do botão; falta validar `role`, `aria-modal`, botões e contexto antes de confirmar.
7. **Contabilidade dos 4 atos salvos.** O diário ainda os marca como `FILLED`; falta reconciliar `COMPLETED_EXTERNALLY`/`ALREADY_COMPLETED` sem incrementar `counters.saved`.
8. **Classificar os 6 `MISSING_FIELDS`.** Separar documento não encontrado, campo ausente no PDF e falha de leitura, com motivo sanitizado.
9. **Ciclo MV3 real.** Suspensão do service worker e reinício do navegador não foram simulados; falta provar que o checkpoint sobrevive sem duplicar.
10. **Cache entre dois processos reais.** O isolamento por `processHash` está implementado e testado, mas não foi exercitado em dois processos distintos no portal.
11. **Autosave do portal.** Comportamento desconhecido; não foi observado durante a digitação real.
12. **Chrome profissional.** Não validado; a extensão não foi instalada no perfil institucional.
13. **G7.** Falta o pacote de release com hashes, instruções de instalação/rollback e aceite formal; o motor deve continuar desligado.

## 7. Riscos e limites

- O caminho automático de salvamento nunca foi exercitado de ponta a ponta; os testes atuais injetam `save`/`verify` sintéticos. Não tratar `AUTOMATED_SAVE_NOT_RUN` como aprovado.
- Sem uma prova de conclusão independente, o motor deve continuar suspendendo em vez de repetir o clique.
- Os quatro salvamentos supervisionados não autorizam novos salvamentos; H2/H3 continuam exigindo autorização específica.
- O portal pode mudar seletores, status ou diálogo; a matriz CA não substitui revalidação no QA.
- Nenhum dado pessoal foi persistido ou publicado; a evidência é sanitizada.

## 8. Próximos passos

1. F1 com TDD: escrever testes RED para os itens 1–6, corrigir o mínimo e rodar a suíte.
2. F2/F3: estabilidade de abas/esperas e classificação dos seis `MISSING_FIELDS`.
3. F4/F5: MV3 por eventos, cache entre processos, autosave e revisão de storage/mensagens.
4. F6: consolidar as 23 especificações em um ciclo e atualizar a matriz CA.
5. Só então avaliar GATE A (um ato novo) e GATE B (lote pequeno), com autorização explícita e build próprio.
6. Manter o build de entrega com `BATCH_EXECUTION_ENABLED=false` até o aceite.

## 9. Segurança e privacidade

- Nenhum número de processo, nome, CPF, matrícula, nascimento, texto de PDF, cookie ou URL assinada foi incluído neste relatório.
- O diário guarda apenas identificadores indispensáveis, estados, contadores e motivos sanitizados.
- Nenhum salvamento ocorreu sem autorização explícita do operador.
- O Chrome profissional e o repositório `Atos-TCE` original não foram alterados.

## 10. Comandos para reproduzir

```powershell
cd C:\Users\slvma\Downloads\Github\Atos-TCE\Complementador-eContas
node --test tests/unit/*.test.mjs
$env:TEST_BROWSER_EXECUTABLE='C:\Users\slvma\AppData\Local\ms-playwright\chromium-1248\chrome-win64\chrome.exe'
$env:TEST_BROWSER_HEADLESS='1'
npm run test:browser
npm run build
```

O build de homologação com preenchimento em lote usa `BATCH_FILL_ONLY=1`. O build de entrega não define `BATCH_EXECUTION` nem `BATCH_FILL_ONLY`.
