# Handoff — execução do fluxo portátil integrado — 08/09/2026

## Estado atual

Implementação local do plano `docs/notes/2026-09-08-fluxo-portatil-plano-implementacao.md` avançada até um candidato integrado. O checkout continua em `main`, sem commit ou push. Não houve login, coleta real, envio de ato, instalação no Chrome, alteração de acervo pessoal ou exclusão de arquivos.

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
- preservar busca, ordem, marca manual e modo offline.

PDF.js está fixado em 5.7.284 com hashes no manifesto e origem oficial da release; não há CDN ou `latest` flutuante.

### Fase 5 — bridge da extensão

Criado `portable/extensao-complementar-ato/lib/bridge-client.js` e seu teste; manifest agora permite somente o portal e `http://127.0.0.1/*`. O painel tem pareamento opcional em `chrome.storage.session`, publicação de seleção com `sequence` monotônica, sincronização de datasets por revisão, conclusão via API local e fallback manual. A publicação nunca chama preenchimento; seleção e conclusão usam revisões distintas para não gerar conflito falso. Artefato atualizado: `artifacts/extensao-complementar-ato-2026-09-08-v3.zip`.

### Fase 6 — publicação incremental

Criado `portable/app/incremental_pipeline.py` e teste; criadas as opções `-ModoPreparacao progressivo|completo` e `-MaxDownloads 1..2`, com publicação atômica por processo e retenção da revisão atual/anterior. `analyze_process` filtra o índice antes do OCR, publica `preparando` e depois o resultado em revisão própria. Cada revisão final também materializa `review-data.json` sanitizado e `dataset.json`; o serviço expõe `/api/v1/review-data?since=N`. A mesa servida em `/review` é aberta pelo menu com bootstrap de uso único, consulta revisões a cada 500 ms visível/2 s oculta e preserva processo, interessado, documento e viewport quando possível. O coletor agora chama essa preparação por processo no modo progressivo e depois da varredura no modo completo, usando o runtime explícito; o menu pergunta o modo e mantém a abertura da mesa após a etapa completa. `Sync-TceProcessManifest` usa runspaces somente para o downloader quando recebe contexto explícito isolável; o pico efetivo é limitado a 1–2 e hash/deduplicação/versões/checkpoint permanecem no coordenador. O token de sessão passa apenas em memória.

### Fase 7 — transporte

Criados `portable/app/prepare_transfer.py` e `test_prepare_transfer.py`; allowlists, auditoria, empacotadores e `TESTAR-PACOTE.ps1` incluem o bridge, sidecar, viewer e licença PDF.js, excluindo `dados-locais`, perfis, credenciais, `.part` e logs privados. Cada revisão incremental também materializa `dataset.json` validável; o README portátil documenta modos progressivo/completo, pareamento, fallback e pesquisa manual.

### Fase 8 — QA seguro

Criados `qa_integrated_workflow.py` e `test_integrated_workflow.py`. O relatório exige `--fixture-only` e informa explicitamente `portal_login=not-run` e `portal_submission=not-run`; QA em Chrome/portal, medição humana de 20 processos, screenshot com dados pessoais e teste em segundo PC continuam checkpoints supervisionados.

## Verificação mais recente

| Gate | Resultado |
|---|---:|
| `node --test` em `portable/extensao-complementar-ato` | 118 pass, 0 falhas, 0 skips |
| `node --test` em `portable/app/web` | 4 pass, 0 falhas |
| `python -m unittest discover -s . -p 'test_*.py' -q` | 248 pass, 0 falhas, 3 skips |
| pacote/auditoria/end-to-end (`test_package_audit test_portable_end_to_end test_prepare_transfer test_integrated_workflow`) | 43 pass, 0 falhas, 2 skips |
| `tests/Test-TcePortable.ps1` | 83 pass, 0 falhas |
| `tests/Test-PortableMenu.ps1` | 73 pass, 0 falhas |
| `tests/Test-PortableReset.ps1` | 31 pass, 0 falhas, 1 skip ambiental |

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

O ZIP anterior foi preservado em `artifacts/extensao-complementar-ato-2026-09-08.zip`.

## GitHub / retomada

- `git remote -v`: sem remoto configurado.
- Commit local: `feat: integrate portable workflow and extension bridge` (hash atual disponível em `git log -1`).
- Push não executado porque não há `origin` configurado.
- O working tree recebeu a implementação da sessão HTML/revisão incremental; o lock observado durante a execução não está mais presente. Após o commit desta etapa, verifique novamente o status.

Pendências reais para chamar de release validada:

1. executar QA manual em Chrome/Área Restrita com usuário autenticado, sem envio/finalização;
2. medir os mesmos 20 processos e p95 de sincronização, e repetir o teste sobre ZIP extraído em ambiente restrito;
3. obter autorização humana para segundo PC, se esse gate for necessário.

Para continuar: preservar as alterações atuais, executar os gates acima, validar o ZIP v2 por `Get-FileHash`, e só então preparar commit/push se um remoto autorizado existir.
