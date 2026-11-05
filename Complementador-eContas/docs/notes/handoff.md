# Handoff — Complementador e-Contas

> Atualização 05/11/2026 (automação em lote): esta seção prevalece sobre todo o histórico abaixo.

## Automação em lote — checkpoint 05/11/2026

- GOAL vigente: automação em lote (T00–T21 e preparação de T24), com H2/H3/G7 dependentes de autorização humana separada.
- Branch: `codex/complementador-e-contas`. Nenhum push, merge ou alteração em `main` nesta rodada.
- Baseline T00: 114 testes unitários e 19 de navegador PASS, build PASS; backup em `work/batch-baseline-2026-11-05` (59 arquivos de fonte + 5 do build, `SHA256SUMS.txt` com 64 linhas, restauração de amostra conferida).
- Ambiente de teste novo: o Chrome de marca não aceita `--load-extension`; a suíte de navegador passou a usar `C:\Users\slvma\AppData\Local\ms-playwright\chromium-1248\chrome-win64\chrome.exe` com `TEST_BROWSER_HEADLESS=1`.
- G1 (listagem): rota `#/dashboard/processos-no-setor/no-setor` e contrato de tabela, link, status e filtros confirmados no Chrome QA; detalhes em `docs/evidence/batch-f0-sanitized.md`.
- Implementado e testado: T02 (leitor da listagem), T03 (fila e limites), T04 (máquina de estados), T05 (diário sanitizado), T07 (abas dedicadas), T08 (interessado único), T10 (campos preexistentes), T12 (adaptador de salvamento com diálogo desconhecido falhando fechado), T14 (recuperação), T15 (esperas), T19 (relatório).
- Testes: `node --test tests/unit/*.test.mjs` com 185 testes PASS (114 originais + 71 novos). Nenhum teste de navegador novo nesta rodada.
- Validação no DOM real: o leitor devolveu 10 linhas da página atual, todas `pending`, com paginação detectada, IDs numéricos e rótulos normalizados; nenhum dado pessoal foi impresso.
- Concluídos também: T06/T17 (protocolo e comandos no background) e T18 (painel na listagem). Verificado no Chrome QA: painel injetado, pré-visualização de 10 pendentes, início com 10 na fila e parada sem examinar nem salvar.
- T13: núcleo do runner implementado e testado (checkpoint SAVE_PENDING antes do clique, tentativa única, SAVE_UNCERTAIN, reconciliação e gate de salvamento fechado). Falta ligar o runner ao background com as dependências reais (T09/T11) e o ciclo MV3 (T16).
- T11 (lado formulário): comandos `BATCH_SELECT_INTERESTED` e `BATCH_VALIDATE_FORM` implementados em `src/form/batch-content.mjs` e registrados no content script, com 5 testes. Devolvem apenas códigos, booleanos e a chave transitória do interessado.
- T09 (adaptador): `src/batch/deps.mjs` conecta abas, mensagens de formulário e preenchimento injetado às dependências do runner, com 5 testes. O salvamento continua fechado (`SAVE_GATE_CLOSED`) e o adaptador real não está ligado.
- Falta para executar de fato: ligar `runOneStep` + `createRunnerDeps` ao background com o `runFillTransaction` real e o ciclo MV3 (T16); o flag de execução permanece desligado até lá.
- T20 concluído: testes travam o botão individual, o fluxo `REQUEST_FILL`, a preservação de valores existentes, a rejeição de remetente não confiável e a separação das chaves de armazenamento do lote e do cache de documentos.
- Pendente: T09 (integração documental), T11 (readback pré-save no content script), T16 (ciclo MV3), T20/T21 (regressão do modo manual e E2E sintético).
- Estado dos filtros do operador salvo em `work/qa-filters.json` e reaplicado por script após reiniciar o Chrome QA.
- Gate de salvamento: o diálogo real de confirmação e a prova pós-salvamento continuam `UNKNOWN_UNTIL_H2`; por isso o adaptador não confirma diálogo desconhecido e retorna `unknown`.
- Nenhum salvamento real foi executado. H2, H3 e G7 permanecem `NOT_RUN`.

> Atualização 04/11/2026: esta seção prevalece sobre o histórico abaixo.

## Correção final — descoberta automática de Resolução e Guia (04/11/2026)

- Estado: implementação concluída e validada no Chrome QA isolado; falta apenas recarga manual no Chrome profissional, que não foi tocado.
- Repositório de trabalho: `<projeto>`; clone do repositório: `<clone>`.
- Branch publicada: `codex/complementador-e-contas`; HEAD anterior `b8ceb0d`; esta rodada gera um commit próprio. `main` do Atos-TCE permanece em `6e1acd5`.
- Build final: `background.js` 62.394 bytes, `form-content.js` 40.608, `autos-content.js` 981.475, `manifest.json` 1.030, `vendor/pdf.worker.mjs` 1.417.586.
- Hashes finais: manifest `91E2D154...`, background `91281F9B...`, form `BBFFC7ED...`, autos `CDA81850...`, worker `BD888051...` (valores completos em `docs/evidence/qa-real-2026-11-04.md`).
- Release: `release/Complementador-eContas-0.1.1.zip`, 619.972 bytes, SHA-256 `D44B37192B49CDE6F5245AF1F84176227C6C89AB0D449C601BC651FE240601EB`; extração independente com hashes iguais a `dist`.
- Testes: `npm test` 114 PASS; `npm run test:browser` 19 PASS (Chrome for Testing 157.0.8103.38, 22,4 s). O `withStack` foi corrigido para fechar o servidor de fixtures mesmo quando a inicialização do navegador falha.
- Descoberta real: 20 eventos com nomes genéricos; Resolução correta no evento 6 (1.812 caracteres), decoys nos eventos 7 e 14, Guia no evento 10 (1.247 caracteres), documento inicial diverso com 1.201 caracteres.
- Performance real: primeiro clique a partir do documento diverso em 14,3–14,5 s; primeiro clique com a Resolução aberta e cache limpo em 7,096 s; com cache, p50 3,026 s e p95 6,729 s (amostras 6.729/3.026/2.833 ms; uma amostra posterior de 8.190 ms).
- Resultado: cinco campos preenchidos em um clique, readback sem pendências, origem Resolução + Guia, Autos restaurados com mesmo `src` e 2 eventos selecionados, cache com os dois ids. Nenhum save/submit.
- Aceite: `REAL_END_TO_END_PASS` no Chrome QA e `NO_SAVE_OR_SUBMIT_VERIFIED`; o Chrome profissional permanece `PROFESSIONAL_BROWSER_PENDING`.
- Verificação de build no QA: os cinco recursos carregados no service worker coincidem byte a byte com `dist`.
- Pendências: recarga manual no Chrome profissional (não autorizada nesta sessão); teste real do isolamento de cache entre dois processos distintos; comportamento de autosave do portal continua desconhecido.

## QA real 04/11/2026

- Chrome for Testing 157.0.8103.38 em perfil QA isolado (`<QA>/profile-debug-20261104`), CDP apenas em `127.0.0.1:9222`; Chrome profissional e Atos-TCE intocados.
- Extensão `Complementador e-Contas` 0.1.1 carregada de `dist` (ID `hfnkjnnoinedjeakknfdaofgggjolehc`, `COMMAND_LINE`, `ENABLED`, sem `disable_reasons`).
- Duas abas do mesmo processo (`QA-PROC-55cab267`), um interessado selecionado, quatro campos presentes, editáveis e vazios.
- Leitura real 1 (`DOC-0f9827c7`): `L1_SUCCESS`, 1 página, 1.874 caracteres, 54.627 bytes, 502 ms; etapas até `PDF_VALIDATED` e `PDF_TEXT_EXTRACTED`.
- Leitura real 2 (`DOC-4840252c`, reseleção do operador): `L1_SUCCESS`, mesmas páginas/caracteres/bytes, 1.026 ms; rede `GET` 200 `application/pdf`; `GET_DIAGNOSTIC` recuperou `L1_SUCCESS` em nova aba.
- Fingerprint do formulário `32e6adbe` antes/depois das duas leituras; nenhum campo escrito; modalidade não selecionada; nenhum ato salvo ou concluído.
- Defeito comprovado: a aba Complementar Ato aberta pelo SPA não recebia o painel porque o Angular usa `pushState` e o content script só ouvia `hashchange`. Correção em `src/form/content.mjs` e `src/autos/content.mjs` com `navigation.navigatesuccess`, mantendo `hashchange`.
- Testes: 100 unitários PASS; 15 de navegador PASS (pushState, replaceState, hashchange, saída de rota, L1, L1 multi-página, recuperação, CPF concatenado, prioridade de data, readback da modalidade, marcador assíncrono e busca da Guia). `git diff --check` PASS.
- Correções do follow-up: CPF colado ao último nome no cartão; prioridade da data do cabeçalho sobre datas do corpo; `revisionMarker` assíncrono estabilizado; `.ng-value` com ícone `×` lido via `.ng-value-label`. Teste controlado final: um clique preencheu modalidade + DOE + cargo + matrícula em 683 ms; nascimento ausente no PDF.
- Busca da Guia implementada: 21 eventos varridos; primeiro clique real em 8,9 s e segundo em 1,1 s com cache de sessão; 5 campos preenchidos, incluindo nascimento; documento original restaurado. O cache guarda apenas `eventId`/`updatedAt`, sem URL ou conteúdo.
- Revisão independente: o achado Critical contra `navigatesuccess` foi refutado em runtime (probe Chromium, RED→GREEN e portal real); `replaceState`, `hashchange` e saída de rota foram adicionados como testes. Nenhum achado de segurança confirmado.
- Pendências: recarga da build no Chrome profissional (não autorizada); L2 real foi executado somente no QA com autorização explícita desta continuação; salvar/complementar o ato continua fora do escopo. Após reload da extensão, as duas abas do portal precisam ser recarregadas.

## Objetivo

Entregar uma extensão Chrome/Edge Manifest V3 independente para complementação assistida de atos no e-Contas do TCE/RN, com um clique, leitura do documento atual, extração determinística, preenchimento seguro e nenhuma submissão.

## Estado

- Repositório de trabalho: `<projeto>`; versão 0.1.1.
- Clone do repositório: `<clone>`, subpasta `Complementador-eContas`.
- Branch: `codex/complementador-e-contas`; `main` do Atos-TCE intocada em `6e1acd5`.
- Publicação: branch publicada; esta rodada consolida os commits locais e o push da mesma branch, sem merge.
- Atos - TCE: não alterado pelo projeto; os documentos aprovados foram apenas copiados para o novo repositório.

## Concluído

- F0 sanitizada, com observação somente leitura das duas abas.
- F1: MV3, rotas, seleção de abas, protocolo e transação única.
- F2: leitura do PDF atual por bytes com PDF.js, parser de datas e campos com proveniência.
- F3: leitura/escrita do formulário com identidade, preservação, readback e sem submit.
- F4: testes unitários, testes de navegador no Edge, auditoria de segurança, benchmark e build.
- Diagnóstico L1 somente leitura (commit c23d9d2), testado em fixtures.
- Correções da revisão independente: clique trusted, vínculo de processo por títulos, cancelamento, listener de autos e permissão de PDF restrita (commit bf70743).
- Diagnóstico L1 recuperável em chrome.storage.session, com estados e métricas sanitizadas e recuperação após reload (commit 734263d).
- README e documentação de evidências.

## Evidências

- npm test: 88 PASS, 0 FAIL.
- npm run test:browser: 10 PASS, 0 FAIL (Edge 156, versão 0.1.1, diagnóstico multi-página, HTTP/login, clique sintético e recuperação após reload).
- npm run build: dist gerado com background.js, form-content.js, autos-content.js, manifest.json e vendor/pdf.worker.mjs.
- benchmark: amostras 232, 192, 156, 138, 133, 111, 116 ms; p50 138 ms; p95 232 ms.
- PDF sintético de 877 bytes: L1_SUCCESS com 1 página, 271 caracteres e 877 bytes; resultado recuperado após recarregar a aba, sem alterar campos.

## Gates e bloqueios

- REAL_VIEWER_UNVERIFIED: o PDF real não foi lido; o iframe é cross-origin e o fetch real não foi provado.
- DIAGNOSTIC_OBSERVABILITY_VERIFIED: PASS sintético; o resultado é recuperado após reload via chrome.storage.session.
- EXTENSION_RELOAD_VERIFIED (build L1 anterior): os dois botões apareceram após recarregar a aba; FINAL_BUILD_RELOAD_PENDING para a build com recovery.
- Cópia instalada: release/Complementador-eContas-0.1.0 foi substituída pela build atual; os hashes coincidem com dist. A build final com recovery ainda não foi recarregada no Chrome profissional.
- Causa: atualizar dist não atualizava a cópia extraída que o Chrome carregava. Chrome mantém o código já carregado em memória; ainda é necessário recarregar a extensão e a aba Complementar Ato.
- A build L1 anterior chegou a ser injetada e o botão apareceu; a build final com recovery está pronta no disco. Nenhum campo foi alterado.
- Verificação final: hasDiagnosticPanel=false na aba atual; a build carregada é a L1 anterior, não a final com recovery. Nenhum campo foi alterado.
- Tentativas oficiais: DevTools MCP sem CDP em 9222; aba chrome://extensions não reivindicável pela automação; controle nativo interrompido pela política do Computer Use por incerteza de URL no Windows. Não houve contorno.
- Estado: SAFE_PARTIAL; DIAGNOSTIC_OBSERVABILITY_VERIFIED; EXTENSION_RELOAD_VERIFIED apenas para a build L1 anterior; FINAL_BUILD_RELOAD_PENDING; REAL_READ_PASS não declarado; REAL_VIEWER_UNVERIFIED; L2_NOT_AUTHORIZED.
- Tentativa L1: clique trusted no diagnóstico disparado; o depurador da automação caiu e a aba de autos ficou Debugger unattached. Nenhum resultado foi obtido.
- Reconexão tentada após 15 s e 30 s: mesmo timeout de CDP; nenhuma métrica real.
- Reconexão posterior: controle voltou e a aba de autos tinha marker ready; clique trusted no Diagnóstico L1 retornou Falha de comunicação com a extensão e nenhum estado final no storage. A build final com recovery continua não confirmada no Chrome.
- L2_NOT_AUTHORIZED: nenhuma escrita real em formulário profissional.
- MULTI_PERSON_UNVERIFIED: só um interessado foi observado no portal.
- AUTOSAVE_UNKNOWN: nenhuma digitação real; se houver autosave, interromper.
- REA_CDP_UNAVAILABLE: não havia endpoint CDP; a observação foi feita com CUA/Playwright read-only, não com REA.
- Chrome gerenciado bloqueia extensões unpacked por linha de comando; testes de navegador usam Edge.
- Chromium do Playwright não foi baixado; o download foi recusado pelo revisor automático.

## Incidente de ambiente

O primeiro comando de git init foi executado por engano em `Downloads/Github` e criou um diretório .git vazio nessa pasta. A remoção foi recusada pelo revisor automático de segurança. O .git do projeto correto está em `<projeto>/.git`. O operador pode remover manualmente o .git acidental de `Downloads/Github` se desejar; nenhum arquivo de projeto foi alterado por ele.

## Próximos passos

1. Revisar o README e a pasta dist.
2. Recarregar a build final em um Chrome autorizado e recarregar somente a aba Complementar Ato; manter a aba de autos e o documento intactos.
3. Clicar apenas em Diagnóstico L1 (somente leitura) e verificar páginas, caracteres, tamanho e tempo; não clicar em Preencher.
4. Se a leitura real passar, registrar REAL_READ_PASS.
5. Só depois, se houver autorização L2 separada, testar escrita apenas nos campos de UI, sem salvar; monitorar autosave.
6. Nunca clicar em Complementar ato, Salvar, Confirmar ou submeter formulário.

## Comandos úteis

    cd <projeto>
    npm test
    npm run test:browser
    npm run build
    npm run benchmark
    git status --short --branch
    git log --oneline

## Arquivos-chave

- extension/manifest.json
- src/background/index.mjs
- src/background/bridge.mjs
- src/autos/document-reader.mjs
- src/extract/dates.mjs
- src/extract/fields.mjs
- src/form/form-reader.mjs
- src/form/form-writer.mjs
- src/form/content.mjs
- src/autos/content.mjs
- docs/evidence/f0-sanitized.md
- docs/evidence/dom-contract.md
- docs/evidence/security-audit.md
- docs/evidence/live-verification.md
- docs/evidence/benchmarks.md
## Build final — 04/11/2026

- manifest.json: 91E2D154D9E8E6C02A5CAC6EEF645F71ED15E74CF4ED030AF6B28C7EC3DF6834
- background.js: 91281F9B92720DE84CD3FBE6BF49214CB26136646C7BB79F3BC0414A1600234A
- form-content.js: BBFFC7ED4B4286C44FD372032F215BCCDB51CB9E69108199A7557BA1207CCBD2
- autos-content.js: CDA8185074184171CA299E035AEFD463DAFFB38C5A8AEF5565C553F3F3E69A90
- vendor/pdf.worker.mjs: BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D
- ZIP: release/Complementador-eContas-0.1.1.zip (619.972 bytes; SHA-256 D44B37192B49CDE6F5245AF1F84176227C6C89AB0D449C601BC651FE240601EB)
