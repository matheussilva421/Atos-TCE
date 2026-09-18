# Handoff — Refatoração da Mesa Local (M1 → M6)

**Data:** 2026-09-18
**Branch:** `codex/mesa-local-refactor`
**Planos de referência:**
- `docs/superpowers/plans/2026-09-18-atos-tce-plano-completo.md`
- `docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md`

## 1. Objetivo

Transformar a Mesa Local no único centro de workflow e estado do sistema,
substituindo gradualmente menu PowerShell, serviço local, HTML gerado e
sidepanel. A migração é um *strangler refactor*: o fluxo legado continua
operacional como fallback até o último marco. O clique final de complementação
do ato permanece humano em todos os marcos (`autoSubmit=false`,
`real_send_enabled=false`).

## 2. Decisões técnicas já tomadas

| Decisão | Motivo |
|---|---|
| Trabalhar na branch `codex/mesa-local-refactor` no checkout principal, não em worktree | Os dados privados ignorados (`work/tce-extractor/acervo-tce`, `Versions/`, `outputs/`, `dados-locais/`) só existem neste checkout; M1 Task 6 e M6 auditam esses caminhos |
| `data/` na raiz como raiz de runtime, ignorada pelo Git | Separação código / dados / distribuição exigida pelo design (§10) |
| Blob canônico = cópia verificada de bytes; visão de processo = hardlink ao blob | É o texto do plano (M1 Task 3, Step 3 e Step 4) e o gate de espaço livre pressupõe uma cópia real |
| `documents.relative_path` é relativo à `data_root` (`archive/processos/...`) | Deixa a resolução da API inequívoca e sempre sob `data_root` |
| Processos importados em M1 nascem `PENDENTE` | O estado real vem da varredura da Área Restrita (M2) e da análise (M4). Evita o risco de um `PRONTO` local bloquear a regra fail-closed de M2 (`PRECISA_COMPLEMENTAR -> PENDENTE`, salvo estado mais avançado) |
| Status legado do registro (`partial`) é preservado no evento `legacy_import`, não como status novo | Conserva informação sem inventar política de workflow antes de M4 |
| Normalização canônica de interessado em `app/core/identity.py` | A chave natural `(process_key, interested_normalized)` precisa ser idêntica no importador Python e no scanner JS; a regra vem de `analysis_pipeline._normalise_interested` / `automation-schema.js` |
| Nomes truncados com acento usam forma canônica recalculada; divergência vira aviso no recibo | Garante que a identidade do importador casa com a identidade que a extensão vai produzir em M2 |
| Documentos são vinculados a cada linha `(process_key, interested)` do processo | 724 pastas e 739 registros: 15 chaves têm mais de um interessado e cada linha precisa ser autocontida para o preenchimento |
| Servidor HTTP só aceita bind em loopback | Invariante de segurança do master plan ("local write APIs require an authenticated Mesa loopback session") |

## 3. Estado das tarefas

### M1 — Foundation, SQLite and Read-Only Mesa

| Tarefa | Estado | Commit |
|---|---|---|
| 1. Root layout and Git safety | concluída | `46d37c4` |
| 2. SQLite schema v1 | concluída | `3d899b4` |
| 3. Safe legacy archive import + SHA-256 dedup | concluída | `0c454cd` |
| 4. Read-only Mesa API | concluída | `330968d` |
| 5. Read-only Mesa UI and launcher | concluída | `465cd11` |
| 6. Real archive migration rehearsal | concluída | `b5d8b14` |

#### Ensaio real do acervo (M1 Task 6)

Comando de ensaio (20 min, sem escrever blobs):

```
python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data
```

- 724 pastas de processo, 14.179 PDFs, 8.892.090.055 bytes.
- 14.179 hashes únicos, **0 duplicados**, **0 avisos**, **0 erros**, 0 blobs copiados.
- Todas as 724 pastas casaram com um registro de interessado: nenhum processo
  recebeu o interessado provisório.
- A normalização canônica de `app/core/identity.py` reproduziu exatamente o
  `interested.normalized` legado nos 739 registros (nenhum aviso de divergência).

Gate de espaço livre: `bytes_unique` (8,28 GiB) + 2 GiB = 10,28 GiB exige menos
que os 56,9 GB livres medidos antes do `--apply`.

Comando de efetivação (~10 min):

```
python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data --apply
```

- 14.179 blobs canônicos gravados (`data/archive/blobs/AA/<sha>.pdf`).
- 14.179 hardlinks em `data/archive/processos/...`; **0 fallback copies**, 0 bytes
  duplicados pela visão de processo.
- 739 linhas de processo e 14.483 linhas de documento (14.179 + 304 linhas
  repetidas nas 15 chaves com mais de um interessado).
- Recibo: `data/logs/legacy-import-20260918T123734Z.json` (`mode=apply`).

Verificação independente depois do `--apply`:

- origem: 14.179 PDFs e 8,28 GB — idêntica antes e depois;
- espaço livre em C: caiu de 56,9 GB para 48,7 GB (8,2 GB = só os blobs);
- Mesa em `--port 18753`: `/api/v1/health` com 739 processos, `/api/v1/storage`
  com 14.179 blobs / 14.483 documentos / 14.179 SHA-256 únicos e
  `deduplicated_bytes = 8.892.090.055` (medido por contagem de links reais);
- `/api/v1/processes/1` devolve 17 documentos com `sha256`, `source_id` legado
  (`100015/2026|7047389|informacao-3166843`) e 2 deles enriquecidos pelo
  `pdfs-alvo-manifest.json` (classificação e `page_count`).

"Duplicate PDFs are deduplicated by SHA-256" foi comprovado por teste de
fixture (2 cópias → 1 blob, 1 hardlink por visão). No acervo real esse contador
ficou em 0 porque os 14.179 PDFs de origem já eram todos distintos.

Regressão do projeto legado (gate obrigatório do AGENTS.md):

```
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
```

7 estágios, 1.251 comandos executados, 1.249 aprovados, **0 falharam**, 2 skips
(extensão 479, web 6, python portable 6, powershell 596, pacote 82, automação 81,
`git diff --check`). O fluxo legado continua íntegro.

### M1 Exit Gate — verde

| Critério | Evidência |
|---|---|
| SQLite schema v1 operacional | `Store.schema_version == 1`, 56 testes na raiz |
| Acervo atual importado sem remover a origem | 14.179 PDFs/8,28 GB intactos após o `--apply` |
| PDFs duplicados deduplicados por SHA-256 com árvore de processo por hardlink | 14.179 hardlinks, 0 fallback copies, `deduplicated_bytes` = 8,28 GB; prova de dedup em fixture |
| Processos reais visíveis na Mesa somente leitura | 739 processos e 14.483 documentos servidos pela API e pela UI |
| Fluxo legado intacto | `verify-project.ps1` 1.249/1.251 sem falha; nada em `work/tce-extractor/` foi alterado |

### M2 — Área Restrita Integration

| Tarefa | Estado | Commit |
|---|---|---|
| 1. SQLite schema v2 (scans + comandos) | concluída | `55fc9cb` |
| 2. Pareamento persistente e API autenticada | concluída | `5efd966` |
| 3. Scanner DOM puro extraído do legado | concluída | `7d47214` |
| 4. Extensão MV3 fina com polling | concluída | `7ba88d7` |
| 5. Fluxo "Analisar Área Restrita" na Mesa | concluída | `b13a65d` |
| 6. Fallback CDP somente leitura | concluída | — |

#### Decisões de M2

| Decisão | Motivo |
|---|---|
| `app/core/identity.py` é o dono Python da normalização e `extension/lib/area-snapshot.js` o espelho JS, com teste cruzado via Node | A chave natural precisa ser idêntica nos dois lados |
| `PORTAL_ROLES` mora em `app/area_restrita/__init__.py` e é importado pelo servidor | Um único dono do vocabulário do portal; snapshot com papel desconhecido nunca vira scan |
| `content/paging.js` concentra a paginação de M2 e será absorvido por `content/navigate.js` em M5 | O plano permite navegar paginação em M2, mas proíbe escrita de formulário |
| O servidor lê o corpo do POST **antes** de qualquer decisão de autorização | Responder enquanto o cliente escreve reinicia a conexão TCP no Windows em vez de entregar o status |
| `token_hash` é comparado com `hmac.compare_digest` | Comparação em tempo constante para o bearer da extensão |
| Código de pareamento é consumido no primeiro sucesso e o token é 32 bytes URL-safe | "um código devolve um token"; o código só aparece na Mesa enquanto nada está pareado |
| O contrato de snapshot exige `role` de uma lista fechada | Um payload malformado é registrado como resultado de comando, nunca persistido como scan |

#### M2 Exit Gate

| Critério | Evidência | Classificação |
|---|---|---|
| Clicar em "Analisar Área Restrita" inicia a varredura | `test_analyze_flow_persists_the_scan_and_updates_processes` cria o comando, a extensão reivindica, posta o snapshot e o scan é persistido | PASS_FIXTURE |
| A varredura da extensão é o caminho primário | Fila `extension_commands` + `SCAN_AREA`; o lado Mesa não lê o portal sozinho | PASS_FIXTURE |
| Resultado persistido em SQLite e estados atualizados | 3 processos com PENDENTE/1, `needs_complement`, `portal_act_id` e `CONCLUÍDO` verificados | PASS_FIXTURE |
| Pareamento acontece uma vez e sobrevive a reinícios | `test_token_survives_a_new_server_instance` (só o hash vai para o SQLite) | PASS_FIXTURE |
| Fallback CDP produz o mesmo esquema e não escreve no portal | Mesmo scanner JS, mesmo `Store.create_area_scan`, teste de fonte sem submit/finalizar e reconciliação de chaves | PASS_FIXTURE |
| Comando de aba do portal não existe ⇒ comando fica na fila | O snapshot só é produzido por aba autenticada; sem aba a extensão devolve erro e o comando continua visível | NOT_TESTED (real) |
| Varredura real: extensão × CDP no mesmo marcador | Requer login humano no portal | **BLOCKED (supervisionado)** |

Comparação real pendente (exige operador autenticado):

```
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\scripts\scan-area-cdp.ps1
```

Comparar `process_key` e contagens com uma varredura da extensão no mesmo
marcador. Diferenças bloqueiam a saída de M2 antes de M3 ser considerado
fechado. Exige Chrome aberto com `--remote-debugging-port` e Área Restrita
autenticada; nunca digitar credenciais por automação.

### M3 — e-Contas Acquisition Controlled by Mesa

| Tarefa | Estado | Commit |
|---|---|---|
| 1. Modelo de jobs de aquisição (schema v3) | concluída | `43f8d0a` |
| 2. Escritor da fila congelada compatível | concluída | `43f8d0a` |
| 3. Adaptador do coletor comprovado | concluída | `afbe02f` |
| 4. Coordenador e lotes internos automáticos | concluída | `afbe02f` |
| 5. API e controles de aquisição na Mesa | concluída | `40e0c18` |
| 6. Gate real supervisionado do e-Contas | BLOCKED (supervisionado) | — |

#### Decisões de M3

| Decisão | Motivo |
|---|---|
| A migração 2 -> 3 marca `acquisition_state='DOWNLOADED'` para processos que já têm documentos | Sem isso o acervo real de 739 processos apareceria como faltando baixar |
| O importador legado marca `DOWNLOADED` ao gravar documentos | Mantém a mesma verdade em reimportações |
| A fila congelada é escrita uma vez por plano e reescrita no início do run | O coletor valida `lots` na ordem da `queue`; reescrever garante o mesmo conteúdo após reinício |
| Toda linha do coletor passa por `redact` antes de ir para log ou para a Mesa | URLs, tokens e valores com cara de segredo nunca são persistidos |
| `-Selecao` e `-ServiceChild` nunca são passados | A Mesa é dona da seleção e não é o serviço-pai do lock legado |
| Falha de autenticação pausa o job em `WAITING_FOR_LOGIN` e para os lotes seguintes | Evita insistir no portal sem sessão |

#### M3 Exit Gate

| Critério | Evidência | Classificação |
|---|---|---|
| A Mesa decide quais pendentes precisam de download | `list_missing_pending_processes` filtra `needs_complement=1`, estado `NOT_DOWNLOADED` ou `FAILED`, e exclui `ATO_COMPLEMENTADO` | PASS_FIXTURE |
| Lotes internos são automáticos e invisíveis | `AcquisitionPlan.lot_count` 50/32; nenhuma API expõe número de lote (teste dedicado) | PASS_FIXTURE |
| O coletor existente aceita a fila gerada pela Mesa | `load_frozen_queue` (Python) e `Read-TceFrozenQueue` (PowerShell) aceitam a mesma fila | PASS_FIXTURE + PASS_PACKAGE |
| Um download real limitado baixa só as chaves pedidas | Requer portal | BLOCKED (supervisionado) |
| Falha de autenticação pausa em vez de continuar | Teste com `auth_required` prova a pausa e a parada dos lotes seguintes | PASS_FIXTURE |
| O coletor legado continua disponível | Apenas o `ValidateSet` de `-ModoPreparacao` mudou (M4 Task 2), com teste de regressão | PASS_PACKAGE |

Observação operacional: o acervo real já está completo. São 739 processos, todos
`DOWNLOADED`, e `list_missing_pending_processes` devolve 0. O gate real de M3 só
poderá ser exercitado quando uma nova varredura da Área Restrita revelar
processos pendentes; nesse momento os passos 3 a 5 da tarefa 6 se aplicam.

### M4 — Analysis, Legal Rules and Evidence

| Tarefa | Estado | Commit |
|---|---|---|
| 1. Normalizar análise incremental em SQLite | concluída | `2299c4b` |
| 2. Serviço de análise e encadeamento automático | concluída | `92fcf2a` |
| 3. Portar regras de fundamento legal para Python | concluída | `cf8f0b3` |
| 4. Serviço de evidência e Range de PDF | concluída | `2fee207` |
| 5. UI de revisão com PDF viewer integrado | concluída | `83f6e4c` |
| 6. Gate real de equivalência da análise | BLOCKED (supervisionado) | — |

#### Tarefa 3: porte do fundamento legal com oráculo JS

`app/analysis/legal.py` é um porte comportamental de toda a cadeia comprovada:
`normalizer.js`, `legal-reference-parser-v2.js`, as partes de parser e decisão de
`legal-foundation.js`, `catalog-option-signature.js`,
`retirement-legal-profile.js` e `portal-legal-crosswalk.js`.

A paridade não é argumentada, é medida: `tests/legal_parity_harness.mjs` roda o
JavaScript original sobre `tests/fixtures/legal-cases.json` e o teste compara
**todo campo** (normalização, os dois parsers, o perfil, as assinaturas de
catálogo e a decisão final) contra o resultado Python. Foram necessárias três
correções para convergir, todas encontradas pelo próprio teste:

1. `String(true)` do JS versus `True` do Python em `transition:` do perfil;
2. `` `${1.0}` `` do JS rende `1` e o Python rendia `1.0`;
3. `.map(optionParts)` do JS passa o índice como segundo argumento, então
   `option.index` existe em `selectableOptions` — o porte inicial passava `None`.

#### Tarefa 5: visualizador e evidência

- `app/web/pdf-viewer.js` preserva o contrato comprovado: retângulos
  normalizados validados, zoom limitado a 75%–300%, rotação em quartos de volta;
- o bundle PDF.js comprovado foi copiado para `app/web/vendor/pdfjs/`;
- a URL é sempre `/api/v1/documents/<id>/pdf` — nunca um caminho de arquivo;
- `GET /api/v1/documents/<id>/pdf` responde 206 com `Content-Range`, aceita
  apenas um intervalo e devolve 416 para intervalo múltiplo, malformado ou fora
  do tamanho;
- a aba **Documentos** e cada campo abrem o documento na página da evidência e
  pintam os retângulos registrados.

#### M4 Exit Gate

| Critério | Evidência | Classificação |
|---|---|---|
| Download concluído agenda análise automaticamente | `test_a_successful_download_schedules_exactly_one_analysis_per_process` | PASS_FIXTURE |
| Estado vira PRONTO, REVISAR ou ERRO pela análise do backend | testes de `AnalysisService.analyze_one` | PASS_FIXTURE |
| Regras de campo obrigatório validadas no centro | `tests/test_analysis_service.py` (seis obrigatórios, `genero` opcional) | PASS_FIXTURE |
| Fundamento legal é do backend com testes de paridade | 23 testes, incluindo comparação campo a campo com o JS | PASS_FIXTURE + PASS_PARITY |
| Mesa mostra fonte/evidência e PDF integrado | rotas de evidência e Range + viewer com testes Node | PASS_FIXTURE |
| Análise legada continua disponível como rollback | `LegacyAnalysisAdapter` sem caminho de UI; suíte legada intacta | PASS_PACKAGE |
| Equivalência real em 10 processos | 10 processos canônicos reais: **70/70 campos** iguais ao `form_value` do oráculo, **10/10** status e **20/20** classificações de documento — método e números em `docs/notes/2026-09-18-m4-equivalencia-real.md` | **PASS_REAL** |

Rotação de status (2026-09-18): o gate real de M4 **não** dependia do portal, e ao
executá-lo contra o acervo canônico apareceram dois defeitos que impediam a
análise na arquitetura nova:

1. o motor promovido exige `processos/<pasta>/processo.json` e
   `evento-*/evento.json`, que o importador de M1 não escreve — nenhum processo
   canônico era analisável (`scan_archive` devolvia lista vazia e `analyze_one`
   falhava com `KeyError`);
2. `documents.relative_path` é relativo à raiz de dados (`archive/processos/...`)
   e o motor resolve contra a raiz do acervo, então todo documento caía como
   `missing` e nenhum campo era extraído.

Correção: `app/analysis/execution_view.py` renderiza o manifesto a partir das
linhas canônicas (idempotente, sem duplicar estado), o serviço passa processo e
documentos ao adaptador e o caminho é normalizado para a raiz do acervo. Oito
testes em `tests/test_analysis_execution_view.py`, incluindo um que exige que o
motor resolva todos os documentos entregues.

#### Decisões de M4 (tarefas 1 e 2)

| Decisão | Motivo |
|---|---|
| `normalize_analysis` é puro e recebe os documentos do processo | A regra de prontidão fica testável sem SQLite nem Tesseract |
| Campo obrigatório ausente ou com status diferente de found implica REVISAR | O plano exige que faltar campo obrigatório nunca vire preenchimento parcial |
| Documento citado que não está registrado resolve para vazio mais aviso | Não inventar vínculo de evidência: o link deve apontar para a fonte real |
| `-ModoPreparacao nenhum` no adaptador do coletor | A Mesa passa a ser dona da análise; o coletor apenas baixa |
| Um worker com fila tipada, não um segundo executor global | Encadeamento download -> análise sem concorrência entre executores |

Divergência registrada no plano, tarefa 1 de M4: o payload de exemplo traz
somente o campo cargo e ainda assim espera status PRONTO. Isso contradiz as
regras explícitas do mesmo plano, que exigem REVISAR quando falta campo
obrigatório e listam seis campos obrigatórios. A implementação seguiu a regra:
PRONTO exige os seis campos obrigatórios marcados como found. Os testes cobrem
os dois lados, inclusive o caso em que falta apenas genero e o status segue
PRONTO.

### M5 — Thin Extension and Mesa-Driven Form Filling

| Tarefa | Estado | Commit |
|---|---|---|
| 1. Máquina de estados do pedido de preenchimento (schema v4) | concluída | `da14094` |
| 2. Preflight de formulário e plano no backend | concluída | `4c3873f` |
| 3. Extrair navegação e leitor de formulário para a extensão fina | concluída | `a764167` |
| 4. Implementação única de preenchimento sem submit | concluída | `67a24f7` |
| 5. Orquestração completa OPEN -> READ -> PREFLIGHT -> FILL | concluída | `c43fd1c` |
| 6. Fallback manual do formulário atual | concluída | `077fe43` |
| 7. Gate real supervisionado de preenchimento | BLOCKED (supervisionado) | — |

#### Tarefa 6: o caminho manual usa o mesmo preenchimento

O operador abre o ato à mão, o sidepanel lê o formulário atual (mensagem
`READ_CURRENT_FORM` ao service worker, que fala com a aba do portal) e envia o
snapshot para `POST /api/v1/portal/manual-form`. O backend encontra o **único**
processo `PRONTO` correspondente e roda o mesmo `build_fill_plan` do caminho
automático — o teste compara o payload de `FILL_FORM` dos dois caminhos e exige
igualdade. Zero ou vários processos correspondentes bloqueiam; o preflight
bloqueia sem enfileirar nenhum `FILL_FORM`.

Autenticação: a rota aceita a sessão da Mesa (UI) **ou** o bearer pareado, porque
o sidepanel não tem cookie de sessão. Nada nela é público — há teste para os dois
casos e para a chamada sem credencial (401).

O sidepanel continua sendo painel operacional: conexão da Mesa, Área Restrita
detectada, identidade do formulário aberto, `Preencher formulário atual`,
`Abrir Mesa` e diagnóstico. Um teste falha se ele mencionar dataset, lote, OCR ou
qualquer interruptor de envio automático.

#### M5 Exit Gate

| Critério | Evidência | Classificação |
|---|---|---|
| Mesa é dona do fluxo de preenchimento | rotas, máquina de estados e testes da cadeia completa | PASS_FIXTURE |
| Extensão só varre, navega, lê e preenche | 86 testes; fonte sem superfície de submit | PASS_FIXTURE |
| O protocolo não consegue enviar um ato | `FORBIDDEN_COMMAND_TYPES` + varredura de fonte | PASS_FIXTURE |
| Automático e manual usam o mesmo preenchimento | teste que compara os dois payloads de `FILL_FORM` | PASS_FIXTURE |
| Preflight do backend é autoritativo | identidade, geração, valor divergente, controle e catálogo | PASS_FIXTURE |
| Preenchimentos reais releem exatamente o proposto | Requer portal e operador | **BLOCKED (supervisionado)** |
| Extensão legada continua disponível para rollback | nada em `work/tce-extractor/` foi removido | PASS_PACKAGE |

#### Tarefa 5: o que a Mesa comanda hoje

`POST /api/v1/processes/<id>/fill` inicia o fluxo (somente processo `PRONTO`),
`GET /api/v1/fill-requests/<id>` acompanha o estado, e o resultado de cada
comando da extensão entra pelo mesmo caminho autenticado já existente. Ao
receber a releitura do formulário, o backend roda o preflight e ou enfileira
`FILL_FORM` com o plano, ou bloqueia sem escrever nada. Só uma releitura em que
**todos** os campos escritos confirmam o proposto marca `PREENCHIDO` e grava o
evento `form_filled`; qualquer divergência vira `BLOQUEADO`, e uma falha do
portal vira `ERRO`.

Testes que provam a cadeia inteira pelas rotas reais (não por atalhos):
abrir -> ler -> preflight -> preencher -> `PREENCHIDO`; valor já existente
divergente bloqueia e não enfileira `FILL_FORM`; releitura diferente bloqueia;
falha de verificação nunca marca preenchido; só `PRONTO` pode ser preenchido;
as rotas exigem sessão da Mesa.

#### M5 Exit Gate (parcial)

| Critério | Evidência | Classificação |
|---|---|---|
| Mesa é dona do fluxo de preenchimento | rotas + máquina de estados + testes da cadeia completa | PASS_FIXTURE |
| A extensão só varre, navega, lê e preenche | 82 testes da extensão; fonte sem superfície de submit | PASS_FIXTURE |
| O protocolo não consegue enviar um ato | `FORBIDDEN_COMMAND_TYPES` + teste que falha se aparecer | PASS_FIXTURE |
| Caminho automático e manual usam o mesmo preenchimento | pendente (tarefa 6) | pendente |
| Preflight do backend é autoritativo | bloqueios por identidade, geração, valor divergente e catálogo | PASS_FIXTURE |
| Preenchimentos reais releem exatamente o proposto | Requer portal | **BLOCKED (supervisionado)** |

#### Tarefa 3: o que a extensão fina sabe fazer do portal

`lib/area-snapshot.js` continua sendo o dono único dos seletores e agora expõe
também `findActControl`, `findInterestedRadio` e um bloco `dom` de travessia.
`content/detect-form.js` porta a leitura do formulário comprovado (mapa de
campos, visibilidade em frames aninhados, rejeição de formulário escondido,
identidade por número/ano e pessoa selecionada, catálogo de opções e geração).
`content/navigate.js` porta só o necessário de `portal-navigation.js`:
localizar a linha exata e abrir o ato, selecionar a pessoa exata, e avançar uma
página da lista. Cada função devolve um código em vez de adivinhar; o
`waitingForFrame` preserva o conhecimento real de que o portal abre o ato em
aba/quadro irmão.

#### Tarefa 4: preenchimento verificado, sem botão final

`content/fill-form.js` porta o caminho de escrita comprovado (setter nativo +
eventos `input`/`change`/`blur`, select só aceita valor existente) e acrescenta o
contrato do plano: **uma** verificação de identidade e geração antes de escrever,
depois releitura de **todos** os campos escritos e preservados. Um único campo
que não releia como proposto (ou que esteja ausente, desabilitado, somente
leitura ou fora do catálogo) faz o preenchimento inteiro falhar, para o backend
nunca marcar `PREENCHIDO` com evidência parcial. O módulo não localiza, não
procura e não clica o botão de conclusão — há um teste que varre o fonte para
provar isso.

#### Vocabulário do protocolo após M5

`STATUS`, `SCAN_AREA`, `OPEN_ACT`, `READ_FORM`, `FILL_FORM` — e
`FORBIDDEN_COMMAND_TYPES` mantém `SUBMIT`, `SEND`, `AUTO_SUBMIT`,
`COMPLEMENT_ACT` e `FINALIZE` fora do protocolo, com teste que falha se algum
deles aparecer.

#### Decisões de M5 (tarefas 1 e 2)

| Decisão | Motivo |
|---|---|
| O resultado de um comando só move o pedido se o comando for o esperado para o estado atual | Resultado repetido, atrasado ou de outro pedido nunca cria um segundo FILL_FORM |
| Identidade divergente bloqueia em vez de seguir | Preencher o ato da pessoa errada é pior do que não preencher |
| `build_fill_plan` decide **antes** de qualquer escrita e bloqueia tudo se um obrigatório falhar | Preenchimento parcial é pior que ato intocado |
| Valor já existente igual é `preserved`; divergente bloqueia com `EXISTING_VALUE_DIVERGENCE` | Não sobrescrever o que o portal já registra |
| Select só aceita proposta que casa por valor ou por rótulo exato; senão `OPTION_NOT_AVAILABLE` | Não inventar opção: o catálogo do portal é a fonte |
| `fundamento_legal` usa `resolve_legal_foundation` com as opções **atuais** do formulário | Decisão jurídica é do backend e depende do catálogo real da tela |
| Decisão jurídica não automática mantém o texto localizado e emite aviso | O operador confirma o ato; o backend não decide silenciosamente |
| Falha do motor jurídico degrada para aviso, não derruba o preenchimento | Um motor indisponível não deve tornar o ato inoperável |

#### Estado da versão do schema

O schema está em **4** e há um único ponto que fixa esse número para a suíte:
`tests/test_fill_service.py::SchemaV4Tests::test_the_store_reports_schema_four`.
M6 sobe para 5 e deve atualizar essa asserção; todos os outros testes de
migração comparam com `SCHEMA_VERSION` e continuam válidos.

### M6 — Packaging, Hybrid Archive, Storage Cleanup and Legacy Retirement

| Tarefa | Estado | Commit |
|---|---|---|
| 1. Remover dependência operacional de `work/tce-extractor/portable` | **concluída** | `ec2234d`, `ae80073` |
| 2. Arquivo híbrido HOT/ARCHIVED/MISSING (schema v5) | **concluída** | `256a857`, `4b91568`, `be953d0` |

Rotas concluídas: `POST /api/v1/processes/ID/archive` (só status `CONCLUÍDO` ou
`PREENCHIDO`, exige `external_root` em `metadata`) e `POST .../restore`, ambas com
sessão da Mesa e 502 quando o resultado não fecha. 7 testes de rota cobrem
ausência de configuração, processo inelegível, MISSING reportado como falha e
401 sem sessão. Falta apenas a UI (botões condicionais e MISSING como erro).

#### Tarefa 2 — núcleo do arquivo híbrido

Schema **v5** com `archive_blobs` (sha256 como chave, tamanho, caminho local,
caminho externo, presença local/externa e `verified_at`) e a migração 4 → 5, que
registra os SHAs já referenciados pelos documentos. Presença **não** é presumida
pela migração: o reconciliador verifica o filesystem e só então vira a flag.

`app/archive/manager.py` implementa `archive_process`, `restore_process` e
`reconcile_locations` com a regra que dá nome à tarefa: **nunca perder a última
cópia verificada**. Arquivar copia o blob para o destino externo, confere o hash
da cópia, e só então remove o link da visão de processo; o blob canônico local só
sai quando nenhum documento HOT ainda precisa dele. Qualquer falha deixa o SHA
inteiro como estava.

Um defeito real apareceu no teste do reconciliador: a varredura cobria apenas os
SHAs registrados na migração, então um documento criado depois nunca teria sua
presença conferida. Agora ela percorre a união entre blobs registrados e SHAs
referenciados pelos documentos (`Store.list_document_shas`).

O que falta na tarefa 2 (próximo passo):

1. `POST /api/v1/processes/ID/archive` (sessão da Mesa; exige `external_root`
   configurado em `metadata`) e `POST /api/v1/processes/ID/restore`;
2. controles na Mesa: `Arquivar processo` só para processo concluído/inativo,
   `Restaurar documentos` para ARCHIVED, e MISSING exibido como erro, nunca como
   arquivamento bem-sucedido;
3. testes de rota e de contrato da UI.
| 3. Inventário de armazenamento e verificador de cópia canônica | **concluída** | `585f6ad` |
| 4. Backup completo explícito e manifesto de restauração | **concluída** | `db6be11` |
| 5. Builder do ZIP portátil sem acervo | **concluída** | `a947c00` |
| 6. Smoke de extração limpa e retenção de dois builds | **concluída** | (este commit) |
| 7. Limpeza por recibo (destrutiva, exige autorização) | **ferramenta concluída**; apply real aguarda autorização | (este commit) |
| 8. Tornar app/extensão/pacote o padrão e retirar o legado | **padrão e documentação concluídos**; remoção bloqueada pelo gate | `83403b0` |

#### Tarefa 3 — auditor de armazenamento (somente leitura)

`scripts/storage-audit.py` mede o repositório por categoria (`canonical_data`,
`dist`, `outputs`, `versions`, `staging`, `temp`, `legacy_archive`, `source`,
`unknown`) e, para cada árvore candidata a remoção, prova se o acervo canônico
ainda guarda cada PDF exclusivo dela. A preservação é provada por bytes: blob
canônico é o arquivo `data/archive/blobs/AA/<sha256>.pdf` cujo nome é o próprio
hash, e uma linha de `archive_blobs` só conta quando o arquivo apontado existe e
o tamanho bate (cópia externa incluída). ZIPs são abertos e cada membro PDF é
hasheado; ZIP ilegível, corrompido ou com arquivo aninhado bloqueia a remoção em
vez de ser ignorado. Junction/reparse point não é seguido e também bloqueia.

Ensaio real no checkout (21 min de I/O, recibo em `data/logs/storage-audit.json`):

| Categoria | Arquivos | Bytes |
|---|---|---|
| canonical_data | 28.361 | 16,97 GB |
| outputs | 99.854 | 38,06 GB |
| versions | 33.060 | 10,10 GB |
| legacy_archive | 32.547 | 9,05 GB |
| source | 3.534 | 356,9 MB |
| unknown | 1.103 | 139,0 MB |
| temp | 87 | 0,2 MB |

| Candidato | PDFs soltos | PDFs em ZIP | Exclusivos | Recuperáveis | safe_to_delete |
|---|---|---|---|---|---|
| `Versions` | 14.179 | 3.273 | **3.273** | 14.179 | não |
| `outputs` | 42.537 | 28.358 | 0 | 14.179 | não |
| `tmp` | 1 | 0 | 1 | 0 | não |
| `work/tce-extractor/acervo-tce` | 14.179 | 0 | 0 | 14.179 | **sim** |
| `work/tce-extractor/outputs` | 0 | 0 | 0 | 0 | sim |
| `work/outputs` | 0 | 0 | 0 | 0 | sim |
| `work/tmp` | 0 | 0 | 0 | 0 | sim |
| `work/tce-extractor/Versions` | ausente | — | — | — | não |

Achados que a tarefa 7/8 precisa respeitar:

1. o acervo canônico está íntegro: 14.179 blobs, 8.892.090.055 bytes,
   `referenced_without_blob=0`, `malformed_entries=0`, nenhuma cópia externa;
2. `work/tce-extractor/acervo-tce` (origem, 9,05 GB) tem **todos** os seus PDFs
   no acervo canônico — é a evidência que faltava para a tarefa 8;
3. `outputs` (38 GB) não guarda nenhum PDF exclusivo, mas fica bloqueado por dois
   ZIPs de pacote que contêm `runtime/python/python314.zip` (aninhado) e por 10
   `trace.zip` **corrompidos** de execuções reais do portal;
4. `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14.zip`
   (1,2 GB) guarda um `acervo-tce` antigo com **3.273 PDFs que não existem no
   acervo canônico**: nada pode remover essa árvore antes de importar os PDFs ou
   de haver autorização explícita para descartá-los;
5. `tmp/m1-fixture/processos/102390-2026/evento-0001-7047389/documento-001-Ato.pdf`
   (22 bytes) é fixture do ensaio de M1, não dado real, e também bloqueia `tmp`.

#### Tarefa 4 — backup explícito com manifesto

`scripts/backup.py` grava um ZIP com o snapshot do SQLite, todos os blobs
canônicos e `manifest.json` (`schema_version`, `created_at`, `db_sha256`,
`db_bytes`, `file_count`, `blob_bytes`, `total_bytes`, caminho e SHA-256 de cada
blob). O banco é copiado pela API de backup do SQLite — o store roda em WAL, e
uma cópia crua do arquivo perderia as linhas que ainda estão no `-wal`; há teste
que falha exatamente nesse caso. A escrita vai para `<output>.tmp` e só é
publicada com `os.replace` depois que o ZIP passa por `testzip()` e o manifesto
confere com o conteúdo gravado; qualquer falha remove o temporário. Destino
dentro de `data/archive` é recusado. Backup é ação explícita: `--output` é
obrigatório e nada agenda a execução.

Ensaio real do backup (destino temporário, 8,9 GB, ~2 min: ZIP com 14.179
blobs + snapshot do banco + manifesto; o próprio comando valida `testzip()` e o
manifesto antes de publicar):

| Medida | Valor |
|---|---|
| Blobs | 14.179 / 8.892.090.055 bytes |
| Banco | 10.354.688 bytes, `schema_version=5` |
| `db_sha256` | `6ded7abb201ac8afc5dd42dc8acdfa8946fd1f3984146d68c5c3ebb5a6f47312` |
| Total | 8.902.444.743 bytes |
| ZIP | 8.899.648.415 bytes, SHA-256 `fd3074b21b16ac7ac9b823a1e8f4266dd5e0a62570724cd187fae31d58b3285a` |
| Divergências de nome | 0 |

O ZIP de prova foi removido do `%TEMP%` depois da medição (era ensaio, não
backup de produção); o comando para um backup real é o mesmo, com `--output`
apontando para o destino definitivo.

#### Tarefa 5 — pacote portátil sem acervo

`packaging/` é o novo dono da distribuição:

| Arquivo | Papel |
|---|---|
| `build-portable.ps1` | monta `dist/Atos-TCE-portable.zip` com a allowlist (app, extension, START.cmd, README, runtime verificado, licenças) |
| `verify-package.ps1` | allowlist, arquivos obrigatórios, inventário de runtime por tamanho+SHA-256 e smoke de extração limpa |
| `runtime-builder.ps1` | cópia promovida de `work/tce-extractor/build-portable-runtime.ps1` |
| `runtime-manifest.json`, `licenses/README.md` | cópias do pacote legado |

O construtor de runtime foi **promovido por cópia byte-exata** com apenas três
edições de caminho (manifesto e README de licenças passam a vir de `packaging/`,
raiz do projeto passa a ser o repositório) e uma linha nova no `python314._pth`:
a entrada `../../..` coloca a raiz do pacote no `sys.path`, sem a qual
`python -m app.main` não importa `app` no Python embutido. Isso foi medido com o
runtime real (`_pth` original não importa o pacote; `../../..` importa de
qualquer CWD) e é provado pelo smoke a cada build.

Checagens de supply chain preservadas: versões fixas (Python 3.14.4, PyMuPDF
1.28.2, openpyxl 3.1.5, et_xmlfile 2.0.0, Tesseract 5.4.0.20240606, 7-Zip
26.02), SHA-256 fixo por componente, HTTPS obrigatório, staging validado com
rollback, extração verificada do NSIS e materialização de licenças. O runtime
publicado só é reutilizado quando versão e hash de cada componente batem com o
manifesto fixado agora.

Build real (rede + fora do sandbox, ~9 min incluindo downloads):

| Medida | Valor |
|---|---|
| ZIP | `dist/Atos-TCE-portable.zip` |
| Tamanho | 96.093.040 bytes (~91,6 MB, contra 5,5 GB do pacote antigo com acervo) |
| SHA-256 | `0b0a794e7e40d09a52fbdfedf6f19eb05bcf960d2762538ae57cf7bfde91b0bc` |
| Entradas | 507 (430 de runtime conferidas por tamanho e SHA-256 contra o manifesto) |
| Reprodutibilidade | segundo build em outro caminho gerou o mesmo SHA-256 |
| Acervo | ausente: `data/`, `acervo-tce/`, `dados-locais/`, `profile/`, PDFs, bancos e HAR/trace são recusados pelo construtor e pelo verificador |

Smoke de extração limpa (executado fora do sandbox, porque encerra a árvore de
processos e usa loopback):

1. extraiu em `tmp/package-test-<id>`;
2. subiu o pacote pelo `START.cmd` (Python embutido) numa porta livre;
3. `/api/v1/health` respondeu `status=ok`, `api_version=1`, `schema_version=5`,
   `process_count=0` em raiz de dados isolada;
4. criou o SQLite dessa raiz isolada e confirmou Manifest V3 da extensão;
5. encerrou a árvore (`taskkill /T`) e **apagou a extração** no PASS.

#### Tarefa 6 — retenção de dois builds

O smoke do passo anterior mora em `verify-package.ps1` (extração única em
`tmp/package-test-<id>`, removida no PASS, preservada e anunciada no FAIL).

`scripts/rotate-builds.py` implementa a retenção: publica o build **verificado**
como `Atos-TCE-portable.zip`, move o que ele substitui para
`Atos-TCE-portable.previous.zip` e remove os demais ZIPs; arquivos que não são
ZIP ficam intocados e são apenas relatados. O padrão é dry-run e `--apply`
**recusa** rodar sem `--verified-hash` (o SHA-256 que o builder e o verificador
reportam), então só um pacote que já passou no gate vira o build atual.

Rotação real executada em `dist/` depois do smoke: `Atos-TCE-portable.zip`
(atual) e `Atos-TCE-portable.previous.zip` (91,6 MB cada, ambos do mesmo build
verificado) — exatamente dois arquivos.

#### Tarefa 7 — limpeza por recibo

`scripts/cleanup-storage.py` só toca nas árvores listadas no recibo da auditoria
e recusa: caminho fora do repositório (inclusive `..` e caminho absoluto); raízes
protegidas (`.git`, `app`, `data`, `dist`, `docs`, `extension`, `packaging`,
`scripts`, `tests`); candidato sem `safe_to_delete` ou sem acervo canônico;
candidato cuja contagem de arquivos ou bytes mudou depois do recibo
(`changed_since_audit`); árvore com junction/reparse point; e
`work/tce-extractor/acervo-tce` sem `--allow-legacy-archive` mais o recibo de
migração de M1. O padrão é dry-run e `--apply` grava
`data/logs/storage-cleanup-<UTC>.json` com o que saiu, os bytes e o resumo
canônico do recibo de auditoria.

Dry-run real (`python scripts/cleanup-storage.py --audit data/logs/storage-audit.json`):

| Árvore | Bytes | Decisão | Motivo |
|---|---|---|---|
| `Versions` | 10,6 GB | recusa | `audit_not_safe` (3.273 PDFs exclusivos) |
| `outputs` | 39,9 GB | recusa | `audit_not_safe` (ZIP aninhado/corrompido) |
| `tmp` | 0,3 MB | recusa | `audit_not_safe` |
| `work/tce-extractor/acervo-tce` | 9,0 GB | recusa | `legacy_archive_requires_flag` |
| `work/tce-extractor/Versions` | 0 | recusa | `absent` |
| `work/outputs` | 40 KB | **aprovado** | — |
| `work/tmp` | 0 | **aprovado** | — |
| `work/tce-extractor/outputs` | 0,7 MB | **aprovado** | — |

Total aprovado: 740.149 bytes. Recibo de migração de M1 localizado em
`data/logs/legacy-import-20260918T123734Z.json`.

O `--apply` real **não** foi executado: o gate destrutivo de M6 exige, além do
recibo e do acervo canônico completo, execução real supervisionada do
preenchimento (M5 tarefa 7, ainda BLOCKED) e autorização explícita do usuário.
A rota de remoção está provada por testes de fixture (dry-run, apply em candidato
seguro, recusa dos casos perigosos e gravação do recibo).

Correção encontrada no ensaio real do importador (2026-09-18, mais tarde): o
dry-run do `migrate-legacy.py` também grava recibo em `data/logs/`, então o
recibo mais novo passaria a ser um `mode=dry-run` e autorizaria a remoção de
`acervo-tce` sem prova de materialização. A limpeza agora só aceita recibo de
migração com `mode=apply` e `errors` vazio, com três testes novos
(`migration_receipt_not_apply`, `migration_receipt_has_errors` e "apply antigo
ganha de dry-run novo").

O inventário completo da aposentadoria do legado (unidades, tamanhos, o que
ainda é carga e a sequência proposta) está em
`docs/notes/2026-09-18-aposentadoria-legado-inventario.md`.

#### Tarefa 1 — o que já foi promovido (e-Contas)

`app/econtas/runtime/` agora contém os quatro arquivos comprovados
(`Coletar-Processos-TCE.ps1`, `TcePortable.Core.psm1`, `TceFrozenQueue.psm1`,
`TcePortal.Driver.js`) e `app/econtas/collector.py` aponta para lá. Duas
decisões ficaram registradas:

* a cópia promovida ganhou `-RaizEstado` para que perfil de navegador e bridge
  fiquem sob a raiz de dados (`data/dados-locais/...`) e nunca dentro de `app/`.
  Sem isso, promover o script moveria silenciosamente o perfil autenticado do
  operador — uma regressão operacional real. O script legado continua intacto;
* a preparação incremental (`-ModoPreparacao progressivo|completo`) continua
  exigindo a árvore legada e está documentada no cabeçalho da cópia promovida. A
  Mesa roda sempre com `nenhum` (M4), e há teste que exige isso.

#### Tarefa 1 — promoção da análise

Medição feita com um script de fechamento transitivo de imports
(`tmp/closure.py`, descartável) — e a medição inicial estava errada por um
detalhe que só apareceu ao abrir os arquivos: `analysis_pipeline.py` também
puxava os dois módulos proibidos, não só o `publish_results`.

```
42.1KB  analysis_pipeline.py     (portable/app)   -> promovido
29.9KB  legal_context.py         (portable/app)   -> promovido
12.2KB  archive_index.py         (portable/app)   -> promovido
11.3KB  evidence_geometry.py     (portable/app)   -> promovido
11.1KB  incremental_pipeline.py  (portable/app)   -> promovido
19.7KB  batch_runner.py          (RAIZ do extrator) -> promovido
28.9KB  tce_extractor.py         (RAIZ do extrator) -> promovido
24.0KB  extension_exporter.py    (portable/app)   -> NÃO carregado
80.9KB  html_generator.py        (RAIZ do extrator) -> NÃO carregado
```

Ou seja: o motor de análise atravessa **duas** pastas e o `run_manifest` de
`batch_runner` puxa `html_generator`. O plano proíbe carregar HTML/exportador,
então a promoção exige uma cópia de `batch_runner` com o passo de apresentação
removido (o dado que a Mesa consome é `processes[].result`, não o relatório) e uma
cópia de `publish_results` sem `dataset.json`/HTML. Copiar os seis módulos de
`portable/app` é direto; o trabalho real está em `batch_runner`/`tce_extractor`.

O que foi feito no commit `ae80073`:

1. `app/analysis/engine/` recebeu sete módulos promovidos (`incremental_pipeline`,
   `analysis_pipeline`, `archive_index`, `evidence_geometry`, `legal_context`,
   `batch_runner`, `tce_extractor`), com imports relativos e sem `sys.path`;
2. `analysis_pipeline` perdeu o `run_local_pipeline` (a preparação de acervo
   inteiro do menu legado, que era o único lugar que chamava HTML e exportador) e
   `publish_results` publica apenas `resultados.json` + ponteiro;
3. `legacy_adapter.py` agora importa o motor pelo pacote (`from .engine import
   incremental_pipeline`), sem manipular `sys.path`;
4. `tests/test_no_legacy_paths.py` fecha a fronteira: nenhum `.py/.ps1/.psm1/.js`
   em `app/` cita o caminho legado, nenhum `.py` de `app/` usa `sys.path.insert`, e
   o pacote promovido não carrega exportador nem HTML;
5. `tests/test_analysis_engine.py` prova o motor promovido em execução:
   `scan_archive` lê um layout real, `publish_results` publica só resultados e
   mantém duas revisões, chave inválida e processo ausente falham fechado.

Duas referências de proveniência em docstrings (`legacy_queue.py` e
`pdf-viewer.js`) foram reescritas sem o caminho literal: a varredura da fronteira
só tem valor se a string significar dependência de runtime.

#### Gate destrutivo de M6

As tarefas 7 e 8 (limpeza de `Versions/`, staging e ZIPs antigos; retirada do
legado) exigem, antes de qualquer remoção: acervo canônico contendo **todo** SHA
único da árvore candidata, `safe_to_delete=true` da auditoria, recibo de migração
de M1, suíte completa verde e tag `pre-legacy-retirement` — e a autorização
explícita do usuário. Nada foi removido até agora.

## 9. Estado verificado nesta sessão (2026-09-18)

| Camada | Resultado |
|---|---|
| Python (raiz `tests/`) | 365 testes, 365 aprovados (inclui `test_storage_audit` e `test_backup`) |
| Extensão (`extension/`, `node --test`) | 86 testes, 86 aprovados |
| Suíte legada PowerShell (`Test-TcePortable.ps1`) | 140 passaram, 0 falharam |
| `verify-project.ps1` (7 estágios) | verde |
| Banco real `data/atos-tce.db` | schema 3, 739 processos, 14.483 documentos e 14.179 blobs |
| Origem preservada | `work/tce-extractor/acervo-tce` intacto, 14.179 PDFs e 8,28 GB |

## 4. Arquivos criados/alterados

**Código novo (raiz, todos dentro do allowlist do `.gitignore`):**

- `app/__init__.py`, `app/core/__init__.py`, `app/archive/__init__.py`, `app/api/__init__.py`
- `app/core/identity.py` — normalização canônica de interessado (dono único da regra)
- `app/core/models.py` — `ProcessRecord`, `DocumentRecord`, `FieldRecord` congelados
- `app/core/store.py` — SQLite schema v1, migrações transacionais, upsert/leitura
- `app/archive/legacy_import.py` — `scan_legacy_archive`, `import_legacy_archive`, `canonicalize_process_tree`, `sha256_file`
- `app/api/views.py` — view models de leitura + `safe_join` + `resolve_document_file`
- `app/api/server.py` — `serve`, rotas explícitas, sem rota genérica de arquivo
- `app/web/index.html`, `app/web/app.js`, `app/web/app.css` — Mesa somente leitura
- `app/main.py` — launcher (`python -m app.main`)
- `scripts/migrate-legacy.py` — CLI de migração (dry-run por padrão)
- `START.cmd` — encaminha para `python -m app.main`
- `tests/test_store.py`, `tests/test_legacy_import.py`, `tests/test_api_server.py`

**Alterados:** `.gitignore` (allowlist de raiz + `/data/`, `/dist/`, `/tmp/`), `README.md` (seção "Mesa Local").

**Nada de `work/tce-extractor/` foi alterado em M1** (exigência do marco).

## 5. Testes executados

```
python -m unittest tests.test_store tests.test_legacy_import tests.test_api_server
```

- 50 testes, 50 aprovados, 0 falharam (antes do Task 6, que não tem teste próprio).
- Destaques: dedup por SHA-256 (1 blob para 2 cópias), acervo de origem intacto
  (hash + mtime), dry-run não materializa nada, hardlink real entre visão de
  processo e blob, reparse point/junction não seguido, CLI em dry-run,
  API sem rota genérica de arquivo e sem escape de `data_root`,
  launcher sobe `/api/v1/health` de verdade em subprocesso.

## 6. Como retomar

1. `git status` / `git log --oneline -8` na branch `codex/mesa-local-refactor`.
2. Conferir se `data/` já tem o resultado do ensaio real (M1 Task 6).
3. Rodar a suíte: `python -m unittest tests.test_store tests.test_legacy_import tests.test_api_server`.
4. Seguir para o Exit Gate de M1 e só então iniciar M2.

Gate de validação do projeto (inalterado, ainda roda o legado):

```
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
```

## 7. Pendências e riscos

- M1 Task 6 depende de espaço em disco: são ~8,4 GB de PDFs de origem e o gate
  exige `bytes_unique + 2 GiB` livres (56,9 GB livres no início do ensaio).
- `tests/fixtures/legacy-archive` citado no plano não é versionado porque
  `**/*.pdf` é ignorado; as fixtures são construídas em teste e o ensaio real
  usa `work/tce-extractor/acervo-tce`.
- O `.git` está somente-leitura dentro do sandbox: `git add`/`git commit` exigem
  aprovação de escalonamento.
- M6 depende de aprovação explícita do usuário antes de qualquer remoção de
  legado ou limpeza de armazenamento (o plano exige tag de segurança, recibos e
  auditoria de SHA antes).

## 8. Fronteiras preservadas

- Nenhum auto-submit foi adicionado; o protocolo novo ainda não existe (M5).
- Login em Área Restrita e e-Contas continua humano.
- `Versions/`, `outputs/`, `dados-locais/` e o acervo privado não foram tocados.

#### Tarefa 8 — o novo fluxo é o padrão (remoção ainda bloqueada)

| Interface exigida pelo plano | Estado |
|---|---|
| `START.cmd` é o launcher normal | feito: usa o Python embutido do pacote quando existe e o do sistema fora dele |
| `extension/` é a extensão suportada | feito: MV3 fina, sem SUBMIT/SEND/AUTO_SUBMIT |
| `packaging/build-portable.ps1` é o build suportado | feito |
| nenhum runtime suportado depende do legado | feito e verificado por `tests/test_no_legacy_paths.py` |

Inventário de referências (passo 3 do plano):

- `app/`, `extension/`, `packaging/` e `START.cmd` não citam `work/tce-extractor`,
  `INICIAR.cmd`, `ABRIR-MESA` nem `automation-controller.js`; as únicas
  ocorrências de `AUTO_SUBMIT` são `FORBIDDEN_COMMAND_TYPES` (prova de ausência)
  e testes que a verificam. Duas proveniências literais (uma docstring na
  extensão e o cabeçalho do builder promovido) foram reescritas para descrever a
  origem sem o caminho, deixando a varredura significar dependência de runtime.
- `scripts/` continua citando o legado de propósito (auditoria, limpeza e
  aposentadoria) e por isso fica fora da varredura, como documentado no teste.
- `README.md` e `docs/ESTRUTURA.md` descrevem o novo fluxo e preservam as notas
  históricas que o gate legado exige (`Test-DocumentationTracking` 20/20).

Gates executados nesta sessão:

| Gate | Resultado |
|---|---|
| Python da raiz | 401 testes, 401 aprovados |
| Extensão (`node --test`) | 86 testes, 86 aprovados |
| `verify-project.ps1` (7 estágios) | verde (extensão, web, python portable, PowerShell 20+100+31+1+140+307, pacote 82, automação 81, `git diff --check`) |
| Contrato do pacote | `tests.test_packaging_contract` 11/11, incluindo o ZIP real |
| Smoke de extração limpa | verde no pacote reconstruído |

Pacote reconstruído depois das mudanças de documentação e extensão:
`dist/Atos-TCE-portable.zip`, 96.094.132 bytes, SHA-256
`f1e47da723770a50e2111f6a54184330528c76bfa3dc05593b33d325922186c9`, 507 entradas,
430 arquivos de runtime conferidos; rotação aplicada com esse hash, deixando
`Atos-TCE-portable.zip` (novo) e `Atos-TCE-portable.previous.zip` (91,6 MB cada).

Preparação da remoção (achados desta varredura, todos não destrutivos e já no
repositório):

1. `tests/legal_parity_harness.mjs` carregava o oráculo legal JS do legado — os 7
   arquivos do fecho foram promovidos para `tests/oracles/legal/` (com README de
   proveniência) e o harness lê de lá, então o gate de paridade de M4 sobrevive à
   retirada;
2. `tests/test_econtas_acquisition.py` lia a fila congelada pelo validador legado
   em 5 testes — eles agora pulam quando a árvore não existe e um teste novo,
   ancorado no validador promovido (`app/econtas/runtime/TceFrozenQueue.psm1`),
   cobre as mesmas invariantes (lotes 50/42 e colapso de duplicatas);
3. `app/analysis/legacy_adapter.py` sondava `portable/runtime/tesseract` como
   fallback de desenvolvimento — a sonda saiu: só `<data_root>/runtime/tesseract`
   e `<repo>/runtime/tesseract` são procuradas, e o erro lista os caminhos;
4. `tests/test_no_legacy_paths.py` agora reprova também o segmento
   `tce-extractor`, pegando caminho composto (`"work" / "tce-extractor" / ...`);
5. `tests/test_legal_rules.py` ganhou um teste que exige o oráculo dentro do
   repositório.

6. `tests/test_promoted_equivalence.py` trava a promoção por comparação estática
   com os arquivos comprovados: os três módulos do runtime e-Contas
   (`TceFrozenQueue.psm1`, `TcePortable.Core.psm1`, `TcePortal.Driver.js`) são
   **byte a byte idênticos** aos legados e o coletor difere apenas no
   `-RaizEstado` documentado (o teste reverte a mudança e exige igualdade do
   resto). No motor de análise, `archive_index.py`, `evidence_geometry.py` e
   `legal_context.py` também são byte a byte idênticos, enquanto
   `tce_extractor.py` e `batch_runner.py` diferem só nos imports (o teste remove
   os imports e compara a lógica). O arquivo traz auto-testes que provam que a
   checagem falha diante de uma mudança real.

Suíte após a preparação: 424 testes, 424 aprovados.

**A remoção (passos 4, 5 e 7 do plano) não foi executada.** O gate destrutivo
continua exigindo: M2 real de leitura da Área Restrita, M3 real de aquisição
limitada e M5 supervisionado de preenchimento (todos dependem de portal e
operador humano), tag `pre-legacy-retirement` com backup remoto confirmado e
autorização explícita do usuário. Enquanto isso, `work/tce-extractor` permanece
como fallback documentado.
