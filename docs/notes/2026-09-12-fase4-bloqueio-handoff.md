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
