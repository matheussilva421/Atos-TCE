# Handoff — Automação real da Área Restrita — 2026-09-10

## Resumo

Foi corrigido o caminho de navegação automática para a estrutura real da Área
Restrita do TCE/RN. O fluxo agora reconhece a tela inicial de `Complementar
Ato` como seleção de interessado, aguarda o formulário no frame irmão criado
pelo portal, encontra o botão `Consultar` no frame `botoesNOVO.asp`, preenche o
fluxo já existente de preparação e retorna fechando a aba dinâmica do ato.

O clique final ainda não foi executado. `real_send_enabled` continua
`false`; não há qualificação real nem evento remoto confirmado.

## Evidência live sanitizada

Sessão autenticada preservada em Chrome com CDP local, sem fechar/reiniciar o
navegador durante a inspeção.

- Origem: `https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp`.
- Lista: `SISTEMAS/Processo/ProcessonoSetor.asp`.
- Filtro: `#cmbMarcadorFiltro`, `name=cmbMarcadorFiltro`.
- Ação do filtro: um `Consultar` em frame irmão
  `botoesNOVO.asp?pagina=ProcessonoSetor`.
- Ação por linha: imagem/ação `Complementar Ato`, com `addtabsinformacao`.
- Formulário: `SISTEMAS/PROCESSO/ComplementarAto.asp`.
- Seleção: rádio `input[name=escolha]`; a tela usa a mesma árvore do
  formulário antes da seleção.
- Campos permitidos confirmados: `txtModalidade`, `txtFundamentoLegal`,
  `txtDataDOE`, `txtCargo`, `txtMatricula`, `txtDataNascimento` e `txtGenero`.
- Botão final: `Complementar Ato` em frame irmão
  `botoesNovo.asp?pagina=ComplementarAto`.
- Retorno: fechar a aba superior com título `Complementar Ato` restaura a
  lista do setor.
- Marcador observado: `PROFESSOR - IPERN - 2 RUBRICAS (549)`.
- Varredura live anterior desse marcador: 549 processos, 290 com ação
  `Complementar Ato` pendente e 259 com `Ato Complementado`.
- Nenhum clique no botão final foi realizado.

## Alterações

- `work/tce-extractor/portable/extensao-complementar-ato/content/portal-navigation.js`
  - diferencia interessado não selecionado de formulário pronto no mesmo
    documento;
  - extrai o nome da coluna legada sem usar CPF/função/radio value;
  - encontra `Consultar` no frame irmão da Área Restrita;
  - não espera mutação no frame da lista quando `addtabsinformacao` abre o ato;
  - fecha a aba dinâmica e devolve um snapshot verificável da lista.
- `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`
  - aceita o primeiro snapshot `interested`/`form` do frame novo criado pelo
    portal.
- `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-navigation.test.mjs`
  - RED/GREEN para tela inicial real, frame de botões, abertura em frame irmão,
    retorno por fechamento da aba e identidade legada.
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
  - regressão para o frame novo de interessado/formulário.
- `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`
  - gate DOM live da Área Restrita marcado como concluído; gates de envio real
    continuam explicitamente pendentes.

## Testes

Comando:

```powershell
Push-Location 'work/tce-extractor/portable/extensao-complementar-ato'
npm test
Pop-Location
```

Resultado: 278 testes executados, 278 aprovados, 0 falhas, 0 cancelados.

Foco TDD adicional:

```powershell
node --test tests/portal-navigation.test.mjs
node --test tests/automation-controller.test.mjs
```

Resultados: 19/19 e 27/27 aprovados, respectivamente.

## Estado do Git/GitHub

- Branch: `codex/fundamentacao-automatico`.
- Há alterações locais ainda não commitadas neste bloco.
- Não existe remoto Git configurado; nenhum push foi realizado.
- Antes do commit, executar `git diff --check`, revisar o diff e fazer stage
  explícito apenas dos quatro arquivos de código/teste e dos dois documentos.

## Pendências reais

1. Rodar três preflights no portal real sem envio.
2. Preparar um ato concreto e obter confirmação imediata antes do primeiro
   clique final.
3. Observar aceitação/erro real, reabrir e capturar fixture sanitizada.
4. Gerar/validar `automacao/qualificacao.json` versionado.
5. Somente depois, validar lote supervisionado de até cinco atos e relatório.
6. Reempacotar ZIP final, executar os gates do pacote e atualizar guia/BAT.

## Retomada

1. Não fechar a sessão autenticada atual.
2. Rodar os testes focais e `npm test` após qualquer nova alteração.
3. Construir o pacote final com a nova allowlist, testar Chrome descartável e
   manter o envio real bloqueado até as pendências acima.
4. Antes de qualquer clique real em `Complementar Ato`, parar no checkpoint de
   confirmação de ação externa; depois registrar resultado observado, sem
   reenvio automático em caso incerto.

## Ampliação aprovada — origem híbrida e lotes (10/09/2026)

O usuário aprovou a especificação do fluxo que permite escolher entre
`Processos no setor / Finalísticos / Proc./Doc. Eletrônicos` e `Meus Processos`.
A Área Restrita continua sendo a autoridade para marcador, ação observada e
necessidade de complementação; o e-Contas será usado apenas para aquisição,
documentos e OCR reconciliados por chave canônica.

Documentos criados:

- `docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md`
- `docs/superpowers/plans/2026-09-10-fluxo-hibrido-lotes.md`

O plano exige prévia com contagens, congelamento determinístico, lotes 50/100,
estados separados por etapa, falhas isoladas por item e pausa em conflito ou
resultado remoto incerto. Nenhuma transmissão final é autorizada por tamanho de
lote ou reinício; o checkpoint de confirmação imediata permanece obrigatório.

### Próxima retomada

1. Implementar Tarefa 1 do plano em TDD (`batch_scope.py` + testes).
2. Implementar reconciliação/snapshot e gerar fixtures sanitizadas.
3. Atualizar o contrato JS e só então integrar a navegação dos dois escopos.
4. Rodar testes focais após cada tarefa e atualizar este handoff com RED/GREEN,
   arquivos e estado do Git.

## Tarefa 1 — contrato canônico de origem/prévia/lote (10/09/2026)

Implementada a primeira fatia do plano aprovado:

- `work/tce-extractor/portable/app/batch_scope.py`
  - escopos fechados `sector_finalistic` e `my_processes`;
  - marcador/valor exatos e fonte `econtas` validada;
  - lotes de 1 a 1000, com atalhos documentados para 50/100;
  - normalização de observações Área Restrita + e-Contas;
  - prévia com contagens de necessidade, conclusão, ação, aquisição, OCR,
    elegibilidade e bloqueios;
  - congelamento determinístico com `analysis_id`/`dataset_sha256`;
  - divisão ordenada sem duplicidade.
- `work/tce-extractor/portable/test_batch_scope.py`
  - 6 testes TDD para ambos os escopos, chaves extras, contagens, fila
    congelada, divisão 50/50/5 e estados fechados.

TDD observado:

- RED inicial: `ModuleNotFoundError: app.batch_scope`;
- GREEN final: 6 testes executados, 6 aprovados, 0 falhas.

Ainda não há integração com o navegador, serviço, e-Contas ou painel nesta
fatia; a próxima etapa é a reconciliação de snapshots/fixtures sanitizadas.

## Tarefas 2–3 — reconciliação e persistência da prévia (10/09/2026)

Implementadas as fatias seguintes do plano:

- `work/tce-extractor/portable/app/source_reconciliation.py`
  - reconcilia a chave canônica processo/interessado da Área Restrita com
    registros e documentos do e-Contas;
  - diferencia `exact`, `missing`, `ambiguous` e `conflict`;
  - ordena candidatos e produz `snapshot_hash` determinístico;
  - remove campos privados como token, URL, caminho absoluto e CPF da projeção.
- `work/tce-extractor/portable/app/analysis_preview.py`
  - persiste snapshots em `automacao/analises/` com escrita atômica;
  - verifica hash/`analysis_id` contra adulteração;
  - sobrevive a reinício e cria lotes ordenados uma única vez.
- Testes TDD adicionados:
  - `test_source_reconciliation.py`: 4/4 verdes;
  - `test_analysis_preview.py`: 2/2 verdes.

Resultado acumulado do bloco: 12 testes novos, 12 aprovados, 0 falhas. A
reconciliação ainda é uma biblioteca local com fixtures; não foi ligada ao
serviço HTTP, à extensão ou a uma sessão autenticada. Próxima etapa: expandir
o RunSpec/mensagens JS e expor a prévia/lotes pela bridge.

## Tarefas 4–7 — origem, análise autenticada e lotes no painel (10/09/2026)

Implementadas e testadas as seguintes integrações:

- `content/portal-navigation.js`: snapshots identificam `source_scope` pela
  rota legada da Área Restrita (`ProcessonoSetor.asp` ou `MeusProcessos.asp`),
  sem expor URL.
- `background/automation-controller.js`: RunSpec propaga `sourceScope`,
  `acquisitionSource` e `lotSize`; execução pausa se a lista autenticada não
  corresponde à origem escolhida; `analyze()` percorre todas as páginas,
  confirma marcador/escopo e produz rows sanitizadas com hash sem congelar fila,
  abrir ato ou enviar dados.
- `lib/messages.js` e `background/service-worker.js`: novo `AUTO_ANALYZE`
  tipado, com resolução da aba autenticada ativa quando necessário.
- `sidepanel/panel.html` e `sidepanel/panel.js`: seletor setor/finalísticos ou
  meus processos, tamanho 50/100 (e piloto 1), análise prévia com métricas e
  botão separado para criação determinística de lotes.
- Testes cobrem rota/escopo, mismatch, análise multipágina sem envio, seletor,
  lotes e contrato `AUTO_ANALYZE`.

TDD/gates executados:

- RED: ausência inicial do método de análise e da propagação origem/lote no
  painel.
- GREEN: `npm test` — 285 testes executados, 285 aprovados, 0 falhas,
  0 cancelados.
- Focos: portal 20/20, controlador 29/29 e painel 40/40; a suíte completa
  também permaneceu verde.

Limite atual: a UI já dispara a fotografia da Área Restrita e persiste a
análise/lotes, mas o cruzamento ainda usa o dataset local previamente
importado. A orquestração que baixa documentos novos do e-Contas por fila
congelada e roda OCR incremental por item ainda precisa ser ligada ao
`Coletar-Processos-TCE.ps1`/`incremental_pipeline.py`; essa etapa não está
concluída nem foi apresentada como download/OCR remoto realizado.

## Tarefa 8 — fila congelada no coletor e preparação/OCR local (10/09/2026)

Implementada a primeira integração operacional da Tarefa 8:

- `work/tce-extractor/portable/app/frozen_queue.py` valida a identidade/hash
  do snapshot, escolhe a fila inteira ou um lote explícito e reconcilia
  chaves canônicas com o e-Contas sem reordenar nem substituir.
- `work/tce-extractor/portable/TceFrozenQueue.psm1` fornece o leitor
  equivalente para Windows PowerShell 5.1 e foi incluído no pacote.
- `work/tce-extractor/portable/Coletar-Processos-TCE.ps1` aceita
  `-FilaCongelada` e `-NumeroLote`; seleção manual e fila congelada são
  mutuamente exclusivas; ausência/duplicidade interrompe antes do primeiro
  download; a preparação/OCR incremental existente roda por item após a
  sincronização.
- allowlist, auditoria do pacote e README foram atualizados.

TDD/gates do bloco:

- RED: `ModuleNotFoundError: app.frozen_queue` ao criar o teste do contrato.
- GREEN: `python -m unittest discover -s portable -p 'test_frozen_queue.py' -q`
  — 5 testes, 5 aprovados, 0 falhas, incluindo Windows PowerShell 5.1.
- GREEN: `npm test` — 285 testes, 285 aprovados, 0 falhas.
- GREEN: `python -m unittest discover -s portable -p 'test_*.py' -q` — 23
  testes, 23 aprovados, 0 falhas.

Limite honesto: o coletor é iniciado localmente com o JSON da análise; ainda
não há execução automática do PowerShell disparada pelo painel. Nenhum
download real, OCR real, preflight ou envio no portal foi alegado nesta etapa.

### Empacotamento e validação adicional

- O primeiro ZIP da fatia revelou `ModuleNotFoundError` porque a allowlist não
  carregava `analysis_preview.py`, `batch_scope.py` e
  `source_reconciliation.py`; a falha foi corrigida e a auditoria foi repetida.
- ZIP validado: `work/tce-extractor/outputs/tce-processos-completo-portatil-fase11b.zip`
  — 98.292.377 bytes, SHA-256
  `ca4e29b8922793ee22fa85fbe7e7139fb7bd7cfa467449cb9db9066186ccebee`.
- Extração `fase11b-extracted`: `TESTAR-PACOTE.ps1` passou 6/6; importação
  real de `local_service.py --help` passou; smoke Chrome descartável passou
  1/1 com pareamento/capabilities.
- A suíte Python ampla (`python -m unittest discover -p 'test_*.py' -q`)
  executou 400 testes, 399 passaram e 1 falhou em
  `test_automation_browser.AutomationBrowserTests.test_simulated_pages_frames_and_send_block`
  por fechamento do canal assíncrono do `Page.evaluate`; não houve falha nos
  23 testes focados do pacote nem nos 285 testes JS. O erro é de ambiente do
  smoke Playwright, não foi mascarado como verde.
- O smoke local real preservou a sessão Chrome autenticada; a lista de alvos
  ainda mostra Área Restrita e e-Contas abertas no DevTools 9222. Nenhuma aba
  foi fechada ou reiniciada.
- Verificação live somente leitura em 10/09/2026: a aba da Área Restrita
  permaneceu em `novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp`, com
  título autenticado, 6 frames e menu visível para “Meus Processos
  Eletrônicos”/“Proc./Doc. Eletrônicos”; a aba e-Contas também permaneceu
  aberta. Não houve clique, navegação, preenchimento ou envio nessa inspeção.
- A inspeção dos frames autenticados também encontrou, no frame de
  `ProcessonoSetor.asp`, o seletor `cmbMarcadorFiltro` com 70 opções, valor
  selecionado `6189` e rótulo sanitizado `PROFESSOR - IPERN - 2 RUBRICAS (549)`;
  a página exibida era `61 - 90 de 549`. No frame irmão de `MeusProcessos.asp`
  a rota e a tela também estavam presentes. Esses dados confirmam o contrato
  de origem/marcador, mas não equivalem a análise completa nem a efeito remoto.

## Git/GitHub após Tarefas 4–8

- Branch: `codex/fundamentacao-automatico`.
- `git add`/commit permanecem bloqueados por permissão em `.git/index.lock`;
  não há remoto configurado e nenhum push foi realizado.
- Alterações permanecem no worktree.

## Próxima retomada prioritária

1. Adicionar teste RED para `batch_runner.py` com fila congelada, retomada,
   cache e falhas 401/403/429, documento ausente e OCR inconclusivo.
2. Expor uma ação local deliberada para iniciar a coleta do lote congelado,
   sem transportar token para a extensão e sem iniciar envio de ato.
3. Revalidar ZIP/Chrome descartável antes de retomar os gates reais
   supervisionados da Área Restrita.

## Tarefas 8–10 — disparo pelo painel, launcher híbrido e conexão (10/09/2026)

O acoplamento local da fila congelada foi concluído nesta rodada, sem habilitar
envio de ato:

- `portable/app/acquisition.py` valida exatamente `lot_number` e monta o
  comando local do coletor com `-FilaCongelada`, `-NumeroLote`,
  `-NaoInterativo` e `-ServiceChild`; o comando não contém
  `-enable-real-send`.
- `portable/app/local_service.py` expõe `POST /api/v1/analysis/{id}/acquire`
  e `GET /api/v1/analysis/{id}/acquire/{job}`. A rota exige bridge pareada,
  análise existente com lotes, impede job duplicado do mesmo lote e retorna
  apenas estado/job/PID, sem token ou caminho absoluto.
- `sidepanel/panel.html`, `sidepanel/panel.js` e `lib/bridge-client.js` agora
  permitem escolher o lote criado, iniciar download/OCR e acompanhar o job.
  O painel exibe separadamente `acquisition_eligible`, itens prontos para
  preflight e itens `acquisition_pending`.
- `portable/Coletar-Processos-TCE.ps1` aceita os switches de execução do
  serviço; `-ServiceChild` usa `.collector.lock`, preservando o lock do serviço
  e bloqueando transferência concorrente.
- `portable/app/menu.ps1`, `portable/INICIAR.cmd` e `portable/INICIAR.bat`
  oferecem as opções 9 (verificar ponte) e 10 (drenar lote congelado). O
  comando `INICIAR.bat ponte` inicia e verifica a ponte sem abrir o menu.
  `Stop-TceLocalService` remove o `.operation.lock` somente quando o PID do
  lock pertence ao serviço identificado.
- `portable/TcePortable.Core.psm1` detecta, somente por leitura, portas
  DevTools locais 9222–9232 com aba TCE/RN. O coletor tenta reutilizar o Chrome
  autenticado já aberto antes de criar perfil/janela nova.
- `portable/README.md` e `portable/GUIA-RAPIDO.md/.html` documentam o fluxo
  híbrido Área Restrita → análise/lotes → e-Contas/download/OCR.

TDD e validações desta rodada:

- RED/GREEN `test_acquisition.py`: 2/2;
- RED/GREEN rota local de aquisição em `test_local_service.py`: incluída na
  suíte local, pareamento/job/status verdes;
- `npm test`: 286/286 testes, 0 falhas;
- `python -m unittest discover -s portable -p 'test_*.py' -q`: 26/26,
  0 falhas;
- `python -m unittest test_local_service test_portable_end_to_end -q`:
  26 executados, 26 aprovados, 0 falhas, 1 ignorado;
- `tests/Test-PortableMenu.ps1`: 83/83 aprovados;
- `test_powershell_encoding.py`: 2/2 aprovados, incluindo detecção de
  `9223` simulada;
- ZIP `work/tce-extractor/outputs/tce-processos-completo-portatil-fase11g.zip`:
  95.875.101 bytes, SHA-256
  `91bdf25a225928f396278b4afe6e5743a9b8eb25057ae11bbe06240baaff6a83`;
- extração `fase11g-extracted`: `TESTAR-PACOTE.ps1` 6/6 aprovados;
- smoke real do launcher: `INICIAR.bat ponte` e `INICIAR.cmd` — 2/2
  aprovados em caminho Unicode, serviço iniciado, `/health` respondendo,
  menu com 10 opções e encerramento sem lock órfão;
- smoke de bridge no ZIP: pareamento HTTP real + capabilities, com
  `real_send_enabled=false` e `rules_version=legal-foundation-v1`;
- estado live somente leitura: `127.0.0.1:9222` continua expondo as abas
  autenticadas da Área Restrita e e-Contas; nenhuma aba foi fechada,
  reiniciada, navegada, preenchida ou enviada nesta rodada.

Limites ainda abertos, deliberadamente não marcados como verdes:

- não foi disparado download real do e-Contas nem OCR real por lote;
- não foram executados os três preflights reais, primeiro envio autorizado,
  observação/reabertura, fixture de resultado, qualificação versionada ou lote
  supervisionado de até cinco atos;
- `real_send_enabled` permanece `false`; a confirmação imediata anterior ao
  botão final continua obrigatória quando/ se a qualificação for concluída;
- o Git continua sem commit/push nesta rodada: `.git/index.lock` permanece
  sem permissão de escrita e não há remoto configurado.

### Retomada exata

1. Carregar/recarregar a extensão a partir de
   `outputs/tce-processos-completo-portatil-fase11g-extracted/extensao-complementar-ato`.
2. Executar `INICIAR.bat` no pacote extraído, informar o pairing code no painel
   e confirmar que o painel mostra “Mesa local conectada”.
3. Com as duas abas já autenticadas, selecionar a origem e marcador na Área
   Restrita, clicar **Analisar pendências no portal**, revisar contagens e
   criar os lotes.
4. Executar o primeiro lote em modo download/OCR; conferir arquivos,
   `cache-ocr.json`, relatório e estado antes de qualquer preflight.
5. Só então retomar os gates reais supervisionados, parando imediatamente
   antes de `Complementar Ato` final até a autorização/qualificação aplicável.

## Verificação adicional do launcher e do pacote — 10/09/2026

Atendendo à solicitação de manter o `INICIAR.bat` atualizado e provar a
conexão sem perder a sessão do Chrome:

- `INICIAR.bat` permanece a entrada compatível e delega todos os modos ao
  `INICIAR.cmd`: menu híbrido, `ponte` e `parar`. O `INICIAR.cmd` inicia a
  ponte antes do menu, oferece as opções 1–10 e mantém download/OCR como ação
  explícita de lote congelado.
- O ZIP atual foi extraído novamente em uma pasta temporária limpa. A
  auditoria `TESTAR-PACOTE.ps1` passou em modo `public` (runtime, manifest,
  dependência Node, ausência esperada de acervo privado e auditoria pública).
  Uma pasta extraída antiga continha `acervo-tce` incompleto e causou uma
  reprovação falsa de `private`; ela não representa os bytes do ZIP atual.
- Smoke do launcher no pacote recém-extraído: `INICIAR.bat ponte` e
  `INICIAR.cmd` passaram 2/2, em caminho Unicode, iniciando o serviço,
  respondendo `/api/v1/health` e encerrando sem lock órfão.
- `npm test`: 286/286 aprovados.
- `python -m unittest discover -s portable -p 'test_*.py' -q`: 26/26
  aprovados.
- `tests/Test-PortableMenu.ps1`: 83/83 aprovados.
- `python -m unittest test_powershell_encoding.PowerShellEncodingTests -v`:
  2/2 aprovados.
- A verificação live somente leitura encontrou `TCE_PORTAL_PORT=9222` e dois
  alvos TCE/RN no mesmo Chrome já aberto: Área Restrita autenticada e
  e-Contas. Nenhuma aba foi fechada, reiniciada, navegada, preenchida ou
  enviada.
- A suíte Python completa foi iniciada, mas ficou sem progresso/resultado por
  mais de dois minutos; foi interrompida para não deixar processo pendurado.
  Portanto ela não é marcada como verde nesta rodada. As suítes focadas acima
  continuam sendo as evidências válidas do bloco alterado.

Estado do artefato verificado:

- ZIP: `work/tce-extractor/outputs/tce-processos-completo-portatil-fase11g.zip`;
- SHA-256: `91bdf25a225928f396278b4afe6e5743a9b8eb25057ae11bbe06240baaff6a83`;
- `real_send_enabled=false`; o botão final e os gates remotos continuam
  deliberadamente não qualificados.

Próxima retomada: carregar a extensão do ZIP extraído limpo, parear a ponte,
executar a análise real de um escopo/marcador, criar um lote pequeno e só
depois disparar download/OCR real. Não reutilizar a pasta extraída antiga sem
regenerar o acervo privado pelo fluxo autorizado.

## Verificação live do marcador e correção de escopo — 10/09/2026

- A Área Restrita permaneceu autenticada no Chrome existente, sem fechamento
  ou reinício. A navegação somente leitura abriu
  `ProcessonoSetor.asp`, selecionou o marcador real `6189` e confirmou no DOM
  o rótulo `PROFESSOR - IPERN - 2 RUBRICAS (549)`.
- O filtro real foi percorrido nas 19 páginas do setor: 549/549 processos
  únicos observados, todos com a ação DOM `Complementar Ato`. A prévia
  derivada é de 11 lotes de 50 ou 6 lotes de 100. Nenhum processo foi aberto,
  nenhum interessado foi selecionado, nenhum campo foi preenchido e nenhum
  ato foi enviado.
- A inspeção encontrou uma lacuna antes do download: o `source_scope` era
  congelado na análise, mas o coletor sempre navegava para `Meus Processos`.
  Corrigido em TDD com `-EscopoPortal`: `sector_finalistic` usa
  `processos-no-setor/no-setor` e `my_processes` usa `meus/meus-processos`.
  O serviço local e a opção 10 do menu agora leem o escopo congelado e passam
  essa escolha ao coletor.
- RED registrado: os testes de aquisição falharam com `unexpected keyword
  argument 'source_scope'` antes da implementação. GREEN: aquisição 3/3,
  serviço 23/23 (1 ignorado), PowerShell 3/3, suíte portátil 27/27 e menu
  83/83.
- Novo ZIP: `work/tce-extractor/outputs/tce-processos-completo-portatil-fase11h.zip`;
  95.875.890 bytes; SHA-256
  `f484579b433d4b300cc06667499fcdda48d0e9b4d13730124e131982eb16a185`.
  Extração limpa: auditoria pública aprovada; `INICIAR.bat ponte`/`INICIAR.cmd`
  2/2; o ZIP contém `EscopoPortal` e a rota finalística.
- Pareamento do pacote `fase11h` testado com HTTP real da ponte: capabilities
  responderam `rules_version=legal-foundation-v1` e
  `real_send_enabled=false`; o serviço foi parado ao fim do smoke.

O número 549 é uma prévia live do portal, não ainda um snapshot persistido
pela extensão. Permanecem pendentes o carregamento da extensão nessa sessão,
a criação do snapshot/lotes pelo painel, o download/OCR real do primeiro lote,
os três preflights, o primeiro envio autorizado, observação/reabertura,
fixture, qualificação e lote supervisionado.

## Coleta real com marcador e ponte de download — 10/09/2026

- O teste de enumeração inicialmente falhou porque o redirecionamento para a
  primeira página podia ocorrer durante o reload Angular do filtro. O teste
  RED/GREEN foi ampliado para exigir espera da paginação (`attempt < 20`,
  espera de 300 ms quando o controle ainda não existe) e o lote congelado não
  altera o tamanho da página antes da volta à página 1.
- A execução real confirmou, no e-Contas, o marcador congelado
  `PROFESSOR - IPERN - 2 RUBRICAS (549)` antes da enumeração e validou
  integralmente o lote 1/50: 50/50 chaves presentes, ordem preservada e zero
  download iniciado fora da fila.
- A ponte de transporte autenticado do Chrome foi exercitada no processo
  `102390/2026`: 18 PDFs foram gravados no acervo, todos com status `complete`
  e sem erro de transporte. A preparação progressiva executou a análise real;
  os campos detectados foram interessado, modalidade, fundamento legal, data
  do DOE, cargo, matrícula e data de nascimento. O gênero permaneceu ausente.
  O pipeline escolheu texto nativo nessas páginas e mantém Tesseract/OCR como
  fallback para páginas sem texto, portanto `cache-ocr.json` vazio nesse
  processo é compatível com a regra de não fazer OCR desnecessário.
- Durante a prova apareceu um erro de compatibilidade do Windows PowerShell:
  `[IO.File]::GetLength` não existe. Foi corrigido em
  `portable/Coletar-Processos-TCE.ps1` para `(Get-Item -LiteralPath
  $Destination).Length`, com teste de regressão e parser PowerShell verdes.
- A execução do lote 1 continua limitada a um download serial por vez. A
  tentativa anterior foi interrompida após registrar erros antigos; ela não
  invalida a nova prova, que grava em
  `work/tce-extractor/outputs/live-real-fase11h-sector-lot50/processos`.

Validações novas:

- `python -m unittest portable/test_portal_driver.py -q`: 5/5 aprovados;
- `python -m unittest test_powershell_encoding.PowerShellEncodingTests -v`:
  5/5 aprovados;
- parser nativo do `Coletar-Processos-TCE.ps1`: `PowerShell syntax OK`;
- prova live: lote 50 validado, processo 102390/2026 com 18/18 PDFs completos
  e análise progressiva real publicada.

Pendências após esta prova: aguardar/fechar o lote em andamento com contagem
final, reconstruir o ZIP fase seguinte incluindo o driver e a correção do
PowerShell, auditar `INICIAR.bat` no ZIP novo, e só então retomar os gates
remotos de preflight/qualificação. `real_send_enabled=false` continua
inalterado; nenhum interessado foi selecionado, formulário foi preenchido ou
ato foi enviado.

## Auditoria independente Luna — 10/09/2026

Auditoria somente leitura concluída pelo subagent Luna xhigh, sem tocar no
Chrome e sem alterar arquivos. O resultado confirma:

- concluído com evidência: marcador 6189 aplicado no e-Contas antes da
  enumeração, lote 1 reconciliado 50/50 e 18/18 PDFs do processo
  `102390/2026` baixados pela sessão autenticada;
- pendente: fechamento/auditoria dos 50 processos, OCR real em ao menos um
  documento sem texto nativo, preenchimento/preflight real e todos os gates de
  envio/observação/qualificação;
- risco controlado: existem resultados antigos em
  `acervo-tce/processos` e a execução corrente grava em
  `processos`; os diretórios não devem ser tratados como um único snapshot;
- `real_send_enabled=false` e o envio final permanecem bloqueados.

Esta auditoria não substitui a validação live nem autoriza envio.

## Compatibilidade do snapshot real schema 2 — 10/09/2026

- A auditoria encontrou e reproduziu uma incompatibilidade: o snapshot live
  persistido pelo fluxo da extensão usa `schema_version=2` e `preview=null`,
  enquanto `AnalysisPreviewStore` aceitava somente schema 1 e exigia uma
  prévia materializada.
- Corrigido em TDD: o store agora grava schema 2, lê schema 1/2 para manter
  compatibilidade e aceita `preview=null` no snapshot já congelado; prévias
  materializadas continuam aceitas.
- RED/GREEN: o teste do snapshot schema 2 falhou antes da correção e passou
  depois; `test_analysis_preview.py` 3/3 e suíte portátil 34/34.
- Validação contra o artefato live: `AnalysisPreviewStore.load` aceitou
  `analysis-2c23cdf170d0a3c3773b8160`, com 549 itens e 11 lotes.

O ZIP precisa ser reconstruído novamente para incluir esta correção antes da
entrega final.

## Fechamento do lote real 1/50 e pacote fase11j — 10/09/2026

- A execução corrente foi concluída sem falhas de processo: 50/50 chaves da
  fila congelada foram processadas, 1.037 PDFs foram baixados pela sessão
  autenticada do Chrome, 1.037/1.037 documentos ficaram `complete` no
  checkpoint e nenhum documento apresentou erro de transporte. Os avisos de
  `Capa` HTTP 400 foram registrados para documentos específicos, sem impedir a
  coleta dos demais documentos nem gerar processo com falha.
- O coletor não baixou processos fora do lote nem processos fora do marcador:
  a fila foi congelada na Área Restrita, o marcador foi aplicado no e-Contas
  antes da enumeração e a reconciliação final permaneceu limitada às 50 chaves.
- 10 processos terminaram `complete` e 40 `partial` no resumo de preparação.
  `partial` aqui significa qualificação incompleta de campos do formulário
  (principalmente gênero/nascimento ausentes em alguns registros), não erro de
  download; os 1.037 documentos baixados estão completos.
- Nenhum PDF dos 1.037 documentos era imagem pura; por isso o pipeline usou
  texto nativo e deixou `cache-ocr.json` vazio, conforme a regra de não aplicar
  OCR quando o texto já existe. O Tesseract empacotado foi validado
  separadamente sobre uma página real baixada (`exit=0`, saída não vazia), sem
  alterar o acervo do processo. Ainda falta uma prova portal-real de fallback
  em PDF originalmente sem texto nativo.
- O ZIP final desta etapa é
  `work/tce-extractor/outputs/tce-processos-completo-portatil-fase11j.zip`,
  95.877.778 bytes, SHA-256
  `7555A9FD4D35E71129B0561CF816098161D34EEA79C5D26D87676C9E11E3E54F`.
  A auditoria em extração limpa passou, `INICIAR.bat ponte` iniciou a ponte,
  `/api/v1/health` respondeu com `rules_version=legal-foundation-v1`,
  `real_send_enabled=false`, `pilot_enabled=false`, e `INICIAR.bat parar`
  encerrou o serviço.
- A correção do snapshot schema 2 está incluída no pacote: o store aceita
  schema 1/2 e `preview=null`; o snapshot live foi carregado com 549 itens e
  11 lotes.

## Campos incompletos do resultado real — 10/09/2026

- A revisão 120 da preparação progressiva contém 50 processos e 51 registros
  de interessado, todos com estado técnico `partial` por pelo menos um campo
  ausente; a contagem anterior de “40 parciais” confundia status de
  sincronização do checkpoint com status da análise.
- `genero` está ausente nos 51 registros. `data_nascimento` está ausente em 9
  registros. `modalidade` e `fundamento_legal` estão ausentes apenas no
  segundo registro do processo `104956/2025`. `data_publicacao_doe`, `cargo` e
  `matricula` foram encontrados nos 51 registros.
- O relatório por processo está em
  `docs/notes/2026-09-10-lote1-campos-incompletos.md`. Regra operacional
  confirmada pelo usuário: `genero` pode ficar ausente e não bloqueia o
  preflight. `modalidade`, `fundamento_legal`, `data_publicacao_doe`, `cargo`,
  `matricula` e `data_nascimento` continuam obrigatórios; qualquer ausência
  bloqueia o preflight e impede escrita parcial.
- A alteração foi coberta por teste dedicado: ausência de gênero é aceita; a
  ausência de cada um dos outros seis campos retorna
  `FIELD_PROPOSAL_MISSING`. A suíte da extensão ficou verde em 287/287.

Pendências de retomada: qualificar os 50 processos parciais, obter uma
evidência real de fallback OCR em documento sem texto nativo, executar somente
após autorização/qualificação os preflights e o primeiro envio supervisionado,
observar/reabrir o resultado, produzir fixture e concluir a qualificação
versionada. `real_send_enabled=false` continua sendo a trava efetiva; nenhum
interessado foi selecionado e nenhum Complementar Ato foi enviado.

### Atualização de regra de campos e release fase11k — 10/09/2026

- [x] Regra operacional confirmada: `genero` é opcional e pode ficar vazio;
  `modalidade`, `fundamento_legal`, `data_publicacao_doe`, `cargo`, `matricula`
  e `data_nascimento` são obrigatórios.
- [x] O preflight automático foi ajustado para aceitar ausência de gênero,
  preservar esse controle sem escrita e bloquear ausência de qualquer um dos
  outros seis campos com `FIELD_PROPOSAL_MISSING`, sem escrita parcial.
- [x] Teste dedicado e suíte da extensão passaram: 287/287 testes.
- [x] Suíte Python portátil passou: 34/34 testes.
- [x] ZIP fase11k reconstruído e auditado em extração limpa:
  `work/tce-extractor/outputs/tce-processos-completo-portatil-fase11k.zip`,
  95.877.835 bytes, SHA-256
  `85BAD2192F6F3C7289F574D4EF126F4700565843AFB5793E61E49CD47DE05FBB`.
- [x] `TESTAR-PACOTE.ps1` passou nos seis gates públicos. `INICIAR.bat ponte`
  iniciou a ponte na porta 18743, o health respondeu com
  `rules_version=legal-foundation-v1`, `real_send_enabled=false`,
  `pilot_enabled=false`, e `INICIAR.bat parar` encerrou o serviço.
- [x] Como a instância Chrome anterior não estava exposta ao controle visual
  nem ao CDP 9222, foi aberto, com autorização do usuário, um perfil Chrome
  de trabalho separado em `.chrome-work`, sem usar o Chrome pessoal. A janela
  está aguardando login manual do usuário; nenhuma credencial foi digitada.

Próxima retomada após o login: confirmar a aba autenticada da Área Restrita,
parear a extensão com a ponte local, repetir análise somente leitura no escopo
escolhido e avançar para DOM sanitizado/preflight. O envio final permanece
desligado e requer confirmação imediata no momento da ação.

### Retomada de sessão Chrome — 10/09/2026

- A sessão visual disponível no host continua limitada ao navegador interno;
  nenhuma janela Chrome nativa aparece na enumeração de UI.
- A tentativa de criar os perfis isolados `.chrome-work` e
  `.chrome-work-cdp*` pelo shell foi encerrada pelo próprio processo Chrome
  antes de criar os diretórios e sem abrir o CDP 9222 (`profile_exists=false`,
  `cdp=0`). O Chrome pessoal não foi usado nem fechado.
- Por isso não há, nesta retomada, evidência de aba autenticada acessível para
  DOM sanitizado, pareamento da extensão ou preflight real. O código e o ZIP
  local permanecem validados; falta apenas reexpor uma sessão Chrome de
  trabalho ao executor visual/CDP para continuar os gates remotos.
