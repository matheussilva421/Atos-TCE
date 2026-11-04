# Auditoria de segurança e privacidade

- Data: 04/11/2026
- Escopo: src, extension, scripts, dist e testes sintéticos.
- Resultado: **PASS** nos controles automatizados; riscos residuais listados ao final.

## Permissões

| Item | Resultado |
|---|---|
| Manifest V3 | Sim. |
| permissions | Apenas storage. |
| host_permissions | Apenas https://processos.tce.rn.gov.br/* e https://novaarearestrita.tce.rn.gov.br/as/consultaprocessotemp/*. |
| all_urls | Ausente. |
| tabs, scripting, downloads, webRequest, debugger, cookies, storage.local, storage.sync | Ausentes. |
| content_scripts.matches | Apenas a origem do portal. |
| web_accessible_resources | Apenas vendor/pdf.worker.mjs, restrito ao portal. |

## Rede

- O fetch do PDF é encapsulado em src/background/pdf-fetch.mjs e chamado pelo service worker. Não há fetch em content scripts.
- Ele aceita somente URL do host do PDF, caminho /as/consultaprocessotemp/AAAA/M/D/GUID/GUID.pdf, sem query, sem hash e sem credenciais na URL.
- Usa credentials include, cache no-store e redirect error.
- Exige resposta ok, content-type application/pdf, limite de 25 MB aplicado ao Content-Length e ao stream, e assinatura %PDF-. Respostas 401/403, redirecionamento, HTML e bytes não-PDF falham fechado.
- Não há chamadas a serviços externos, telemetria, WebSocket, XHR ou sendBeacon.
- Nenhum dado documental é enviado para fora do navegador.

## Armazenamento e logs

- Sem chrome.storage.local/sync, IndexedDB, localStorage, sessionStorage ou arquivos.
- chrome.storage.session é usado somente pelo service worker para o último diagnóstico sanitizado (estado, tempos, páginas, caracteres e tamanho) e para o cache `complementadorDocumentCache` (`processHash` e ids dos eventos da Resolução e da Guia). O content script não acessa storage; recebe o resultado por GET_DIAGNOSTIC/DIAGNOSTIC_UPDATE. Nenhum texto, nome, CPF, matrícula, data, URL ou número de processo é armazenado.
- Texto do PDF, propostas e relatórios existem apenas em memória durante a transação.
- Sem console.log, console.info, console.warn ou console.error no código de produção.
- Sem screenshots, HAR, PDFs ou tokens no dist.

## Submissão e escrita

- Não há form.submit, requestSubmit, dispatchEvent de submit, clique em Complementar ato, Salvar ou Confirmar.
- A escrita usa setter nativo e eventos input/change/blur nos quatro inputs.
- A modalidade usa clique em uma opção única do ng-select; não há botão de salvar modalidade.
- Antes de cada escrita, processo, interessado e revisionMarker são revalidados.
- Após cada escrita, há readback; divergência aborta o restante.
- Testes negativos confirmam zero submit e zero POST/PUT.

## Privacidade dos dados

- Fixtures usam apenas dados sintéticos: PESSOA UM/PESSOA DOIS, CPFs 000.000.000-00 e 111.111.111-11, processo 999001.
- O teste de segurança varre fontes e docs por padrões de CPF e falha para qualquer valor não sintético.
- O pacote dist não contém PDFs, HAR, PNGs ou fixtures.
- Nenhum dado real do portal foi copiado para o repositório.

## Testes executados

- npm test: 114 testes, 114 PASS.
- npm run test:browser: 19 testes, 19 PASS (Chrome for Testing 157.0.8103.38, versão 0.1.1).
- npm run build: dist com manifest, background, dois content scripts e worker PDF.js.
- git diff --check: sem erros de whitespace.

## Diagnóstico L1 somente leitura

- O caminho DIAGNOSE_DOCUMENT lê o PDF atual e retorna apenas páginas, caracteres, chave documental, origem e tempo.
- Não retorna texto das páginas, não cria plano de preenchimento e não escreve em campos.
- O teste de navegador confirma campos vazios, uma leitura de PDF e zero POST/PUT. Também cobre PDF multi-página, rejeição de HTML/login, clique sintético bloqueado e recuperação do último resultado após reload.
- O processo é vinculado por rótulos independentes dos títulos dos autos e do formulário; divergência falha fechada.
- O fetch do PDF exige uma transação ativa e a permissão é restrita ao caminho consultaprocessotemp.
- O resultado recuperável contém apenas métricas técnicas sanitizadas; teste de armazenamento rejeita name, CPF, texto, URL, processo e documentKey.

## Descoberta automática de Resolução e Guia

- A busca é acionada somente após o clique em Preencher. Ela ocorre quando o documento atual não é uma Resolução completa ou quando falta a data de nascimento.
- Ela clica apenas em cartões `.card-event` da lista de Autos; não clica em Salvar, Complementar ato, Confirmar ou submit.
- Lê até 2 páginas de cada PDF candidato em memória para classificar pelo título. Apenas a Resolução relevante e a Guia com nascimento são lidas integralmente; o texto dos demais documentos não é persistido.
- A Resolução é escolhida pelo maior número de campos exatos; empate com valores divergentes falha fechado. O nascimento é correlacionado ao interessado por CPF transitório do cartão, com nome como fallback; ambiguidade falha fechado.
- Ao final, restaura o iframe e a seleção do evento original no `finally`, com guarda de rota.
- O cache de sessão `complementadorDocumentCache` guarda apenas `processHash`, `resolutionEventId`, `guiaEventId` e `updatedAt`; não guarda URL, texto, nome, CPF, matrícula, data ou número de processo. Um processo diferente não reutiliza ids antigos. O cache é apagado ao fim da sessão do navegador.
- Não houve nova permissão de host, storage persistente, cookie, debugger ou webRequest.

## Riscos residuais

- O fetch do PDF real com cookies/SameSite do portal foi comprovado no Chrome QA em 04/11/2026 (HTTP 200 `application/pdf`, `PDF_FETCH_OK` e `PDF_VALIDATED`); o Chrome profissional continua sem recarga autorizada.
- O comportamento de autosave do formulário real é desconhecido: AUTOSAVE_UNKNOWN.
- Múltiplos interessados no portal real não foram observados: MULTI_PERSON_UNVERIFIED.
- O isolamento do cache entre dois processos reais não foi exercitado; a cobertura é sintética.
- O DOM do portal pode mudar; o produto falha fechado, mas pode deixar de preencher.
- A escrita real L2 foi executada apenas no Chrome QA, com autorização explícita nesta continuação; nenhum ato foi salvo, complementado ou enviado e o Chrome profissional não foi tocado.
- O Chrome gerenciado desta estação bloqueia extensões unpacked; os testes de navegador usam Chrome for Testing 157 e o QA real usou o mesmo binário em perfil isolado.
