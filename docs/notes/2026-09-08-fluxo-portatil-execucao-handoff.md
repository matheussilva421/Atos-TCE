# Handoff — execução do fluxo portátil integrado — 08/09/2026

## Estado atual

Implementação local do plano `docs/notes/2026-09-08-fluxo-portatil-plano-implementacao.md` avançada até um candidato integrado. O checkout continua em `main`; a última etapa local adiciona retry/autenticação sanitizados à coleta, documentada também em `docs/notes/2026-09-08-retry-autenticacao-coleta-handoff.md`. Não há push por falta de remoto `origin`. Não houve login, coleta real, envio de ato, instalação no Chrome, alteração de acervo pessoal ou exclusão de arquivos.

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

Criados `portable/app/prepare_transfer.py` e `test_prepare_transfer.py`; allowlists, auditoria, empacotadores e `TESTAR-PACOTE.ps1` incluem o bridge, sidecar, viewer e licença PDF.js, excluindo `dados-locais`, perfis, credenciais, `.part` e logs privados. Foi criado `empacotar-extensao-complementar-ato.ps1` com allowlist explícita e verificação CRC/entradas para reproduzir o ZIP somente da extensão. Cada revisão incremental também materializa `dataset.json` validável; o README portátil documenta modos progressivo/completo, pareamento, fallback e pesquisa manual. A transferência agora compartilha um lease exclusivo com o coletor e o serviço: recusa snapshot enquanto houver execução ativa, recupera marcadores obsoletos por PID morto e libera o lease em `finally`; detalhes em `docs/notes/2026-09-08-transferencia-quiescente-handoff.md`.

### Fase 8 — QA seguro

Criados `qa_integrated_workflow.py` e `test_integrated_workflow.py`. O relatório exige `--fixture-only` e informa explicitamente `portal_login=not-run` e `portal_submission=not-run`; QA em Chrome/portal, medição humana de 20 processos, screenshot com dados pessoais e teste em segundo PC continuam checkpoints supervisionados.

## Verificação mais recente

| Gate | Resultado |
|---|---:|
| `node --test` em `portable/extensao-complementar-ato` | 118 pass, 0 falhas, 0 skips |
| `node --test` em `portable/app/web` | 4 pass, 0 falhas |
| `python -m unittest discover -s . -p 'test_*.py' -q` | 254 pass, 0 falhas, 3 skips |
| pacote/auditoria/end-to-end + transferência quiescente | 47 pass, 0 falhas, 2 skips |
| `tests/Test-TcePortable.ps1` | 114 pass, 0 falhas |
| `tests/Test-PortableMenu.ps1` | 74 pass, 0 falhas |
| `tests/Test-PortableReset.ps1` | 31 pass, 0 falhas, 1 skip ambiental |
| teste focado estado/sessão + ativos da mesa | 2 pass, 0 falhas |
| `qa_integrated_workflow.py --project-root . --fixture-only` | passed; login/submission not-run |
| subconjunto browser/reset/runtime | 15 pass, 0 falhas |
| sessão da mesa gravando progresso pelo cookie | 1 pass, 0 falhas |
| smoke Chrome contra ZIP v3 extraído em pasta temporária | pass; Chrome 145; 7 linhas, persistência após restart, controles protegidos intactos |
| `test_extension_zip_packager.py` + empacotamento oficial | 1 pass; 11 arquivos, CRC verificado |
| smoke Chrome contra ZIP v4 oficial extraído | pass; Chrome 145; 7 linhas, persistência após restart, controles protegidos intactos |
| `empacotar-extensao-complementar-ato.ps1` | ZIP v4 reproduzível; 11 arquivos; SHA-256 `8B0BBBA8131EA1D9B8156AAC60D374A85ED1D16D2AF1B55C77D1809ADCF61E46` |
| `test_review_live_browser.py` | seleção publicada, pausa/retomada e entrega em menos de 2 s; 1 pass |

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

O ZIP anterior foi preservado em `artifacts/extensao-complementar-ato-2026-09-08.zip`.

## Auditoria de montagens antigas

Foi executado `python portable/app/package_audit.py staging-final --distribution private` apenas em leitura. A montagem histórica `staging-final` foi reprovada por conter `downloads/` privados, referências de PyMuPDF ausentes/divergentes e ausência de `acervo-tce/dados-complementar-ato.json`; ela não é o ZIP v4, não foi corrigida nem removida. O ZIP v4 da extensão foi auditado separadamente e passou: 11 entradas, 0 fora de `extensao-complementar-ato/`, seguido de smoke Chrome após extração.

## GitHub / retomada

- `git remote -v`: sem remoto configurado.
- Commits locais relevantes: `f2c770b feat: sync incremental bridge datasets`, `9b9a473 feat: serve live portable review revisions`, `ca1e372 feat: follow live portal selection in review desk`, `4d0153c fix: synchronize review completion with local service`, `cefcdfc docs: record extracted extension smoke`, `c14580a docs: clarify shared portable completion state`, `a0424ac build: add reproducible extension-only package`, `50830bd test: verify live review selection in browser` e `6c88d2a fix: block transfer during active portable operations`.
- Push não executado porque não há `origin` configurado.
- O bloco de acompanhamento da seleção e a conclusão compartilhada foram implementados em `html_generator.py` e `portable/app/local_service.py`, com RED→GREEN em `test_local_service.py` e `test_review_assets.py`; a implementação está em `4d0153c` e a evidência do ZIP extraído foi registrada nos commits de documentação.
- Na primeira execução da suíte Python completa após um smoke concorrente, três testes do supervisor apresentaram falhas intermitentes e processos ainda vivos; os três casos passaram isoladamente, a suíte `test_qa_extension_runtime` passou 7/7 e novas execuções completas passaram 249/249 e 250/250. Nenhum ajuste foi feito no supervisor; o comportamento transitório fica registrado para retomada se voltar a ocorrer.
- O teste browser local `test_review_live_browser.py` confirma a seleção publicada pelo bridge, pausa manual e retomada em sessão autenticada; não acessa o portal real.
- A correção `6c88d2a` adiciona lease compartilhado entre `prepare_transfer`, coletor e serviço; 16 testes focados Python cobrem serviço/auth/transferência, incluindo recusa de runtime ativo, recuperação de lock obsoleto e liberação após falha de build.

Pendências reais para chamar de release validada:

1. executar QA manual em Chrome/Área Restrita com usuário autenticado, sem envio/finalização;
2. medir os mesmos 20 processos e p95 de sincronização, e repetir o teste sobre ZIP extraído em ambiente restrito;
3. obter autorização humana para segundo PC, se esse gate for necessário.
4. validar em ambiente restrito a retomada após 401/403 e o comportamento do ZIP extraído sem Python/Node no `PATH`.

Para continuar: executar os gates supervisionados acima, validar o ZIP v4 pelo empacotador oficial, e só então preparar push quando um remoto autorizado existir. A API de transferência usa recusa segura em vez de drenagem formal do coordenador; essa limitação permanece documentada. Rechecar `git status` antes de retomar.
