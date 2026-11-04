# Verificação real e gates

> Estado atual em 04/11/2026: a descoberta automática da Resolução e da Guia foi validada no Chrome QA isolado. Um único clique preencheu os cinco campos, com readback, origem dupla e Autos restaurados; o primeiro clique a partir de documento diverso levou 14,3–14,5 s, com a Resolução aberta e cache limpo 7,096 s, e com cache p50 3,026 s/p95 6,729 s. A build carregada no QA coincide byte a byte com `dist`. Nada foi salvo ou concluído. Ver `qa-real-2026-11-04.md`.

## Matriz atual (04/11/2026)

| Status | Resultado | Evidência |
|---|---|---|
| SYNTHETIC_PASS | PASS | 114 testes unitários e 19 testes de navegador. |
| REAL_END_TO_END_PASS (Chrome QA) | PASS | Critérios do GOAL atendidos no QA; Chrome profissional pendente. |
| RESOLUTION_AUTO_DISCOVERY_VERIFIED | PASS | Resolução correta encontrada no evento 6 entre 20 eventos e decoys nos eventos 7/14. |
| BIRTH_GUIDE_AUTO_DISCOVERY_VERIFIED | PASS | Guia encontrada no evento 10; nascimento correlacionado ao interessado. |
| SINGLE_CLICK_VERIFIED | PASS | Um clique preencheu os cinco campos. |
| REAL_FIELD_READBACK_VERIFIED | PASS | Modalidade, DOE, cargo, matrícula e nascimento presentes sem pendências. |
| AUTOS_RESTORE_VERIFIED | PASS | Mesmo `src` inicial e 2 eventos selecionados antes/depois. |
| QA_EXTENSION_BUILD_VERIFIED | PASS | SHA-256 dos cinco recursos carregados no service worker igual a `dist`. |
| CACHE_ISOLATION_VERIFIED | PASS sintético | Processo diferente não reutiliza ids; sem teste real entre dois processos. |
| FINAL_BUILD_VERIFIED_ON_DISK | PASS | Build, release e ZIP extraído com hashes iguais. |
| NO_SAVE_OR_SUBMIT_VERIFIED | PASS | Nenhum ato foi salvo, complementado ou enviado (`NO_REAL_SAVE_OR_SUBMIT`). |
| PROFESSIONAL_BROWSER_PENDING | PENDENTE | O Chrome profissional não foi tocado nem recarregado. |
| REAL_SAVE_OR_SUBMIT | NÃO EXECUTADO | Fora do escopo. |

## Histórico das tentativas anteriores (03/11/2026)

- Data: 03/11/2026
- Ambiente: estação do operador, Chrome gerenciado, duas abas do e-Contas já abertas.
- Privacidade: nenhum nome, CPF, matrícula, número de processo, conteúdo documental, cookie, token, HAR ou screenshot foi persistido.

### Matriz histórica

| Status | Resultado | Evidência |
|---|---|---|
| SYNTHETIC_PASS | PASS | 88 testes unitários. |
| SYNTHETIC_E2E_PASS | PASS | 10 testes de navegador no Edge, incluindo diagnóstico multi-página, HTTP/login, clique sintético bloqueado e recuperação após reload. |
| L1_DIAGNOSTIC_READY | PASS SINTÉTICO | Botão de diagnóstico somente leitura implementado; leitura real pendente de recarga. |
| EXTENSION_RELOAD_VERIFIED (build L1 anterior) | PASS | Botões ⚡ Preencher e Diagnóstico L1 apareceram após recarregar a aba Complementar Ato. |
| FINAL_BUILD_VERIFIED_ON_DISK | PASS | Versão 0.1.1 em dist, release/0.1.1 e ZIP; hashes conferidos. |
| FINAL_BUILD_RELOAD_PENDING | PENDENTE | A build 0.1.1 não foi recarregada no Chrome profissional. |
| DIAGNOSTIC_OBSERVABILITY_VERIFIED | PASS SINTÉTICO | L1_SUCCESS com 1 página, 271 caracteres e 877 bytes foi recuperado após reload da aba; teste automatizado. |
| REAL_RETRY_AFTER_RECOVERY | INCONCLUSIVO | Controle do Chrome voltou; clique trusted no Diagnóstico L1 retornou Falha de comunicação com a extensão, sem estado no storage e sem alterar campos. |
| REAL_READ_ATTEMPTED | INCONCLUSIVO | Clique trusted no Diagnóstico L1 disparado; depurador CDP da automação caiu antes de qualquer resultado ou métrica. |
| BROWSER_CONTROL_LOST | CONFIRMADO | Timeout em Emulation.setFocusEmulationEnabled; a aba de autos retornou Debugger unattached. |
| REAL_READ_PASS_NOT_VERIFIED | NÃO DECLARADO | Nenhuma evidência de leitura real foi obtida; a build 0.1.1 não está carregada no Chrome. |
| REAL_VIEWER_UNVERIFIED | CONFIRMADO | O iframe é cross-origin e o DOM pai não expõe o texto. |
| L2_NOT_AUTHORIZED | CONFIRMADO | Nenhuma escrita em formulário real foi autorizada ou executada. |
| REAL_FILL_VERIFIED | NÃO DECLARADO | Só há preenchimento sintético com readback. |
| REAL_SAVE_OR_SUBMIT | NÃO EXECUTADO | Nenhum ato foi salvo, complementado ou enviado. |

## Revisão independente e correções

- A revisão independente confirmou que o caminho DIAGNOSE_DOCUMENT não chama preenchimento, submit ou endpoint de gravação.
- Achado Critical corrigido: o botão de preenchimento agora rejeita eventos sintéticos da página; somente cliques trusted executam o fluxo. Teste de navegador cobre o caso.
- Achado Important corrigido: o processo é vinculado pelo título "AUTOS DO PROCESSO .../..." e "COMPLEMENTAR ATO - PROCESSO .../...", não apenas pelo valor que o leitor injetava. Divergência retorna PROCESS_LABEL_MISMATCH; ausência retorna PROCESS_BINDING_UNVERIFIED.
- Achados menores corrigidos: cancelamento do diagnóstico, listener de autos registrado sempre, fetch do PDF exigindo transação ativa e permissão do PDF restrita a /as/consultaprocessotemp/*.
- O limite de Content-Length foi corrigido com leitura em streaming e aborto acima de 25 MB. Permanecem documentados: homônimos de interessados e deslocamento de janela de texto com acentos no caminho L2; L2 não foi executado.
- O leitor HTTP foi extraído para src/background/pdf-fetch.mjs e coberto por testes de 401, 403, redirecionamento, HTML, bytes não-PDF, tamanho declarado e corpo em streaming.

## Diagnóstico recuperável

- O service worker registra L1_STARTED, SOURCE_TAB_RESOLVED, IFRAME_IDENTIFIED, PDF_FETCH_STARTED, PDF_FETCH_OK, PDF_VALIDATED, PDF_TEXT_EXTRACTED, L1_SUCCESS/L1_ERROR/L1_TIMEOUT/L1_CANCELLED.
- O service worker mantém chrome.storage.session em DIAGNOSTIC_KEY, com apenas estado, tempos, páginas, caracteres e tamanho; sem texto, nome, CPF, matrícula, URL, cookie ou processo.
- O content script não acessa storage; solicita o último resultado por GET_DIAGNOSTIC e recebe DIAGNOSTIC_UPDATE, ambos sanitizados.
- O painel da extensão solicita o último resultado ao carregar e escuta DIAGNOSTIC_UPDATE; o storage permanece no contexto confiável do service worker.
- Teste real sintético: L1_SUCCESS com 1 página, 271 caracteres, 877 bytes; recuperado após recarregar a aba, sem alterar campos.
- O registro é reiniciado em cada novo diagnóstico e desaparece ao fim da sessão do Chrome.

## O que foi observado no portal

- As duas abas existiam no mesmo perfil, com o mesmo idProcesso. O valor não foi registrado.
- O documento estava aberto no visualizador de autos; a interface indicou 1/1 página no documento observado.
- O formulário exibiu a modalidade do processo e os quatro campos do interessado selecionado.
- Não houve clique em Complementar ato, Salvar, Confirmar, Voltar ou em qualquer submit.
- A observação foi somente leitura, via controlador de navegador. O REA não tinha CDP e não foi usado.

## Instalação e versão observadas

- A extensão foi instalada manualmente pelo operador no Chrome profissional.
- Na auditoria de 03/11/2026, a versão ativa ainda era a build antiga: apenas o botão ⚡ Preencher; o botão Diagnóstico L1 não aparecia.
- O commit c23d9d2 adiciona o diagnóstico L1 somente leitura e a pasta dist foi reconstruída.
- A cópia extraída em release/Complementador-eContas-0.1.0 ainda tinha a build antiga: form-content.js com SHA-256 7D6527... e sem o texto Diagnóstico L1. O dist novo tem form-content.js B3D03C..., background.js 231D12... e autos-content.js 9FE0AC...; manifest.json é idêntico (D2D190...).
- Causa comprovada: a pasta instalada era a cópia antiga de release, não o dist atualizado; atualizar o dist sozinho não alterava a cópia carregada.
- Mecanismos oficiais tentados: o servidor DevTools não tinha CDP em 9222 e a página chrome://extensions foi bloqueada pela política de URL do navegador. Nenhum contorno, nenhuma leitura de Preferences, cookies ou tokens.
- Correção aplicada: a pasta release/Complementador-eContas-0.1.0 foi substituída pela build atual e os hashes agora coincidem com dist. Falta apenas a recarga manual da extensão e da aba Complementar Ato.
- Nova verificação após a correção: a aba Complementar Ato ainda apresentava apenas o botão ⚡ Preencher; o botão Diagnóstico L1 não apareceu porque a extensão e a aba não foram recarregadas. Nenhum campo foi alterado e nenhuma leitura real foi executada.
- Em 04/11/2026, a aba Complementar Ato foi recarregada e a build L1 anterior foi injetada: os botões ⚡ Preencher e Diagnóstico L1 apareceram. **EXTENSION_RELOAD_VERIFIED (build L1 anterior)**; a build final com recovery está pendente de recarga.
- O Diagnóstico L1 foi acionado com clique trusted. Em seguida o depurador da automação caiu; a aba do formulário ficou sem resposta a comandos CDP e a aba de autos retornou Debugger unattached. Nenhum resultado de páginas, caracteres ou tempo foi obtido.
- Nenhum campo foi alterado e a aba de autos não foi navegada.
- Tentativas adicionais de reconexão após 15 s e 30 s falharam com o mesmo timeout de Emulation.setFocusEmulationEnabled; a aba de autos também retornou Debugger unattached. Nenhuma métrica real foi obtida.
- Após a reconexão posterior, a aba de autos tinha o marker ready e os dois botões apareceram, mas o clique trusted no Diagnóstico L1 terminou em Falha de comunicação com a extensão; o storage não recebeu estado final. A build final com recovery ainda não está confirmada no Chrome.
- Tentativas oficiais de recarga: o servidor Chrome DevTools MCP não tinha CDP em 127.0.0.1:9222; a aba chrome://extensions/?id=ngaooomnjgifdhbkbfepccgbailmjbcm existe, mas não pode ser reivindicada pela extensão de automação; o controle nativo do Chrome foi interrompido pela política do Computer Use por não conseguir determinar a URL atual no Windows. Nenhum contorno foi tentado.
- A versão instalada foi confirmada pelo operador em release/Complementador-eContas-0.1.0. O código e o build têm o diagnóstico; a versão carregada no Chrome permanece antiga.
- As abas atuais do e-Contas foram substituídas por outro processo; nenhum idProcesso, nome, CPF, matrícula ou conteúdo documental foi registrado.
- Estado consolidado: SAFE_PARTIAL; SYNTHETIC_PASS; DIAGNOSTIC_OBSERVABILITY_VERIFIED; FINAL_BUILD_VERIFIED_ON_DISK; FINAL_BUILD_RELOAD_PENDING; REAL_READ_PASS_NOT_VERIFIED; REAL_VIEWER_UNVERIFIED; L2_NOT_AUTHORIZED.
- A recarga confirmada em 04/11/2026 foi a da build L1 anterior. A verificação final mostrou hasDiagnosticPanel=false, provando que a build final com recovery ainda não está carregada no Chrome.
- Nenhum clique em Preencher foi feito na versão ativa; nenhum campo foi alterado.

## Por que a leitura real não foi executada

1. A extensão está instalada e a build nova foi injetada após a recarga da aba Complementar Ato; o botão Diagnóstico L1 apareceu.
2. O clique trusted no Diagnóstico L1 foi disparado, mas o depurador da automação caiu antes de qualquer resultado. A aba do formulário ficou sem resposta a CDP e a aba de autos retornou Debugger unattached.
3. Sem resultado observado, não há base para declarar REAL_READ_PASS; nenhuma métrica de páginas, caracteres ou tempo foi obtida.
4. A escrita L2 é um gate separado e não autorizado.

## Próximo passo mínimo para resolver os gates

- Restaurar o controle de automação das abas e repetir somente o Diagnóstico L1 (somente leitura); não clicar em ⚡ Preencher.
- Verificar páginas, caracteres e tempo; se o resultado for obtido, registrar REAL_READ_PASS. Sem resultado, manter REAL_VIEWER_UNVERIFIED.
- Preservar a aba de autos e o documento; L2 continua fora do escopo.
- A escrita real (L2) exige autorização explícita separada, em um processo concreto, apenas nos campos de UI, sem salvar. Se houver autosave, interromper.

## Limitações

- Não há prova de que o fetch do PDF real funcione com cookies/SameSite do portal.
- O diagnóstico L1 real foi acionado, mas o controle de automação foi perdido antes do resultado; nenhuma métrica real foi obtida.
- Não há prova de múltiplos interessados no portal real.
- Não há prova de que o Angular/bsDatepicker reaja como no fixture.
- A versão do portal pode mudar.
