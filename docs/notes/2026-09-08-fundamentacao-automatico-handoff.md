# Handoff — plano por fases de fundamentação e automação

## Estado da execução

- Implementação iniciada em `codex/fundamentacao-automatico`, derivada de `main` em `dc84402`.
- O ledger vivo está em `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/progress.md` (git-ignorado) e registra tasks, conflitos e decisões.
- Task atual: Fase 4 — API local e compatibilidade da extensão; Fases 1–3 aprovadas e fechadas.
- Baseline desta execução: `npm test` 124/124 pass; Python focal 99/99 pass, 1 skip ambiental. Warnings de `fitz` depreciado e `ResourceWarning` já aparecem na baseline e não foram introduzidos nesta branch.
- Fase 0 concluída e revisada: commits `b99fd80` e `54dcf9f`; fixtures/testes sanitizados aprovados em re-revisão Luna. A suíte JS pós-fase ficou 125/126 porque a regressão RED do matcher continua intencional para a Fase 2.
- Fase 1 aprovada em revisão final após cinco rounds de correção: commits de código `f0a72b5`, `e84ac95`, `8b3a411`, `e85aa35`, `d305ee6`, `0876f2d` e documentação `5b1a732`, `8a64d4d`, `86837a9`, `559b089`, `6a3b63c`, `45e225e`. Último foco: 18/18 testes de contexto, 7/7 pipeline dirigido, 89/89 focal Python, 19/19 batch runner; revisão final Approved. O pacote portátil continua pendente para a Fase 10.
- Envio real continua bloqueado; nenhum PDF, dado de processo ou sessão autenticada será publicado no Git.

## Trabalho documental concluído

- Entrevista de requisitos consolidada em plano detalhado de 11 fases (0 a 10), vinculado aos módulos reais da extensão e serviço Python.
- Inspecionados contratos de dataset/mensagens, matcher, detector, worker, cliente HTTP, serviço, progresso, extração, pipeline e empacotador.
- Registrados interfaces propostas, TDD por fase, critérios de aceite, regras operacionais, relatório incremental, matriz de interrupções e gates reais.
- Revisão solicitada posteriormente: redesign completo acrescentado à fase 8, com entregas 8A–8E, tokens visuais, wireframes, estados, acessibilidade, componentes, testes e impacto no pacote.

## Arquivos

- Criado `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`.
- Criado este handoff.
- Nenhum código funcional foi alterado na entrega documental original; a implementação funcional desta execução ocorrerá somente na branch acima.

## Decisões principais

- EC41 art. 6º ou 7º; art. 7º isolado aceito operacionalmente pelo usuário.
- Variante §5 somente quando CF art. 40 §5 constar na resolução; cargo não basta.
- EC47 art. 3º para terceira família; outras opções por maior semelhança conforme escolha expressa, com risco e rastreabilidade documentados.
- Todos os disponíveis; pendências documentais e divergências são registradas e puladas; envio incerto pausa sem repetição automática.
- Sete campos atuais; diário SQLite separado do progresso legado; relatórios HTML/CSV locais e painel.
- Proposta visual para implementação futura: Ato atual / Execução / Histórico, configurações recolhidas, campos verticais e trilha Resolução → Regra → Opção. Tema claro azul-petróleo, fontes locais e nenhuma tabela larga no painel estreito.
- Ajuste posterior solicitado no wireframe: botão “Preencher campos disponíveis” e indicação do modo manual no topo de Ato atual, logo abaixo das abas e antes da fundamentação. Plano, wireframe e critério de aceite atualizados; ação não será duplicada no rodapé. Somente documentação alterada.
- Histórico passa a exigir endpoints autenticados paginados de execuções/eventos; contratos adicionados na seção 13.4 e vinculados à fase 4.

## Validação e testes da entrega documental

- Baseline JS executada na etapa anterior desta mesma sessão: `npm test`, 124 testes, 124 passaram, 0 falharam.
- Nesta entrega documental não se implementaram os testes futuros descritos no plano.
- Inspeção manual anterior: portal autenticado, 170 processos/9 páginas, catálogo e frames verificados; nenhum envio ou preenchimento realizado, retorno à lista confirmado.
- Verificação documental executada: 8 verificações, 8 passaram, 0 falharam. Conferidos 11 fases, 18 seções, blocos de código balanceados, ausência de TBD/TODO, critérios de aceite, contrato de consumo único, handoff e fontes de empacotamento.
- Plano com mais de 600 linhas; revisão adicionou contrato explícito de consumo único e procedimento de habilitação após piloto.
- Redesign fundamentado na leitura de `panel.html`, `panel.css`, `panel.js` e contratos de testes; tabela atual tem largura mínima de 42rem. Não houve renderização, screenshot ou QA visual real nesta revisão; esses gates constam nas entregas 8A/8D.
- Verificação da revisão de redesign: 8 verificações, 8 passaram, 0 falharam (11 fases preservadas, cinco subseções, fences balanceadas, wireframes, API de histórico, QA responsiva, empacotamento e escopo documental). `git diff --check` passou. Suíte funcional não reexecutada, pois somente Markdown mudou.
- `git diff --cached --check` deve passar antes do commit. Nenhuma suíte funcional adicional necessária para estes dois arquivos Markdown.

## GitHub e branch atual

- Estado inicial desta execução: `main`, limpo, nenhum remoto configurado; branch de implementação criada como `codex/fundamentacao-automatico`.
- Os dois documentos integram o commit documental desta entrega; obter seu identificador com `git log -1 --oneline -- docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`.
- Push indisponível sem destino; não configurar remoto arbitrário. Nenhum envio ao GitHub realizado.

## Registro por fase — Fase 4 — API local e compatibilidade

- Implementada a API autenticada v1 em `portable/app/local_service.py` para
  capabilities, contexto jurídico, runs, queue, snapshot, events, control e
  relatórios HTML/CSV. O serviço recalcula o hash do dataset atual, confere
  identidade/contexto, limita corpo a 2 MiB e lote a 10.000, e não aceita
  root/path/URL do cliente.
- Implementados `automation-schema.js`, métodos de automação no bridge,
  mensagens AUTO_START/AUTO_PAUSE/AUTO_RESUME/AUTO_STOP/AUTO_STATUS e cache
  contextual no worker com invalidação por dataset/revisão. Serviço antigo
  preserva o modo manual; somente páginas da extensão controlam execução.
- TDD: RED cobriu falta de token/origin, dataset trocado, revisão obsoleta,
  payload extra e limites; GREEN focal Python 30 testes (29 pass, 1 skip),
  JS focal 37/37 e suíte JS 169/169. Python ampliado: 79 executados, 78 pass,
  1 skip. `py_compile` e `git diff --check` passaram.
- A descoberta Python completa foi tentada, ficou sem saída e foi encerrada no
  PID específico 15456 após acesso negado no encerramento normal. Não restou
  processo dessa execução; a descoberta ampla não é declarada PASS. Warnings
  de `fitz`/`ResourceWarning` permanecem conhecidos do ambiente.
- Nenhum envio real, consumo de comando ou alteração de navegação do portal
  foi iniciado. Detalhes: `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/task-4-report.md` e `task-4-handoff.md`.

## Problemas e soluções

- Primeiro `git add` falhou por acesso negado a `.git/index.lock` no sandbox.
- Com permissão ampliada, Git detectou proprietário diferente. Resolvido com `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos'`, limitado ao comando; configuração global não alterada.
- Staging limitado nominalmente aos dois Markdown; nenhum `git add .` utilizado.

## Tasks e retomada

1. [x] Ler o plano salvo, especialmente decisões da seção 1 e contratos da seção 4.
2. [x] Criar branch de implementação e ledger vivo.
3. [x] Executar fase 0 com baseline atualizada, reprodução RED e fixtures sanitizadas.
4. [~] Implementar fases 1–10 em ordem de dependência, atualizando este handoff após cada bloco; Fases 0–1 concluídas, Fase 2 em preparação.
3. Não interpretar `completed` legado nem sinal DOM como envio confirmado.
4. Confirmação real após envio ainda não foi observada. Fase 9 define como obter e transformar em fixture/teste.
5. Não executar lote real apenas porque o plano foi salvo. Esta solicitação foi de documentação.
6. Nenhuma reversão funcional necessária; alterações funcionais serão feitas apenas na branch de execução.
7. Para o redesign, ler toda a seção 13.1–13.5 antes de trocar a marcação: `ELEMENT_IDS`, `renderRows`, mensagem permanente, fixtures e allowlist precisam ser atualizados juntos na implementação.

## Registro por fase — Fase 0

- Comandos: `node --test tests/matcher.test.mjs tests/normalizer.test.mjs`; `npm test`; `python -m unittest test_tce_extractor test_analysis_pipeline test_extension_exporter test_local_service -q`.
- Resultado: focal 34 testes, 33 pass, 1 RED conhecido; full JS 126, 125 pass, 1 RED conhecido; Python focal 85 pass, 1 skip ambiental. A baseline anterior foi 124/124 JS e 99/99 Python focal ampliado.
- RED: matcher legado escolhe `synthetic-ec41-without-p5` em texto sem referências, onde a Fase 2 deverá retornar pendência/null.
- GREEN: catálogo, fixtures simuladas, IDs duplicados no frame e contratos de sanitização passaram após os fixes.
- Validação: somente fixtures sintéticas; nenhum clique, preenchimento ou envio real.
- Limitação: a Fase 0 não corrige produção; a falha RED é esperada até o resolvedor da Fase 2.
- Próximo passo: implementar `legal-foundation.js`/testes da Fase 2, preservando o dataset v1 e consumindo somente contexto completo.

## Registro por fase — Fase 1 — encerramento

- Código: `legal_context.py` e integração do pipeline preservam texto nativo/OCR cacheado, identidade documental completa, páginas físicas, interessado inequívoco, `operative_text`, concorrência fail-closed e publicação atômica.
- Testes finais: `python -m unittest test_legal_context -q` 18/18; pipeline dirigido 7/7; focal Python 89/89; batch runner 19/19; matcher 33/34 com RED intencional da Fase 0.
- Validação: nenhum portal, clique, preenchimento, envio ou dado real; fixture absoluto removido e re-revisado Approved.
- Limitação: allowlist/ZIP portátil ainda não inclui `legal_context.py`; tratar na Fase 10 sem afirmar pacote release-ready agora.
- Próximo passo: implementar `parseLegalReferences`/`resolveLegalFoundation` e fechar a RED do matcher, sem integrar worker/painel até a Fase 4.

## Registro por fase — Fase 1

- Estado: implementação local concluída no commit `f0a72b5`.
- Arquivos: `work/tce-extractor/portable/app/legal_context.py`,
  `work/tce-extractor/test_legal_context.py`,
  `work/tce-extractor/portable/app/analysis_pipeline.py` e
  `work/tce-extractor/test_analysis_pipeline.py`.
- Contrato: sidecar `fundamentos-contexto.v1.json` com contexto multipágina,
  citações `{document_id,event_id,page,pdf_sha256}`, texto operativo sem
  truncamento, versão de extração e estados `complete`/`missing`/`incomplete`/
  `conflict`.
- Integração: `run_local_pipeline` reutiliza caches locais e vincula o sidecar
  ao `batch.logical_sha256` do dataset v1; não chama OCR adicional nem portal.
- TDD: suíte obrigatória Python 75/75; `test_batch_runner` 19/19; `git diff
  --check` verde. A RED JavaScript do matcher permanece 1 falha intencional.
- Escopo deliberadamente preservado: `empacotar-coletor-portatil.ps1` e
  `test_portable_end_to_end.py` estão byte a byte no HEAD `08cf8b9`. Como
  consequência, o teste do ZIP autocontido falha por não incluir o novo módulo;
  não tratar esse concern sem autorização/fase apropriada.
- Retomada: manter o matcher RED e resolver a dependência do empacotador somente
  em escopo posterior autorizado.

## Registro por fase — Fase 1 fix round 1

- Estado: revisão corrigida no commit
  `e84ac95 fix: harden legal context evidence publication`.
- Ownership: somente `portable/app/analysis_pipeline.py`,
  `portable/app/legal_context.py`, `test_analysis_pipeline.py` e
  `test_legal_context.py` foram alterados no fix. Empacotador e
  `test_portable_end_to_end.py` continuam exatamente no HEAD `08cf8b9`.
- Correções: páginas nativas já classificadas chegam ao sidecar sem OCR;
  interessado precisa aparecer em página citada; marcador operativo usa o
  bloco `resolve` final; `page_count` é preservado/validado; temporários
  são limpos também em falhas de serialização e `fsync`.
- Versões: `legal-context-v2` e `analysis-pipeline-v3`, mantendo o dataset
  v1 de sete campos e o exportador sem alterações.
- TDD: RED registrado no relatório; GREEN com 82/82 testes Python focais e
  19/19 testes de `test_batch_runner`. A suíte JS permanece 33/34 por uma
  única RED intencional do matcher.
- Validação de escopo: `git diff 08cf8b9 --exit-code --` nos dois arquivos
  proibidos passou; `git diff --check` passou.
- Documentação: `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/task-1-report.md`
  contém o fix report completo e lista este handoff global alterado.
- GitHub: nenhum remoto configurado; não houve push.
- Retomada: não corrigir matcher nem incluir empacotamento. Qualquer release
  portátil que dependa de `legal_context.py` requer autorização posterior.

## Registro por fase — Fase 1 fix round 2

- Estado: código e testes no commit
  `8b3a411 fix: preserve physical legal context coverage`; relatório
  atualizado neste mesmo bloco documental.
- Ownership: somente `portable/app/analysis_pipeline.py`,
  `portable/app/legal_context.py`, `test_analysis_pipeline.py` e
  `test_legal_context.py` foram alterados no código. Nenhum empacotamento
  ou matcher foi tocado.
- Cobertura física: a contagem nativa observada é lower bound; cache OCR menor
  não reduz `page_count`, páginas faltantes são evidenciadas e o status
  não pode ser `complete`.
- Identidade: nomes usam sequência de tokens normalizados com fronteira;
  ANA/MARIANA não colidem, homônimos ficam `conflict` sem identificador e
  matrícula pode desambiguar a fonte.
- Versões: `EXTRACTOR_VERSION` permanece `analysis-pipeline-v2`;
  `LEGAL_CONTEXT_VERSION` é independente em `legal-context-v3`.
  Cache OCR antigo foi validado sem nova chamada de OCR.
- TDD/gates: RED registrado no task-1-report; GREEN em 87/87 focais Python e
  19/19 batch runner; `git diff --check` passou. Matcher permanece 33/34
  por RED intencional.
- Escopo: os arquivos `empacotar-coletor-portatil.ps1` e
  `test_portable_end_to_end.py` continuam idênticos ao HEAD `08cf8b9`.
- Retomada: nenhum novo trabalho nesta fase sem revisão; manter a RED do matcher
  e a dependência do empacotador como concern separado.

## Registro por fase — Fase 1 fix round 3

- Estado: código e testes no commit
  e85aa35 fix: close legal context evidence and cache gaps; o report foi
  atualizado no mesmo bloco documental.
- Ownership: somente portable/app/analysis_pipeline.py,
  portable/app/legal_context.py, test_analysis_pipeline.py e
  test_legal_context.py foram alterados no código. Empacotamento e matcher
  permaneceram intocados.
- Fontes concorrentes: source_evidence preserva todas as resoluções do
  processo, incluindo fontes sem page_texts; status_reasons registra
  source_evidence_missing, e a ausência impede complete.
- Matrícula: identificadores numéricos exigem rótulo de identificação e
  segmento contíguo; Ano: 12 + Página: 34 não vira 1234.
- Versões: EXTRACTOR_VERSION permanece analysis-pipeline-v3, compatível com o
  cache OCR v3 anterior; LEGAL_CONTEXT_VERSION é independente em
  legal-context-v4. Mudança de contexto não dispara OCR nem rejeita cache.
- TDD/gates: RED de 18 testes com 3 falhas esperadas antes do código; GREEN
  em 89/89 testes Python focais e 19/19 batch runner; git diff --check e
  comparação dos arquivos proibidos ao HEAD 08cf8b9 passaram.
- Concerns: a RED intencional do matcher continua 33/34; o teste de pacote
  continua fora do escopo porque o empacotador preservado não inclui
  legal_context.py. Nenhum BLOCKED no round 3.
- Retomada: não corrigir matcher nem incluir empacotamento; qualquer mudança
  futura de cache deve preservar a compatibilidade v3 ou registrar migração
  explícita e autorizada.

## Registro por fase — Fase 1 fix round 4

- Estado: código e testes no commit
  d305ee6 fix: require unambiguous evidence identity; report atualizado
  neste bloco documental.
- Ownership: somente portable/app/analysis_pipeline.py,
  portable/app/legal_context.py, test_analysis_pipeline.py e
  test_legal_context.py foram alterados no código. Empacotamento e matcher
  continuam intocados.
- Identidade documental: alias só é aceito quando document_id, event_id e
  pdf_sha256 do payload/manifesto formam identidade inequívoca. event_id
  sozinho não reutiliza página entre fontes; alias ambíguo fica
  incomplete/conflict, com source_evidence e status_reasons observáveis.
- Geometria: geometry_capable=True reutiliza cache textual v3 válido sem OCR
  adicional quando não há geometry cache. Texto/citações do sidecar são
  preservados, geometry_status=unavailable é explicitado, e operações visuais
  continuam sob seu gate geométrico existente.
- TDD/gates: RED de 2 testes com 2 falhas esperadas antes do código; GREEN em
  91/91 testes Python focais e 19/19 batch runner; git diff --check e
  comparação dos arquivos proibidos ao HEAD 08cf8b9 passaram.
- Concerns: RED intencional do matcher continua 33/34; teste do pacote
  continua fora do escopo porque o empacotador preservado não inclui
  legal_context.py. BLOCKED nenhum.
- Retomada: não corrigir matcher nem incluir empacotamento; manter a separação
  entre consumo de texto cacheado e exigência de geometry nas próximas fases.

## Registro por fase — Fase 1 fix round 5

- Estado: fixture sanitizado no commit
  0876f2d test: sanitize legal context fixture path; report atualizado neste
  bloco.
- Alteração: test_legal_context.py gera dinamicamente um caminho sintético
  temporário para continuar cobrindo a sanitização de basename, sem caminho
  absoluto literal versionado.
- TDD/gates: RED curto detectou uma ocorrência do literal proibido; GREEN em
  18/18 test_legal_context; git diff --check passou e o guard não encontrou
  ocorrências após a edição.
- Ownership: nenhum empacotamento, matcher ou lógica funcional foi alterado.
- BLOCKED: nenhum. Retomada: manter fixtures versionados sem caminhos
  absolutos reais ou literais de máquina.

## Registro por fase — Fase 2 — resolvedor específico de fundamento

- Estado: implementação local concluída no commit com a mensagem
  `fix: resolve legal foundations from documentary references`.
- Ownership: criados `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js`
  e seu teste; alterados somente `lib/matcher.js`, `lib/normalizer.js` e os
  respectivos testes, além deste handoff e do relatório da Fase 2.
- Contrato: `parseLegalReferences(text)` separa EC/ECE/CF, preserva ano,
  artigo com sufixo, parágrafos/incisos, `ambos`, `c/c`, referências invertidas
  e retorna sinais por referência. `resolveLegalFoundation` consome
  `LegalContext` completo e retorna `LegalDecision` com `status`, `method`,
  `rule_id`, opção, score, razões, ranking completo, referências, citações e
  versão das regras.
- Regras: EC41 aceita art. 6º ou 7º ligado à EC41/2003; §5 só é ativado por
  CF art. 40 §5 no trecho operativo; EC47 art. 3º exige seus sinais; art. 6º-A,
  ECE, ano ausente, ano divergente, conflito, empate e score zero não fazem
  seleção silenciosa. Placeholder e opções sem valor não entram no ranking.
- TDD: RED/GREEN detalhado em
  `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/task-2-report.md`.
  Focal final: 52/52; full final: 144/144. `git diff --check` passou no
  estado de código atual.
- Compatibilidade: chamadas legadas do matcher continuam sem contexto e a
  modalidade não usa o resolvedor; com contexto explícito, o matcher carrega
  `legalDecision` sem alterar os campos v1. Worker, painel, API, persistência,
  navegação, envio, redesign e dataset v1 continuam fora desta fase.
- Validação manual: cenários sintéticos apenas; nenhuma sessão, clique,
  preenchimento ou envio real foi iniciado.
- Concern: o empacotador ainda não inclui `legal_context.py` da Fase 1; isso
  permanece pendência posterior e não foi expandido nesta implementação.
- GitHub: branch `codex/fundamentacao-automatico`; checkout sem remoto, sem
  push. Retomada: verificar o commit e só depois permitir integração
  sequencial nas fases futuras.

## Atualização final — contrato público da Fase 2

- Estado: correção local pronta para commit; os dois achados da revisão
  independente foram corrigidos sem tocar worker, painel, API, persistência,
  navegação ou envio real.
- Arquivos alterados nesta rodada: `lib/legal-foundation.js`,
  `lib/matcher.js`, `tests/legal-foundation.test.mjs`,
  `tests/matcher.test.mjs` e o relatório da Fase 2.
- Contrato: `LegalDecision.status` público é `selected|pending`; `method` é
  `exact|rule|similarity|none`. Equivalência estrutural de família conhecida
  usa `rule`, preservando `kind: "probable"` no matcher legado; sem família
  usa `exact`.
- Correção funcional: `hasIncisos` foi restaurada para resolver CF art. 40
  § 1º, inciso II sem alterar as regras fail-closed anteriores.
- TDD: RED inicial 58/59; RED após asserts de contrato 49/60; GREEN focal
  60/60; full 152/152; `git diff --check` sem diagnóstico.
- Validação manual: somente cenários e testes sintéticos; nenhuma sessão,
  clique, preenchimento ou envio real foi iniciado.
- GitHub: branch `codex/fundamentacao-automatico`, checkout sem remoto e sem
  push. Próximo passo: conferir diff/status, criar o commit solicitado
  `fix: restore phase 2 public contract` e validar o SHA.

## Rodada de correção — associação explícita em três referências

- Estado: correção implementada no checkout compartilhado, aguardando o commit
  desta rodada.
- RED reproduzido antes do código: em `RESOLVE: art. 6º da EC nº 41/2003;
  art. 7º da ECE nº 41/2020; art. 2º da EC nº 47/2005`, o parser atribuía
  `EC 41/2003` ao art. 7º e o resolvedor não detectava o conflito.
- Correção: `legal-foundation.js` passa a associar o diploma pós-artigo quando
  a ligação explícita termina em `da`, `do` ou `de`, sem alterar worker,
  painel, API, persistência, navegação ou envio real.
- Teste novo: `tests/legal-foundation.test.mjs` verifica os três diplomas
  explícitos e `status: "pending"` com `family-conflict`.
- Validação: focal 61/61; `npm test` 153/153; `git diff --check` verde.
- Arquivos desta rodada: `lib/legal-foundation.js`,
  `tests/legal-foundation.test.mjs`, `task-2-report.md` e este handoff.
- Próximo passo: criar o commit
  `fix: bind each legal reference to its diploma`, conferir SHA e status.

## Rodada de correção — combinado EC41/CF, CE e compatibilidade legada

- Estado: quatro achados da revisão independente corrigidos no checkout
  compartilhado via TDD; mudanças alheias não foram revertidas.
- RED: focal com 64 testes, 59 passados e 5 falhos antes da implementação.
- Correções: `legal-foundation.js` aceita CF §5 combinado com um único art. 6º
  ou 7º da EC41; `normalizer.js` reconhece `CE`; `matcher.js` preserva o
  retorno legado sem `context` e reserva `pending/null` ao caminho contextual de
  fundamento; `messages.js` converte pending para `tie` antes da validação v1.
- Contrato preservado: `LegalDecision.status` permanece `selected|pending` e
  `method` permanece `exact|rule|similarity|none`; valores de mensagem v1
  desconhecidos continuam rejeitados.
- GREEN focal: 64/64; `npm test`: 157/157; `git diff --check`: sem diagnóstico.
- Testes alterados: `tests/legal-foundation.test.mjs`,
  `tests/matcher.test.mjs` e `tests/schema.test.mjs`.
- Escopo: somente resolvedor, normalizador, matcher, mensagens e testes/
  documentação foram alterados; nenhum worker, painel, API, persistência,
  navegação, ambiente ou envio real foi alterado ou executado.
- GitHub: checkout sem remoto configurado; commit local pendente, sem push.
- Fechamento: commit funcional `7ceb326c43adf9bb347712b6e3b20ed6125d4ab8`.
- Revisão independente final: aprovada sem achados funcionais; a correção
  posterior foi apenas documental, ajustando o focal para 64/64.
- GitHub: checkout sem remoto configurado; nenhum push foi realizado.
- Próxima tarefa: executar a Fase 3 conforme `task-3-brief.md`.

## Registro por fase — Fase 3 — encerramento

- Estado: diário SQLite e relatórios duráveis implementados nos commits
  `d3035da`, `f0e1dc8`, `924cfef`, `b13f868` e `4046fbd`.
- Ownership: `automation_store.py`, `automation_report.py` e seus testes;
  nenhum serviço, API, worker, painel, empacotador ou envio real foi alterado.
- Contratos: pragmas SQLite obrigatórios, `BEGIN IMMEDIATE`, projeção atômica,
  idempotência/conflito, revisão obrigatória, recovery fail-closed, replay
  legado explicitamente indisponível, allowlist/redaction, citações por IDs,
  publicação versionada e manifesto SHA-256.
- Validação final: `python -m unittest test_automation_store
  test_automation_report -q` — 31/31; focais Python — 69/69, 3 skips
  ambientais; `py_compile` e `git diff --check` verdes; revisão independente
  final **Approved**.
- Pendências: integração com a API/serviço e fases posteriores; eventos
  legados sem `result_json` exigem backfill antes de replay.
- Próxima tarefa: executar a Fase 4 conforme `task-4-brief.md`.
