# Handoff — Fase 4 bloqueada e retomada

**Data:** 2026-09-12  
**Status:** Fase 4.1 concluída; Fase 4.2 **NÃO PASSA / bloqueada**.  
**Escopo operacional:** somente a lista autenticada de processos do setor com
o marcador `PROFESSOR - IPERN - 2 - RUBRICAS`, valor `6189`, em
`ProcessonoSetor.asp` (`source_scope=sector_finalistic`). **Não usar
`MeusProcessos.asp`.**

## Onde está o plano que deve ser seguido

- [Especificação aprovada](<C:/Users/slvma/Downloads/Github/Complementação de Atos/docs/notes/2026-09-10-consolidacao-main-e-conclusao-spec.md>) — objetivo, autoridades e critérios globais.
- [Plano de execução — Fase 4, Tarefa 4.1 e Tarefa 4.2](<C:/Users/slvma/Downloads/Github/Complementação de Atos/docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md:367>) — a Tarefa 4.2 começa em [linha 400](<C:/Users/slvma/Downloads/Github/Complementação de Atos/docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md:400>) e exige três preflights reais sem envio.
- [Ledger de progresso/tasks](<C:/Users/slvma/Downloads/Github/Complementação de Atos/.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/progress.md>) — histórico operacional, commits, gates e pendências.
- [Handoff anterior da reconciliação](<C:/Users/slvma/Downloads/Github/Complementação de Atos/docs/notes/2026-09-11-fase42-reconciliacao-handoff.md>) — evidências portal-reais e decisões de segurança anteriores.

## Estado executivo

- A Tarefa 4.1 foi comprovada com Chrome isolado, login humano, Área Restrita/e-Contas, extensão carregada e bridge pareado. Isso não promove a Tarefa 4.2.
- A Tarefa 4.2 ainda não tem os três preflights formais, a releitura pós-preparação nem a evidência de igualdade persistida exigidas pelo plano.
- Fases 5+ permanecem bloqueadas pelo gate formal de 4.2.
- `autoSubmit=false`/`real_send_enabled=false` devem permanecer ativos. Não clicar em enviar, concluir ou finalizar.
- O Chrome/CDP isolado não estava aberto na última verificação: `ECONNREFUSED 127.0.0.1:19232`. Portanto, o estado do último run não pôde ser consultado nem confirmado como parado nesta sessão; o próximo agente deve tratar o run como não confirmado e fazer uma nova verificação controlada após reabrir a superfície.

## Problemas que fizeram a execução parar na Fase 4

### 1. Registro tardio do formulário

O portal primeiro exibe o rádio do interessado e só depois cria os sentinelas
do formulário na mesma moldura. O `form-detector.js` originalmente emitia
`FORM_READY` apenas na injeção, antes desses elementos existirem. O worker
ficava sem registro de frame e o bridge retornava `FRAME_NOT_REGISTERED`.

Referências: `work/tce-extractor/portable/extensao-complementar-ato/content/form-detector.js`,
`tests/form-detector.test.mjs` e o registro correspondente no plano em
[Tarefa 4.2](<C:/Users/slvma/Downloads/Github/Complementação de Atos/docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md:1077>).

### 2. Transição real `interested → form`

O clique no único rádio não cria necessariamente outra tela: ele pode mudar a
mesma moldura diretamente de `interested` para `form`. O contrato antigo
aceitava somente `interested` como progresso e expirava com
`NAVIGATION_TIMEOUT`. O patch TDD em
`work/tce-extractor/portable/extensao-complementar-ato/content/portal-navigation.js`
agora aceita `form` somente quando a identidade selecionada é exatamente a
solicitada. Essa correção está testada, mas não prova sozinha o fluxo live.

### 3. Bloqueio atual: corrida entre `open_act` e o frame interessado

Este é o problema que ainda impede sair da Fase 4:

1. `open_act` abre `Complementar Ato` em um frame/aba irmã e deixa o frame da
   lista montado.
2. O portal cria primeiro o snapshot `interested` e só depois o formulário.
3. O controlador já está com `processSnapshot` em voo aguardando a resposta de
   `open_act`; eventos concorrentes são retidos por
   `pendingPortalSnapshot` em `automation-controller.js`.
4. No último piloto real, o item ficou `queued`, `currentIdentity=null` e não
   houve `select_interested`, apesar de o frame interessado ter aparecido. O
   run ficou `running`/não confirmado em vez de avançar ou pausar claramente.

Pontos para inspeção: `automation-controller.js` em
`processSnapshot` (~1649), `driveSnapshot` (~1770), `handlePortalEvent` (~1790)
e `content/portal-navigation.js` nas regras de frame/`open_act`.
O teste de regressão local está em
`tests/automation-controller.test.mjs` no caso
`replays a newly created interested frame that arrives during open-act navigation`
(~1322). Ele passou em ambiente sintético, mas a reprodução live ainda falhou;
o próximo agente deve instrumentar a ordem real dos eventos e verificar se o
listener/frame do pacote carregado está emitindo e sendo aceito, sem liberar
escrita como paliativo.

### 4. Armadilhas de ambiente já encontradas

- O bridge foi iniciado uma vez na raiz errada `live/acervo-tce`, produzindo
  dataset incompatível. A raiz correta do piloto é o pacote live
  `work/tce-extractor/outputs/live-real-fase11h-sector-lot50`, com o modo
  `--automation-pilot`; não reutilizar a raiz errada.
- Um auxiliar de reload já clicou no primeiro botão `Recarregar` da página de
  extensões, que podia pertencer a outra extensão. O reload deve ser limitado
  ao ID `fpnamgnjnddmmcpnjobnokpfakpooecg` e depois verificado pelo manifest.
- O erro visual de carregar extensão a partir de uma pasta truncada/sem
  `manifest.json` não é resolvido pelo login: a pasta carregada deve ser a
  extração completa `...\\extensao-complementar-ato`.
- O último Chrome isolado usado foi controlado por CDP `127.0.0.1:19232`, com
  perfil de trabalho separado. Nunca reutilizar o perfil pessoal.

### 5. Dados não elegíveis não podem ser usados para “destravar” o gate

O candidato `100182/2024` foi bloqueado por divergências substantivas entre
fonte e portal (DOE, nascimento e fundamentação; gênero ausente na fonte).
Ele não deve ser contado como preflight aprovado. A preferência do usuário é
aceitar fundamentação por similaridade quando a decisão legal está
`selected`; isso não dispensa igualdade de identidade, datas, valores de
opções/catalogo, contexto/hash e os demais campos obrigatórios do protocolo.

## Última evidência runtime conhecida

Antes de o CDP ficar indisponível, o piloto explícito estava no marcador
`6189`, com `autoSubmit=false`, e apresentou:

- run: `run-d90d0286d44a4f51b4ad65a5390224e8`;
- status observado: `running`;
- fila congelada: `true`;
- totais: `discovered=1`, `unique=1`, `pending=0`;
- item: `100065/2026`, estado `queued`;
- `currentIdentity=null`;
- frames observados: lista e interessado; nenhum frame de formulário;
- nenhuma chamada `APPLY_FIELDS`, nenhum preenchimento, envio ou finalização.

A seleção de rádio feita durante a inspeção foi reversível e somente para
revelar os campos. Isso não é evidência de preflight aprovado.

## Gates locais

- `node --test tests/automation-controller.test.mjs`: **50/50 aprovados, 0 falhas**.
- `npm test`: **346/346 aprovados, 0 falhas**.
- `node --check background/automation-controller.js`: passou.
- `node --check tests/automation-controller.test.mjs`: passou.
- Hash SHA-256 registrado na última comparação: controlador portable e live
  iguais (`EBF860C797DE163D5A80223648577D623295717C853AB8056C8D46ABF41D3EC7`).

Esses gates provam o contrato local/sintético, não a passagem portal-real da
Tarefa 4.2.

## Retomada exata para outro agente

1. Ler este handoff, o [spec](<C:/Users/slvma/Downloads/Github/Complementação de Atos/docs/notes/2026-09-10-consolidacao-main-e-conclusao-spec.md>) e a seção [Fase 4 do plano](<C:/Users/slvma/Downloads/Github/Complementação de Atos/docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md:367>); manter os checkboxes formais de 4.2 desmarcados.
2. Verificar `git status --short --branch`, `git diff --check` e os hashes do controlador portable/live. Não adicionar diagnósticos de `tmp/fase41` ao commit.
3. Abrir somente o Chrome de trabalho isolado e carregar a extração completa da extensão em `work/tce-extractor/outputs/live-real-fase11h-sector-lot50/extensao-complementar-ato`; confirmar o ID e o manifest antes de qualquer navegação.
4. Iniciar/revalidar o bridge usando a raiz live correta e `--automation-pilot`. Fazer pareamento com código fresco uma única vez; não compartilhar o mesmo código entre dois fluxos.
5. Parar para login humano se a sessão tiver expirado. Depois navegar por Home → **Processos do setor** → `ProcessonoSetor.asp`, selecionar somente o valor `6189` e confirmar o rótulo observado `PROFESSOR - IPERN - 2 RUBRICAS (470)`. Não abrir **Meus Processos**.
6. Antes de repetir os três atos, reproduzir o bloqueio do item `100065/2026` com tracing sanitizado da sequência `open_act → interested → select_interested → form`. Corrigir a associação entre evento, tab/frame, geração e `inFlight`; a resolução deve ser TDD e fail-closed.
7. Reexecutar o teste focal e `npm test`; só sincronizar/recarregar o pacote live depois de ambos verdes. Confirmar no runtime que `select_interested` foi emitido e que o frame de formulário foi registrado.
8. Selecionar três atos representativos do marcador, cobrindo duas famílias de fundamento e um caso de gênero ausente. Para cada um, conferir identidade, marcador, dataset/hash, seis campos obrigatórios, catálogo atual e decisão legal `selected`; similarity é permitida para fundamentação conforme a decisão registrada, mas divergência substantiva continua bloqueada.
9. Registrar os três preflights e a releitura exigida pelo plano, mantendo todos os comandos de envio/finalização fora do piloto. Atualizar este handoff, o ledger e o plano a cada bloco.
10. Só depois dos gates reais completos avançar para as tarefas 5+, com novo handoff e verificação GitHub. Não declarar conclusão por suíte local verde.

## Git e arquivos desta retomada

- Branch observada: `main`, anteriormente `ahead 4` em relação a
  `origin/main` durante a coleta deste handoff; confirmar novamente antes de
  publicar.
- Alterações locais relacionadas já existentes antes deste documento:
  `background/automation-controller.js`,
  `tests/automation-controller.test.mjs`, o ledger e os dois documentos de
  plano/handoff anteriores.
- Diagnósticos temporários em `tmp/fase41` permanecem fora do escopo de commit.
- Este documento é o ponto de entrada para retomada; não apagar o handoff
  anterior nem os relatórios de evidência.

## Publicação deste handoff

- Commit: `2c73abf` (`docs: handoff phase 4 blocked state`).
- Push: concluído em `origin/main` por fast-forward.
- Verificação: `HEAD == origin/main == 2c73abf`, worktree limpo e
  `git diff --check` sem saída.

---

## Atualização 2026-09-12 — retomada após a correção do sandbox

**Status:** Fase 4.1 concluída; a Tarefa 4.2 continua **NÃO PASSA / bloqueada**.
Nada foi promovido: os três preflights portal-reais ainda não existem.

### Infraestrutura

- O sandbox local voltou a funcionar nesta sessão: comandos, `git`,
  `node --test` e escrita no repositório rodaram sem escalonamento e sem
  rejeição do revisor automático. O bloqueio anterior
  (`helper_sandbox_lock_failed` combinado com
  `Provider error 400 ... This response_format type is unavailable now`)
  não se repetiu.
- No início desta retomada **nenhuma** porta de depuração estava em escuta:
  Chrome/CDP isolado (19232), bridge (18743/18746) e janela de piloto estavam
  fechados. O run anterior segue **não confirmado como parado**.
- Ativos conferidos em disco: Chromium do Playwright em
  `%LOCALAPPDATA%\ms-playwright\chromium-1208\chrome-win64\chrome.exe`,
  perfil de trabalho `tmp\fase41\chrome-work-auth-profile`, extração live
  completa com `manifest.json` (versão 1.1.0, "Complementar Ato TCE/RN") e
  Python em `C:\Python314\python.exe`.

### Correções validadas neste worktree (TDD; sem prova portal-real)

1. `background/automation-controller.js` — recuperação determinística de
   identidade. Quando existe **exatamente uma** identidade enfileirada e o
   snapshot `interested` traz a ação `select_interested` correspondente, o
   controlador a adota como `currentIdentity` em vez de descartar o evento
   com `currentIdentity=null`. Teste:
   `rehydrated pilot recovers its sole queued identity from an interested snapshot`
   (`tests/automation-controller.test.mjs`).
2. `background/service-worker.js` — o cache de descoberta da bridge deixou de
   memorizar resultado nulo. Depois de um pareamento tardio, `AUTO_START` volta
   a descobrir a bridge em vez de responder `AUTOMATION_UNAVAILABLE` para
   sempre. Teste: `AUTO_START retries bridge discovery after credentials are
   paired late` (`tests/service-worker.test.mjs`).
3. `content/portal-navigation.js` — o controle `Consultar` da Área Restrita
   passa a ser procurado em **frames descendentes** (busca em largura, limite
   64), cobrindo o aninhamento real
   `ProcessonoSetor.asp` → `botoesNOVO.asp`, e não apenas irmãos diretos do
   topo. Teste: `finds the Area Restrita Consultar control in a nested sibling
   frame` (`tests/portal-navigation.test.mjs`).

### Sincronização do pacote live

O pacote
`work/tce-extractor/outputs/live-real-fase11h-sector-lot50/extensao-complementar-ato`
recebeu os dois arquivos que estavam defasados. O live é um subconjunto sem
`tests/`; fora os testes, portable e live agora são byte a byte idênticos.

| Arquivo | SHA-256 (portable == live) |
| --- | --- |
| `background/automation-controller.js` | `E3568E4FE974105CB6E3CD6F328433E53717C5C8CEC42603C0177011901FA468` |
| `background/service-worker.js` | `B55DA19BBCE4ECCD4D6D8432B3E04BE93F78D6EBA1A70D7F3FA0999875D2867F` |
| `content/portal-navigation.js` | `F7B95447753F3DC2F4BAB0A885BBE39757C3A964ED26026A897FF2B1C665EFC5` |
| `content/form-detector.js` | `DBDFC9C62F78090A5D91C3F241861A2E6E4BDDCEB1C10096936422FAFE382447` |

O hash `EBF860C…` registrado em "Gates locais" acima está **superado** por
estes quatro.

### Gates executados nesta retomada

- `node --test tests/automation-controller.test.mjs tests/portal-navigation.test.mjs tests/service-worker.test.mjs`:
  **128/128 aprovados, 0 falhas**.
- `npm test`: **349/349 aprovados, 0 falhas** (eram 346).
- `node --check` nos três arquivos de runtime: ok.
- `git diff --check`: **limpo** — cinco linhas com CR solto foram normalizadas
  para LF antes do commit.
- Suíte local verde **não** promove a Tarefa 4.2.

### Retomada imediata

1. Abrir o Chrome isolado com o perfil de trabalho e carregar a extração live já
   sincronizada; confirmar ID `fpnamgnjnddmmcpnjobnokpfakpooecg` e manifest.
2. Subir a bridge na raiz `work/tce-extractor/outputs/live-real-fase11h-sector-lot50`
   com `--automation-pilot` e parear **uma única vez** com código fresco.
3. Parar para login humano se a sessão do portal tiver expirado. Navegar
   Home → Processos do setor → `ProcessonoSetor.asp` com o marcador `6189`
   (`PROFESSOR - IPERN - 2 RUBRICAS`). Nunca `MeusProcessos.asp`.
4. Reproduzir o item `100065/2026` e confirmar no runtime que
   `select_interested` foi emitido e que o frame de formulário foi registrado.
   Se a corrida reaparecer, corrigir de forma fail-closed, sem aumentar timeout.
5. Executar os três preflights exigidos pela Tarefa 4.2 e só então marcar os
   checkboxes do plano. `autoSubmit=false` permanece.

### Locks obsoletos no pacote live (não são bloqueio)

No pacote live, `dados-locais/bridge/service.json` aponta para o pid 13512 e
`.operation.lock` para o pid 4188 — **ambos mortos**. O
`acervo-tce/.workflow-state.lock` também cita o pid 4188.
`app/prepare_transfer.py` recupera esses marcadores sozinho
(`_active_runtime` e `transfer_requested` removem marcador cujo pid não está
vivo), então **não** é preciso apagá-los à mão antes de subir o serviço. Nenhum
processo do serviço local nem Chrome de trabalho estava rodando nesta retomada;
só há Chrome do perfil pessoal.

### Publicação pendente (exige execução humana)

Este bloco está **escrito e validado, mas não commitado**. Nesta sessão o
sandbox expõe `.git` somente para leitura
(`fatal: Unable to create '.git/index.lock': Permission denied`) e o revisor
automático de aprovação continua falhando
(`Provider error 400 ... This response_format type is unavailable now`), então
`git add`/`commit`/`push` precisam ser executados pelo usuário:

```powershell
cd "C:\Users\slvma\Downloads\Github\Complementação de Atos"
git add -- ".superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/progress.md" "docs/notes/2026-09-12-fase4-bloqueio-handoff.md" "work/tce-extractor/portable/extensao-complementar-ato"
git commit -m "fix: recover queued pilot identity and nested consultar frame"
git push
```

A staging é nominal de propósito (o projeto não usa `git add .`/`-A`). Os
três caminhos acima cobrem exatamente os 8 arquivos de `git status`; `tmp/` e
`work/tce-extractor/outputs/` são ignorados pelo `.gitignore`. Se aparecer
`dubious ownership`, repetir com
`git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos'`.

---

## Atualização 2026-09-12 — defeito 5 (deriva de geração), defeito 6 (retomada de identidade) e estado para a retomada

**Status:** Fase 4.1 concluída; a Tarefa 4.2 continua **NÃO PASSA / bloqueada**.
Nada foi promovido e nenhum `APPLY_FIELDS` real ocorreu. Os checkboxes formais
de 4.2 seguem desmarcados no plano. Este bloco **para** a execução: nenhum
piloto foi iniciado na sessão que o escreveu.

### Defeito 5 — o portal repinta a própria tela de ato e a navegação desistia

Ao contrário dos defeitos 1 a 3, este não é corrida de eventos nem registro
tardio: é **contrato de geração**. A tela de ato montada pelo portal executa
`body onload="includeDataJs()"` e desvanece `#dvLoading` no `window load`,
então o *fingerprint* de conteúdo (`currentGeneration` em
`content/portal-navigation.js`) avança **depois** de o controlador já ter
observado a moldura. Duas consequências opostas foram tratadas:

1. **Navegação recusada pelo gate.** O controlador enviava
   `expected_generation` com o valor da observação anterior e recebia
   `STALE_GENERATION`; o `setPaused("portal frame unavailable")` resultante
   escondia a causa real e deixava o item em `queued`.
   Correção em `background/automation-controller.js`: retry **único** da mesma
   ação contra a geração que o próprio gate reportou, com
   `noteFrameGeneration()` gravando a geração viva no registro de frames, e
   `navigationFailureReason()` distinguindo as três saídas — `tab closed`,
   `portal screen changed under the run; manual intervention required` e
   `portal frame unavailable`. Testes:
   `retries the act navigation once when the portal reports a newer screen generation`
   e `pauses instead of retrying forever when the portal keeps reporting newer
   generations` (o segundo prova que o retry **não** é laço: a segunda recusa
   pausa o run).
2. **Verificação recusada por deriva de geração.** `verifyPreparedSnapshot`
   exigia `portalBefore.generation === portalAfter.generation`; a repintura de
   boot do próprio ato fazia uma preparação **correta** ser rejeitada. A deriva
   agora é provada estruturalmente, e não por igualdade de fingerprint: a
   moldura precisa continuar sendo superfície de ato
   (`ACT_SURFACE_ROLES = new Set(["form", "buttons"])`) **e** a releitura campo
   a campo precisa reproduzir cada valor planejado sobre o catálogo de opções
   inalterado. Testes:
   `verifies the prepared act when the portal mutates its own act screen between
   the snapshot and the reread` (GREEN) e
   `fails the prepared act when the portal leaves the act screen during
   preparation` (continua fail-closed: sair da superfície de ato barra a
   preparação). O motivo de falha mudou para
   `portal surface changed during preparation`.
3. **Repintura lida como intervenção humana.** O listener
   `chromeApi.tabs.onUpdated` pausava o run com `manual navigation detected` a
   cada recarga da **submoldura** do ato, que o portal refaz sozinho e sempre
   depois de a promessa de navegação do controlador já ter resolvido. O listener
   agora ignora `changeInfo.frameId` diferente de `0`; o guarda de divergência
   de verdade continua sendo o snapshot canônico do ato (identidade, moldura,
   geração e igualdade de campos). Teste:
   `keeps running when the legacy portal reloads its own act subframe outside a
   navigation`.

### Defeito 6 — retomada sem identidade corrente na tela de ato

Quando o service worker morre entre `open_act` e o boot da moldura do ato, o
run reiniciado fica sem `currentIdentity` e o item fica parado em `queued`
para sempre, mesmo com a tela de ato mostrando o interessado. Correção em
`automation-controller.js` (`resumeIdentityFromActSnapshot`): uma moldura de
ato que publica `return_list` traz a identidade canônica daquele interessado, e
o run adota o **próximo item enfileirado** apenas quando essa identidade é
exatamente igual. Nunca inventa identidade a partir de snapshot genérico.
Testes: `rehydrated running pilot resumes its queued identity from the act form
snapshot and prepares it without sending` (GREEN: prepara **sem enviar**),
`rehydrated pilot stays parked when the act form snapshot carries a diverging
identity` e `rehydrated pilot does not invent an identity from a generic
return_list act snapshot` (ambos fail-closed).

### Correções menores do mesmo bloco (TDD)

- `lib/bridge-client.js` — `wireEventPayload()` converte `identity` para o
  formato de rede dentro de eventos, em vez de repassar o objeto interno cru.
  Teste: `event payload without identity is forwarded without fabricating one`.
- `lib/legal-foundation.js` — `candidateRuleId()` deriva `rule_id` da família
  candidata quando a opção do portal não declara id próprio, preservando o
  vínculo com o catálogo. Teste:
  `names the matched catalog rule when portal options carry no rule id`.

Esses defeitos estão corrigidos **no contrato local/sintético**. Suíte verde
**não** promove a Tarefa 4.2: faltam os três preflights portal-reais.

### Gates desta sessão

- `node --test tests/automation-controller.test.mjs`: **59/59 aprovados, 0 falhas**.
- `npm test`: **359/359 aprovados, 0 falhas**.
- `node --check` nos arquivos de runtime: ok.
- `git diff --check`: **limpo**.
- `git status --short --branch`: `main`, `HEAD = b8c0024` == `origin/main`,
  **6 arquivos portable modificados e ainda não publicados**.

| Arquivo | SHA-256 (portable == live) |
| --- | --- |
| `background/automation-controller.js` | `F08D6BF2B907305D4DDDFF111CC7E2E3E8A7A132379DF3C7DF1AD360F6EFC53B` |
| `background/service-worker.js` | `B55DA19BBCE4ECCD4D6D8432B3E04BE93F78D6EBA1A70D7F3FA0999875D2867F` |
| `content/portal-navigation.js` | `F7B95447753F3DC2F4BAB0A885BBE39757C3A964ED26026A897FF2B1C665EFC5` |
| `content/form-detector.js` | `DBDFC9C62F78090A5D91C3F241861A2E6E4BDDCEB1C10096936422FAFE382447` |
| `lib/bridge-client.js` | `95C3A66651317D6C1FF95C65A272FB8AD768ACED66E709E5FC0E1ED985B99DCE` |
| `lib/legal-foundation.js` | `8DF09A071A26A10B59A845E62663051F3A9EB2D29E0487AB02104D8CBC2A2F02` |

Portable e pacote live estão byte a byte idênticos nos seis. O live é um
subconjunto sem `tests/`.

### Causa real do bloqueio agora (depois dos reloads da extensão)

O run não é barrado pelo portal: é barrado por **estado de sessão da extensão**.
Verificado ao vivo, com o Chrome isolado e a bridge de pé:

1. `chrome.storage.session` tem **apenas** `frame-registrations:v1: []`. O
   reload da extensão apaga o registro de molduras **e** as credenciais da
   bridge, porque ambos vivem em `storage.session`.
2. Os contextos da extensão trazem **só** `TAB`
   (`sidepanel/panel.html`, tabId 1899399451); não há service worker ativo —
   normal no MV3 até existir evento, mas significa que nada foi registrado desde
   o reload.
3. O painel exibe literalmente `Falha no pareamento: pareamento rejeitado` e
   `Tela incompatível: formulário Complementar Ato não detectado`.
4. O `pairing_code` vivo (`[código temporário omitido]`, gravado no boot da bridge às 11:28:01)
   **expirou**: `app/bridge_auth.py` usa `ttl=timedelta(seconds=120)` e
   `max_attempts=5`, e o código é emitido uma única vez em
   `app/local_service.py` (`_write_runtime_metadata`). **Não há reemissão sem
   reiniciar a bridge**: sem restart, todo pareamento devolve `PAIRING_REJECTED`.
5. A moldura da lista está viva mas **sem filtro de marcador**: frame 82
   (`ProcessonoSetor.asp`, `source_scope=sector_finalistic`, generation 2)
   reporta `marker: null` e `identity_count: 0`. O filtro do valor `6189` se
   perdeu no reload. A leitura dessa lista é por resposta de rede, não pelo DOM;
   por isso `identity_count` fica 0 na sondagem de mensagens.

### Fato de arquitetura que a matriz de bloqueio anterior superestimou

O registro de molduras **não** bloqueia a descoberta. `readPortalSnapshot` faz
*broadcast* (`sendPortalMessage(tabId, …, frameId = null)`) e aceita qualquer
resposta com `role` e `source_scope` corretos, sem exigir moldura registrada. O
`FRAME_NOT_REGISTERED` observado antes vem de `currentTabRegistration()`
(`background/service-worker.js`), que só guarda os handlers de mensagem do
**painel** (pareamento, prévia, `AUTO_STATUS`). Ou seja: painel e prévia exigem
registro; o run não. Um `frame-registrations:v1` vazio explica falha de
pareamento e de prévia, **não** impede a automação por si só.

### Por que a tela de ato ainda não é um formulário

`ComplementarAto.asp` abre como `role: "interested"` com **um** rádio
(`name="escolha"`, `onclick="ComplementarAto('58084','APO',…)"`). Os seis campos
obrigatórios só nascem **depois** desse clique, e `FORM_READY` só é emitido
quando os nove sentinelas existem (`txtNumeroProcesso`, `txtAnoProcesso`,
`txtModalidade`, `txtFundamentoLegal`, `txtDataDOE`, `txtCargo`,
`txtMatricula`, `txtDataNascimento`, `txtGenero`). O fluxo real é
`open_act` → `interested` → `select_interested` → `form`, e não
`open_act` → `form`.

### Estado dos ativos no momento deste handoff

- Bridge de pé: **pid 20564**, porta **18743**, raiz
  `work/tce-extractor/outputs/live-real-fase11h-sector-lot50`, modo
  `--automation-pilot`; `/health` responde **401** sem token (esperado).
- Chrome isolado de trabalho: CDP **127.0.0.1:19232** (pid 28564); tab do portal
  **1899399381** (`telaPrincipalMenu.asp`, 12 molduras).
- Molduras: 0, 74, 75, 78, 79, 80, 81, 82, 83, 84, 85, 86. Lista em **82**
  (`marker: null`), botões da lista em **83**, o ato `100065/2026` em **84**
  (wrapper `telaDeTrabalho.asp`) e **85** (`role: interested`, 1 identidade),
  botões do ato em **86**.
- Último run: `run-51d3169773174d5893ced37362e0d418`, `state stopped`,
  revisão **2**, item `100065/2026 → queued`, exatamente **2 eventos**
  (`queue_frozen`, `run_stopped` em `2026-09-12T14:38:17Z`). **Zero
  `APPLY_FIELDS`, zero preenchimento, zero envio.**
- Todos os runs recentes estão `stopped`; nenhum run ativo.
- A seleção do rádio feita em inspeções anteriores foi reversível e **não**
  conta como preflight.

### Retomada exata

1. **Reiniciar a bridge** para obter código de pareamento fresco:
   `tmp/fase41/restart-bridge-18743-safe.ps1`. Sem isso o pareamento continuará
   sendo rejeitado por TTL.
2. **Parear uma única vez** pelo painel
   (`tmp/fase41/pair-pilot-19232-safe.py`) com o código recém-emitido e
   confirmar no painel que `Tela atual` deixa de dizer "Tela incompatível".
3. **Reaplicar o marcador** `6189` (rótulo observado
   `PROFESSOR - IPERN - 2 RUBRICAS (470)`) com
   `tmp/fase41/filter-sector-marker-19232-safe.py`. O controlador também tem
   `ensureMarkerFilter` (ação `filter_marker`), então o próprio run pode
   reaplicá-lo se a política permitir — mas confirmar o marcador antes de
   começar evita preflight sobre lista errada.
4. **Reabrir o ato** do candidato com
   `tmp/fase41/open-candidate-19232-safe.py 100065/2026` (a tabId muda; conferir
   com `tmp/fase41/probe-tabs-sendmessage-19232-safe.py`). Evitar
   `tmp/fase41/ext-reload-19232-safe.py`: cada reload apaga
   `chrome.storage.session`.
5. **Piloto explícito** com
   `tmp/fase41/start-explicit-pilot-safe.py 100065/2026 <tabId>`. Alvos de
   observação: `item_prepared` e `fields_verified` presentes, **sem**
   `REQUEST_COMPLEMENTAR_ATO`; depois ler o DOM com
   `tmp/fase41/read-form-values-19232-safe.py` e comparar campo a campo; por
   fim, `tmp/fase41/auto-stop-run-safe.py <runId> <rev>`.
6. **Repetir para os três alvos** (esquema de envio: `AUTO_START` =
   `{spec, eventId}`; `AUTO_STOP`/`AUTO_PAUSE` = `{runId, eventId, expectedRevision}`):

   - `100065/2026` — identidade conferida em evidência privada, identificador
     `[omitido]`, **EC 47/2005** (option `7`), `PROFESSOR SUPLEMENTAR P9-C`,
     matrícula `102.135-4/1`, nascimento `20/05/1964`, DOE `24.04.2024`,
     modalidade `12`, `hideIdRegistroAto=58084`.
   - `100273/2025` — identidade em evidência privada — **EC 41/2003** —
     `PROFESSOR PN - III, Classe "E"`, matrícula `119.565-4/1`, nascimento
     `21/07/1964`, DOE `26/06/2020`.
   - `103795/2025` — identidade em evidência privada — **ECE 20/2020 c/ EC 41/2003** —
     `PROFESSOR PERMANANTE NIVEL - III, Classe "G"`, matrícula `110.081-5/1`,
     nascimento `02/06/1968`, DOE `19/04/2024`.
   - Descartado: `103777/2025` identidade em evidência privada (sem
     `data_nascimento`; não pode ser contado como preflight).

7. Só depois dos três preflights reais, atualizar plano, ledger e este handoff.
   Publicar em `origin/main` **com autorização explícita antes do push**.

### Publicação deste bloco

Escrito e validado nesta sessão. A staging é nominal e cobre **exatamente** os 6
arquivos portable de `git status` mais este handoff e o ledger; `tmp/` e
`work/tce-extractor/outputs/` são ignorados pelo `.gitignore`.

---

## Solicitações do usuário que continuam pendentes (não são código)

Estas respostas foram pedidas pelo usuário e **ainda não foram entregues**; elas
não bloqueiam a Tarefa 4.2, mas precisam de resposta do próximo agente:

1. **Por que não dá para fazer a complementação só por script, sem a extensão.**
   O portal não expõe API: a sessão da Área Restrita é cookie de navegador e cada
   etapa é uma navegação ASP com frames aninhados (`telaDeTrabalho.asp` →
   `ComplementarAto.asp` → `botoesNovo.asp`). Um script externo precisaria
   reimplementar sessão, frames, catálogo de modalidades/fundamentos e o estado
   do rádio do interessado, e passaria a ser um login automatizado de terceiro,
   sem os guardas do piloto. A extensão roda **dentro** da página autenticada do
   operador, reaproveitando a sessão humana e mantendo a escrita limitada a
   `APPLY_FIELDS` com releitura e `autoSubmit=false`.
2. **Viabilidade de um pacote portátil em ZIP para PC sem instalação.** É
   viável: o pacote live já é autocontido (Python embutido em `runtime/python`,
   `dados-locais`, extensão em pasta) e não exige instalação, apenas navegador
   com carregamento de extensão descompactada e o serviço local em
   `127.0.0.1`. O que **não** é portátil sem preparo é o navegador: o Chrome de
   trabalho foi lançado de um Chromium do Playwright e a extensão é carregada por
   perfil dedicado. Fechar isso como entrega é um bloco de trabalho separado, com
   checklist próprio (perfil pré-carregado, atalho de inicialização e verificação
   de ID/manifest).
3. **Annotation pendente:** explicação, em linguagem simples, de *service worker,
   sidepanel, pareamento, bridge e corridas entre mensagens* — os termos que
   descrevem a arquitetura da extensão do piloto.
# Escopo cancelado pelo usuário em 12/09/2026

A automação foi abandonada a pedido do usuário. Não retomar os pilotos descritos neste histórico. Entrega atual: ZIP de coleta, extração, HTML e extensão manual, documentado em `2026-09-12-pacote-manual-handoff.md`. Tarefa 4.2 não concluída. Nenhum ato enviado; bridge piloto encerrada.
