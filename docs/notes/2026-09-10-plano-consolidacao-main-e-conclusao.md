# Consolidação na main e conclusão do fluxo automático — Plano de Implementação

> **Para agentes executores:** SUB-SKILL OBRIGATÓRIA: usar
> `superpowers:subagent-driven-development` (recomendado) ou
> `superpowers:executing-plans` e executar tarefa por tarefa. As caixas são o
> registro oficial; nenhuma fase posterior pode antecipar gates humanos.

**Objetivo:** organizar e sanear o workspace, consolidar todo o trabalho válido
em uma única branch `main` e concluir a qualificação/release do fluxo automático
de Complementação de Atos.

**Arquitetura:** a execução começa por inventário, recuperação e consolidação
Git sem perda. A limpeza usa análise somente leitura, manifesto e quarentena.
Depois estabiliza os gates, qualifica dados/portal em camadas e só amplia a
automação quando cada gate anterior produzir evidência real.

**Stack:** Git, Windows PowerShell 5.1/PowerShell, Python 3.14 `unittest`, Node
`node:test`, extensão Chrome Manifest V3, serviço HTTP loopback e scripts do
pacote portátil.

**Especificação:** `docs/notes/2026-09-10-consolidacao-main-e-conclusao-spec.md`

## Restrições globais

- Não apagar, mover ou sobrescrever antes de inventário, hash e manifesto.
- Não usar `git add .`, `git reset --hard`, `git clean` ou exclusão recursiva
  ampla.
- Não fechar/reiniciar Chrome pessoal nem tocar em perfil autenticado ativo.
- Não versionar `outputs`, `tmp`, PDFs, ZIPs, tokens, cookies ou dados privados.
- Não habilitar envio por teste sintético; `real_send_enabled=false` até a
  qualificação portal-real.
- Não preencher parcialmente quando um dos seis campos obrigatórios faltar.
- Toda mutação remota ou envio exige checkpoint humano explícito.
- Após cada tarefa: atualizar o handoff, executar gates focais, revisar status,
  fazer stage nominal e commit coerente quando aplicável.

---

## Fase 0 — organização local, main única e limpeza segura

### Tarefa 0.1 — congelar a fotografia inicial e criar recuperação

**Arquivos:**
- Criar: `docs/notes/2026-09-10-fase0-inventario-inicial.md`
- Criar local/ignorado: `tmp/fase0-recovery/`

**Produz:** inventário imutável, patch binário do diff rastreado, lista dos
arquivos não rastreados e hashes dos artefatos essenciais.

- [x] Registrar `git status --porcelain=v2 --branch`, `git branch -vv`,
  `git worktree list --porcelain`, `git log --graph --all -30`, `git remote -v`
  e `git fsck --no-dangling` no inventário, resumindo saídas extensas.
- [x] Confirmar `HEAD=16bf74e` ou registrar drift antes de prosseguir.
- [x] Gerar `tmp/fase0-recovery/tracked.patch` com `git diff --binary HEAD` e
  validar que o arquivo é não vazio.
- [x] Copiar os dez arquivos não rastreados para
  `tmp/fase0-recovery/untracked/`, preservando caminhos relativos e hashes.
- [x] Registrar SHA-256 do ZIP `fase11k`, do acervo autorizado de 05/09 e de
  qualquer ZIP candidato a retenção; nunca abrir conteúdo privado no relatório.
- [x] Executar `git diff --check`; aceitar apenas o aviso conhecido de EOL do
  `INICIAR.cmd`, sem erros de whitespace.
- [x] STOP se qualquer cópia/hash falhar ou se o backup não puder ser lido de
  volta; não iniciar organização sem recuperação verificável.

### Tarefa 0.2 — criar o analisador somente leitura

**Arquivos:**
- Criar: `work/tce-extractor/analyze-local-workspace.ps1`
- Criar: `work/tce-extractor/tests/Test-WorkspaceCleanup.ps1`

**Interface:** `analyze-local-workspace.ps1 -Root <absoluto> -ManifestPath
<json>` produz schema fechado com `path`, `resolved_path`, `kind`, `bytes`,
`sha256`, `git_state`, `referenced_by`, `classification`, `reason` e
`recommended_action`; nunca altera arquivos.

- [x] Escrever testes RED que montem fixture temporária com fonte rastreável,
  ZIP duplicado, staging, cache, perfil, arquivo desconhecido e symlink/junction.
- [x] Exigir que o analisador recuse raiz vazia, raiz fora do projeto e qualquer
  caminho resolvido fora da raiz.
- [x] Exigir que perfis, `.git`, `.codex*`, dados privados e desconhecidos nunca
  recebam recomendação `delete` automática.
- [x] Executar `tests/Test-WorkspaceCleanup.ps1`; confirmar falha porque o
  analisador ainda não existe.
- [x] Implementar enumeração sem seguir reparse points e hash streaming para
  arquivos, sem ler conteúdo de PDFs/ZIPs/perfis.
- [x] Implementar busca de referências por caminhos/literais usando `rg`,
  registrando apenas arquivo/linha, nunca conteúdo sensível.
- [x] Rodar os testes e exigir todos verdes.
- [x] Executar contra a raiz real e gravar somente o manifesto em `tmp/fase0`.

### Tarefa 0.3 — classificar todo o workspace

**Escopo mínimo:** `.codex-remote-attachments`, `.superpowers`, `.worktrees`,
`artifacts`, `outputs`, `portable`, `tmp`, `TCE-Acervo... - v2`, ZIP raiz,
`work/tce-extractor/outputs` e arquivos de raiz.

- [x] Classificar item a item nas nove classes da especificação.
- [x] Marcar como preservação obrigatória: `.git`, fontes, docs versionadas,
  pacote `fase11k`, evidência live do lote 1, acervo autorizado de 05/09 e
  anexos originais ainda referenciados.
- [x] Comparar por SHA-256 o ZIP de 1,737 GB da raiz e o de `outputs`; apenas
  se forem idênticos escolher uma cópia canônica.
- [x] Identificar referências antes de classificar `portable/`, `artifacts/`,
  montagens `staging*`, `.package-staging-*` e diretórios extraídos.
- [x] Tratar `.worktrees` como removível somente se `git worktree list` não
  apontar para seus diretórios e `git worktree prune --dry-run` confirmar.
- [x] Tratar `.chrome-work*`, perfis e locks como preservados até provar ausência
  de processo e de sessão necessária.
- [x] Produzir tabela `reter`, `quarentenar`, `investigar`, `duplicata` e
  `proibido remover`, com tamanho recuperável estimado.
- [x] Obter aprovação humana do manifesto antes da Tarefa 0.8. (aprovada em 2026-09-10)

### Tarefa 0.4 — reconciliar documentação e arquivos ignorados

**Arquivos:**
- Modificar: `.gitignore`
- Modificar: `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`
- Modificar: `README.md`
- Migrar conteúdo de: `docs/superpowers/plans/2026-09-10-fluxo-hibrido-lotes.md`

- [x] Escrever teste/checagem RED que falhe enquanto o plano híbrido existir e
  `git check-ignore` o classificar como ignorado.
- [x] Escolher uma única cópia canônica em `docs/notes/`; não manter dois planos
  divergentes.
- [x] Atualizar o plano mestre: marcar download real, fechamento do lote e ZIP
  reconstruído como concluídos; remover duplicação de pendências sem apagar o
  histórico cronológico.
- [x] Atualizar README para distinguir acervo privado de 227 processos, runtime
  `fase11k` e estado não qualificado do envio automático.
- [x] Ajustar `.gitignore` apenas se um diretório de docs adicional continuar
  necessário; preservar default-deny para dados/ZIPs/perfis.
- [x] Rodar `git check-ignore -v` nos documentos novos e exigir que os canônicos
  não estejam ignorados.

### Tarefa 0.5 — revisar e dividir o bloco local em commits

**Escopo:** 32 arquivos modificados e módulos novos de fila, aquisição,
prévia, escopo e reconciliação.

- [x] Revisar cada hunk contra a especificação híbrida e o handoff; rejeitar
  mudança sem teste, documentação ou vínculo com requisito aprovado.
- [x] Confirmar que novos módulos constam na allowlist do empacotador e no teste
  de inventário do ZIP.
- [x] Confirmar ausência de token, cookie, URL autenticada, CPF bruto e caminho
  privado com buscas estruturais e revisão manual dos resultados.
- [x] Executar os gates focais: `npm test`, Python portátil 34+, menu 83+ e
  `git diff --check`.
- [x] Fazer stage nominal do primeiro conjunto: contratos Python, respectivos
  testes e documentação de origem/lotes; revisar `git diff --cached` e commit
  `feat: add deterministic hybrid batch analysis`.
- [x] Fazer stage nominal do segundo conjunto: integração de aquisição,
  launcher, bridge/painel e testes; commit
  `feat: integrate frozen batch acquisition`.
- [x] Fazer stage nominal do terceiro conjunto: correções portal-reais,
  preflight de gênero opcional, guias e handoffs; commit
  `fix: qualify real batch preparation boundaries`.
- [x] STOP se algum gate falhar; não consolidar `main` com worktree parcial.

### Tarefa 0.6 — reconciliar a branch de transferência

- [x] Comparar `git diff 6c88d2a ef7d44b --` e confirmar diff vazio.
- [x] Confirmar que `main` futura conterá `6c88d2a` ou árvore equivalente.
- [x] Registrar no handoff que `codex/transfer-quiescence` é duplicata de
  patch, não trabalho exclusivo.
- [x] Não fazer merge dessa branch; reservar sua exclusão para a Tarefa 0.10.

### Tarefa 0.7 — avançar main por fast-forward

- [x] Exigir worktree limpo em `codex/fundamentacao-automatico`.
- [x] Executar `git merge-base --is-ancestor main
  codex/fundamentacao-automatico`; esperado exit 0.
- [x] Trocar para `main` e executar `git merge --ff-only
  codex/fundamentacao-automatico`.
- [x] Confirmar que `git rev-parse main` é igual ao commit consolidado.
- [x] Repetir extensão, Python portátil, menu e `git diff --check` em `main`.
- [x] STOP se fast-forward não for possível; não usar merge commit nem rebase
  improvisado. Registrar a divergência para nova decisão.

### Tarefa 0.8 — criar limpador por manifesto e simular

**Arquivos:**
- Criar: `work/tce-extractor/clean-local-workspace.ps1`
- Modificar: `work/tce-extractor/tests/Test-WorkspaceCleanup.ps1`

**Interface:** `clean-local-workspace.ps1 -Root <absoluto> -ManifestPath <json>
[-Apply] [-PurgeQuarantine]`; sem `-Apply`, somente WhatIf.

- [x] Criar testes RED para hash divergente, alvo ausente, path traversal,
  reparse point, item não aprovado, perfil ativo e destino fora da raiz.
- [x] Implementar validação de raiz/path/hash e mover somente itens aprovados
  para `tmp/quarantine/YYYYMMDD-HHMMSS/<caminho-relativo>`.
- [x] Criar recibo JSON com origem, destino, hash, timestamp e resultado.
- [x] Implementar purge separado que aceita somente uma quarentena explícita,
  após validar recibo e raiz; nunca aceitar `tmp`, raiz ou glob amplo.
- [x] Rodar testes e depois WhatIf no manifesto real; comparar contagens e bytes
  com o analisador.
- [x] Exigir aprovação humana do WhatIf antes de `-Apply`. (aprovada em 2026-09-10)

### Tarefa 0.9 — quarentenar e validar a pasta organizada

- [x] Aplicar somente itens `quarentenar` aprovados; desconhecidos permanecem.
  (executada em 2026-09-10 22:13–22:36: `-Apply` exit 0 contra o manifesto r2
  `A7994FF698DFABC690A0A50654D0C3A68996677DE4E336FF0AF6075DA11E492F`;
  recibo `tmp/quarantine/20260911-012750-653/receipt.json` com `moved=16074`,
  `not_moved=0` e `moved_bytes=23126367618`; nenhum purge executado.)
- [x] Reexecutar analisador e confirmar que fontes, docs, entregas, lote live e
  recuperação continuam presentes com hashes iguais.
  (executada em 2026-09-10: reanálise r3 exit 0 com `entries=31721`;
  `preserved_missing=0`, `approved_still_present=0`, `not_moved=0`. Os 58
  hashes alterados foram auditados um a um: 38 caches `.pyc` regenerados por
  execuções de teste, 19 arquivos rastreados e limpos frente ao Git (edições do
  próprio dia já commitadas) e 1 log ignorado do analisador; mtime máxima
  `21:27:00`, anterior ao início do `-Apply` às `22:13:39`, então nenhuma
  alteração é efeito da quarentena.)
- [x] Rodar pacote `fase11k` em extração limpa e os seis gates públicos.
- [x] Rodar os testes focais novamente.
  (executada em 2026-09-10: `Test-WorkspaceCleanup.ps1` 307/307, 0 falhas,
  exit 0 em duas execuções pós-quarentena.)
- [x] Preservar a quarentena durante todas as fases de qualificação; não fazer
  purge definitivo nesta tarefa.
  (executada em 2026-09-10: quarentena preservada em
  `tmp/quarantine/20260911-012750-653`; `-PurgeQuarantine` nunca executado.)

### Tarefa 0.10 — deixar somente main

- [x] Confirmar worktree limpo, `HEAD == main` e testes verdes.
  (executado em 2026-09-10: `HEAD` e `main` no mesmo commit; o checkout estava
  limpo exceto pelos arquivos então em edição pelos agentes das tarefas 0.8 e
  1.2, commitados em seguida; gates verdes antes das exclusões.)
- [x] Excluir `codex/transfer-quiescence` com `git branch -d`; usar `-D` somente
  se a equivalência de árvore estiver registrada e houver aprovação específica.
  (equivalência registrada e aprovada especificamente pelo usuário; executado
  `git branch -D codex/transfer-quiescence` → `Deleted branch
  codex/transfer-quiescence (was ef7d44b)`, exit 0. O commit `ef7d44b` tem tree
  idêntica à de `6c88d2a` da `main` e `git diff 6c88d2a ef7d44b` é vazio.)
- [x] Excluir `codex/fundamentacao-automatico` com `git branch -d` após confirmar
  que `main` contém seu tip.
  (executado: `Deleted branch codex/fundamentacao-automatico (was d8e9b7d)`,
  exit 0.)
- [x] Executar `git branch --format='%(refname:short)'`; esperado: uma linha,
  `main`.
  (medido: saída exata `main`.)
- [x] Executar `git worktree prune --dry-run`, revisar, e só então podar metadado
  comprovadamente órfão.
  (medido: saída vazia; nenhum metadado órfão existia, nada foi podado.)
- [x] Atualizar handoff da fase zero com árvore final, hashes e lista retida.
  (handoff `docs/notes/2026-09-10-consolidacao-main-e-conclusao-handoff.md`
  atualizado com árvore de branch única, hashes e estado do remoto.)

---

## Fase 1 — baseline canônico e saúde da suíte

### Tarefa 1.1 — localizar a lentidão da suíte Python ampla

**Arquivos:**
- Criar: `docs/notes/2026-09-10-python-suite-baseline.md`
- Modificar testes/harness somente após reproduzir causa específica.

- [x] Executar descoberta ampla com verbosidade e log local ignorado para obter
  o último teste iniciado antes da paralisação.
- [x] Reexecutar apenas esse módulo/teste com timeout externo de 60 segundos.
- [x] Classificar causa: espera de navegador, processo filho, servidor, lock,
  rede, fixture grande ou cleanup ausente.
- [x] Escrever teste RED/asserção de cleanup ou timeout proporcional à causa.
- [x] Implementar correção mínima sem pular o teste nem reduzir cobertura.
- [x] Rodar teste focal três vezes e a suíte ampla duas vezes; registrar total,
  aprovados, skips, duração e warnings.
  (focal 3/3 verde: 17,115 s / 5,454 s / 5,205 s; ampla 2/2 verde: 409
  executados, 401 aprovados, 8 skips, 144,316 s e 147,969 s; registro em
  `docs/notes/2026-09-10-python-suite-baseline.md`.)
- [x] Commit `test: stabilize complete Python verification`. A correção real
  (`window.frames` array-like no content script) já estava publicada na
  `main` em `7137dc3` (`fix(portal): iterate array-like window.frames and
  route local Voltar to the generic wait path`), então o commit deste gate
  registra as medições de fechamento em
  `docs/notes/2026-09-10-python-suite-baseline.md`; verificado em 2026-09-10
  com o teste focal (3/3) e a suíte ampla (2/2) reexecutados.

### Tarefa 1.2 — estabelecer o comando único de verificação

**Arquivos:**
- Criar: `work/tce-extractor/verify-project.ps1`
- Criar/Modificar: `work/tce-extractor/tests/Test-ProjectVerification.ps1`
- Modificar: `README.md`

- [x] Testar que o verificador executa extensão, web, Python ampla, PowerShell,
  empacotamento/auditoria e `git diff --check`, preservando códigos distintos.
  (43/43 em `Test-ProjectVerification.ps1`, no Windows PowerShell 5.1 e no
  PowerShell 7, cobrindo códigos distintos por etapa, timeout, encerramento de
  PID e recusa de `Authenticated`, `Collect` e `Send`.)
- [x] Exigir resumo final com comando, executados, aprovados, falhos e skips.
  (duas execuções completas: `Executed: 959`, `Passed: 957`, `Failed: 0`,
  `Skips: 2`, exit 0, 108,97 s e 108,12 s; repetição pós-push em 112,07 s com
  o mesmo resultado.)
- [x] Não iniciar Chrome autenticado, coleta ou envio nesse comando.
  (verificado: o gate não abre Chrome autenticado, não coleta/baixa, não roda
  OCR e não envia ou finaliza atos.)
- [x] Rodar em checkout limpo; expected exit 0.
  (executado com a árvore limpa antes do commit; exit 0 nas duas rodadas.)
- [x] Commit `test: add reproducible project verification gate`.
  (`0cc3680`; handoff de fechamento em `f8b5444`; `HEAD == origin/main ==
  `f8b5444207eceadd26a48372743ccfec81f62a26`.)

---

## Fase 2 — reconciliação dos dados do lote 1

### Tarefa 2.1 — fechar a contagem 50 processos/51 interessados

**Arquivos:**
- Modificar: `docs/notes/2026-09-10-lote1-campos-incompletos.md`
- Criar script/teste sanitizado somente se necessário para reproduzir contagens.

- [x] Recalcular por chave de processo e por identidade de interessado a partir
  da revisão 120, sem publicar nomes/CPF além do já autorizado.
  (medido: 50 processos, 51 registros/identidades; 41 prontos; 10 bloqueados em
  9 processos; em `work/tce-extractor/reconcile_lote1.py` +
  `test_reconcile_lote1.py`, teste 1/1 verde.)
- [x] Explicar a diferença entre os 40 “somente gênero”, os 9 sem nascimento e
  o total de 50 processos; listar a categoria do processo restante ou corrigir
  a contagem incorreta.
  (corrigido de 40 para 41 “somente gênero”; o processo restante é
  `104611/2025`; matriz `data_nascimento=9`,
  `modalidade+fundamento_legal=1`.)
- [x] Confirmar que `104956/2025` possui dois interessados e registrar qual
  combinação de campos falta em cada identidade sem confundi-los.
  (confirmado: registro #1 sem nascimento; registro #2 sem
  modalidade/fundamento legal.)
- [x] Produzir matriz agregada `ready_for_preflight` versus `blocked_fields`.
- [x] Commit `docs: reconcile first real batch field readiness` (publicado na
  `main` em `21054a4`).

### Tarefa 2.2 — resolver evidência dos campos obrigatórios ausentes

- [x] Para cada um dos nove registros sem nascimento, revisar documentos já
  baixados e evidências por página; não inferir data por idade ou identificador.
- [x] Para o segundo interessado de `104956/2025`, revisar modalidade e
  fundamento vinculados à identidade correta.
- [x] Se o dado existir, corrigir a extração em TDD com fixture sanitizada e
  evidência exata; se não existir, manter bloqueado com motivo explícito.
- [x] Reexecutar análise apenas dos itens afetados e provar que itens íntegros
  não foram baixados/processados novamente.
- [x] Atualizar relatório com contagem final de elegíveis e bloqueados.

---

## Fase 3 — prova real do fallback OCR

### Tarefa 3.1 — selecionar documento apto sem alterar o portal

- [ ] Identificar no escopo autorizado um PDF originalmente sem texto nativo;
  registrar processo/documento apenas na evidência privada.
- [ ] Confirmar hash do original e `native_text_length=0` antes do OCR.
- [ ] Executar o pipeline normal, não um comando Tesseract isolado.
- [ ] Confirmar cache por hash/versão, caixas TSV, confiança e evidência de
  página; não alterar o PDF original.
- [ ] Reexecutar e provar cache hit sem segundo OCR.
- [x] Se nenhum documento apto existir, registrar gate `not-observed`, não PASS.
  (executada em 2026-09-10: 28.398 PDFs / 98.515 páginas varridos no escopo
  `work` sem runtime/vendor/site-packages, `native_zero=0`; 10 caches
  `cache-ocr*.json` vazios; nenhum código de produção alterado; evidência no
  handoff e em `task-3.1-report.md`.)

---

## Fase 4 — recuperação do Chrome e três preflights reais

### Tarefa 4.1 — recuperar uma superfície controlável

- [x] Detectar Chrome/Edge/CDP existente somente por leitura.
  (comprovado em 2026-09-11 pela evidência sanitizada
  `tmp/fase41/mirror-bridge-evidence.json`: CDP `127.0.0.1:19231`,
  `Chrome/151.0.7922.34`; nenhuma alteração de navegador foi necessária.)
- [x] Preferir perfil de trabalho isolado; nunca fechar ou reutilizar perfil
  pessoal sem autorização.
- [x] Parar para login humano; não digitar credenciais.
- [x] Confirmar Área Restrita e e-Contas autenticados, extensão `fase11k` ou
  posterior carregada e ponte pareada.
- [x] Capturar somente DOM sanitizado necessário, sem sessão/CPF/token.

> **Atualização rastreada — 2026-09-11 (status: concluída).** A evidência
> `tmp/fase41/mirror-bridge-evidence.json`, combinada com
> `tmp/fase41/inspect-live-final.json` e o registro sanitizado da autenticação,
> comprova CDP `127.0.0.1:19231` em perfil de trabalho isolado,
> `Chrome/151.0.7922.34`, Área Restrita e e-Contas sem sinal de login e com
> controles estruturais autenticados. A extensão `1.1.0` está carregada e
> pareada; a ponte respondeu health, dataset, state e capabilities em HTTP 200.
> O dataset é a revisão `120`, com `51` registros e prefixo lógico SHA-256
> `23cce5807c01`. O login foi feito pelo usuário após o agente parar no
> checkpoint; nenhuma credencial foi digitada pelo agente.
>
> O mirror é temporário e somente de evidência/ponte; o pacote live original
> não foi alterado. `real_send_enabled=false` e `pilot_enabled=false` permanecem
> registrados tanto em `/capabilities` quanto na saúde da ponte. A captura
> guardou somente flags, contagens, origens e prefixos; não contém sessão,
> cookie, token, CPF ou DOM bruto. Nenhum item de 4.2 ou de Fase 5+ é
> antecipado por esta atualização.

### Tarefa 4.2 — executar preflight de três atos sem envio

- [ ] Selecionar três atos representativos e elegíveis, cobrindo pelo menos duas
  famílias de fundamento e um caso de gênero ausente.
- [ ] Para cada ato, confirmar processo, interessado, marcador, dataset/hash,
  seis campos obrigatórios e catálogo atual do portal.
- [ ] Gerar proposta, comparar manualmente com resolução/evidências e executar
  apenas APPLY_FIELDS quando todos os checks estiverem verdes.
- [ ] Reler os campos e confirmar igualdade; restaurar valores se o protocolo de
  QA não mantiver a preparação.
- [ ] Não clicar botão final; registrar resultado dos três preflights.
- [ ] STOP em divergência de identidade, opção, frame, campo ou evidência.

---

## Fase 5 — primeiro envio supervisionado e observação

### Tarefa 5.1 — preparar o candidato único

- [ ] Escolher um dos três preflights aprovados e produzir relatório prévio.
- [ ] Confirmar serviço/extensão/regras/hash e ausência de comando consumido.
- [ ] Exibir ao usuário identidade, campos, evidências, ação externa e efeito.
- [ ] Solicitar autorização imediata; autorização antiga ou genérica não vale.

### Tarefa 5.2 — emitir um comando e observar

- [ ] Após autorização, emitir exatamente um `send_intent`/command id.
- [ ] Consumir antes do clique e clicar apenas o botão do frame qualificado.
- [ ] Observar mensagem/DOM/rede permitida até o timeout definido.
- [ ] Em timeout/ambiguidade: gravar `unconfirmed`, pausar e nunca reenviar.
- [ ] Em aceitação/erro explícito: registrar prova sanitizada.
- [ ] Reabrir o mesmo ato e reler os seis campos para confirmar persistência.
- [ ] Restaurar/não alterar qualquer campo fora da allowlist.

### Tarefa 5.3 — transformar observação em contrato

**Arquivos:**
- Modificar: fixture sanitizada em `work/tce-extractor/tests/fixtures/automatic-portal/`
- Modificar: testes de `portal-submit.js`/classificação de resultado.

- [ ] Criar fixture mínima sem dados pessoais/sessão.
- [ ] Escrever RED para o resultado observado e para variantes ambíguas.
- [ ] Implementar classificação mínima, sem interceptar genericamente diálogos.
- [ ] Rodar testes focais, extensão completa e revisão de sanitização.
- [ ] Commit `test: qualify observed portal submission outcome`.

---

## Fase 6 — qualificação versionada e piloto de cinco atos

### Tarefa 6.1 — gerar qualificação vinculada aos bytes

- [ ] Gerar `automacao/qualificacao.json` local com versões de extensão,
  serviço, regras, hashes das fixtures e ID do evento confirmado.
- [ ] Validar que alteração de envio/classificação invalida a qualificação.
- [ ] Validar que copiar o arquivo para outra máquina não concede autorização.
- [ ] Confirmar capabilities esperadas; somente então permitir piloto.

### Tarefa 6.2 — executar lote supervisionado de até cinco

- [ ] Selecionar até cinco itens elegíveis, sem usar bloqueados para completar
  artificialmente o lote.
- [ ] Para cada item: identidade → preflight → releitura → comando único →
  resultado → reabertura → relatório.
- [ ] Pausar o lote na primeira divergência, autenticação expirada, resultado
  incerto ou falha de persistência.
- [ ] Conferir ausência de duplicidade de command/event IDs após reinício.
- [ ] Revisar relatório de dados, decisões, fontes, timestamps e redaction.

---

## Fase 7 — rollout progressivo do marcador

### Tarefa 7.1 — definir política de ondas

- [ ] Fixar snapshot/marker/hash e separar elegíveis de bloqueados.
- [ ] Executar ondas 1, 5, 10 e no máximo 50; ampliar somente após revisão da
  onda anterior.
- [ ] Exigir zero `unconfirmed`, zero identidade divergente e zero escrita
  parcial para ampliar.
- [ ] Renovar confirmação humana por onda; tamanho de lote não autoriza envio.

### Tarefa 7.2 — operar e reconciliar cada onda

- [ ] Processar estritamente na ordem congelada e registrar ordinal.
- [ ] Não incluir processos novos sem nova análise/snapshot.
- [ ] Reconciliar resultado observado com lista atual da Área Restrita.
- [ ] Manter bloqueados fora do envio e em relatório de tratamento manual.
- [ ] Gerar checkpoint recuperável após cada ato e resumo após cada onda.

---

## Fase 8 — release final e documentação

### Tarefa 8.1 — construir pacote candidato final

- [ ] Atualizar allowlist para todos os módulos rastreados necessários.
- [ ] Construir ZIP em staging novo, sem reutilizar extração antiga.
- [ ] Auditar ausência de perfis, cookies, tokens, dados locais, logs e caminhos
  privados.
- [ ] Extrair em caminho Unicode limpo e executar seis gates públicos.
- [ ] Executar `INICIAR.bat ponte`, health/capabilities e `parar`, confirmando
  ausência de lock órfão.
- [ ] Rodar `verify-project.ps1` completo e registrar contagens.
- [ ] Registrar tamanho, SHA-256, inventário e modo de distribuição.

### Tarefa 8.2 — reconciliar toda a documentação

**Arquivos:**
- Modificar: `README.md`
- Modificar: `docs/ESTRUTURA.md`
- Modificar: plano mestre e handoff final
- Modificar: `portable/README.md`, `GUIA-RAPIDO.md` e `.html`

- [ ] Remover referências a pacote “atual” que não seja o candidato final.
- [ ] Distinguir coleta, preparação, preflight, envio, confirmação e conclusão.
- [ ] Documentar campos opcionais/obrigatórios e tratamento de bloqueios.
- [ ] Documentar que qualificação não transporta autorização entre máquinas.
- [ ] Confirmar todos os caminhos/comandos contra uma extração limpa.
- [ ] Commit `docs: publish qualified automatic workflow release`.

---

## Fase 9 — encerramento Git, GitHub e limpeza definitiva

### Tarefa 9.1 — fechar main

- [ ] Executar `git status`, `git branch`, `git log`, `git diff --check` e
  `verify-project.ps1`.
- [ ] Exigir: apenas `main`, worktree limpo, todos os documentos rastreados e
  nenhum arquivo necessário ignorado.
- [ ] Se o usuário fornecer remoto privado, configurar URL explicitamente,
  fazer `git push -u origin main` e verificar `HEAD == origin/main`.
- [ ] Sem remoto, registrar comandos exatos e estado local; não inventar GitHub.

### Tarefa 9.2 — decidir benchmark histórico de 20 processos

- [ ] Decidir explicitamente se o benchmark continua critério de release.
- [ ] Se mantido, obter lista exata e baseline/candidato observáveis com tempos,
  cliques, OCR, mediana e p95.
- [ ] Se substituído pela evidência do lote 1/50, registrar decisão e limites;
  não reclassificar retroativamente o benchmark antigo como PASS.

### Tarefa 9.3 — purgar quarentena aprovada

- [ ] Revalidar recibo, hashes retidos, pacote final e backup de recuperação.
- [ ] Apresentar lista e bytes exatos para aprovação de exclusão permanente.
- [ ] Executar purge apenas da quarentena nomeada.
- [ ] Reexecutar analisador; esperado: nenhum lixo aprovado restante, nenhum
  arquivo obrigatório ausente e nenhum path fora da raiz tocado.
- [ ] Registrar o que foi removido e se ainda existe cópia recuperável.

### Tarefa 9.4 — handoff final

- [ ] Registrar resumo, arquivos/commits, testes, validações reais, ZIP/hash,
  Git/GitHub, itens removidos, bloqueados, riscos e retomada.
- [ ] Confirmar `real_send_enabled`/qualificação exatamente como entregue.
- [ ] Não declarar conclusão se algum gate obrigatório estiver `not-observed`,
  bloqueado ou sem resultado.

## Ordem crítica

```text
Fase 0 organização/main única
  -> Fase 1 baseline reproduzível
  -> Fase 2 dados elegíveis
  -> Fase 3 OCR portal-real
  -> Fase 4 três preflights
  -> Fase 5 primeiro envio
  -> Fase 6 qualificação + cinco
  -> Fase 7 rollout progressivo
  -> Fase 8 release
  -> Fase 9 encerramento/purge
```

Nenhuma fase posterior reduz os gates de uma fase anterior. A quarentena só é
apagada na Fase 9, e somente depois de a release final e `main` estarem
verificadas.

## Atualização — Tarefa 4.2: preflight real bloqueado (2026-09-11)

**Status:** NÃO PASSA. Os checkboxes da Tarefa 4.2 e de todas as tarefas 5+
permanecem desmarcados. Este bloco é a evidência mais recente e supersede a
retomada genérica anterior que tratava 4.2 apenas como próximo passo.

### Evidência sanitizada observada

- Contexto: login manual já realizado pelo usuário em Chromium 151 isolado,
  controlado por CDP `127.0.0.1:19231`; o agente não digitou credenciais.
- No `ProcessonoSetor`, três representantes foram localizados por consulta
  exata: `100120/2026`, `100273/2025` e `100065/2026`.
- Em cada caso houve uma única ação semanticamente identificada como
  `Complementar Ato`; a identidade processo/ano conferiu.
- Cada tela apresentou um único rádio de interessado. A seleção foi apenas
  reversível para inspeção; depois dela, os sete controles esperados estavam
  presentes.
- Catálogo atual observado: 13 opções de modalidade, 35 de fundamento legal e
  3 de gênero.
- Após reload da sidepanel, a extensão mostrou `preview ready` com 7 cards,
  revisão `120` e prefixo de dataset `23cce5807c01`; `send` e `pilot` estavam
  desabilitados.

### Divergências que bloquearam o preflight

Somente os nomes dos campos são registrados; valores de campos, nomes,
documentos de identidade e demais dados pessoais não são publicados.

| Processo/ano | Campos divergentes entre preview e portal |
| --- | --- |
| `100120/2026` | `fundamento_legal`, `data_publicacao_doe` |
| `100273/2025` | `modalidade`, `data_publicacao_doe`, `matricula` |
| `100065/2026` | `data_publicacao_doe` |

Como houve divergência de campo em todos os três representantes, o protocolo
parou antes de qualquer `APPLY_FIELDS`. Não houve envio, finalização ou outra
mutação no portal. As abas `Complementar Ato` abertas pelo agente foram
fechadas ao final da observação; nenhuma alteração foi persistida.

### Limite e retomada

- Não promover esta execução a PASS, qualificação, piloto ou release.
- Não iniciar a Fase 5. `real_send_enabled=false` e `pilot_enabled=false`
  continuam sendo a fronteira documentada.
- Retomar somente após reconciliar a origem das divergências em nova sessão
  controlada, repetir identidade/ação/rádio/catálogo, comparar novamente os
  sete controles e obter igualdade completa do preview com o portal.
- Mesmo com igualdade, qualquer preenchimento continuaria condicionado ao
  protocolo reversível e a autorização humana imediata; envio e finalização
  permanecem fora deste gate.

## Reconciliação da Tarefa 4.2 — classificação canônica (2026-09-11)

**Resultado:** a reconciliação foi executada novamente em sessão controlada,
com consulta exata, ação única `Complementar Ato`, rádio único e releitura dos
sete controles. Nenhum campo foi escrito e o status da Tarefa 4.2 continua
**NÃO PASSA / bloqueado**.

### Proveniência local

- Auditoria independente confirmou 50 processos e 51 registros, com os três
  candidatos presentes uma única vez e hash lógico do dataset conferente.
- Os seis campos obrigatórios têm `source_value` e `form_value` presentes,
  `status=found`, `confidence=high` e citações com processo, evento, página e
  documento.
- `genero` permanece ausente na fonte nos três casos e continua opcional.
- As citações não carregam hash do PDF nem âncora textual suficiente para
  reextrair automaticamente as datas; portanto a proveniência não autoriza
  corrigir divergências no portal.

### Classificação sanitizada

| Processo/ano | Reconciliado | Classificação segura | Bloqueio remanescente |
| --- | --- | --- | --- |
| `100120/2026` | DOE tem mesma data civil após canonicalização; cargo, matrícula e nascimento coincidem; modalidade e fundamento não têm correspondência exata com o catálogo | DOE = formato/representação; selects = mapeamento indeterminado (`tie`) | `modalidade`/`fundamento_legal` sem `option.value` exato; não preparar |
| `100273/2025` | modalidade permanece empatada; fundamento não resolve `option.value`; DOE não tem mesma data civil; matrícula não coincide nem após compactação conservadora; cargo/nascimento coincidem | modalidade/fundamento = evidência insuficiente; DOE/matrícula = diferença substantiva ou fonte desatualizada, não mera formatação | `modalidade`, `data_publicacao_doe`, `matricula` e fundamento sem decisão segura |
| `100065/2026` | DOE tem mesma data civil após canonicalização; cargo, matrícula e nascimento coincidem; modalidade/fundamento continuam sem correspondência exata segura | DOE = formato/representação; selects = mapeamento indeterminado (`tie`/`probable`) | selects obrigatórios sem proposta determinística; não preparar |

Nas três linhas, a identidade, a ação, o rádio único, o catálogo (13/35/3) e
o frame foram confirmados. A diferença entre igualdade civil e o estado bruto
`Divergente` da sidepanel é real para o contrato atual: a UI compara texto cru
e não deve promover uma equivalência semântica não registrada. Os selects
`tie`/`probable` não foram convertidos em escolha por normalização jurídica.

### Decisão operacional

- A reconciliação eliminou a hipótese de tratar todos os DOEs como divergência
  substantiva, mas só dois são comprovadamente equivalentes por data civil;
  `100273/2025` continua diferente.
- Não há correção de dados no portal. Não há `APPLY_FIELDS`, envio,
  finalização ou alteração persistida.
- O preflight automático aceita `similarity` quando a decisão jurídica já está
  `selected`; `pending` e `tie` continuam bloqueados antes de qualquer
  preparação. A decisão selecionada ainda exige contexto/hash/valor da opção,
  catálogo atual e ausência de divergência nos campos. O comportamento foi
  ajustado por TDD (RED e depois verde) sem liberar qualquer ação portal.
- A Tarefa 4.2 e todas as tarefas 5+ permanecem desmarcadas. A retomada exige
  fonte/âncora suficiente para as datas e `option.value` único para cada
  select obrigatório.

## Correção de requisito — `similarity` permitido (2026-09-11)

O hardening publicado no commit anterior restringia o método jurídico a
`exact`/`rule`, mas isso contrariava o requisito operacional: o catálogo do
portal pode não reproduzir literalmente a fundamentação documental. A
restrição foi removida.

- `LegalDecision.status=selected` com `method=similarity` é aceito;
- `status=pending` e `status=tie` permanecem bloqueados;
- contexto completo, hash, `option.value`, catálogo e divergência continuam
  sendo validados pelo preflight;
- teste focal: 20/20; suíte da extensão reportada por Luna: 291/291;
- nenhum `APPLY_FIELDS`, envio ou finalização foi executado.

## Hardening de reconciliação para retomada da Tarefa 4.2 (2026-09-11)

A regra de negócio foi reconciliada com o requisito: `similarity` é uma
proposta válida quando o matcher seleciona uma opção do catálogo, mesmo que a
fundamentação documental não seja literalmente igual ao rótulo. A igualdade
literal continua não sendo exigida para fundamentação; exigem-se decisão
`selected`, `option.value` presente no catálogo atual, contexto/hash válidos e
ausência de divergência real.

O bloco TDD publicado também corrigiu os pontos de integração que impediam uma
reavaliação honesta:

- `resolveAutomaticAct` agora transporta `matchedValues` reais para
  `modalidade` e `fundamento_legal`, somente quando o valor existe no catálogo;
- o preflight compara selects pelo `value`, nunca tenta fabricar um value a
  partir do rótulo documental;
- um `tie` de select só é preservado quando o portal já contém exatamente o
  `matchedValue` presente no catálogo; campo vazio, value ausente ou value
  divergente continuam bloqueados por `SELECT_MATCH_TIE`/conflito;
- datas civis `DD/MM/YYYY` e `YYYY-MM-DD` são comparadas por chave canônica,
  com calendário validado; formato desconhecido ou data impossível não vira
  igualdade;
- sidepanel e preflight usam a mesma comparação segura, sem transformar
  divergência textual de select em equivalência semântica.

A triagem local independente dos dados confirmou 51 registros, 50 processos
distintos, 41 registros completos nos seis campos obrigatórios e 10
incompletos. `genero` está ausente em todos; 246/246 citações dos completos
possuem processo, evento, página e documento com `found/high`. A duplicidade
esperada é `104956/2025`, que possui dois interessados e não deve ser tratada
como erro de processo.

O conjunto focado após a integração passou em 137/137 testes. O gate real da
Tarefa 4.2 ainda não foi marcado: é necessário repetir a sessão controlada,
obter três preflights reais verdes e registrar a evidência sem executar envio.
Nenhum `APPLY_FIELDS`, envio ou finalização foi executado neste bloco.

## Retomada da Tarefa 4.2 interrompida por expiração de sessão (2026-09-11)

Uma consulta exata somente leitura foi iniciada na origem correta
`ProcessonoSetor.asp` (`sector_finalistic`). Durante a consulta, a Área Restrita
redirecionou essa moldura para `SISTEMAS/PROCESSO/expirou.asp`. Portanto a
sessão autenticada deixou de estar disponível e o gate foi interrompido no
checkpoint humano.

Nenhum ato foi selecionado; nenhum interessado foi alterado; não houve
`APPLY_FIELDS`, envio ou finalização. Os checkboxes da Tarefa 4.2 e das Fases
5+ continuam desmarcados. A retomada requer novo login humano no Chrome isolado,
seguido de confirmação das duas origens (`ProcessonoSetor.asp` e
`MeusProcessos.asp`) antes de qualquer novo preflight.

## Atualização de tasks — separação das origens da Área Restrita (2026-09-11)

- [x] Confirmar, por evidência visual e navegação controlada, a distinção entre
  `Proc./ Doc. Eletrônicos`/processos no setor e `Meus Processos Eletrônicos`.
- [x] Mapear `ProcessonoSetor.asp` para `sector_finalistic` e
  `MeusProcessos.asp` para `my_processes`.
- [x] Filtrar frames de lista pela origem solicitada e impedir a restauração de
  frame persistido da origem errada.
- [x] Permitir `source_scope` nulo somente em frame derivado
  `ComplementarAto.asp` e ignorar iframe oculto como lista ativa.
- [x] Atualizar rótulos da sidepanel, testes TDD e pacote controlado.
- [x] QA: 313/313 na suíte da extensão; smoke read-only em Chromium isolado;
  bridge sem envio real.
- [ ] Reexecutar três preflights reais verdes na origem correta. A Tarefa 4.2
  e todas as tarefas 5+ permanecem desmarcadas.
