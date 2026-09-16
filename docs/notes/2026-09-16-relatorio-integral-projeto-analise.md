# Relatório integral do projeto Atos-TCE — o que existe, o que falta e por que a automação da Área Restrita está parada

**Data:** 16/09/2026
**Checkout:** `C:\Users\slvma\Downloads\Github\Atos-TCE`
**HEAD:** `2cb5a54` (`docs: clarify html completion state migration`), `main == origin/main`, árvore limpa
**Remoto:** `https://github.com/matheussilva421/Atos-TCE.git` (conferido em `git remote -v`)
**Destino deste documento:** outro agente/IA que vai decidir e executar a continuidade
**Escopo desta análise:** leitura de código, documentos, artefatos locais e execução de gates offline. Nenhum login, nenhum preflight, nenhum `APPLY_FIELDS`, nenhum envio, nenhum dado privado publicado.

---

## 1. Resumo executivo

O projeto entrega hoje **um fluxo manual completo e funcional** (coletar processos do e-Contas → extrair/OCR → gerar HTML de conferência → exportar JSON → preencher campos pela extensão com revisão humana) e mantém **uma automação de Complementação de Ato construída, testada em nível local, mas nunca qualificada no portal real**.

Três afirmações resumem o estado:

1. **A entrega manual está pronta** — pacote portátil reconstruído e auditado em extração limpa, com launchers, ponte local, mesa HTML e extensão.
2. **A automação está parada no mesmo ponto desde 12/09/2026** — zero preflights reais, zero envios, e os cinco gates do portal seguem `BLOCKED`; a matriz QA oficial é `24 PASS_FIXTURE, 1 PASS_PACKAGE, 5 BLOCKED, 0 PASS_REAL`.
3. **O bloqueio não é mais um defeito local conhecido** — os seis defeitos de runtime identificados foram corrigidos com TDD e a suíte local está verde. O que falta é **execução real supervisionada** (sessão Chrome isolada + login humano + três preflights) e **um envio supervisionado** para transformar a observação em contrato e gerar o `qualificacao.json`.

Além disso, esta análise encontrou quatro problemas novos ou confirmados que precisam de correção antes de qualquer gate real (detalhados na seção 4).

---

## 2. Mapa do projeto

### 2.1 Camadas e artefatos

| Camada | Arquivo/pasta principal | Estado |
|---|---|---|
| Coleta no e-Contas (CDP) | `work/tce-extractor/portable/TcePortal.Driver.js`, `Coletar-Processos-TCE.ps1` | Funcional; coleta real do lote 1/50 concluída em rodada anterior (evidência privada) |
| Extração/OCR e HTML | `portable/app/analysis_pipeline.py`, `html_generator.py`, `app/web/*` | Funcional; mesa HTTP com PDF.js, busca, zoom e "concluído" |
| Extensão Chrome | `portable/extensao-complementar-ato/` (painel, service worker, content scripts, lib) | 406 testes Node; modo manual estável; automação pronta localmente, não qualificada |
| Ponte/mesa local | `portable/app/local_service.py` (HTTP em `127.0.0.1:18743`), `bridge_auth.py` | Funcional; pareamento por código com TTL de 120 s |
| Serviço de automação | `portable/app/automation_store.py`, `qualification.py`, `test_automation_api.py` | Funcional; gate `real_send_enabled` fail-closed implementado |
| Pacote portátil | `portable/*.ps1`, `portable/*.cmd`, `runtime-manifest.json` | Reconstruído em 16/09 e validado em extração limpa |
| Gates de QA | `work/tce-extractor/verify-project.ps1`, `portable/TESTAR-PACOTE.ps1`, `qa_*.py` | Funcionais, com duas lacunas de cobertura (seção 4) |

### 2.2 Onde ficam os dados

- **Repositório Git:** somente código, testes e documentação. O `.gitignore` é lista de permissão (default deny); `outputs/`, `tmp/`, `Versions/`, `acervo-tce/`, `dados-locais/` e perfis não são versionados.
- **`outputs/`:** ZIPs de distribuição. Presentes hoje: público `tce-processos-completo-portatil-2026-09-16.zip` (96.226.201 bytes) e privado `...private-2026-09-16-v2.zip` (1.275.633.919 bytes).
- **`Versions/`:** seis extrações validadas, incluindo `...-2026-09-16-final-v2` (privada, com `acervo-tce`) e `...-2026-09-16-public-v2` (sem acervo).
- **`work/tce-extractor/acervo-tce/`:** 32.547 arquivos de estado de trabalho real (processos, HTML, JSONs, `automacao/`). É dado pessoal; nunca publicar. Atenção: este diretório é a **raiz de workflow** quando o serviço sobe pelo menu, porque `menu.ps1` passa `--root <pacote>/acervo-tce`.
- **`work/tce-extractor/dados-locais/bridge/`:** `service.json` e `.operation.lock` residuais (ponte de sessão anterior). São estado efêmero; não migrar nem publicar.

---

## 3. O problema central: automatizar a Complementação de Ato na Área Restrita

### 3.1 O que a automação precisa fazer

Fluxo real do portal (confirmado por observação em sessão autenticada em 11–12/09):

```text
Home → Processos do setor (ProcessonoSetor.asp, source_scope=sector_finalistic)
  → filtro de marcador (valor 6189, rótulo PROFESSOR - IPERN - 2 RUBRICAS)
  → abrir o ato (ComplementarAto.asp em telaDeTrabalho.asp)
  → tela "interested" com UM rádio (name="escolha", onclick="ComplementarAto('<idAto>','APO',…)")
  → clique no rádio cria os sentinelas dos campos na MESMA moldura
  → seis campos obrigatórios + gênero opcional: txtNumeroProcesso, txtAnoProcesso, txtModalidade,
    txtFundamentoLegal, txtDataDOE, txtCargo, txtMatricula, txtDataNascimento, txtGenero
  → preencher → conferir → (gate manual) concluir
```

Existe ainda a superfície irmã `botoesNOVO.asp`, que hospeda o botão `Complementar Ato` usado no envio.

### 3.2 Por que isso é difícil (obstáculos reais, com evidência)

**a) O portal não expõe API.** É ASP legado com molduras aninhadas (`telaDeTrabalho.asp` → `ComplementarAto.asp` → `botoesNOVO.asp`). A sessão é cookie de navegador. Um script externo teria de reimplementar sessão, frames, catálogo de modalidades/fundamentos e o estado do rádio — e passaria a ser um login automatizado de terceiro, sem os guardas do piloto. Por isso a arquitetura escolhida roda **dentro** da página autenticada do operador.

**b) O formulário nasce tarde.** A tela abre como `interested` com um único rádio; os nove sentinelas só existem depois do clique. O `form-detector.js` originalmente só emitia `FORM_READY` na injeção, o que produzia `FRAME_NOT_REGISTERED`. Corrigido: o detector reavalia e o contrato de navegação aceita a transição `interested → form` apenas quando a identidade selecionada é exatamente a solicitada.

**c) Corrida entre `open_act` e a moldura do interessado.** O `open_act` abre a tela de ato em moldura/aba irmã; o portal cria primeiro o snapshot `interested` e só depois o formulário. Eventos concorrentes ficam retidos em `pendingPortalSnapshot`. Em 12/09 o item `100065/2026` ficou `queued` com `currentIdentity=null` — havia correção local testada, mas a reprodução live falhou.

**d) Deriva de geração da própria tela.** A tela de ato executa `body onload="includeDataJs()"` e desvanece `#dvLoading` no `window load`, avançando o fingerprint (`currentGeneration`) **depois** de o controlador já ter observado a moldura. Isso gerava `STALE_GENERATION` em navegação correta e reprovava preparação correta. Corrigido com: retry único contra a geração reportada pelo gate, `noteFrameGeneration()`, aceitação de deriva apenas se a moldura continuar superfície de ato (`ACT_SURFACE_ROLES = form | buttons`) e a releitura campo a campo reproduzir o planejado sobre catálogo inalterado.

**e) Ciclo de vida MV3.** O service worker pode ser suspenso/destruído no meio do run (perde fila, identidade e registro de molduras). Corrigido com `rehydrate()` (restaura snapshot v1, item states e spec validado) e `resumeIdentityFromActSnapshot()` (adota a identidade enfileirada apenas quando a tela de ato publica identidade canônica idêntica).

**f) Estado de sessão volátil.** `chrome.storage.session` guarda o registro de molduras **e** as credenciais da ponte. Um reload da extensão apaga os dois. Pior: o código de pareamento é emitido **uma única vez no boot da ponte**, com `ttl=120s` e `max_attempts=5` (`app/bridge_auth.py`). Sem reiniciar a ponte, todo pareamento devolve `PAIRING_REJECTED`. Esse foi o bloqueio observado em 12/09 (`Falha no pareamento` + `Tela incompatível`).

**g) Repintura lida como intervenção humana.** O portal recarrega sozinho a submoldura do ato; o listener `tabs.onUpdated` pausava o run com `manual navigation detected`. Corrigido ignorando `changeInfo.frameId !== 0` e usando `webNavigation` para detectar navegação principal.

### 3.3 Contratos de segurança que já existem (não afrouxar)

A automação está cercada por gates fail-closed implementados em código:

- `autoSubmit=false` por padrão; a marcação de envio automático no painel exige `real_send_enabled` **ou** `pilot_enabled`, com confirmação em tempo de ação (`confirmFn`).
- `assertAutoSubmitCapability()` consulta `/capabilities` da ponte e recusa com `REAL_SEND_DISABLED`. Em modo `pilot` exige `pilot_enabled` e `pilot_consumes_remaining`; fora dele exige `real_send_enabled`.
- `local_service.py` só habilita `real_send_enabled` com `--enable-real-send` **e** `automacao/qualificacao.json` válido (`inspect_qualification`); o arquivo precisa casar versões (`extension`, `service_api`, `automation_schema`, `legal_context_schema`, `rules=legal-foundation-v2`, `outcome_classifier=portal-outcome-v1`), `status=qualified`, hashes de fixture e `real_event_id`.
- Escrita limitada a campos da allowlist de sete (`modalidade`, `fundamento_legal`, `data_publicacao_doe`, `cargo`, `matricula`, `data_nascimento`, `genero`), com seis obrigatórios.
- `prepareAutomaticAct()` bloqueia por: identidade ausente/divergente, papel de snapshot diferente de `form`, geração/frame stale, contexto incompleto, hash de dataset divergente, decisão legal não selecionada, confiança < 0,90, margem < 0,12, empate inseguro em select, valor já existente divergente, campo desabilitado/read-only, valor fora do catálogo atual, data civil inválida e qualquer valor que pareça dado privado/URL/caminho.
- Envio: comando com `command_id`, TTL de 15 s, vínculo de frame/geração/hash dos campos, consumo único (`COMMAND_ALREADY_CONSUMED`), botão único habilitado com rótulo **exato** `Complementar Ato`, observador de resultado obrigatório (`OUTCOME_OBSERVER_UNAVAILABLE` aborta sem clique), timeout → `unconfirmed` + pausa, sem reenvio.

### 3.4 O que bloqueia hoje, na prática

1. **Zero preflights reais.** Tarefa 4.2 do plano mestre nunca foi marcada (todos os checkboxes em `[ ]`). Sem três preflights verdes não se avança para a Fase 5.
2. **Qualificação inexistente.** `automacao/qualificacao.json` não existe nem no checkout nem na extração privada `...-2026-09-16-final-v2` (verificado nesta análise). Sem fixture sanitizada do resultado real, o arquivo não pode ser fabricado.
3. **Runner oficial com bypass de TLS.** `work/tce-extractor/real_portal_session.py:188` passa `--ignore-certificate-errors` para o Chromium. O próprio plano proíbe usá-lo para qualificação até remover o bypass. O gravador de QA (`qa_portal_recorder.py`) **não** usa esse flag e é o caminho recomendado.
4. **Sessão observacional anterior terminou `BLOCKED`.** Em 14/09 o `observe_only` registrou 83 eventos estruturais e zero `submit_attempt`, mas com `ERR_INVALID_AUTH_CREDENTIALS`, requisições abortadas e um erro de console; a matriz manteve os cinco gates como `BLOCKED`.
5. **Superfície de piloto precisa ser reconstruída.** O pacote live `work/tce-extractor/outputs/live-real-fase11h-sector-lot50` **não existe mais** neste checkout, e os helpers `tmp/fase41/*` também não. O runbook de retomada de 12/09 não pode ser seguido ao pé da letra.
6. **Modo piloto não vem habilitado no pacote.** Nenhum launcher (`INICIAR.cmd`, `ABRIR-MESA.cmd`, `menu.ps1`, `TcePortable.Core.psm1`) passa `--automation-pilot` ou `--enable-real-send` — comportamento fail-closed correto, mas obriga a subir o serviço manualmente com a flag para qualquer gate real.

### 3.5 Alternativas de abordagem (para o próximo agente avaliar com o usuário)

| Opção | Como funciona | Prós | Contras | Situação |
|---|---|---|---|---|
| **A. Extensão dentro da página autenticada** (atual) | Content scripts no portal + service worker + ponte local | Reaproveita a sessão humana; nenhuma credencial passa pela automação; escrita limitada por allowlist; melhor auditoria | Complexidade de MV3, corridas de frame/geração, estado volátil em `storage.session`, exige extensão descompactada | Implementada; falta qualificação real |
| **B. Playwright/CDP com login humano** | Chromium do Playwright, contexto persistente, trace/HAR | Esperas determinísticas, locators por papel/nome, trace/HAR, frames tratados pela API | É automação de terceiro dentro de sessão bancária do portal; o Chrome/Edge instalado removeu as flags de extensão; precisa de TLS válido | Adotada como camada de **QA/observação** (`qa_portal_recorder.py`), não para o envio |
| **C. Cliente HTTP puro (replay de POSTs ASP)** | `requests` reimplementando sessão e contrato do portal | Simples, rápido, bom para lote | Exige engenharia reversa do portal; sem supervisão visual; risco de disparo massivo; não é "mesma ação do operador" | Descartada historicamente; só reabrir com decisão explícita |
| **D. Híbrida (extensão prepara, Playwright observa)** | Extensão escreve; Playwright grava evidência | Evidência rica sem mudar o caminho de escrita | Duas sessões/processos; a evidência do Playwright não é a sessão que escreveu | Viável, mas adiciona superfície; exigiria decisão nova |

**Recomendação técnica:** manter A como caminho de escrita e B como caminho de observação/evidência, exatamente como já decidido em `docs/notes/2026-09-15-pesquisa-playwright-puppeteer-automacao.md`.

---

## 4. Problemas encontrados e confirmados nesta análise

Classificação: P0 bloqueia release real; P1 quebra gate único ou mascarar risco; P2 degrada confiabilidade/UX; P3 melhoria.

### P1-1 — Suíte da extensão é flaky no teste de confirmação do envio automático

- **Evidência (16/09, nesta análise):** `npm test` em `portable/extensao-complementar-ato` produziu **405 pass / 1 fail** em uma execução e **406/0** em três execuções consecutivas seguintes. Também oscilou quando o mesmo arquivo foi executado duas vezes em paralelo.
- **Teste:** `tests/panel.test.mjs:1077` — `"automatic submission requires capability and an action-time confirmation"`; falha em `assert.match(confirmation, /envio automático|ações externas|Complementar Ato/iu)` com `''`.
- **Causa provável:** o teste espera a carga de capabilities com um orçamento fixo de 5 `setImmediate`. Sob contenção de CPU, um `render()` posterior roda depois de o teste marcar o checkbox — e `render()` faz, incondicionalmente, `elements["automation-auto-submit"].checked = false` (`sidepanel/panel.js:540`). Sem checkbox marcado, `autoSubmit` é falso, `confirmFn` nunca é chamado e `startAutomation()` ainda retorna `true`.
- **Impacto duplo:** (a) gate único não é confiável; (b) em produção, qualquer re-render entre a marcação do operador e o clique **descarta silenciosamente** o opt-in de envio. O efeito é fail-safe (não envia), mas o operador pode acreditar que autorizou o envio automático.
- **Correção sugerida:** não resetar a marcação dentro de `render()` (preservar a intenção do operador, resetando apenas quando capacidades mudarem de inexistente para existente, ou ao iniciar/finalizar o run) e trocar o `setImmediate ×5` do teste por `waitUntil(() => app.getState().automationCapabilities)`, que a própria suíte já usa em outros casos.

### P1-2 — O verificador oficial não cobre os testes Python de automação

- **Evidência:** a etapa `python` de `verify-project.ps1` executa `python -m unittest discover -s portable -p 'test_*.py' -q`. Rodado hoje: `Ran 6 tests … OK`. Existem **49 módulos `test_*.py` na raiz** de `work/tce-extractor` (74 arquivos `.py` no total) que **não** entram nesse discovery.
- **Consequência:** `verify-project.ps1` pode reportar verde com a API de automação, o serviço local e a qualificação quebrados. Foi exatamente o que o handoff de 16/09 já registrava como pendência ("o gate de release deve incorporá-los ou documentar explicitamente essa separação").
- **Evidência complementar coletada hoje (fora do gate):** `python -m unittest test_automation_api test_automation_qualification test_automation_store test_automation_report test_local_service -q` → `Ran 89 tests … OK (skipped=1)` em ~39 s.
- **Correção sugerida:** adicionar uma etapa `python-automation` ao verificador com a lista nominal dos módulos de automação (ou `discover -s . -p 'test_automation*.py'`), mantendo timeout próprio e reportando contagens separadas.

### P1-3 — `real_portal_session.py` ainda usa `--ignore-certificate-errors`

- **Evidência:** `work/tce-extractor/real_portal_session.py:188`. O `test_qa_workflow.py:159` já **proíbe** esse flag no gravador de QA, mas o runner oficial continua com ele.
- **Consequência:** inutiliza o runner para qualificação (mascara problemas de TLS) e viola o limite registrado no handoff de 16/09.
- **Correção sugerida:** remover o flag e validar o certificado; se o ambiente exigir exceção, registrar a causa e obter decisão explícita antes de usar em gate real.

### P2-1 — Runbook de retomada aponta para superfícies que não existem mais

- **Evidência:** `work/tce-extractor/outputs/` contém apenas `01a0a10f-5286-7cb0-95d1-d78b57c226af`; não há `live-real-fase11h-sector-lot50`. Não há `tmp/fase41/` nem `tmp/quarantine/` neste checkout. Os handoffs de 11–12/09 citam ambos como pré-requisito.
- **Consequência:** o próximo agente perde tempo procurando artefatos; o piloto precisa ser montado a partir de `Versions/...-2026-09-16-final-v2` + ponte reiniciada com `--automation-pilot`.
- **Correção sugerida:** reescrever o runbook (seção 9 deste relatório) e marcar os handoffs antigos como históricos.

### P2-2 — Documentação de distribuição contradiz o estado da automação

- **Evidência:** `portable/GUIA-RAPIDO.md` começa com "Pacote portátil TCE/RN — 12/09/2026. Fluxo manual, sem automação de atos." e instrui "Não use os controles de execução automática, piloto ou conclusão automática." — enquanto `README.md` da raiz descreve `pilot_enabled=false`/gates portal-real e o pacote embarca os módulos de automação.
- **Consequência:** o operador do pacote não sabe se a automação é opção ou proibição; a Fase 8.2 do plano exige reconciliar isso.
- **Correção sugerida:** decidir a mensagem (recomendo: "modo manual = entrega suportada; automação = em qualificação, habilitada apenas em sessão supervisionada") e atualizar `GUIA-RAPIDO.md`/`.html`, `portable/README.md` e `README.md` no mesmo commit.

### P2-3 — Escopo da automação tem registro de cancelamento antigo ainda no repositório

- **Evidência:** `docs/notes/2026-09-12-fase4-bloqueio-handoff.md` termina com "Escopo cancelado pelo usuário em 12/09/2026. A automação foi abandonada a pedido do usuário. Não retomar os pilotos descritos neste histórico.", enquanto `docs/notes/2026-09-16-automacao-complementacao-analise-handoff.md` lista como próximos passos exatamente os três preflights e um envio supervisionado.
- **Consequência:** um agente que leia apenas o primeiro documento conclui que a automação está fora de escopo.
- **Ação:** o próximo agente deve confirmar com o usuário qual é o escopo vigente **antes** de qualquer login/preflight, e depois corrigir o documento antigo com uma nota de supersessão.

### P3-1 — Estado privado e montagens residuais no checkout de desenvolvimento

- `work/tce-extractor/acervo-tce/` (32.547 arquivos, dado pessoal), `dados-locais/bridge/{service.json,.operation.lock}` e oito pastas `.package-staging-*` mais `staging-task5-verified` permanecem no checkout. São ignorados pelo Git, mas confundem navegação e aumentam risco de publicação acidental. `staging-task5-verified` **não** pode ser removida sem checar o empacotador (README).
- O lock `.workflow-state.lock` em `acervo-tce` é transitório: `prepare_transfer.py` limpa lock órfão sozinho, não é preciso apagar à mão.

### P3-2 — Fase 9 do plano referencia artefatos que não existem neste checkout

- A Tarefa 9.3 (purga da quarentena) pressupõe o recibo `tmp/quarantine/20260911-012750-653/receipt.json` (16.074 itens, 23,1 GB) e a Tarefa 9.2 pressupõe o benchmark histórico de 20 processos. Ambos viviam no checkout antigo `…\Github\Complementação de Atos`, que **não existe mais** (verificado). É preciso decidir explicitamente: substituir por evidência do lote 1/50 ou registrar como não aplicável.

---

## 5. O que já foi feito (entregas verificáveis)

| Frente | Entrega | Evidência |
|---|---|---|
| Organização e limpeza | Fases 0 e 1 do plano concluídas (64 e 12 checkboxes) | `docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md` |
| Dados do lote 1 | Fase 2 concluída (10 itens): 50 processos/51 interessados fechados | idem + `docs/notes/2026-09-10-lote1-reconciliacao-campos.md` |
| Fundamentação legal v2 | Crosswalk, perfil previdenciário, parser de referência e gates de confiança/margem integrados | `lib/legal-foundation.js`, `portal-legal-crosswalk.js`, `.superpowers/sdd/2026-09-15-corrigir-achados-qa-plano/*`, commits `3d92e0d`…`ac8cb6a` |
| Automação (contrato local) | Seis defeitos de runtime corrigidos com TDD (form tardio, transição interested→form, corrida open_act, deriva de geração, retomada de identidade, identidade conflitante) | `docs/notes/2026-09-12-fase4-bloqueio-handoff.md`, `docs/notes/2026-09-15-qa-final-handoff.md` |
| QA do pacote | Matriz de 30 funções com 24 `PASS_FIXTURE` e 1 `PASS_PACKAGE` | `docs/notes/qa-final-2026-09-14/qa-report.md` |
| Pacote portátil | Reconstrução, auditoria `private`/`public` sem achados, `TESTAR-PACOTE.ps1` 7/7 em extração limpa, `ABRIR-MESA.bat` corrigido, CORS da ponte corrigido | `docs/notes/2026-09-16-automacao-complementacao-analise-handoff.md` |
| Consolidação Git | `main` única, alinhada com `origin/main`, sem worktrees pendentes | `docs/notes/2026-09-16-consolidacao-main-handoff.md` |
| Planilha de processos ausentes | Workbook derivado com 192 processos ausentes e zero downloads | memória do projeto; artefato privado |

---

## 6. O que falta fazer (backlog priorizado)

### Bloco A — Antes de qualquer acesso ao portal (offline, seguro)

1. **Estabilizar o painel e o teste flaky** (P1-1): preservar a marcação em `render()`; trocar o orçamento de ticks por `waitUntil`. Rodar `npm test` 5× e `node --test tests/panel.test.mjs` 5×.
2. **Fechar o gate Python** (P1-2): incorporar os módulos de automação ao `verify-project.ps1` e rodar o verificador completo registrando contagens por etapa.
3. **Remover `--ignore-certificate-errors`** do runner oficial ou substituí-lo pelo gravador Playwright (P1-3).
4. **Reconciliar documentação** (P2-2, P2-3): `GUIA-RAPIDO.md/.html`, `portable/README.md`, `README.md`, nota de supersessão no handoff de 12/09.
5. **Reconstruir a superfície de piloto**: copiar `Versions/TCE-…-final-v2` para uma pasta de trabalho, subir o serviço com `--automation-pilot` (`--enable-real-send` continua proibido sem qualificação) e registrar PID/porta/raiz.
6. **Preparar a fixture do resultado real** (Tarefa 5.3): hoje não existe; só pode ser criada depois de observar um resultado real.

### Bloco B — Gates reais (exigem sessão humana; parar para login)

7. Repetir a **observação** `observe_only` no Chrome de trabalho isolado, sem erros de rede/console e sem `submit_attempt`; registrar trace/HAR privados.
8. Executar os **três preflights** da Tarefa 4.2 no escopo `ProcessonoSetor.asp`/`sector_finalistic`, marcador `6189`, com identidade processo/interessado exata, catálogo atual e seis campos obrigatórios. Candidatos já estudados: `100065/2026`, `100273/2025`, `103795/2025` (valores conferidos em evidência privada; `100182/2024` foi bloqueado por divergência e `103777/2025` descartado por falta de `data_nascimento`). Para cada preflight: preparação reversível → releitura → igualdade de identidade, frame, geração, campos e catálogo; divergência interrompe.
9. **Um único envio supervisionado** (Tarefa 5.2) — somente com autorização imediata e específica; observar resultado, reabrir o ato e confirmar persistência; `unconfirmed` nunca é reenviado.

### Bloco C — Depois do primeiro envio observado

10. Criar a fixture sanitizada do resultado e o contrato de classificação (Tarefa 5.3).
11. Gerar `acervo-tce/automacao/qualificacao.json` vinculado às versões/hashes atuais e validar `real_send_enabled` fail-closed (Fase 6.1).
12. Piloto supervisionado de até cinco atos (Fase 6.2), depois ondas 1/5/10/50 (Fase 7).
13. Release final da Fase 8 e encerramento da Fase 9 (decidir 9.2/9.3 à luz da P3-2).

---

## 7. Evidência de testes coletada nesta análise (16/09/2026)

| Comando | Resultado | Status |
|---|---|---|
| `npm test` (extensão) ×4 | 406/0, 406/0, 406/0 e **405/1** | Verde com flake (P1-1) |
| `node --test tests/panel.test.mjs` | 53/53 em uma execução; falha na outra | Flake confirmado |
| `node --test tests/*.test.mjs` (web) | 6/6 | Verde |
| `python -m unittest discover -s portable -p 'test_*.py' -q` (etapa oficial) | `Ran 6 tests` — OK | Verde, cobertura insuficiente (P1-2) |
| `python -m unittest test_automation_api test_automation_qualification test_automation_store test_automation_report test_local_service -q` | `Ran 89 tests` — OK, 1 skip, 38,9 s | Verde (fora do gate oficial) |
| `git status --short --branch` / `git log` | `main == origin/main` em `2cb5a54`, árvore limpa | Verde |

Não executados nesta análise: suíte PowerShell completa, `TESTAR-PACOTE.ps1`, `qa_matrix_runner.py`, empacotamento, qualquer acesso autenticado, qualquer preflight e qualquer envio.

---

## 8. Riscos e limites

- **Não tratar fixture como prova real.** `PASS_FIXTURE`/`PASS_PACKAGE` não promovem o gate do portal.
- **Não reutilizar o perfil pessoal do Chrome**, não digitar credenciais por automação, não publicar cookies/tokens/HAR/trace/PDFs.
- **Pareamento expira**: código é emitido uma vez por boot da ponte (`ttl=120s`, 5 tentativas). Qualquer reload da extensão exige reiniciar a ponte.
- **Evitar reload da extensão durante o piloto**: apaga `chrome.storage.session` (molduras + credenciais).
- **Um envio por autorização**: autorização genérica/antiga não vale; `unconfirmed` pausa e exige conciliação manual.
- **O portal expira a sessão** durante a navegação (já observado: substituição por `expirou.asp`); sessão expirada = parar e pedir novo login humano.
- **Não apagar `staging-task5-verified`** nem montagens sem checar o empacotador.

---

## 9. Retomada passo a passo (runbook atualizado)

```powershell
# 0. Estado
cd "C:\Users\slvma\Downloads\Github\Atos-TCE"
git status --short --branch; git diff --check

# 1. Gates offline
cd work\tce-extractor\portable\extensao-complementar-ato; npm test
cd ..\..\..; powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\verify-project.ps1

# 2. Superfície de piloto (não usa --enable-real-send sem qualificação)
#    Copie Versions\TCE-...-final-v2 para uma pasta de trabalho curta e suba:
#    runtime\python\python.exe app\local_service.py --root <pacote>\acervo-tce ^
#      --bridge-root <pacote>\dados-locais\bridge --port 18743 --automation-pilot

# 3. Chrome de trabalho isolado (perfil dedicado), extensão carregada da pasta completa
#    4. PARAR para login humano na Área Restrita/e-Contas
#    5. Navegar Processos do setor -> ProcessonoSetor.asp -> marcador 6189 (nunca MeusProcessos.asp)
#    6. Preflight: identidade -> catálogo -> seis campos -> preparação reversível -> releitura
#    7. Registrar evidência privada; NÃO clicar em concluir/enviar sem autorização imediata
```

Antes do passo 4, confirmar com o usuário o escopo vigente da automação (P2-3).

---

## 10. Anexo A — arquivos-chave

- Plano mestre: `docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md` (Fase 4.2 em diante)
- Especificação: `docs/notes/2026-09-10-consolidacao-main-e-conclusao-spec.md`
- Ledger: `.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/progress.md`
- Bloqueio histórico: `docs/notes/2026-09-12-fase4-bloqueio-handoff.md`
- QA final: `docs/notes/2026-09-15-qa-final-handoff.md`; matriz em `docs/notes/qa-final-2026-09-14/qa-report.md`
- Análise de 16/09: `docs/notes/2026-09-16-automacao-complementacao-analise-handoff.md`
- Pesquisa Playwright/Puppeteer: `docs/notes/2026-09-15-pesquisa-playwright-puppeteer-automacao.md`
- Controlador: `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`
- Preflight de campos: `…/lib/automation-preflight.js`; envio: `…/content/portal-submit.js`
- Serviço local: `work/tce-extractor/portable/app/local_service.py`; qualificação: `…/app/qualification.py`
- Ponte: `work/tce-extractor/portable/app/bridge_auth.py`

## 11. Anexo B — comandos e fatos de ambiente

- Remoto conferido: `origin https://github.com/matheussilva421/Atos-TCE.git` (fetch/push).
- Python de QA: 3.14.4 (`C:\Python314`); dependências fixadas em `requirements-qa.txt` (openpyxl 3.1.5, et-xmlfile 2.0.0, playwright 1.58.0, PyMuPDF 1.28.2).
- Node disponível para as suítes da extensão e da web.
- Portas usadas historicamente: CDP `127.0.0.1:19232`/19231, ponte/mesa `127.0.0.1:18743`/18746.
- `/health` da ponte responde 401 sem token (esperado).

## 12. Anexo C — decisões que dependem do usuário

1. A automação da Área Restrita está em escopo agora? (P2-3)
2. Autorizar a correção do painel (P1-1) e do gate Python (P1-2) como primeiro bloco?
3. Substituir o runner com `--ignore-certificate-errors` pelo gravador Playwright para a observação?
4. Fases 9.2/9.3: substituir pela evidência do lote 1/50 ou marcar como não aplicável?
5. Mensagem final do pacote para o operador: manual suportado + automação em qualificação?
