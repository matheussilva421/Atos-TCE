# Complementador e-Contas

Extensão Manifest V3 independente para o formulário **Complementar Ato** do e-Contas do TCE/RN. Ela localiza nos eventos dos autos a Resolução Administrativa e a Guia Financeira/Taxação de Proventos do processo, propõe os campos e preenche somente controles vazios e editáveis. No modo individual, **não salva, não complementa o ato e não envia dados a serviços externos**. A versão 2.0.3 inclui automação em lote com salvamento automático homologado no Chrome QA; cada lote exige clique explícito e limites definidos pelo operador.

## O que faz

- Mostra um único botão **⚡ Preencher** na tela Complementar Ato.
- Não lê PDF, não extrai texto e não interpreta nada antes do clique.
- Localiza a aba de autos do mesmo processo, sem escolher por aba mais recente.
- Lê o PDF atual somente após o clique.
- Se o documento atual já contiver a Resolução completa, usa os dados; se faltar a Resolução ou a data de nascimento, percorre os cartões de evento dos autos.
- Classifica os candidatos pelo texto do PDF e procura **Resolução Administrativa** e **Guia Financeira/Taxação de Proventos**.
- Lê até 2 páginas de cada candidato para classificar e lê integralmente apenas os documentos relevantes.
- Escolhe a Resolução com mais campos exatos; empate com valores divergentes falha fechado.
- Correlaciona a data de nascimento ao interessado selecionado, usando o CPF transitório do cartão e o nome como fallback; ambiguidade falha.
- Restaura o documento e a seleção originais dos Autos ao terminar.
- Mantém um cache de sessão por processo com o hash do processo e os ids dos eventos da Resolução e da Guia. Processo diferente não reutiliza ids antigos.
- Extrai modalidade do ato, data da resolução administrativa, cargo, matrícula e data de nascimento.
- Preenche apenas campos vazios e editáveis; preserva valores existentes e readonly.
- Relê cada campo após a escrita e mostra preenchidos, preservados e pendências.
- O botão secundário **Diagnóstico L1 (somente leitura)** lê o PDF e mostra apenas páginas, caracteres e tempo; não altera campos.
- O diagnóstico confere o título de processo dos autos e do formulário; divergência falha sem preencher.
- O último resultado técnico do diagnóstico é recuperado após recarregar a aba, usando apenas chrome.storage.session com métricas sanitizadas.
- Cliques sintéticos gerados pela página são ignorados; somente eventos trusted iniciam o preenchimento ou o diagnóstico.
- Exibe **Origem: data da resolução administrativa** para a data proposta ao campo DOE.
- Cancela sem escrever se processo, interessado, aba, rota ou documento mudarem durante a leitura.

## Automação em lote (2.0.3)

- O painel **⚡ Rodar automação** aparece na listagem de processos e captura apenas a página atual.
- A fila exclui processos já complementados, recusa múltiplos interessados e respeita dois limites independentes (examinados e salvos).
- O modo só-preenchimento (build com `BATCH_FILL_ONLY=1`) preenche os processos e mantém as abas abertas para revisão, sem nenhum caminho de salvamento.
- O salvamento automático foi homologado em 10 atos reais no Chrome QA (10/10 verificados), com checkpoint, diálogo estrutural e verificação independente. Cada execução exige clique explícito; não há início automático.
- O painel tem o checkbox **Manter abas de processos com problema**: marcado, revisões/falhas mantêm as duas abas abertas; desmarcado, elas fecham. A escolha é persistida.
- O diário do lote usa `chrome.storage.local` com identificadores, estados e motivos sanitizados; não guarda PDFs nem dados pessoais.

## Requisitos

- Chrome ou Edge 110 ou superior.
- Duas abas ou janelas do **mesmo perfil**: autos e Complementar Ato do mesmo processo.
- A lista de eventos dos autos disponível. Não é necessário abrir manualmente a Resolução ou a Guia; a extensão as procura.
- O interessado correto selecionado no Complementar Ato.

## Instalação por pasta

1. Gere a pasta **dist** com o comando de build ou use a pasta entregue.
2. Abra **chrome://extensions** ou **edge://extensions**.
3. Ative **Modo do desenvolvedor**.
4. Escolha **Carregar sem compactação** e selecione a pasta **dist**.
5. Fixe a extensão na barra, se desejar.

A instalação no perfil profissional deve ser feita pelo operador, com a extensão visível e revisada. O projeto não instala nada silenciosamente.

## Uso

1. Abra os autos do processo. Pode deixar qualquer evento aberto; a extensão procura a Resolução e a Guia.
2. Abra o Complementar Ato do mesmo processo e selecione o interessado.
3. Clique em **⚡ Preencher**.
4. O primeiro clique pode levar alguns segundos enquanto os eventos são percorridos. Os cliques seguintes usam o cache de sessão do mesmo processo.
5. Confira os campos e a legenda de origem da data.
6. Se estiver correto, use os controles normais do portal para concluir o ato. A extensão não faz isso.

## Segurança e limites

- Permissões de host restritas a **processos.tce.rn.gov.br** e **novaarearestrita.tce.rn.gov.br**.
- No modo individual, sem storage persistente; o service worker usa chrome.storage.session para métricas sanitizadas do diagnóstico e para o cache `complementadorDocumentCache`, que guarda apenas `processHash`, `resolutionEventId`, `guiaEventId` e `updatedAt`. A automação em lote usa `chrome.storage.local` apenas para o diário sanitizado (IDs, estados, contadores e motivos) e para o preset de filtros. Sem all_urls, downloads, webRequest, debugger, cookies, IndexedDB ou telemetria.
- O content script não acessa storage; recebe somente resultados sanitizados por mensagens GET_DIAGNOSTIC/DIAGNOSTIC_UPDATE. Não há nome, CPF, matrícula, texto, URL documental ou identificador de processo.
- Os únicos fetches de rede são os PDFs do documento atual e dos candidatos dos eventos, no service worker, com validação de origem, caminho, tipo, tamanho e assinatura PDF. A busca clica somente nos cartões de evento, lê até 2 páginas por candidato e restaura o documento original.
- Nenhum PDF, texto integral, nome, CPF, matrícula, token ou cookie é persistido.
- Sem OCR, LLM, backend, banco ou nuvem no MVP.
- Se o documento tiver páginas sem texto legível, a extensão falha fechada e não preenche.
- Se houver mais de uma aba de autos do mesmo processo, a extensão recusa em vez de escolher uma.
- A versão 2.0.3 realizou 10 salvamentos reais no Chrome QA com autorização explícita; o Chrome profissional não foi tocado. A rota **Meus Processos** também é suportada. Se o portal indicar autosave durante a digitação, interrompa o uso e reporte.

## Atualização, remoção e rollback

- Atualizar: substitua os arquivos da pasta **dist**, abra a página de extensões e clique em **Atualizar**.
- Remover: na página de extensões, escolha **Remover**. A extensão não altera dados do portal.
- Rollback: desative ou remova a extensão e recarregue manualmente a página do portal. Campos preenchidos e não salvos podem ser descartados pelo próprio operador; a extensão não automatiza reload nem limpeza de formulário.

## Desenvolvimento

    npm install
    npm test
    npm run test:browser
    npm run build
    npm run benchmark

- **npm test** executa os testes unitários com node:test e jsdom.
- **npm run test:browser** executa o fluxo sintético em navegador real. Com `TEST_BROWSER_EXECUTABLE` apontando para o Chrome for Testing, usa esse binário; sem a variável, usa o canal `msedge`. O harness aceita `TEST_BROWSER_CHANNEL` e `TEST_BROWSER_HEADLESS`.
- **npm run build** gera **dist** com a extensão de produção.
- **npm run build:test** gera **dist-test** com permissões para o servidor local de fixtures.
- **npm run benchmark** mede clique até readback em PDF sintético e grava docs/evidence/benchmarks.md.

## Status verificável

- **SYNTHETIC_PASS**: 114 testes unitários e 19 testes de navegador aprovados.
- **REAL_END_TO_END_PASS (Chrome QA)**: PASS; os critérios do GOAL foram atendidos no QA, incluindo descoberta dos dois documentos, um clique, cinco campos, readback, restauração e ausência de save/submit. O Chrome profissional continua pendente.
- **SYNTHETIC_E2E_PASS**: descoberta automática a partir de documento diverso, Guia aberta, Resolução multipágina, documentos ausentes, readback, restauração dos Autos e isolamento do cache.
- **REAL_DISCOVERY_VERIFIED**: no Chrome QA, a extensão encontrou a Resolução correta e a Guia em 20 eventos com nomes genéricos e documentos decoy; a Resolução correta tinha 1.812 caracteres e a Guia 1.247 caracteres.
- **SINGLE_CLICK_VERIFIED**: um único clique preencheu os cinco campos em todas as amostras; a origem exibida incluiu Resolução e Guia.
- **REAL_FIELD_READBACK_VERIFIED**: a leitura do formulário após o clique mostrou modalidade, DOE, cargo, matrícula e nascimento preenchidos, sem pendências.
- **AUTOS_RESTORE_VERIFIED**: o iframe voltou ao mesmo `src` inicial e a quantidade de eventos selecionados foi preservada.
- **REAL_PERFORMANCE**: primeiro clique a partir de documento diverso levou 14,3–14,5 s; com a Resolução já aberta e cache limpo, 7,096 s; com cache, amostras de 2,8–6,7 s (p50 3,026 s; p95 6,729 s).
- **QA_EXTENSION_BUILD_VERIFIED**: os cinco arquivos carregados no Chrome QA coincidem byte a byte com `dist` (SHA-256 conferido no service worker).
- **CACHE_ISOLATION_VERIFIED**: PASS sintético; processo diferente não reutiliza ids. Não houve teste real com dois processos distintos.
- **NO_SAVE_OR_SUBMIT_VERIFIED**: PASS no modo individual; o lote 2.0.3 realizou 10 salvamentos autorizados no QA, todos verificados no portal.
- **FINAL_BUILD_VERIFIED_ON_DISK**: build, pasta de release e ZIP extraído com os mesmos hashes.
- **PROFESSIONAL_BROWSER_PENDING**: o Chrome profissional não foi tocado nem recarregado; a instalação lá continua manual.
- No modo individual, nenhum ato é salvo ou concluído; no lote 2.0.3, 10 atos foram salvos no QA com autorização e verificação independente.

## Documentação

- docs/evidence/f0-sanitized.md
- docs/evidence/dom-contract.md
- docs/evidence/security-audit.md
- docs/evidence/live-verification.md
- docs/evidence/qa-real-2026-11-04.md
- docs/evidence/benchmarks.md
- docs/notes/handoff.md
