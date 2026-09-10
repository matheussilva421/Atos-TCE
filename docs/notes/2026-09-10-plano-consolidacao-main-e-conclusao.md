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
- [ ] Executar contra a raiz real e gravar somente o manifesto em `tmp/fase0`.

### Tarefa 0.3 — classificar todo o workspace

**Escopo mínimo:** `.codex-remote-attachments`, `.superpowers`, `.worktrees`,
`artifacts`, `outputs`, `portable`, `tmp`, `TCE-Acervo... - v2`, ZIP raiz,
`work/tce-extractor/outputs` e arquivos de raiz.

- [ ] Classificar item a item nas nove classes da especificação.
- [ ] Marcar como preservação obrigatória: `.git`, fontes, docs versionadas,
  pacote `fase11k`, evidência live do lote 1, acervo autorizado de 05/09 e
  anexos originais ainda referenciados.
- [ ] Comparar por SHA-256 o ZIP de 1,737 GB da raiz e o de `outputs`; apenas
  se forem idênticos escolher uma cópia canônica.
- [ ] Identificar referências antes de classificar `portable/`, `artifacts/`,
  montagens `staging*`, `.package-staging-*` e diretórios extraídos.
- [ ] Tratar `.worktrees` como removível somente se `git worktree list` não
  apontar para seus diretórios e `git worktree prune --dry-run` confirmar.
- [ ] Tratar `.chrome-work*`, perfis e locks como preservados até provar ausência
  de processo e de sessão necessária.
- [ ] Produzir tabela `reter`, `quarentenar`, `investigar`, `duplicata` e
  `proibido remover`, com tamanho recuperável estimado.
- [ ] Obter aprovação humana do manifesto antes da Tarefa 0.8.

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

- [ ] Revisar cada hunk contra a especificação híbrida e o handoff; rejeitar
  mudança sem teste, documentação ou vínculo com requisito aprovado.
- [ ] Confirmar que novos módulos constam na allowlist do empacotador e no teste
  de inventário do ZIP.
- [ ] Confirmar ausência de token, cookie, URL autenticada, CPF bruto e caminho
  privado com buscas estruturais e revisão manual dos resultados.
- [ ] Executar os gates focais: `npm test`, Python portátil 34+, menu 83+ e
  `git diff --check`.
- [ ] Fazer stage nominal do primeiro conjunto: contratos Python, respectivos
  testes e documentação de origem/lotes; revisar `git diff --cached` e commit
  `feat: add deterministic hybrid batch analysis`.
- [ ] Fazer stage nominal do segundo conjunto: integração de aquisição,
  launcher, bridge/painel e testes; commit
  `feat: integrate frozen batch acquisition`.
- [ ] Fazer stage nominal do terceiro conjunto: correções portal-reais,
  preflight de gênero opcional, guias e handoffs; commit
  `fix: qualify real batch preparation boundaries`.
- [ ] STOP se algum gate falhar; não consolidar `main` com worktree parcial.

### Tarefa 0.6 — reconciliar a branch de transferência

- [ ] Comparar `git diff 6c88d2a ef7d44b --` e confirmar diff vazio.
- [ ] Confirmar que `main` futura conterá `6c88d2a` ou árvore equivalente.
- [ ] Registrar no handoff que `codex/transfer-quiescence` é duplicata de
  patch, não trabalho exclusivo.
- [ ] Não fazer merge dessa branch; reservar sua exclusão para a Tarefa 0.10.

### Tarefa 0.7 — avançar main por fast-forward

- [ ] Exigir worktree limpo em `codex/fundamentacao-automatico`.
- [ ] Executar `git merge-base --is-ancestor main
  codex/fundamentacao-automatico`; esperado exit 0.
- [ ] Trocar para `main` e executar `git merge --ff-only
  codex/fundamentacao-automatico`.
- [ ] Confirmar que `git rev-parse main` é igual ao commit consolidado.
- [ ] Repetir extensão, Python portátil, menu e `git diff --check` em `main`.
- [ ] STOP se fast-forward não for possível; não usar merge commit nem rebase
  improvisado. Registrar a divergência para nova decisão.

### Tarefa 0.8 — criar limpador por manifesto e simular

**Arquivos:**
- Criar: `work/tce-extractor/clean-local-workspace.ps1`
- Modificar: `work/tce-extractor/tests/Test-WorkspaceCleanup.ps1`

**Interface:** `clean-local-workspace.ps1 -Root <absoluto> -ManifestPath <json>
[-Apply] [-PurgeQuarantine]`; sem `-Apply`, somente WhatIf.

- [ ] Criar testes RED para hash divergente, alvo ausente, path traversal,
  reparse point, item não aprovado, perfil ativo e destino fora da raiz.
- [ ] Implementar validação de raiz/path/hash e mover somente itens aprovados
  para `tmp/quarantine/YYYYMMDD-HHMMSS/<caminho-relativo>`.
- [ ] Criar recibo JSON com origem, destino, hash, timestamp e resultado.
- [ ] Implementar purge separado que aceita somente uma quarentena explícita,
  após validar recibo e raiz; nunca aceitar `tmp`, raiz ou glob amplo.
- [ ] Rodar testes e depois WhatIf no manifesto real; comparar contagens e bytes
  com o analisador.
- [ ] Exigir aprovação humana do WhatIf antes de `-Apply`.

### Tarefa 0.9 — quarentenar e validar a pasta organizada

- [ ] Aplicar somente itens `quarentenar` aprovados; desconhecidos permanecem.
- [ ] Reexecutar analisador e confirmar que fontes, docs, entregas, lote live e
  recuperação continuam presentes com hashes iguais.
- [ ] Rodar pacote `fase11k` em extração limpa e os seis gates públicos.
- [ ] Rodar os testes focais novamente.
- [ ] Preservar a quarentena durante todas as fases de qualificação; não fazer
  purge definitivo nesta tarefa.

### Tarefa 0.10 — deixar somente main

- [ ] Confirmar worktree limpo, `HEAD == main` e testes verdes.
- [ ] Excluir `codex/transfer-quiescence` com `git branch -d`; usar `-D` somente
  se a equivalência de árvore estiver registrada e houver aprovação específica.
- [ ] Excluir `codex/fundamentacao-automatico` com `git branch -d` após confirmar
  que `main` contém seu tip.
- [ ] Executar `git branch --format='%(refname:short)'`; esperado: uma linha,
  `main`.
- [ ] Executar `git worktree prune --dry-run`, revisar, e só então podar metadado
  comprovadamente órfão.
- [ ] Atualizar handoff da fase zero com árvore final, hashes e lista retida.

---

## Fase 1 — baseline canônico e saúde da suíte

### Tarefa 1.1 — localizar a lentidão da suíte Python ampla

**Arquivos:**
- Criar: `docs/notes/2026-09-10-python-suite-baseline.md`
- Modificar testes/harness somente após reproduzir causa específica.

- [ ] Executar descoberta ampla com verbosidade e log local ignorado para obter
  o último teste iniciado antes da paralisação.
- [ ] Reexecutar apenas esse módulo/teste com timeout externo de 60 segundos.
- [ ] Classificar causa: espera de navegador, processo filho, servidor, lock,
  rede, fixture grande ou cleanup ausente.
- [ ] Escrever teste RED/asserção de cleanup ou timeout proporcional à causa.
- [ ] Implementar correção mínima sem pular o teste nem reduzir cobertura.
- [ ] Rodar teste focal três vezes e a suíte ampla duas vezes; registrar total,
  aprovados, skips, duração e warnings.
- [ ] Commit `test: stabilize complete Python verification`.

### Tarefa 1.2 — estabelecer o comando único de verificação

**Arquivos:**
- Criar: `work/tce-extractor/verify-project.ps1`
- Criar/Modificar: `work/tce-extractor/tests/Test-ProjectVerification.ps1`
- Modificar: `README.md`

- [ ] Testar que o verificador executa extensão, web, Python ampla, PowerShell,
  empacotamento/auditoria e `git diff --check`, preservando códigos distintos.
- [ ] Exigir resumo final com comando, executados, aprovados, falhos e skips.
- [ ] Não iniciar Chrome autenticado, coleta ou envio nesse comando.
- [ ] Rodar em checkout limpo; expected exit 0.
- [ ] Commit `test: add reproducible project verification gate`.

---

## Fase 2 — reconciliação dos dados do lote 1

### Tarefa 2.1 — fechar a contagem 50 processos/51 interessados

**Arquivos:**
- Modificar: `docs/notes/2026-09-10-lote1-campos-incompletos.md`
- Criar script/teste sanitizado somente se necessário para reproduzir contagens.

- [ ] Recalcular por chave de processo e por identidade de interessado a partir
  da revisão 120, sem publicar nomes/CPF além do já autorizado.
- [ ] Explicar a diferença entre os 40 “somente gênero”, os 9 sem nascimento e
  o total de 50 processos; listar a categoria do processo restante ou corrigir
  a contagem incorreta.
- [ ] Confirmar que `104956/2025` possui dois interessados e registrar qual
  combinação de campos falta em cada identidade sem confundi-los.
- [ ] Produzir matriz agregada `ready_for_preflight` versus `blocked_fields`.
- [ ] Commit `docs: reconcile first real batch field readiness`.

### Tarefa 2.2 — resolver evidência dos campos obrigatórios ausentes

- [ ] Para cada um dos nove registros sem nascimento, revisar documentos já
  baixados e evidências por página; não inferir data por idade ou identificador.
- [ ] Para o segundo interessado de `104956/2025`, revisar modalidade e
  fundamento vinculados à identidade correta.
- [ ] Se o dado existir, corrigir a extração em TDD com fixture sanitizada e
  evidência exata; se não existir, manter bloqueado com motivo explícito.
- [ ] Reexecutar análise apenas dos itens afetados e provar que itens íntegros
  não foram baixados/processados novamente.
- [ ] Atualizar relatório com contagem final de elegíveis e bloqueados.

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
- [ ] Se nenhum documento apto existir, registrar gate `not-observed`, não PASS.

---

## Fase 4 — recuperação do Chrome e três preflights reais

### Tarefa 4.1 — recuperar uma superfície controlável

- [ ] Detectar Chrome/Edge/CDP existente somente por leitura.
- [ ] Preferir perfil de trabalho isolado; nunca fechar ou reutilizar perfil
  pessoal sem autorização.
- [ ] Parar para login humano; não digitar credenciais.
- [ ] Confirmar Área Restrita e e-Contas autenticados, extensão `fase11k` ou
  posterior carregada e ponte pareada.
- [ ] Capturar somente DOM sanitizado necessário, sem sessão/CPF/token.

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
