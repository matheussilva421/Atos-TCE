# Handoff — consolidação na main e conclusão do fluxo automático

Data: 2026-09-11 (última atualização)
Plano: `docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md`
Especificação: `docs/notes/2026-09-10-consolidacao-main-e-conclusao-spec.md`

## Estado atual

- Execução SDD ativa em `main`. Em 2026-09-10 o remoto privado
  `https://github.com/matheussilva421/Atos-TCE.git` foi conectado e a `main`
  vem sendo publicada a cada bloco concluído; `HEAD == origin/main` no fim de
  cada tarefa.
- Tip funcional consolidado: `f508cac`; commits documentais posteriores estão
  registrados no histórico Git desta branch.
- As atualizações documentais desta sessão foram publicadas em `origin/main`
  por fast-forward; a branch `main` continua única. Os SHAs dos commits e as
  verificações de cada checkpoint estão registrados ao final deste handoff.
- A recuperação da fotografia inicial está em `tmp/fase0-recovery/` e deve ser
  preservada até a validação final. Ela contém `tracked.patch` de 196.257 bytes
  e 13 cópias verificadas por hash.
- A quarentena física foi aplicada e permanece preservada para a Fase 9.3:
  recibo `tmp/quarantine/20260911-012750-653/receipt.json`, com
  `moved=16074`, `not_moved=0` e `moved_bytes=23126367618`; nenhum purge
  definitivo foi executado.

## Tarefas

- [x] Tarefa 0.1 — inventário e recuperação inicial. Commit `1eb1903c`; revisão
  independente aprovada. Divergência real: 13 arquivos não rastreados, embora
  o texto do plano mencionasse 10; todos foram preservados.
- [x] Tarefa 0.2 — analisador read-only implementado; 174/174 testes verdes;
  manifesto real em geração sobre 109.050 arquivos/45,3 GB.
- [x] Tarefa 0.3 — classificação concluída e aprovada pelo usuário antes do
  WhatIf da Tarefa 0.8.
- [x] Tarefa 0.4 — reconciliação documental; 19/19 testes verdes em Windows
  PowerShell 5.1 e PowerShell 7.
- [x] Tarefa 0.5 — bloco local revisado, testado e dividido em commits nominais.
- [x] Tarefa 0.6 — branch de transferência comprovada como duplicata de patch;
  nenhum merge foi feito.
- [x] Tarefa 0.7 — fast-forward de `main`; tips conferidos e gates repetidos.
- [x] Tarefa 0.8 — limpador por manifesto implementado, validado por suíte
  focada (307/307) e hardening r2 publicado (`5dee162`, `d179b59`) após laudo
  FAIL da revisão 3; WhatIf real aprovado pelo usuário. `-Apply` aguarda a
  revisão independente 4.
- [ ] Tarefa 0.9 — quarentena física pendente do `-Apply`; pacote `fase11k` já
  rodou em extração limpa com os seis gates públicos verdes.
- [x] Tarefa 0.10 — somente `main`: branch única, `worktree prune --dry-run`
  vazio e handoff atualizado.
- [x] Tarefa 1.1 — baseline da suíte Python registrado em
  `docs/notes/2026-09-10-python-suite-baseline.md` (409 executados, 401
  aprovados, 8 skips; focal 3/3).
- [x] Tarefa 1.2 — `verify-project.ps1` publicado como comando único de
  verificação (`0cc3680`, `f8b5444`): 959 executados, 957 aprovados, 0 falhas,
  2 skips, exit 0 em duas rodadas completas.
- [ ] Fases 4–9 — pendentes; dependem de login humano no e-Contas/Área Restrita
  e de autorização explícita por envio. Nenhum gate portal-real, envio,
  qualificação, piloto, release ou purge foi antecipado.

## Evidência da Tarefa 0.1

- Inventário: `docs/notes/2026-09-10-fase0-inventario-inicial.md`.
- Relatório SDD: `.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/task-0.1-report.md`.
- Revisão SDD: `.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/task-0.1-review.md`.
- `git diff --check`: status 0; apenas o aviso conhecido de normalização
  LF/CRLF em `work/tce-extractor/portable/INICIAR.cmd`.
- Cinco ZIPs essenciais/candidatos foram hashados sem abrir conteúdo privado;
  o acervo autorizado de 05/09 possui duas cópias byte a byte equivalentes.

## Evidências das Tarefas 0.2, 0.4 e 0.5

- Analisador endurecido contra overwrite/reparse do manifesto, paths externos,
  diretórios ilegíveis e leitura de diretórios privados; commit `17185fc`.
- `Test-WorkspaceCleanup.ps1`: 174 executados, 174 passaram, 0 falharam.
- `Test-DocumentationTracking.ps1`: 19 executados, 19 passaram, 0 falharam.
- Gates do bloco local: extensão 287/287, Python portátil 34/34 e menu 83/83.
- Commits nominais: `416bbfe` (contratos determinísticos), `11342f3`
  (aquisição congelada) e `f508cac` (limites portal-reais).
- Busca estrutural: nenhum Bearer/API key/caminho privado; o único CPF bruto
  detectado estava em fixture novo, foi sanitizado sem registrar seu valor e a
  suíte da extensão permaneceu 287/287.
- `git diff 6c88d2a ef7d44b --` vazio; a transferência é patch-equivalente e
  fica reservada apenas para exclusão após consolidação em `main`.
- Pós-fast-forward: Python 34/34 e menu 83/83 verdes. A extensão revelou um
  teste de polling intermitente (286/287); a causa foi atraso fixo de cinco
  voltas do event loop. O teste passou 10/10 isolado após espera condicionada
  e a suíte completa voltou a 287/287.
- `git diff --check`: status 0; somente o aviso EOL conhecido de `INICIAR.cmd`.
- A análise real foi concluída em `tmp/fase0/workspace-manifest-r2.json`; não
  avançar para limpeza física antes de validar o manifesto e obter aprovação.
- A análise real terminou com 29.559 entradas, schema 10/10 válido, quatro
  diretórios não enumerados e zero padrão sensível no JSON. A proposta em
  `docs/notes/2026-09-10-fase0-classificacao-workspace.md` limita a quarentena
  a 21,91 GiB de alvos recuperáveis explícitos e mantém desconhecidos intactos.

## Decisões e riscos

- O plano exige preservar o checkout atual para recuperar as alterações locais;
  não foi criado um worktree vazio.
- A contagem 10→13 é fato do estado inicial, não motivo para descartar arquivos.
- Minor pendente da revisão: explicitar na próxima classificação a separação
  entre ZIPs de retenção, históricos e staging.
- Nenhum envio real foi autorizado; `real_send_enabled=false` permanece a
  fronteira funcional. Nenhum perfil Chrome pessoal será tocado.

## Retomada

1. Validar schema, contagens, avisos e privacidade de
   `tmp/fase0/workspace-manifest-r2.json` quando a análise real terminar.
2. Produzir a classificação da Tarefa 0.3 e solicitar aprovação do manifesto.
3. Concluir os commits nominais da Tarefa 0.5 e reconciliar a branch de
   transferência sem merge.
4. Parar antes de qualquer Apply, purge, troca/exclusão de branch ou gate portal
   que exija login/autorização imediata.

Atualização: os itens 1–3 do bloco acima foram concluídos nas tarefas 0.1–0.7 e
0.10. A retomada vigente é a lista “Pendências imediatas” da última seção deste
documento.

## Atualização — Tarefa 3.1 (2026-09-10)

- Gate fallback OCR real: `not-observed`.
- Busca local medida: acervo bruto 4.532 PDFs/15.833 páginas, `native_zero=0`;
  outputs 1.037 PDFs/3.260 páginas, `native_zero=0`; QA v6 4.532
  PDFs/15.833 páginas, `native_zero=0`; escopo `work` (sem runtime/vendor/
  site-packages) 28.398 PDFs/98.515 páginas, `native_zero=0`. Todos os
  documentos abriram sem erro.
- A implementação de cache versionado, cache geométrico, TSV/confiança e
  integração no pipeline já existia em `portable/app/analysis_pipeline.py`,
  `portable/app/evidence_geometry.py`, `tce_extractor.py` e `batch_runner.py`;
  nenhum código de produção foi alterado nesta tarefa.
- Foram encontrados 10 arquivos `cache-ocr*.json`, todos com zero entradas;
  não há cache hit, caixas ou confiança reais observáveis para reportar.
- Testes focais: 66/66 aprovados, 0 falhados (`test_tce_extractor.py`,
  `test_evidence_geometry.py`, `test_analysis_pipeline.py`). Fixtures
  sintéticas não qualificam o gate real.
- Relatório completo: `.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/task-3.1-report.md`.
- Retomada: somente após disponibilizar PDF local autorizado com
  `native_text_length=0`; hash antes do OCR; executar `run_local_pipeline` em
  raiz de saída separada; provar primeira execução, geometria e segunda
  execução sem novo OCR. Nenhum Git mutável, portal, Chrome ou rede foi usado.

## Atualização — Tarefa 2.2 (2026-09-10)

- Status: PASS para a reconciliação de evidências. O relatório detalhado está
  em `.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/task-2.2-report.md`.
- O classificador/extrator passou a reconhecer os dois layouts locais de guia
  financeira. TDD focal: RED/GREEN para a guia de cálculo e RED/GREEN para o
  layout longo; suítes finais: `test_tce_extractor` 31/31,
  `test_batch_runner` 19/19, `test_analysis_pipeline` 24/24 e
  `test_reconcile_lote1` 1/1.
- Reexecução somente leitura: 9 processos afetados, 19 documentos
  prioritários, 10 blocos; 8 nascimentos recuperados. A fonte
  `resultados.json` permaneceu com SHA-256
  `182742bac0ae070fb8b9ffcb3573f1843fe3fbaa82bf5201618ce6bed78f0d2b` antes
  e depois. Os 41 processos íntegros não entraram no manifesto/checkpoint
  (`intact_processes_in_target_checkpoint=0`).
- Matriz final derivada: 49 registros elegíveis, 1 bloqueado por
  `data_nascimento` e 1 por `modalidade` + `fundamento_legal`; apenas
  `104956/2025` continua com bloqueio de processo. `genero` segue opcional.
- Pendências: o registro #1 de `104956/2025` ainda não tem evidência de
  nascimento; o registro #2 ainda não tem documento suficiente para modalidade
  e fundamento legal. Permanecem fora de preflight.
- Nenhum commit, stage, push, portal, Chrome ou rede foi usado nesta tarefa;
  o controlador deve revisar e consolidar os arquivos alterados. Os arquivos
  concorrentes de limpeza e reconciliação foram preservados.

## Atualização — sessão subagent-driven de 2026-09-10 (tarde/noite)

### Remoto e publicação

- Remoto privado conectado: `https://github.com/matheussilva421/Atos-TCE.git`.
  Cada bloco concluído foi publicado; `HEAD == origin/main` ao fim de cada
  tarefa. Commits desta sessão: `1956d8b`, `4b551ec`, `21054a4`, `1b60543`,
  `99f63ca`, `2a20d74`, `5dee162`, `d179b59`, `bbd6b70`, `0cc3680`, `f8b5444`.
- Nota operacional: a escalação de sandbox do controlador está quebrada
  (auto-revisor retorna erro de provider). Toda escrita Git foi executada por
  agente Luna com `require_escalated`; o controlador permaneceu somente leitura.

### Tarefa 0.8 — hardening r2

- Laudo da revisão 3: FAIL com três bloqueantes (N1 TOCTOU entre validação e
  `Move-Item`; N2 recibo parcial sem fallback de journal no `Resume`; N3
  enumeração de processos de navegador fail-open) e três não-bloqueantes
  (N4 preflight de reparse no purge, N5 `-WhatIf` explícito, N6 raiz com
  separador final).
- Hardening aplicado com RED→GREEN: baseline 279 aprovados; RED 282/15; GREEN
  307 aprovados, 0 falhas, em duas execuções consecutivas.
- Contratos implementados: pin por `FileStream` (share `Read|Delete`) com hash
  pelo mesmo stream e erro `source file is in use`; `Write-Receipt` atômico com
  fallback de journal no `Resume` (purge segue estrito); `Get-CleanupProcessNames`
  fail-closed com `-TestDenyProcessEnumeration`; `Get-BrowserProcesses` com
  `user_data_dir` via CIM e blocker por item com prova de exclusividade
  (`FileShare::None`).
- Evidência do controlador sobre o manifesto r2: 16.074 aprovados,
  23.126.367.618 bytes; 794 itens em área de navegador, 0 possuídos por
  processos em execução, 794 abrem em modo exclusivo, 0 travados, 0 ausentes.
  Portanto o falso positivo que abortou o `-Apply` anterior não se repete.
- A quarentena física está aplicada em `tmp/quarantine/20260911-012750-653`
  (recibo `moved=16074`, `not_moved=0`, `moved_bytes=23126367618`); nada foi
  purgado.

### Tarefa 0.9 — concluída

- Pacote `fase11k` executado em extração limpa (`%TEMP%`), seis gates públicos
  6/6 PASSOU, exit 0; a pasta foi preservada de propósito.
- Revisão independente 4 (Luna xhigh, somente leitura): PASS, com suíte 307/307
  duas vezes, reprodução de N1–N6 e mutation testing de N1–N3
  (`task-0.8-review-4.md`).
- `-Apply` executado em 2026-09-10 (22:13–22:36, PowerShell 5.1): recibo
  `tmp/quarantine/20260911-012750-653/receipt.json` com `items=16074`,
  `moved=16074`, `not_moved=0`, `moved_bytes=23126367618`; purge nunca executado.
- Reanálise r3 (read-only) exit 0, `entries=31721`; verificação pós-quarentena:
  `preserved_checked=13485`, `preserved_missing=0`, `approved_still_present=0`,
  `not_moved=0`. Os 58 divergentes de hash foram auditados item a item (38
  `.pyc`, 19 rastreados limpos frente ao Git, 1 log ignorado; mtime máxima
  21:27, anterior ao `-Apply`): nenhum efeito da quarentena.
- `Test-WorkspaceCleanup.ps1` 307/307 exit 0 em duas execuções pós-quarentena.

### Tarefa 0.10 — concluída

- `git branch -D codex/transfer-quiescence` (árvore idêntica a `6c88d2a` da
  `main`, aprovada especificamente pelo usuário) e
  `git branch -d codex/fundamentacao-automatico`.
- `git branch --format='%(refname:short)'` → apenas `main`;
  `git worktree prune --dry-run` → saída vazia.

### Tarefa 1.2 — concluída

- Causa raiz das falhas: `CreateNoWindow=true` fazia Python 3.14 retornar
  `WinError 87` em `os.kill(pid, 0)`, tratando processos vivos como mortos e
  derrubando os três cenários de `TransferBusyError`. Correção mínima em
  `verify-project.ps1`.
- Gate completo: 959 executados, 957 aprovados, 0 falhas, 2 skips, exit 0 em
  duas rodadas (108,97 s e 108,12 s) e repetição pós-push em 112,07 s.
- `Test-ProjectVerification.ps1` 43/43 em PowerShell 5.1 e 7;
  `test_prepare_transfer` 10/10.

### Pendências imediatas (atualizada em 2026-09-10 23:10)

1. Fase 0 encerrada: 0.8, 0.9 e 0.10 concluídas; quarentena preservada para a
   Fase 9.3 (purge somente depois da release final verificada e de aprovação
   específica de exclusão).
2. Fase 4.1 — parada humana obrigatória: login no e-Contas e na Área Restrita em
   navegador controlado com perfil de trabalho isolado (nunca reutilizar ou
   fechar o perfil pessoal), extensão `fase11k` carregada e ponte pareada.
3. Fases 4.2 e 5–7 — preflights, envio supervisionado e ondas exigem
   autorização humana imediata, ato a ato; autorização genérica não vale.
4. Fase 8 — release final: ZIP candidato, gates públicos em extração limpa e
   documentação reconciliada.
5. Fase 9.2 — decidir explicitamente se o benchmark histórico de 20 processos
   continua critério de release.

## Atualização — Tarefa 4.1 (2026-09-11)

Status: parcial; somente o item de detecção read-only de CDP foi marcado no
plano. Fonte única desta atualização: `tmp/fase41/mirror-bridge-evidence.json`
(sanitizada e temporária).

### Evidência comprovada

- CDP existente em `127.0.0.1:19231`, versão `Chrome/151.0.7922.34`.
- `portal_tab_present=true` e `e_contas_tab_present=true`.
- Ponte pareada na porta `18746`, `health_http=200`.
- `/dataset` HTTP 200, revisão `120`, `record_count=51` e prefixo lógico
  SHA-256 `23cce5807c01`.
- `/state` HTTP 200 e `/capabilities` HTTP 200.
- `real_send_enabled=false` e `pilot_enabled=false` tanto na ponte quanto nas
  capacidades.

### Limites e retomada

- A presença das abas e o pareamento da ponte não são promovidos aqui a prova
  de autenticação estrutural dos portais. O artefato também não comprova a
  origem de um perfil de trabalho isolado, a parada de login humano ou captura
  DOM; esses itens permanecem pendentes no plano.
- O mirror deve ser tratado como temporário, apenas para observação/evidência.
  O pacote live original não foi alterado, e nenhum dado live, ACL, navegador,
  portal ou código foi modificado nesta atualização documental.
- Não marcar 4.2 nem qualquer tarefa 5+. A retomada segura é obter, em
  checkpoint humano e sem credenciais digitadas pelo agente, a prova faltante
  de perfil/login/autenticação/DOM antes de qualquer preflight; manter envio e
  piloto desabilitados.

### Publicação desta atualização

- Commit nominal: `0427b71` — `docs: record authenticated phase 4.1`.
- Push fast-forward para `origin/main` confirmado; `git ls-remote` retornou
  `0427b7149b1bca9901ca9e057f7a21f0bf9d6b14 refs/heads/main`.
- Fechamento do handoff: `2822ef2` — `docs: close phase 4.1 publication
  record`, também publicado em `origin/main` por fast-forward.
- Verificação pós-push: `HEAD == origin/main`, worktree limpo e
  `git diff --check` sem erros.

## Correção operacional — Tarefa 4.1 concluída (2026-09-11)

O registro anterior de 4.1 referia-se a uma tentativa anterior contra o live
e não deve ser usado como estado atual. A validação atual foi feita após o
login manual do usuário, em Chromium 151 isolado via CDP `127.0.0.1:19231`,
sem reutilizar o perfil pessoal e sem o agente digitar credenciais.

- `tmp/fase41/mirror-bridge-evidence.json` comprova extensão 1.1.0 carregada e
  pareada com a ponte temporária em `127.0.0.1:18746`.
- Health, dataset, state e capabilities retornaram HTTP 200; dataset revisão
  120, 51 registros, prefixo lógico SHA-256 `23cce5807c01`; state revision 0.
- `real_send_enabled=false` e `pilot_enabled=false` permaneceram falsos.
- `tmp/fase41/inspect-live-final.json` registra Área Restrita e e-Contas sem
  sinal de login, com UI/controles estruturais autenticados; a coleta não
  persistiu sessão, cookie, token, CPF ou DOM bruto.
- O pacote live original não foi alterado. O mirror existe apenas para tornar
  a leitura possível ao processo da ponte, pois a publicação live tem ACL que
  recusou leitura ao usuário do serviço; os hashes dos sete arquivos copiados
  foram conferidos como idênticos.

### Retomada

Tarefa 4.2 é o próximo passo: usar navegação manual no portal, selecionar três
atos elegíveis de pelo menos duas famílias legais e condição de gênero ausente,
comparar proposta em memória com as evidências e reler sem aplicar campos.
Não iniciar Fase 5: qualquer envio exige autorização imediata ato a ato.

## Correção de retomada — Tarefa 4.2 bloqueada por divergências (2026-09-11)

O bloco acima era uma orientação de retomada anterior. O resultado observado
mais recente é **NÃO PASSA** e deve ser usado como estado vigente.

### Evidência sanitizada

- Sessão observada após login manual do usuário em Chromium 151 isolado via
  CDP `127.0.0.1:19231`; o agente não digitou credenciais.
- Consultas exatas no `ProcessonoSetor` localizaram `100120/2026`,
  `100273/2025` e `100065/2026`. Cada representante tinha uma única ação
  semântica `Complementar Ato`, com a identidade processo/ano conferida.
- Cada tela exibiu um único rádio de interessado. A seleção foi reversível e
  revelou os sete controles de formulário esperados.
- Catálogo observado: 13 modalidades, 35 fundamentos legais e 3 gêneros.
- A sidepanel, após reload, exibiu `preview ready`, 7 cards, revisão `120`,
  prefixo de dataset `23cce5807c01`; `send`/`pilot` permaneceram desabilitados.

### Matriz de bloqueio

| Processo/ano | Divergências de nomes de campo preview ↔ portal |
| --- | --- |
| `100120/2026` | `fundamento_legal`, `data_publicacao_doe` |
| `100273/2025` | `modalidade`, `data_publicacao_doe`, `matricula` |
| `100065/2026` | `data_publicacao_doe` |

Os valores dos campos, nomes, CPF, tokens, cookies e DOM bruto não fazem parte
deste handoff. A divergência em cada representante acionou STOP: não houve
`APPLY_FIELDS`, envio, finalização ou persistência de alteração. As abas
`Complementar Ato` abertas pelo agente foram fechadas; nenhuma mutação ocorreu.

### Testes, limites e retomada

- Esta atualização é documental e não altera código, pacote live, portal,
  Chrome, `tmp`, branches ou quarentena.
- Não foram executados testes de código nem qualquer ação de preenchimento ou
  envio. A validação aplicável ao bloco é revisão do diff documental,
  `git diff --check` e busca de conteúdo sensível antes da publicação.
- 4.2 e 5+ continuam pendentes e desmarcadas. Não tratar esta evidência como
  qualificação, piloto, release ou autorização de envio.
- Retomar somente com nova sessão controlada, reconciliação das divergências e
  repetição completa da conferência; manter `real_send_enabled=false` e
  `pilot_enabled=false`.

### GitHub

O registro será publicado em `main` por commit documental nominal e push
fast-forward para `origin/main`, sem force push. A SHA final e o estado
pós-push devem ser conferidos no fechamento desta sessão.

## Reconciliação efetiva da Tarefa 4.2 (2026-09-11)

Foi feita uma nova leitura, em modo somente leitura, dos três candidatos já
observados. A sessão confirmou consulta exata, uma ação `Complementar Ato`, um
rádio de interessado, sete controles do formulário e catálogo 13/35/3. As
abas de `Complementar Ato` foram fechadas ao final; `APPLY_FIELDS`, envio e
finalização não foram chamados.

### Resultado sanitizado

- A auditoria independente confirmou 50 processos/51 registros, unicidade dos
  três candidatos, hash lógico válido e os seis campos obrigatórios presentes
  com confiança alta e citações completas em chave.
- `genero` está ausente na fonte nos três registros e permanece opcional.
- `100120/2026`: DOE é a mesma data civil em representação diferente; cargo,
  matrícula e nascimento coincidem; modalidade e fundamento não possuem
  correspondência exata e o matcher sinaliza empate.
- `100273/2025`: modalidade permanece empatada; fundamento não produz
  `option.value` seguro; DOE não é a mesma data civil; matrícula não coincide
  nem com compactação conservadora; cargo/nascimento coincidem.
- `100065/2026`: DOE é a mesma data civil em representação diferente; cargo,
  matrícula e nascimento coincidem; modalidade/fundamento permanecem sem
  proposta determinística (`tie`/`probable`).

### Conclusão

A hipótese de divergência puramente textual foi confirmada somente para os
DOEs de `100120/2026` e `100065/2026`. Isso não basta para marcar o preflight
como aprovado porque a sidepanel compara texto bruto e porque os selects
obrigatórios continuam sem mapeamento único. `100273/2025` mantém diferenças
substantivas ou fonte desatualizada não resolvidas. O gate 4.2 continua
**NÃO PASSA** e as fases 5+ continuam desmarcadas.

Correção posterior de requisito: `prepareAutomaticAct` aceita decisão
selecionada com método `similarity`, pois a fundamentação documental pode não
ser textualmente idêntica ao catálogo. `pending` e `tie` continuam bloqueados,
assim como contexto/hash/valor da opção ausentes ou divergência de campo.
O teste que cobre `similarity` ficou verde e não libera qualquer ação portal.

## Correção de requisito — `similarity` mantido (2026-09-11)

O guard `LEGAL_DECISION_METHOD_UNSAFE` foi removido imediatamente após a
confirmação do usuário. O estado vigente é: `selected` com `exact`, `rule` ou
`similarity` pode prosseguir para o restante do preflight; `pending`/`tie`
não. A mudança TDD passou em 20/20 testes focais e a suíte da extensão foi
reportada em 291/291, sem portal/Chrome e sem commit/push pelo worker.

## Atualização de retomada — matcher, datas e selects (2026-09-11)

A reconciliação do requisito confirmou que `similarity` deve permanecer
aceitável quando a fundamentação do documento for apenas a opção mais parecida
do catálogo. O hardening foi ampliado sem liberar envio:

- `service-worker.js` retorna `matchedValues` de catálogo para os selects; o
  controller os encaminha ao preflight;
- `automation-preflight.js` usa esses values, valida catálogo e preserva um
  select empatado somente quando o value já selecionado no portal é exatamente
  o value retornado pelo matcher;
- empate que exige nova escolha, value ausente ou divergência permanece
  bloqueado;
- datas display/ISO equivalentes usam comparação civil estrita, e inválidos
  continuam divergentes;
- `panel.js` e `panel-view.js` compartilham a comparação, mantendo select por
  value.

Evidência TDD do bloco: RED reproduzido pelos novos casos e GREEN em 137/137
testes focados, incluindo controller, service worker, preflight e os dois
previews. A suíte anterior da extensão estava em 299/299 antes da regra de
preservação de empate; a verificação ampla final deste bloco ainda precisa ser
registrada antes do push documental.

Triagem independente sanitizada: 51 registros/50 processos, 41 completos nos
seis campos obrigatórios, 10 incompletos, gênero ausente em 51/51 e 246/246
citações completas com chaves de processo/evento/página/documento. O par de
interessados no processo `104956/2025` explica a contagem 51/50.

Status operacional: Tarefa 4.2 continua **NÃO PASSA / pendente** até três
preflights reais verdes. Não houve `APPLY_FIELDS`, envio, finalização ou
alteração persistida no portal. A próxima retomada deve recarregar o pacote
controlado, repetir identidade/ação/rádio/catálogo e registrar somente a
qualificação sanitizada.
