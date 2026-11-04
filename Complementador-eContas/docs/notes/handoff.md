# Handoff — Complementador e-Contas

> Atualização 04/11/2026: esta seção prevalece sobre o histórico abaixo.

## QA real 04/11/2026

- Chrome for Testing 157.0.8103.38 em perfil QA isolado (`%USERPROFILE%\.codex\qa-econtas\profile-debug-20261104`), CDP apenas em `127.0.0.1:9222`; Chrome profissional e Atos-TCE intocados.
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

- Repositório novo: %USERPROFILE%/Downloads/Github/Complementador-eContas
- Branch: main
- HEAD de implementação/testes: d7282a8a80885062d5935dd9c5d1f67f8570a113; versão 0.1.1; ver git log para os commits de documentação seguintes.
- Remoto: nenhum
- Publicação/push/PR: nenhum
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

O primeiro comando de git init foi executado por engano em %USERPROFILE%/Downloads/Github e criou um diretório .git vazio nessa pasta. A remoção foi recusada pelo revisor automático de segurança. O .git do projeto correto está em %USERPROFILE%/Downloads/Github/Complementador-eContas/.git. O operador pode remover manualmente o .git acidental de Downloads/Github se desejar; nenhum arquivo de projeto foi alterado por ele.

## Próximos passos

1. Revisar o README e a pasta dist.
2. Recarregar a build final em um Chrome autorizado e recarregar somente a aba Complementar Ato; manter a aba de autos e o documento intactos.
3. Clicar apenas em Diagnóstico L1 (somente leitura) e verificar páginas, caracteres, tamanho e tempo; não clicar em Preencher.
4. Se a leitura real passar, registrar REAL_READ_PASS.
5. Só depois, se houver autorização L2 separada, testar escrita apenas nos campos de UI, sem salvar; monitorar autosave.
6. Nunca clicar em Complementar ato, Salvar, Confirmar ou submeter formulário.

## Comandos úteis

    cd C:Users%USER%DownloadsGithubComplementador-eContas
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
- background.js: 1305EF31173C4FCC699EE3313198E46F3C6785AE9B8A09B36CD3774A057F2F6D
- form-content.js: D26C94A0952D63C9B53635FEF33567C1A2C7120D9D387D33961C362EBE9EC3EF
- autos-content.js: 6EE121B357C1682C8B7FE4B2B5C4D5578DB71AEEC1A2FF9F2A33D78E3F0C2000
- vendor/pdf.worker.mjs: BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D
- ZIP: release/Complementador-eContas-0.1.1.zip (613.459 bytes; SHA-256 7AEDF6F14C6B365990495EF9648491F0FCBAAC5171F5CC9430A4FA3AC6267742)
