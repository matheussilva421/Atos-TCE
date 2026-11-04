# Complementador e-Contas

Extensão Manifest V3 independente para o formulário **Complementar Ato** do e-Contas do TCE/RN. Ela lê o documento que o operador deixou aberto na aba de autos do mesmo processo, propõe os campos e preenche somente controles vazios e editáveis. **Não salva, não complementa o ato e não envia dados a serviços externos.**

## O que faz

- Mostra um único botão **⚡ Preencher** na tela Complementar Ato.
- Não lê PDF, não extrai texto e não interpreta nada antes do clique.
- Localiza a aba de autos do mesmo processo, sem escolher por aba mais recente.
- Lê todas as páginas do PDF atual somente após o clique.
- Extrai modalidade do ato, data da resolução administrativa, cargo, matrícula e data de nascimento.
- Preenche apenas campos vazios e editáveis; preserva valores existentes e readonly.
- Relê cada campo após a escrita e mostra preenchidos, preservados e pendências.
- O botão secundário **Diagnóstico L1 (somente leitura)** lê o PDF e mostra apenas páginas, caracteres e tempo; não altera campos.
- O diagnóstico confere o título de processo dos autos e do formulário; divergência falha sem preencher.
- O último resultado técnico do diagnóstico é recuperado após recarregar a aba, usando apenas chrome.storage.session com métricas sanitizadas.
- Se a data de nascimento não estiver no documento atual, procura o documento **Guia Financeira/Taxação de Proventos** nos eventos dos autos, extrai somente a data de nascimento e completa o preenchimento. O primeiro clique pode levar alguns segundos; o evento localizado fica em cache de sessão para os próximos.
- Cliques sintéticos gerados pela página são ignorados; somente eventos trusted iniciam o preenchimento ou o diagnóstico.
- Exibe **Origem: data da resolução administrativa** para a data proposta ao campo DOE.
- Cancela sem escrever se processo, interessado, aba, rota ou documento mudarem durante a leitura.

## Requisitos

- Chrome ou Edge 110 ou superior.
- Duas abas ou janelas do **mesmo perfil**: autos e Complementar Ato do mesmo processo.
- O documento correto já aberto no visualizador de autos; o número do evento pode variar.
- O interessado correto selecionado no Complementar Ato.

## Instalação por pasta

1. Gere a pasta **dist** com o comando de build ou use a pasta entregue.
2. Abra **chrome://extensions** ou **edge://extensions**.
3. Ative **Modo do desenvolvedor**.
4. Escolha **Carregar sem compactação** e selecione a pasta **dist**.
5. Fixe a extensão na barra, se desejar.

A instalação no perfil profissional deve ser feita pelo operador, com a extensão visível e revisada. O projeto não instala nada silenciosamente.

## Uso

1. Abra os autos do processo e deixe o documento correto aberto no visualizador.
2. Abra o Complementar Ato do mesmo processo e selecione o interessado.
3. Clique em **⚡ Preencher**.
4. Confira os campos e a legenda de origem da data.
5. Se estiver correto, use os controles normais do portal para concluir o ato. A extensão não faz isso.

## Segurança e limites

- Permissões de host restritas a **processos.tce.rn.gov.br** e **novaarearestrita.tce.rn.gov.br**.
- Sem storage persistente; o service worker usa chrome.storage.session para métricas sanitizadas do diagnóstico e para o id do evento da Guia. Sem all_urls, downloads, webRequest, debugger, cookies, IndexedDB ou telemetria.
- O content script não acessa storage; recebe somente resultados sanitizados por mensagens GET_DIAGNOSTIC/DIAGNOSTIC_UPDATE. Não há nome, CPF, matrícula, texto, URL documental ou identificador de processo.
- Os únicos fetches de rede são os PDFs do documento atual e da Guia, no service worker, com validação de origem, caminho, tipo, tamanho e assinatura PDF. A busca da Guia clica somente nos cartões de evento e restaura o documento original.
- Nenhum PDF, texto integral, nome, CPF, matrícula, token ou cookie é persistido.
- Sem OCR, LLM, backend, banco ou nuvem no MVP.
- Se o documento tiver páginas sem texto legível, a extensão falha fechada e não preenche.
- Se houver mais de uma aba de autos do mesmo processo, a extensão recusa em vez de escolher uma.
- O L2 real foi executado no Chrome QA com autorização explícita; nenhum ato foi salvo ou concluído. Se o portal indicar autosave durante a digitação, interrompa o uso e reporte.

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
- **npm run test:browser** executa o fluxo sintético no Edge/Chromium. O Chrome gerenciado desta estação bloqueia extensões unpacked; o Edge foi usado como navegador de teste. O harness aceita TEST_BROWSER_CHANNEL.
- **npm run build** gera **dist** com a extensão de produção.
- **npm run build:test** gera **dist-test** com permissões para o servidor local de fixtures.
- **npm run benchmark** mede clique até readback em PDF sintético e grava docs/evidence/benchmarks.md.

## Status verificável

- **SYNTHETIC_PASS**: 100 testes unitários e 15 testes de navegador aprovados.
- **SYNTHETIC_E2E_PASS**: leitura de PDF sintético, extração, preenchimento, readback, diagnóstico L1 multi-página, recuperação após recarregar a aba e busca da Guia com cache no Edge.
- **REAL_READ_PASS**: leitura real no Chrome QA isolado com `L1_SUCCESS`: 1 página, 1.874 caracteres e 54.627 bytes; 502 ms na primeira execução e 1.026 ms na segunda, com HTTP 200 `application/pdf`. Evidência sanitizada em `docs/evidence/qa-real-2026-11-04.md`.
- **REAL_VIEWER_VERIFIED_IN_QA**: o iframe real do portal foi lido por bytes e o PDF foi validado; o Chrome profissional não foi tocado.
- **L1_DIAGNOSTIC_READY**: leitura real comprovada; a recuperação por `GET_DIAGNOSTIC` foi confirmada no QA.
- **EXTENSION_RELOAD_VERIFIED**: a build 0.1.1 com a correção de rota foi recarregada no Chrome QA e os botões apareceram na aba original.
- **FINAL_BUILD_VERIFIED_ON_DISK**: a build 0.1.1, o release e o ZIP coincidem com o código-fonte e os hashes registrados.
- **FINAL_BUILD_RELOAD_PENDING**: a build final foi validada no Chrome QA; o Chrome profissional continua sem recarga, por não ter sido autorizado.
- **DIAGNOSTIC_OBSERVABILITY_VERIFIED**: o resultado técnico sanitizado é recuperado após reload e em nova aba, tanto em teste quanto no QA real.
- **SPA_ROUTE_FIX_VERIFIED**: `pushState`, `replaceState`, `hashchange` e saída de rota cobertos por testes; 15 PASS.
- **MODALITY_READBACK_FIX_VERIFIED**: o rótulo da modalidade é lido sem o ícone de limpar `×`; o primeiro clique deixou de falhar.
- **REAL_FILL_VERIFIED (L2 follow-up)**: com autorização explícita nesta continuação, um único clique no Chrome QA preencheu modalidade, DOE, cargo, matrícula e nascimento; a data de nascimento veio da Guia Financeira/Taxação de Proventos.
- **BIRTH_GUIDE_SEARCH_VERIFIED**: primeiro clique real levou 8,9 s (varredura dos eventos); o segundo, com cache de sessão, levou 1,1 s. O documento original foi restaurado e o cache guarda apenas o id do evento.
- **NO_REAL_SAVE_OR_SUBMIT**: PASS; nenhum ato foi salvo, complementado ou enviado.
- **L2_REAL_FILL_AUTHORIZED_IN_QA**: a escrita real ocorreu somente no Chrome QA; o Chrome profissional não foi tocado.
- **NO_REAL_WRITE_VERIFIED (L1)**: as duas leituras L1 mantiveram o fingerprint do formulário e não escreveram campos.
- Nenhum ato foi salvo ou concluído.

## Documentação

- docs/evidence/f0-sanitized.md
- docs/evidence/dom-contract.md
- docs/evidence/security-audit.md
- docs/evidence/live-verification.md
- docs/evidence/qa-real-2026-11-04.md
- docs/evidence/benchmarks.md
- docs/notes/handoff.md
