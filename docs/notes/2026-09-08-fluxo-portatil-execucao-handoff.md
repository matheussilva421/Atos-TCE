# Handoff — execução do fluxo portátil integrado — 08/09/2026

## Estado atual

Atualização de 08/09/2026: três subagentes Luna xhigh fizeram auditoria separada de bridge/estado, serviço e empacotamento. O agente principal revisou os diffs, corrigiu a liberação do lock no encerramento do serviço, o fallback manual em falha de porta e a transformação geométrica nativa para CropBox/rotação. Nesta continuação foram endurecidos Origin/CSRF/seleção no servidor, bloqueada colisão de identidade normalizada, implementado pedido de pausa+drenagem de transferência e conectado o módulo servido da mesa. O source da extensão foi reempacotado como v5; este handoff permanece candidato integrado até os gates externos.

Implementação local do plano `docs/notes/2026-09-08-fluxo-portatil-plano-implementacao.md` avançada até um candidato integrado. O checkout continua em `main`; a última etapa local adiciona retry/autenticação sanitizados à coleta, documentada também em `docs/notes/2026-09-08-retry-autenticacao-coleta-handoff.md`. Não há push por falta de remoto `origin`. O usuário autenticou o Chrome separado do projeto e instalou a extensão unpacked a partir do pacote extraído para o QA; não houve coleta real, envio/finalização de ato, alteração de acervo pessoal ou exclusão de arquivos.

O fluxo mantém a separação aprovada:

- o HTML e a mesa local são somente leitura;
- a extensão é o único componente autorizado a escrever nos sete campos;
- **Sinalizar Complementar Ato** somente encaminha o sinal tipado ao frame atual; não clica, envia, assina, tramita ou conclui;
- a pesquisa por processo/nome localiza registro sem mudar o interessado do portal;
- conclusão/feito permanece uma confirmação humana independente do status de coleta.

## Ambiente medido

- Python: `C:\Python314\python.exe`, 3.14.4.
- Node: v24.15.0.
- Windows PowerShell: 5.1.26100.9168.
- Tesseract não está no `PATH`; não foi instalado nem presumido fora do runtime portátil.

## Fases implementadas

### Fase 0 — baseline

Baseline inicial reproduzível: extensão 106/106; Python 199/199 com 3 skips; PowerShell TCE 74/74; Menu 63/63; Reset 28/28 com 1 skip ambiental de symlink/reparse. `git diff --check` estava limpo.

### Fase 1 — estado portátil

Criado `portable/app/workflow_state.py` com revisão, ordem canônica, escrita atômica e conflito de revisão. `archive_index.py` e `reset_archive.py` preservam `progresso.json` e `ordem-portal.json` sem promover a marca legada `Revisado`.

### Fase 2 — serviço loopback

Criados `portable/app/bridge_auth.py` e `portable/app/local_service.py`; alterados `portable/app/menu.ps1`, `portable/INICIAR.cmd` e `tests/Test-PortableMenu.ps1`.

- bind somente em `127.0.0.1`, portas 18743–18752;
- Host/Origin restritos, token Bearer efêmero em memória, pairing de uso único com TTL;
- rotas health, pair, state, dataset, evidence, PDF por ID, selection e progress;
- Range de PDF, rejeição de traversal, 401/403/404/409/416;
- estado da ponte fora de `acervo-tce`, launcher oculto e comando explícito `INICIAR.cmd parar`;
- o menu exibe o código temporário retornado pelo helper, sem persistir token no acervo ou no ZIP;
- a mesa servida pelo helper usa bootstrap de uso único em fragmento, cookie HttpOnly/SameSite local, CSP/Referrer-Policy e não expõe o código depois do primeiro uso;
- falha da ponte não impede HTML/JSON manual.

### Fase 3 — evidências geométricas

Criados `portable/app/evidence_geometry.py` e `test_evidence_geometry.py`; `FieldEvidence`, `batch_runner.py` e `analysis_pipeline.py` propagam quote/rects/método e escrevem `evidencias-visuais.json`. Retângulos só são emitidos quando a ocorrência é única e normalizada; repetição ambígua fica sem destaque. O JSON v1 da extensão continua sem coordenadas.

`extract_pdf_pages(..., return_geometry=True)` agora devolve texto e geometria do mesmo passe TSV do Tesseract para páginas escaneadas; o `batch_runner` consome esse retorno e não faz uma segunda chamada de OCR para montar as caixas. `cache-ocr-geometria.json` é separado do cache de texto e é invalidado por hash do PDF, versão geométrica e runtime OCR. O `run_local_pipeline` e `analyze_process` repassam esse cache ao batch; quando válido, páginas e caixas são reutilizadas sem novo OCR. A compatibilidade com adaptadores antigos permanece em fallback nativo, sem iniciar OCR adicional.

### Fase 4 — mesa offline

Criados `portable/app/web/review-app.js`, `pdf-viewer.js`, `review.css`, `web/package.json`, `web/vendor/pdfjs/{pdf.mjs,pdf.worker.mjs,LICENSE,manifest.json,README.md}` e `test_review_assets.py`. Alterado `html_generator.py` para:

- expor identidade documental estável (`document_id`/hash) na mesa;
- consumir o sidecar visual sem inserir dados extras no exportador v1;
- usar PDF.js local fixado com fallback explícito para iframe nativo;
- abrir evidência por `document_id + page`, nunca por número de evento isolado;
- preservar busca, ordem, marca manual e modo offline; quando servido pelo helper, o controle de feito usa a mesma API de progresso da extensão e reverte em conflito/erro.

PDF.js está fixado em 5.7.284 com hashes no manifesto e origem oficial da release; não há CDN ou `latest` flutuante.

### Fase 5 — bridge da extensão

Criado `portable/extensao-complementar-ato/lib/bridge-client.js` e seu teste; manifest agora permite somente o portal e `http://127.0.0.1/*`. O painel tem pareamento opcional em `chrome.storage.session`, publicação de seleção com `sequence` monotônica, sincronização de datasets por revisão, conclusão via API local e fallback manual. A publicação nunca chama preenchimento; seleção e conclusão usam revisões distintas para não gerar conflito falso. A mesa HTML servida pelo helper usa o mesmo endpoint `/api/v1/progress/<processo>` para o controle Concluído; no modo `file:` mantém persistência local. Artefato atualizado: `artifacts/extensao-complementar-ato-2026-09-08-v3.zip`.

### Fase 6 — publicação incremental

Criado `portable/app/incremental_pipeline.py` e teste; criadas as opções `-ModoPreparacao progressivo|completo` e `-MaxDownloads 1..2`, com publicação atômica por processo e retenção da revisão atual/anterior. `analyze_process` filtra o índice antes do OCR, publica `preparando` e depois o resultado em revisão própria. Cada revisão final também materializa `review-data.json` sanitizado e `dataset.json`; o serviço expõe `/api/v1/review-data?since=N`. A mesa servida em `/review` é aberta pelo menu com bootstrap de uso único, consulta revisões a cada 500 ms visível/2 s oculta e preserva processo, interessado, documento e viewport quando possível. O acompanhamento também lê `/api/v1/state` pela sessão autenticada, segue a seleção publicada pela extensão, pausa quando o usuário navega manualmente e oferece retomada explícita; falhas usam backoff limitado a 10 s. O coletor agora chama essa preparação por processo no modo progressivo e depois da varredura no modo completo, usando o runtime explícito; o menu pergunta o modo e mantém a abertura da mesa após a etapa completa. `Sync-TceProcessManifest` usa runspaces somente para o downloader quando recebe contexto explícito isolável; o pico efetivo é limitado a 1–2 e hash/deduplicação/versões/checkpoint permanecem no coordenador. O token de sessão passa apenas em memória. A política de download trata 429 com `Retry-After` e no máximo três tentativas, reduz chamadas posteriores a um worker, retorna 401/403 como `auth_required`/`suspended`, mantém 400 sem retry e faz o coletor parar/solicitar login sem continuar análise de processos não coletados.

### Fase 7 — transporte

Criados `portable/app/prepare_transfer.py` e `test_prepare_transfer.py`; allowlists, auditoria, empacotadores e `TESTAR-PACOTE.ps1` incluem o bridge, sidecar, viewer e licença PDF.js, excluindo `dados-locais`, perfis, credenciais, `.part` e logs privados. Foi criado `empacotar-extensao-complementar-ato.ps1` com allowlist explícita e verificação CRC/entradas para reproduzir o ZIP somente da extensão. Cada revisão incremental também materializa `dataset.json` validável; o README portátil documenta modos progressivo/completo, pareamento, fallback e pesquisa manual. A transferência agora grava `transfer-request.json`, pausa novos escritores, aguarda o coletor/serviço liberar seus marcadores até 60 s, adquire o lease após a drenagem e libera solicitação/lease em `finally`.

### Fase 8 — QA seguro

Criados `qa_integrated_workflow.py` e `test_integrated_workflow.py`. O relatório exige `--fixture-only` e informa explicitamente `portal_login=not-run` e `portal_submission=not-run`; QA em Chrome/portal, medição humana de 20 processos, screenshot com dados pessoais e teste em segundo PC continuam checkpoints supervisionados.

## QA manual no Chrome separado — 08/09/2026

O Chrome aberto pelo projeto permaneceu conectado em CDP `127.0.0.1:63097`, sem ser fechado pelo agente. O usuário autenticou a sessão; as páginas de e-Contas e Área Restrita estavam abertas. A extensão foi instalada manualmente a partir de:

`work/tce-extractor/qa-extracted-portable-acervo-v2-20260908/extensao-complementar-ato`

Foi usado o formulário real da Área Restrita para `101440/2026`, interessado `MARIA DO SOCORRO LOPES DE SOUZA`, com os campos documentais vazios antes do teste.

- importação do lote no painel: 227 processos e 235 interessados;
- prévia real carregada, com as fontes de evidência exibidas e os botões `Preencher campos disponíveis` e `Sinalizar Complementar Ato` habilitados;
- pesquisa por número `101440`: 1 resultado, seleção correta;
- pesquisa por nome `MARIA DO SOCORRO`: 2 resultados, com seleção correta do registro `101440/2026`;
- a mensagem da pesquisa informa que ela não altera o formulário;
- o botão `Sinalizar Complementar Ato` despachou exatamente um evento no frame real, com `processKey=101440/2026` e `interestedNormalized=maria do socorro lopes de souza`;
- após o sinal, os campos documentais permaneceram vazios/inalterados e o painel confirmou: `Sinal enviado à área restrita; nenhuma ação final foi executada pela extensão`;
- não foram clicados envio, assinatura, tramitação ou finalização.

O primeiro smoke após a instalação exigiu recarregar somente o frame do formulário, que estava sem edição pendente, e clicar `Atualizar prévia`: a extensão havia sido instalada depois de a página já estar aberta e ainda não tinha content script naquele documento. Depois disso a descoberta do frame e a prévia ficaram funcionais.

Evidência visual fixture-only em 900×1440: `C:\Users\slvma\.codex\visualizations\2026\09\08\01a08073-a0f7-7c53-a436-ec585e281a5a\qa-html-extracted-900x1440.png`. O runtime confirmou splitter em 52%, PDF selecionado, persistência de `Concluído` após reload e ausência de overflow horizontal da raiz. Essa evidência não substitui os gates ainda pendentes de zoom/rotação, dois PDFs em abas e portal real.

## Verificação mais recente

### Pacote portátil completo montado a partir do acervo fornecido

Em 08/09/2026 foi usado, somente como fonte de leitura, o diretório fornecido pelo usuário:

`C:\Users\slvma\Downloads\Github\Complementação de Atos\TCE-Acervo-Atualizado-227-2026-09-05 - v2`

Esse snapshot não é o lote mais recente, mas contém os PDFs necessários. O staging foi montado com o código atual, a extensão atualizada, o runtime portátil dessa cópia e o `acervo-tce` fornecido. O diretório de origem não foi alterado.

- fonte: 227 processos, 4.532 PDFs, aproximadamente 2,08 GB;
- `dados-complementar-ato.json`: reprojetado pelo `portable/app/extension_exporter.py` atual e validado; 227 processos e 235 registros;
- `ordem-portal.json`: derivado da ordem do `indice-local.json` fornecido;
- `progresso.json`: criado com revisão 0 e todos os processos não concluídos, pois a fonte não trazia um progresso humano válido;
- `indice-classificado.json`: removidos somente `absolute_path` herdados do computador de origem;
- `pdfs-alvo-manifest.json`: `pdf_path` absolutos substituídos pelos `relative_path` locais; 460 referências reescritas, 0 ausentes;
- pacote não contém `dados-locais`, bridge, credenciais, perfil de navegador, `downloads`, `.part` ou `.tmp`.

Artefato:

- ZIP: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\pacote-portatil-completo-2026-09-08-acervo-2026-09-05-v2.zip`;
- tamanho: 1.738.370.102 bytes;
- 10.276 entradas, 227 `processo.json`, 5.236 `evento.json` e 4.532 PDFs;
- SHA-256: `19B38B1E808B84860C425B94CB7A70DE79C8C21998BE0817DD6C911968CF4E92`;
- CRC verificado e auditoria privada verde.

QA do ZIP extraído em pasta nova com espaços/acentos, com Python e Node removidos do `PATH`:

- runtime interno Python/Tesseract: passou;
- Manifest V3 e arquivos declarados: passou;
- dependência Node no destino: passou, Node não necessário;
- dataset v1 e auditoria privada: passou;
- comando: `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File TESTAR-PACOTE.ps1 -PackageRoot <extraído>`;
- extração: `work/tce-extractor/qa-extracted-portable-acervo-v2-20260908`.

Esse resultado comprova um pacote portátil completo baseado no snapshot fornecido, não a atualização do acervo perante o portal nem o QA funcional no portal real.

| Gate | Resultado |
|---|---:|
| `node --test` em `portable/extensao-complementar-ato` | 124 pass, 0 falhas, 0 skips |
| `node --test` em `portable/app/web` | 5 pass, 0 falhas |
| `C:\Python314\python.exe -m unittest discover -s . -p 'test_*.py' -q` | 284 pass, 0 falhas, 5 skips |
| pacote/auditoria/end-to-end + transferência quiescente | 47 pass, 0 falhas, 2 skips |
| `tests/Test-TcePortable.ps1` | 114 pass, 0 falhas |
| `tests/Test-PortableMenu.ps1` | 74 pass, 0 falhas |
| `tests/Test-PortableReset.ps1` | 31 pass, 0 falhas, 1 skip ambiental |
| teste focado estado/sessão + ativos da mesa | 2 pass, 0 falhas |
| `qa_integrated_workflow.py --project-root . --fixture-only` | passed; login/submission not-run |
| QA manual Chrome separado: busca por processo/nome + sinal no formulário real | pass; 1 evento capturado, campos documentais inalterados, sem envio/finalização |
| `test_integrated_workflow.py` após QA | 2 pass, 0 falhas |
| subconjunto browser/reset/runtime | 15 pass, 0 falhas |
| sessão da mesa gravando progresso pelo cookie | 1 pass, 0 falhas |
| smoke Chrome contra ZIP v3 extraído em pasta temporária | pass; Chrome 145; 7 linhas, persistência após restart, controles protegidos intactos |
| `test_extension_zip_packager.py` + empacotamento oficial | 1 pass; 11 arquivos, CRC verificado |
| smoke Chrome contra ZIP v4 oficial extraído | pass; Chrome 145; 7 linhas, persistência após restart, controles protegidos intactos |
| `empacotar-extensao-complementar-ato.ps1` | ZIP v4 reproduzível; 11 arquivos; SHA-256 `8B0BBBA8131EA1D9B8156AAC60D374A85ED1D16D2AF1B55C77D1809ADCF61E46` |
| `empacotar-extensao-complementar-ato.ps1` após a auditoria final | ZIP v5 reproduzível; 11 arquivos; SHA-256 `4CA334FECA7483B44429C12C6A6DFAAB126202F03D64F3296B3463F33B019E98` |
| `test_review_live_browser.py` | seleção publicada, pausa/retomada e entrega em menos de 2 s; 1 pass |
| pacote portátil completo com acervo fornecido | 10.276 entradas, 4.532 PDFs, CRC/auditoria verdes; SHA-256 registrado acima |
| `TESTAR-PACOTE.ps1` no ZIP extraído sem Python/Node no `PATH` | 7 gates passaram; runtime interno, dataset, manifest, Node e auditoria |

O handoff de retry/autenticação registra também três repetições do teste PowerShell (114/114), sem acesso ao portal real. O contrato mantém tokens fora de erros, resultados e checkpoints; a parada é cooperativa e deixa requests já iniciados terminarem.

O Python exibiu apenas avisos ResourceWarning dos testes de erro HTTP e a mensagem de uso deliberada do caso `--timeout-seconds 0`; a suíte terminou verde. Os skips ambientais/fixture não validam OCR real, bridge em navegador ou portal.

## Artefato isolado solicitado

Gerado por subagent Luna xhigh e conferido novamente no checkout:

- ZIP: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\extensao-complementar-ato-2026-09-08-v2.zip`
- SHA-256: `936472A38C70E21A184B2EF0961E659FAA7675655E2592F0E1C23B24777BE859`
- 11 arquivos, todos sob `extensao-complementar-ato/`, 0 entradas fora do escopo;
- inclui `lib/bridge-client.js`, botão/sinal, pesquisa, manifest e fontes de serviço;
- não inclui `package.json`, testes, `docs`, `work` ou acervo;
- handoff específico: `docs/notes/2026-09-08-extensao-complementar-ato-empacotamento-v2-handoff.md`.

Versão atualizada após o bridge incremental:

- ZIP: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\extensao-complementar-ato-2026-09-08-v3.zip`
- SHA-256: `8B0BBBA8131EA1D9B8156AAC60D374A85ED1D16D2AF1B55C77D1809ADCF61E46`
- handoff: `docs/notes/2026-09-08-extensao-complementar-ato-empacotamento-v3-handoff.md`.

Versão reproduzível pelo empacotador oficial:

- ZIP: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\extensao-complementar-ato-2026-09-08-v4.zip`
- SHA-256: `8B0BBBA8131EA1D9B8156AAC60D374A85ED1D16D2AF1B55C77D1809ADCF61E46`
- gerado por `work/tce-extractor/empacotar-extensao-complementar-ato.ps1`; 11 entradas allowlisted, sem `package.json`, testes ou documentação.
- handoff específico: `docs/notes/2026-09-08-extensao-complementar-ato-empacotamento-v4-handoff.md`.

Versão atual após a auditoria do bridge, serviço e preservação de `Revisado`:

- ZIP: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\extensao-complementar-ato-2026-09-08-v5.zip`
- tamanho: 34.364 bytes; 11 entradas; CRC verificado
- SHA-256: `4CA334FECA7483B44429C12C6A6DFAAB126202F03D64F3296B3463F33B019E98`
- handoff específico: `docs/notes/2026-09-08-bridge-servico-geometria-empacotamento-handoff.md`.

O ZIP anterior foi preservado em `artifacts/extensao-complementar-ato-2026-09-08.zip`.

## Auditoria de montagens antigas

Foi executado `python portable/app/package_audit.py staging-final --distribution private` apenas em leitura. A montagem histórica `staging-final` foi reprovada por conter `downloads/` privados, referências de PyMuPDF ausentes/divergentes e ausência de `acervo-tce/dados-complementar-ato.json`; ela não é o ZIP v4/v5, não foi corrigida nem removida. O ZIP v5 da extensão foi auditado separadamente e passou: 11 entradas, 0 fora de `extensao-complementar-ato/`, CRC válido e teste do empacotador verde. O smoke Chrome do ZIP v4 continua sendo a última evidência de navegador extraído; o v5 ainda não teve smoke em Chrome.

## GitHub / retomada

- `git remote -v`: sem remoto configurado.
- commit desta continuação: `e2d2016 feat: complete portable review package gates`; árvore limpa após o registro documental.
- Commits locais relevantes: `f2c770b feat: sync incremental bridge datasets`, `9b9a473 feat: serve live portable review revisions`, `ca1e372 feat: follow live portal selection in review desk`, `4d0153c fix: synchronize review completion with local service`, `cefcdfc docs: record extracted extension smoke`, `c14580a docs: clarify shared portable completion state`, `a0424ac build: add reproducible extension-only package`, `50830bd test: verify live review selection in browser`, `6c88d2a fix: block transfer during active portable operations`, `3b24678 feat: harden portable download retries and auth`, `e041a93 feat: harden portable bridge and package validation`, `42fef65 feat: close portable security and transfer gaps` e `141db71 docs: record portable archive package validation`.
- Push não executado porque não há `origin` configurado.
- O bloco de acompanhamento da seleção e a conclusão compartilhada foram implementados em `html_generator.py` e `portable/app/local_service.py`, com RED→GREEN em `test_local_service.py` e `test_review_assets.py`; a implementação está em `4d0153c` e a evidência do ZIP extraído foi registrada nos commits de documentação.
- Na primeira execução da suíte Python completa após um smoke concorrente, três testes do supervisor apresentaram falhas intermitentes e processos ainda vivos; os três casos passaram isoladamente, a suíte `test_qa_extension_runtime` passou 7/7 e novas execuções completas passaram 249/249 e 250/250. Nenhum ajuste foi feito no supervisor; o comportamento transitório fica registrado para retomada se voltar a ocorrer.
- O teste browser local `test_review_live_browser.py` confirma a seleção publicada pelo bridge, pausa manual e retomada em sessão autenticada; não acessa o portal real.
- A continuação adiciona 6 testes focados de segurança/seleção/colisão/drenagem; o protocolo publica `transfer-request.json`, pausa novos escritores e aguarda o marcador ativo até 60 s. `BridgeAuth`, CSRF da mesa e exportador de identidade têm cobertura RED→GREEN.

Pendências reais para chamar de release validada:

1. concluir os gates integrados de preenchimento em fixture e portal, HTML em outra janela acompanhando seleção em até 2 s, pause/resume, dois PDFs em abas, zoom/rotação, sete links de evidência e `Concluído` sem navegação;
2. medir os mesmos 20 processos e p95 de sincronização, registrando hardware/rede/modo;
3. repetir os gates de serviço bloqueado/fallback, retomada após 401/403 e pacote extraído em ambiente restrito; o smoke sem Python/Node no `PATH` já passou, mas não substitui todos esses cenários.

O gate de segundo PC foi dispensado explicitamente pelo usuário e não será executado.

Para continuar: executar os gates integrados restantes no mesmo Chrome separado, sem envio/finalização. O pacote portátil completo agora existe a partir do snapshot fornecido, mas o snapshot é de 05/09/2026 e não deve ser tratado como acervo atualizado; uma nova coleta poderá substituir apenas os dados locais quando autorizada. Preparar commit/push somente quando o QA externo terminar e um remoto autorizado existir. Rechecar `git status` antes de retomar.

## Atualização posterior — pacote v5, mesa responsiva e controles PDF

Foi encontrado e corrigido um defeito de distribuição: o snapshot antigo de `acervo-tce/complementar-ato.html` podia ser copiado para o ZIP mesmo quando `app/html_generator.py` já estava atualizado. `package_complete_archive.py` agora regenera somente a cópia em staging do HTML privado quando os metadados de extração estão presentes; a pasta fonte e o acervo fornecido não são alterados. Há teste RED→GREEN para preservar o HTML fonte e verificar `follow-toggle`/metadados da mesa no ZIP.

Também foi corrigido o layout em 900×1440: o botão de acompanhamento não invade os indicadores superiores. A mesa agora expõe controles integrados de reduzir/aumentar zoom, girar em quartos de volta e restaurar a visualização. `pdf-viewer.js` aplica escala limitada de 75% a 300% e rotação normalizada; o teste do adaptador confirma que esses valores chegam ao viewport PDF.js.

Os assets planejados de `portable/app/web` passaram a ser explicitamente versionáveis no `.gitignore`, incluindo o adaptador, seleção, CSS, testes e PDF.js local fixado/licenciado. Acervo, PDFs, ZIPs e perfis continuam ignorados.

### Pacote privado corrente

- ZIP: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\pacote-portatil-completo-2026-09-08-acervo-2026-09-05-v5.zip`
- tamanho: 1.739.036.007 bytes; 10.276 entradas; 227 processos; 5.236 eventos; 4.532 PDFs; 235 registros da extensão;
- SHA-256: `9D3E693B6D590A93CE6FF8073766242004F1A4E76429F54D1F8CFF2040BA8EAF`;
- CRC, auditoria privada, manifesto e runtime interno verdes;
- extração: `work/tce-extractor/qa-extracted-portable-acervo-v2-20260908-v5`.

### QA do HTML extraído

O utilitário `work/tce-extractor/qa_html_gates.py` foi executado contra o HTML do ZIP v5 extraído em Chrome headless 145, viewport 900×1440. No processo `102885/2023`, confirmou seleção manual pausando/retomando acompanhamento, zoom 150%→175%, rotação 90° e reset 150%/0°, seis fontes com resolução para PDF/página, a pendência de gênero explicitamente sem evidência, dois documentos distintos em duas páginas/abas, e `Concluído` persistido após reload sem navegação. O screenshot final está fora do Git em `C:\Users\slvma\.codex\visualizations\2026\09\08\01a08073-a0f7-7c53-a436-ec585e281a5a\qa-html-gates-extracted-v5-zoom-rotation-900x1440.png`.

### Testes mais recentes

| Comando | Resultado |
|---|---:|
| `node --test portable/extensao-complementar-ato/tests/*.test.mjs` | 124 pass, 0 falhas, 0 skips |
| `node --test portable/app/web/tests/*.test.mjs` | 6 pass, 0 falhas |
| `C:\Python314\python.exe -m unittest discover -s . -p 'test_*.py' -q` | 285 pass, 0 falhas, 5 skips |
| `tests/Test-TcePortable.ps1` | 114 pass, 0 falhas |
| `tests/Test-PortableMenu.ps1` | 74 pass, 0 falhas |
| `tests/Test-PortableReset.ps1` | 31 pass, 0 falhas, 1 skip ambiental |
| `TESTAR-PACOTE.ps1` no v5 extraído sem Python/Node no PATH | 7 gates passaram |
| `qa_html_gates.py` no v5 extraído | passou; zoom/rotação/evidências/abas/conclusão |

Os testes PowerShell foram executados com Windows PowerShell 5.1 explícito. Os avisos ResourceWarning e o caso deliberado de timeout permanecem esperados; não houve falha.

### Estado de release após esta atualização

Os gates de layout 900×1440, controles de zoom/rotação, HTML regenerado no pacote, persistência de conclusão sem navegação e validação extraída estão comprovados. Continuam pendentes: benchmark dos mesmos 20 processos com p95, gate geométrico em PDF escaneado/rotacionado/hash modificado/checkpoint, teste do serviço bloqueado/fallback e o gate completo de preenchimento na fixture/portal real. A validação manual no Chrome separado permanece limitada à pesquisa por processo/nome e sinal real sem alteração dos campos e sem envio/finalização. Portanto o resultado continua sendo candidato integrado, não release portátil validada.
