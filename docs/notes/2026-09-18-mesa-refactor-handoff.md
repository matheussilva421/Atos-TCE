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
| Equivalência real em 10 processos | Requer acervo real e runtime Tesseract | **BLOCKED (supervisionado)** |

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
| 2. Arquivo híbrido HOT/ARCHIVED/MISSING (schema v5) | **parcial** (núcleo pronto; rotas e UI pendentes) | — |

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
| 3. Inventário de armazenamento e verificador de cópia canônica | pendente | — |
| 4. Backup completo explícito e manifesto de restauração | pendente | — |
| 5. Builder do ZIP portátil sem acervo | pendente | — |
| 6. Smoke de extração limpa e retenção de dois builds | pendente | — |
| 7. Limpeza por recibo (destrutiva, exige autorização) | pendente | — |
| 8. Tornar app/extensão/pacote o padrão e retirar o legado | pendente | — |

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
| Python (raiz `tests/`) | 308 testes, 308 aprovados |
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
