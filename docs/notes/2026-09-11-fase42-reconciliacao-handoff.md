# Fase 4.2 — reconciliação dos bloqueios (2026-09-11)

Status: **NÃO PASSA / bloqueado**. Esta atualização registra a reconciliação
sanitizada; não houve preenchimento, envio, finalização ou persistência no
portal.

## Evidência portal-real

Em Chromium 151 isolado, já autenticado manualmente pelo usuário, foram
repetidos os três fluxos de leitura:

1. consulta exata do processo/ano;
2. identificação de uma única ação `Complementar Ato`;
3. confirmação da identidade e seleção reversível do único rádio;
4. releitura dos sete controles e do catálogo;
5. reload da sidepanel e comparação por hashes/flags, sem publicar valores.

O catálogo observado continha 13 opções de modalidade, 35 de fundamento legal
e 3 de gênero. As abas abertas foram fechadas e a inspeção final não deixou
frame `ComplementarAto` ativo.

## Proveniência do dataset

Auditoria independente em modo somente leitura:

- 50 processos e 51 registros;
- os três candidatos presentes uma única vez;
- seis campos obrigatórios presentes em `source_value`/`form_value`, com
  `status=found`, `confidence=high` e citações com chaves de processo,
  evento, página e documento;
- `genero` ausente na fonte nos três candidatos;
- hash lógico do dataset válido.

As citações não fornecem hash de PDF nem âncora textual suficiente para
reextrair uma data automaticamente. `source_value=form_value` nos campos
textuais/selects locais não prova que o `option.value` atual do portal seja o
mesmo.

## Matriz de reconciliação

| Processo/ano | Evidência comparável | Classificação | Decisão |
| --- | --- | --- | --- |
| `100120/2026` | DOE: `date_canonical_equal=true`; cargo/matrícula/nascimento: igualdade direta; modalidade/fundamento: sem igualdade com valor/rótulo selecionado, matcher `tie` | DOE somente representação; selects indeterminados | Bloqueado |
| `100273/2025` | modalidade `tie`; fundamento sem valor selecionado seguro; DOE `date_canonical_equal=false`; matrícula `identifier_compact_equal=false`; cargo/nascimento iguais | selects insuficientes; DOE/matrícula não são formato comprovado | Bloqueado |
| `100065/2026` | DOE: `date_canonical_equal=true`; cargo/matrícula/nascimento: igualdade direta; modalidade `tie`, fundamento `probable`, sem proposta determinística | DOE somente representação; selects indeterminados | Bloqueado |

O estado `Divergente` de DOE na sidepanel permanece esperado no contrato
atual, pois a UI compara a representação textual bruta. A igualdade civil foi
registrada apenas como evidência de reconciliação; não foi usada para escrever
ou marcar o preflight como aprovado. Também não foi aplicado normalizador de
matrícula, pois uma comparação somente por dígitos poderia colidir registros.

## Hardening identificado

Correção posterior de requisito: o preflight automático aceita também
`method=similarity` quando a decisão está `selected`, porque a fundamentação
documental pode não ser literalmente igual ao catálogo. `pending` e `tie`
continuam bloqueados, junto com contexto/hash/valor da opção ausentes e
divergências de campo. A mudança TDD ficou restrita aos arquivos do preflight
e passou: 20/20 testes focais e 291/291 na suíte da extensão.

## Retomada

- manter `real_send_enabled=false` e `pilot_enabled=false`;
- não usar `APPLY_FIELDS` enquanto houver divergência, empate que exija nova
  escolha, decisão provável sem `option.value` seguro ou evidência incompleta;
- obter âncora/hash documental suficiente para as datas e `option.value` único
  para os selects obrigatórios;
- repetir a sessão controlada e só então reavaliar a Tarefa 4.2;
- mesmo com três preflights verdes, qualquer envio exige autorização humana
  imediata ato a ato.

## Correção aplicada antes da nova reavaliação (2026-09-11)

O requisito foi reconciliado: uma fundamentação `similarity` selecionada pode
ser usada como a opção mais parecida do catálogo, ainda exigindo value presente,
contexto/hash válidos e decisão jurídica `selected`. O código não exige
igualdade literal com o documento.

Também foram publicados os seguintes hardenings TDD:

- o resolvedor autenticado transporta os `optionValue` reais de modalidade e
  fundamento legal;
- o preflight mantém selects por value e permite preservar um `tie` somente
  quando o portal já está exatamente no value escolhido e catalogado; empate
  sem value existente ou que exigiria escrita continua bloqueado;
- datas `DD/MM/YYYY`/`YYYY-MM-DD` são validadas e comparadas civilmente;
- os dois previews usam essa comparação, sem normalizar selects por rótulo.

Testes focados do bloco: 137/137 passaram. A suíte ampla e a repetição portal-
real ainda são pendências desta retomada. A Tarefa 4.2 permanece **NÃO PASSA**
até existirem três preflights reais verdes; nenhum `APPLY_FIELDS`, envio ou
finalização foi executado.

## Correção de origem da Área Restrita (2026-09-11)

A evidência visual fornecida pelo usuário confirma duas origens distintas na
Área Restrita: `Proc./ Doc. Eletrônicos` (processos no setor) e `Meus Processos
Eletrônicos`. A inspeção controlada confirmou o mapeamento canônico:

- `ProcessonoSetor.asp` -> `sector_finalistic`;
- `MeusProcessos.asp` -> `my_processes`;
- `ComplementarAto.asp` não declara origem própria; o frame interessado/form é
  aceito somente como continuação da origem de lista já selecionada.

O controlador agora filtra frames de lista pela origem selecionada, não restaura
um único frame persistido de origem incompatível e mantém o caminho de frame
explicitamente autorizado para navegações já vinculadas. O detector também
ignora documentos/iframes ocultos como listas ativas. A sidepanel exibe as duas
opções com rótulos distintos e envia o valor correspondente ao controlador.

Validação TDD do hardening: RED reproduzido com duas origens, frame persistido
incorreto, frame `ComplementarAto` sem origem e iframe oculto; GREEN em 36/36
testes do controlador, 27/27 de navegação, 43/43 de sidepanel e 313/313 na
suíte completa da extensão. O pacote controlado foi sincronizado por hash.

No smoke read-only, o Chromium isolado abriu as duas abas, com
`ProcessonoSetor.asp` visível e `MeusProcessos.asp` separado/oculto conforme a
aba ativa. O bridge permaneceu sem envio real; nenhum preflight real foi
promovido a PASS e a Tarefa 4.2 continua bloqueada até três preflights verdes.

## Publicação do hardening

Commit `eae3c161f23c7fe552e2a382a0d4e279d555cf2d` foi publicado em
`origin/main` por fast-forward. Após a publicação, `HEAD == origin/main` e
`git diff --check` passaram; o worktree estava limpo. A pendência operacional
permanece somente a obtenção de três preflights reais verdes.

## Retomada interrompida — sessão expirada (2026-09-11)

Na retomada seguinte, a origem correta continuou sendo tratada como
`sector_finalistic`/`ProcessonoSetor.asp`. A consulta exata foi preparada sem
selecionar ato, interessado, ação `Complementar Ato`, preenchimento ou botão
final. A submissão do formulário de consulta, porém, fez a moldura do setor
redirecionar para `SISTEMAS/PROCESSO/expirou.asp`; a sessão da Área Restrita
expirou durante a navegação.

Não houve `APPLY_FIELDS`, envio, finalização, alteração de campo ou seleção de
ato. Os testes locais permanecem verdes conforme a publicação anterior. A
Tarefa 4.2 não muda de classificação: continua **NÃO PASSA** até três
preflights reais verdes.

### Retomada exigida

- usuário deve autenticar novamente no Chrome de trabalho isolado;
- depois confirmar que `ProcessonoSetor.asp` está visível e que
  `MeusProcessos.asp` continua uma origem separada;
- repetir a busca somente após o sinal autenticado, sem usar qualquer botão de
  envio/finalização;
- manter `real_send_enabled=false` e `pilot_enabled=true` apenas para o modo
  controlado sem envio; nenhum piloto foi executado.

O diagnóstico descartável `tmp/fase41/query-sector-form-readonly.py` ficou
disponível para retomada, mas a próxima sessão deve preferir a interação
visível de consulta se o portal voltar a exigir a sessão. O resultado da
auditoria independente Luna da Tarefa 3.1 ainda não foi necessário para este
checkpoint.

## Verificação offline após o checkpoint (2026-09-11)

Foi executado `verify-project.ps1` no estado atual, sem depender da sessão do
portal. O resultado foi 982 casos/comandos agregados, 980 aprovados, 0 falhas e
2 skips. A extensão passou em 313/313, a suíte web em 6/6, Python em 34/34,
PowerShell em 555/555, os contratos do pacote em 71/73 com 2 skips esperados e
`git diff --check` passou. Esta verificação não altera a classificação da
Tarefa 4.2: ainda faltam três preflights reais verdes.

## Retomada controlada após login — piloto de descoberta (2026-09-11)

O usuário confirmou novo login no Chrome de trabalho isolado. A sessão foi
validada novamente na Área Restrita, mantendo separadas as origens
`ProcessonoSetor.asp` (`sector_finalistic`) e `MeusProcessos.asp`
(`my_processes`). O candidato usado para o piloto foi `102390/2026`, localizado
por consulta exata na lista do setor, com uma única ação `Complementar Ato` e
um único rádio de interessado. A seleção do rádio foi reversível e feita para
revisão; nenhum botão final foi acionado.

A extensão 1.1.0 foi recarregada com o guard de tela não reconhecida já
sincronizado no pacote live. A ponte temporária foi renovada e pareada no
dataset correto: revisão `120`, 51 registros, SHA-256 lógico com prefixo
`23cce5807c01`, `pilot_enabled=true`, `pilot_consumes_remaining=true` e
`real_send_enabled=false`. O piloto foi configurado com origem
`sector_finalistic`, lote de 1 e `autoSubmit=false`.

O piloto comprovou a descoberta da identidade e congelou uma fila de 1 item,
mas não alcançou preparação de campos: o run persistiu somente
`queue_frozen` e, após a navegação para a aba irmã `Complementar Ato`, ficou
com o item em `queued`. A integração perdeu os registros de frame durante a
recriação/suspensão do service worker; o run foi encerrado pela ponte local
sem `item_prepared`, `fields_verified`, `APPLY_FIELDS`, envio ou finalização.
Esse resultado é **bloqueado/not-observed**, não é preflight verde.

### Retomada

- manter a sessão autenticada e as duas origens explicitamente distinguíveis;
- corrigir/retestar a reidratação do run/frame antes de repetir o piloto;
- repetir três preflights reais somente com decisão, catálogo, identidade e
  evidência documental suficientes;
- manter `real_send_enabled=false` e `autoSubmit=false`;
- não iniciar Fase 5+ nem promover este piloto a PASS.

## Implementação da reidratação do run/frame — TDD (2026-09-11)

O bloqueio técnico observado no piloto foi corrigido em ciclo TDD. A Luna
`Newton` escreveu o teste focal antes da implementação: a nova instância do
service worker não podia recuperar um run remoto ativo e falhava com estado
local nulo. O RED foi reproduzido com 0/1 teste aprovado.

O controlador agora expõe `rehydrate(snapshot, spec)` e restaura somente
snapshots v1 ativos, identidades canônicas, estados dos itens, revisão, origem,
aba e frames registrados na `storage.session`. Itens em estados de envio,
incerteza, falha ou conclusão não são recolocados na fila executável. A
`service-worker` persiste a RunSpec validada junto do run id, compara a spec
persistida com o snapshot remoto antes de reutilizá-la e reidrata antes de
status, controle ou novo `AUTO_START`; assim um retry não cria um segundo run.
Um run encerrado continua disponível ao painel como histórico, mas não bloqueia
um novo start.

Validação GREEN:

- teste focal de reidratação/controle: 1/1;
- regressão de retry e associação de spec: 2/2;
- suíte da extensão: 317/317;
- `git diff --check`: passou.

O contrato de origem permanece explícito: a lista precisa confirmar
`sector_finalistic` ou `my_processes`; somente a moldura derivada de
`ComplementarAto.asp` pode chegar sem `source_scope`, e ainda exige identidade
canônica, geração e frame compatíveis. O piloto real anterior não foi repetido
neste bloco; não houve `APPLY_FIELDS`, envio ou finalização.

### Retomada após esta implementação

- sincronizar o pacote live com os dois módulos de background e recarregar a
  extensão no Chrome isolado;
- repetir somente o piloto de descoberta de um item na origem
  `sector_finalistic`, com `autoSubmit=false`;
- observar `item_prepared`/`fields_verified` sem promover a preflight verde se
  houver divergência documental, de catálogo, contexto ou identidade;
- manter `real_send_enabled=false` e não iniciar Fase 5+.

## Hardening pós-revisão independente e piloto de lista — TDD (2026-09-11)

A revisão independente Luna identificou quatro riscos concretos: duas partidas
concorrentes poderiam criar runs simultâneos; `verify`/`consume` não reidratavam
um worker recriado; a lista registrada como `unknown` não era sondada; e o
snapshot remoto podia ter projeção parcial da RunSpec. Os dois primeiros foram
corrigidos no worker, e o controlador passou a sondar frames registrados como
`list` ou `unknown`, mantendo o filtro de `source_scope`.

O ciclo TDD ficou verde nos focos: frame registrado desconhecido 1/1, partidas
concorrentes 1/1, reidratação antes de verify/consume 1/1 e suíte da extensão
321/321. O pacote live recebeu hashes idênticos nos dois módulos de background.

Na repetição controlada, a lista `ProcessonoSetor.asp` foi reconhecida como
`sector_finalistic`, a fila de um item foi congelada, mas o piloto permaneceu
`queued` porque a instância Chromium perdeu a injeção dos content scripts após
a recarga da extensão; foi observado `chrome.runtime` ausente nas abas novas e
falha de inicialização do service worker no Chromium (`DidStartWorkerFail`). A
ponte foi renovada/pareada, o run foi encerrado sem preparação. Não houve
`APPLY_FIELDS`, preenchimento, envio ou finalização.

### Tasks atualizadas

- [x] Hardening TDD de mutex para `AUTO_START` concorrente.
- [x] Hardening TDD de reidratação para verify/consume após recriação do worker.
- [x] Sondagem de frame de lista persistido com papel `unknown`.
- [x] Suíte da extensão: 321/321; hashes source/live conferidos.
- [ ] Tarefa 4.2: três preflights reais verdes. O piloto atual é
  **bloqueado/not-observed**, não conta como preflight.
- [ ] Tarefas 5+ permanecem desmarcadas.

### Retomada

Reabrir a instância Chromium isolada com o service worker carregando sem erro,
confirmar a injeção `TCEPortalNavigation`/`TCEFormDetector` na lista e no
formulário, parear a ponte com código fresco e repetir o piloto. Só depois de
três preflights verdes, com identidade, catálogo, contexto e evidência
documental conferidos, atualizar a Tarefa 4.2. Manter `autoSubmit=false` e
`real_send_enabled=false`.

## Publicação final deste bloco (2026-09-11)

A Luna publicou exatamente os oito arquivos rastreados deste bloco no commit
`5ec4ae7181faa2412d235b0c86e4efa3214df916`. O push para `origin/main` foi
concluído sem force; fetch posterior confirmou `HEAD == origin/main`,
worktree limpo e `git diff --check` sem erros. Os diagnósticos em `tmp/` não
foram incluídos.

## Novo checkpoint de ambiente — login necessário (2026-09-11)

Após a tentativa de recuperar a instância Chromium, o runner oficial criou uma
janela isolada com a extensão corretamente carregada e a ponte local ativa, mas
a navegação do portal terminou em `chrome-error://chromewebdata/`. A checagem
HTTPS externa confirmou que o endpoint está disponível e responde `401
Unauthorized` sem uma sessão autenticada. O runner registrou
`credentials_typed_by_runner=false` e `submission_performed_by_runner=false`.

O próximo passo depende de login humano no Chrome de trabalho isolado que está
aberto. Depois do login, confirmar `ProcessonoSetor.asp` como
`sector_finalistic`, manter `MeusProcessos.asp` como origem distinta e repetir
o piloto de um item. Nenhum `APPLY_FIELDS`, preenchimento, envio ou
finalização deve ser executado antes da retomada.

## Escopo operacional confirmado — marcador e rota do Chrome (2026-09-11)

O escopo desta retomada foi restringido pelo usuário a processos do setor com
o marcador `PROFESSOR - IPERN - 2 - RUBRICAS`. A Área Restrita apresenta esse
marcador no catálogo como `PROFESSOR - IPERN - 2 RUBRICAS (470)`; o separador e
o contador são apresentação dinâmica. A opção canônica observada nesta sessão
é `value=6189`. Antes de cada análise, confirmar novamente o par
`label/value` no catálogo e exigir `source_scope=sector_finalistic`.

`MeusProcessos.asp`/`my_processes` não pertence ao escopo desta fase. A lista
válida é exclusivamente `ProcessonoSetor.asp`/`sector_finalistic`; uma tela
`ComplementarAto.asp` só é válida quando derivada dessa lista. Não misturar
identidades, marcadores ou páginas das duas origens.

### Procedimento canônico de abertura

Usar o Chrome de sistema em perfil isolado, nunca o perfil pessoal, carregando
a extensão antes de abrir/recarregar o portal. O caminho correto da extensão é:

`work/tce-extractor/outputs/live-real-fase11h-sector-lot50/extensao-complementar-ato`

O lançamento controlado deve usar `--user-data-dir` no perfil de trabalho,
`--disable-extensions-except` e `--load-extension` apontando exatamente para o
diretório acima, sem `--ignore-certificate-errors`. Abrir então
`https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp`, autenticar
manualmente se solicitado, e só depois abrir a sidepanel. A verificação válida
da extensão ocorre no mundo isolado nomeado `Complementar Ato TCE/RN`; testar
somente o mundo principal pode produzir o falso diagnóstico de que a extensão
não carregou.

Após o login: abrir `Proc./Doc. Eletrônicos` > processos no setor, confirmar
`ProcessonoSetor.asp`, selecionar/confirmar o marcador pelo valor `6189`,
manter `source_scope=sector_finalistic`, e somente então consultar um processo
do dataset. Não usar a aba `Meus Processos Eletrônicos` para este fluxo.

### Falha técnica em correção

A análise da lista falhava depois da filtragem correta porque a espera de
navegação tratava a primeira mutação intermediária da paginação como timeout.
O painel também descartava o erro interno retornado pelo controlador e exibia
apenas uma mensagem genérica. Duas correções TDD independentes estão em curso;
os guards de marcador, origem, geração, aba/frame, identidade e
`real_send_enabled=false` permanecem obrigatórios.

## Evidência live mais recente — paginação ainda bloqueada (2026-09-11)

A sessão foi reaberta no Chrome isolado com o marcador do setor confirmado:
`PROFESSOR - IPERN - 2 RUBRICAS (470)`, valor `6189`, `source_scope` igual a
`sector_finalistic`. A ponte local respondeu capabilities HTTP 200 com
`pilot_enabled=true` e `real_send_enabled=false`.

O `AUTO_ANALYZE` seguro descobriu 32 identidades na primeira página, mas a
execução terminou fail-closed em `portal frame unavailable` ao avançar para a
segunda página. O resultado não é um preflight verde e não deve ser promovido
a PASS. Não houve `APPLY_FIELDS`, preenchimento, envio ou finalização.

Foi despachada uma Luna com ownership exclusivo de
`content/portal-navigation.js` e seus testes para reproduzir e corrigir o
rollover de frame da ação `next_page` em TDD. Depois da integração, repetir a
verificação com o mesmo marcador e registrar o resultado antes de avaliar os
três preflights exigidos pela Tarefa 4.2.

## QA desta retomada (2026-09-11)

- `npm test` na extensão: 325 testes executados, 325 aprovados, 0 falhas.
- `tests/Test-TcePortable.ps1`: 114 testes executados, 114 aprovados, 0 falhas.
- `git diff --check`: aprovado.
- A tentativa live de `AUTO_ANALYZE` confirmou o marcador/escopo e descobriu
  32 identidades, mas falhou de modo seguro em `portal frame unavailable` ao
  executar `next_page`. Isso não fecha nenhum dos três preflights exigidos.

A Luna adicional foi encerrada sem commit novo porque não devolveu uma
correção verificável dentro do limite operacional. Não há alteração de código
pendente desta tentativa; ficam preservados os commits já publicados e a
task de paginação continua explicitamente aberta. Não houve preenchimento,
`APPLY_FIELDS`, envio ou finalização.

## Publicação deste checkpoint (2026-09-11)

O registro deste checkpoint foi publicado no commit `d63d3a2` em
`origin/main`. A verificação posterior confirmou `HEAD == origin/main`,
worktree limpo e `git diff --check` sem erros. O próximo agente deve retomar
pela task de paginação/frame, repetir o preflight apenas no marcador `6189` do
setor e não promover a descoberta parcial a PASS.

## Reconciliação posterior — paginação verde no marcador restrito (2026-09-11)

O trecho “paginação ainda bloqueada” acima é preservado como histórico da
falha observada antes da correção. A implementação local corrigiu a submissão
legacy e o rollover do frame em TDD; a correção foi sincronizada para o
artefato live e validada em três execuções independentes desde a página 1.

Resultado comum das três execuções `AUTO_ANALYZE` read-only:

- `outer_ok=true`, `error=null`;
- `source_scope=sector_finalistic`;
- marcador `PROFESSOR - IPERN - 2 RUBRICAS (470)`, valor canônico `6189`;
- `row_count=470`, `discovered=502`, `unique=472`, `pending=2`;
- sem `portal frame unavailable`, `APPLY_FIELDS`, preenchimento, envio ou
  finalização.

O `inner_ok=null` observado no utilitário não é falha: o controller devolve o
payload da análise diretamente, sem o wrapper `{ ok: true }`. O critério de
sucesso é o envelope externo, ausência de erro e os guards de origem/marcador.

### Procedimento canônico para não repetir o erro de carregamento

1. Usar o executável de sistema
   `C:\Program Files\Google\Chrome\Application\chrome.exe`.
2. Usar somente o perfil isolado
   `C:\Users\slvma\Downloads\Github\Complementação de Atos\tmp\fase41\chrome-work-auth-profile-152`.
3. Carregar exatamente o diretório que contém `manifest.json`:
   `C:\Users\slvma\Downloads\Github\Complementação de Atos\work\tce-extractor\outputs\live-real-fase11h-sector-lot50\extensao-complementar-ato`.
   Não selecionar o diretório pai `live-real-fase11h-sector-lot50` nem outro
   diretório `live`; isso causa a mensagem “manifesto faltando ou ilegível”.
4. Iniciar com `--remote-debugging-port=19232`,
   `--disable-extensions-except` e `--load-extension` apontando para o caminho
   acima. Não usar `--ignore-certificate-errors`.
5. Abrir `https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp`, fazer
   login manual se solicitado, abrir `Proc./Doc. Eletrônicos` > processos no
   setor e confirmar `ProcessonoSetor.asp`.
6. Abrir a sidepanel somente após confirmar o marcador `6189` e
   `source_scope=sector_finalistic`. A aba `Meus Processos Eletrônicos` e
   `MeusProcessos.asp` ficam fora deste fluxo.

Após recarregar a extensão, parear novamente a ponte local, pois o reload
limpa o armazenamento de sessão e não reinjeta content scripts em frames já
abertos. A ponte deve continuar com `pilot_enabled=true` e
`real_send_enabled=false`. A Tarefa 4.2 de três atos ainda está aberta; o
preflight verde acima é apenas o gate técnico da paginação.

## Estado de tasks após a reconciliação

- [x] Escopo restrito ao marcador `PROFESSOR - IPERN - 2 - RUBRICAS` (catálogo:
  `PROFESSOR - IPERN - 2 RUBRICAS (470)`, valor `6189`).
- [x] Origem restrita a processos do setor (`ProcessonoSetor.asp`).
- [x] Paginação e recuperação de frame validadas em 3/3 execuções live.
- [x] Suíte da extensão: 335/335; validador portátil: 114/114.
- [ ] Tarefa 4.2: três preflights de atos; nenhum ato foi preenchido ou
  enviado.
- [ ] Fases 5+ continuam bloqueadas pelo gate funcional 4.2 e pelo checkpoint
  humano obrigatório para qualquer primeiro envio.

## Estado vigente — três prévias read-only reconciliadas (2026-09-11)

### Escopo confirmado

- Área Restrita: `ProcessonoSetor.asp` / `sector_finalistic`.
- Marcador: `PROFESSOR - IPERN - 2 - RUBRICAS`; apresentação live observada:
  `PROFESSOR - IPERN - 2 RUBRICAS (470)`, valor `6189`.
- `MeusProcessos.asp` / `my_processes`: fora do escopo; nenhuma identidade
  dessa origem foi usada.
- Ponte: dataset revisão 120; extensão live com `panel.js` sincronizado pelo
  mesmo SHA-256 do source; `real_send_enabled=false`.

### Prévia read-only observada

Foram feitos três ciclos separados. Em cada ciclo, a aba derivada antiga foi
fechada antes do próximo candidato e o frame foi selecionado por processo/ano,
evitando misturar uma tela stale com a identidade ativa.

| Candidato | Método | Campos obrigatórios | Selects | Gênero | Resultado |
| --- | --- | --- | --- | --- | --- |
| `100065/2026` | `Por regra` | 6/6 sem divergência | value atual coincide com proposta | ausente/opcional | read-only verde |
| `102380/2026` | `Por regra` | 6/6 sem divergência | value atual coincide com proposta | ausente/opcional | read-only verde |
| `100455/2025` | `Por regra` | 6/6 sem divergência | value atual coincide com proposta | ausente/opcional | read-only verde |

O conjunto cobre pelo menos duas famílias legais. `tie` de modalidade e
`aproximado` de fundamento não foram tratados como igualdade textual: a
preservação é segura somente porque o valor já selecionado coincide com o
`matchedValue` validado no catálogo, conforme o preflight TDD. Nenhum valor
documental bruto, nome, CPF, token, cookie ou DOM foi incluído neste handoff.

### Correção operacional registrada

Os auxiliares de observação estavam selecionando o primeiro frame histórico de
`ComplementarAto.asp` depois de várias consultas. Isso explicava a prévia
mostrar uma identidade anterior mesmo quando o portal acabara de abrir outra.
Os auxiliares passaram a selecionar pelo processo/ano e a rotina fecha a aba
derivada entre ciclos. Trata-se de ferramenta ignorada em `tmp/`; o código de
produção apenas recebeu a correção já descrita de encaminhamento do contexto
legal pela sidepanel.

### Tasks e fronteiras

- [x] Confirmar três candidatos do setor e do marcador restrito em prévia
  read-only, com identidade, rádio, catálogo e seis campos conferidos.
- [x] Confirmar duas famílias legais e gênero ausente/opcional.
- [x] Corrigir a seleção de frame stale nos auxiliares e registrar a causa.
- [x] Executar QA da extensão: 45/45 focado no painel e 336/336 na suíte
  completa, sem falhas.
- [ ] Tarefa 4.2 formal: `APPLY_FIELDS` e releitura pós-escrita ainda não
  executados; portanto a preparação persistida não foi marcada como concluída.
- [ ] Fases 5+ continuam bloqueadas; nenhum envio/finalização pode ser
  inferido da prévia read-only.

Não houve escrita de campos, `APPLY_FIELDS`, salvar, enviar, concluir ou
finalizar. Para retomar, manter a rota do setor, confirmar novamente o valor
`6189`, abrir um candidato por vez, parear a ponte com código fresco após
reload da extensão e parar antes de qualquer ação externa.

## QA amplo e estado de publicação (2026-09-11)

O primeiro `verify-project.ps1` do bloco encontrou 22 falhas derivadas de uma
única causa: `portable/app/package_audit.py` não acompanhava a permissão
`webNavigation` já exigida pelo manifest e pelo validador portátil. A Luna
corrigiu somente o auditor e seu teste. O RED foi reproduzido removendo
temporariamente essa permissão da allowlist; o novo teste falhou com
`extension_permissions`; a allowlist foi restaurada e o teste passou.

O commit local da correção é `10f4b68` (`fix: align extension permission
audit`). A verificação ampla posterior passou:

- 1006 execuções;
- 1004 aprovadas;
- 0 falhas;
- 2 skips explícitos;
- extensão 336/336, web 6/6, Python 34/34, PowerShell 555/555;
- pacote 74 testes, 72 aprovados e 2 skips;
- `git diff --check` verde.

### Publicação pendente

`main` está um commit à frente de `origin/main` por causa do commit da Luna;
as alterações não commitadas deste bloco são `panel.js`, seu teste e os dois
documentos de task/handoff. Próximo passo: revisar/stagear somente esses
quatro caminhos, criar um commit nominal e executar `git push` fast-forward.
Depois conferir `HEAD == origin/main` e worktree limpo. Os diagnósticos
ignorados em `tmp/` e o sidecar de contexto gerado no output live não entram
no commit.

## Publicação confirmada do bloco (2026-09-11)

- [x] Commit `10f4b68` da correção do auditor e commit `88fba46` do bloco
  atual publicados em `origin/main` por fast-forward.
- [x] Push retornou `9c5049d..88fba46 main -> main`.
- [x] Verificação pós-push confirmou `HEAD == origin/main` e worktree limpo.
- [ ] Tarefa 4.2 formal permanece pendente: as três prévias read-only não
  foram convertidas em preparação persistida; não houve `APPLY_FIELDS`, envio
  ou finalização.

## Retomada 2026-09-12 — correção TDD do avanço interessado→form

Escopo obrigatório para a retomada: somente o marcador
`PROFESSOR - IPERN - 2 - RUBRICAS` (valor `6189`) na lista autenticada do
setor (`ProcessonoSetor.asp`, `source_scope=sector_finalistic`). Não abrir nem
consultar `MeusProcessos.asp`.

O piloto anterior foi encerrado antes de qualquer escrita. A inspeção
controlada do candidato `100455/2025` mostrou que a ação única “Ato
Complementado” abre a tela com um rádio de interessado; selecionar o rádio
carrega os campos e muda diretamente a classificação da tela para `form`.
O controlador aguardava `interested` depois dessa seleção e expirava com
`NAVIGATION_TIMEOUT`.

### Patch validado

`content/portal-navigation.js` agora exige `before.role === "interested"` e
aceita `after.role === "form"` somente com `selectedIdentity` idêntica à
identidade solicitada. Os testes cobrem o caminho real de
`MutationObserver`, o bloqueio `form→form` e a identidade divergente.

- RED: 1 caso falhou pela razão esperada (`NAVIGATION_TIMEOUT`).
- GREEN focal final: 34/34.
- Suíte completa: `npm test` — 339/339.
- `node --check` e `git diff --check`: verdes.
- Revisão independente Luna `Anscombe`: conforme, 0 findings.
- Arquivos alterados: `content/portal-navigation.js` e
  `tests/portal-navigation.test.mjs`.

Nenhum `APPLY_FIELDS`, preenchimento, envio, conclusão ou finalização foi
executado. O patch ainda precisa ser sincronizado no pacote live, a extensão
recarregada e o bridge pareado com código fresco antes dos três preflights
formais. `autoSubmit=false` deve permanecer em todos os runs.

O `git fetch origin` posterior foi tentado, mas o sandbox não pôde abrir
`.git/FETCH_HEAD`. Isso não altera a confirmação do push nem a igualdade do
ref remoto atualizado pelo próprio push.

## Retomada 2026-09-12 — causa-raiz do FRAME_NOT_REGISTERED

O login permaneceu válido no Chrome isolado. A navegação foi feita novamente
somente por `ProcessonoSetor.asp`, com o valor `6189` do marcador
`PROFESSOR - IPERN - 2 - RUBRICAS`; `MeusProcessos.asp` não foi aberto.
`100455/2025` foi consultado e aberto apenas para inspeção. O rádio único foi
selecionado reversivelmente e os campos apareceram, mas não houve registro de
frame no worker.

O diagnóstico estático mostrou a causa: `form-detector.js` envia `FORM_READY`
apenas no momento da injeção e somente se o conjunto completo de sentinelas já
existir. O portal injeta o detector antes da seleção do interessado e cria os
campos depois; logo, o frame não se registra e o bridge retorna
`FRAME_NOT_REGISTERED`. O worker estava ativo, e a sessão autenticada estava
confirmada; portanto não se trata de login nem de uso da origem errada.

Uma Luna foi encarregada da correção TDD somente em
`content/form-detector.js` e `tests/form-detector.test.mjs`, com observação
limitada à criação tardia do formulário, emissão única de `FORM_READY` e
limpeza do observer. A validação ainda está em andamento. Não houve escrita no
portal, `APPLY_FIELDS`, preenchimento, envio ou finalização.

## Tarefa 4.2 — registro tardio da lista visível (2026-09-12)

A reprodução live reportada no Chrome/CDP ficou restrita à lista do setor em
`ProcessonoSetor.asp`, com `source_scope=sector_finalistic` e marcador valor
`6189`, rótulo observado `PROFESSOR - IPERN - 2 RUBRICAS (470)`. O iframe da
lista começava com bounding rect `0x0`, emitia snapshot `unknown` e não
reenviava quando passava a estar visível.

### Correção TDD

- RED focal: o teste novo falhou pela razão esperada, com `0 !== 1` ao exigir
  o registro tardio do observador.
- GREEN focal do caso: passou com evento inicial `unknown`, um único
  `PORTAL_EVENT` posterior com papel `list` e `source_scope=sector_finalistic`,
  `disconnect` após sucesso e nenhum terceiro evento.
- Suíte focal `node --test tests/portal-navigation.test.mjs`: 35/35 aprovados,
  0 falhas.
- Suíte da extensão `npm test`: 341/341 aprovados, 0 falhas.
- `node --check content/portal-navigation.js` e `git diff --check`: aprovados.
- Commit local: `862b2c2e16fae391ce3863a59f1f51ddf7d9887a`.

`installPortalNavigation` mantém o snapshot inicial e, somente quando ele é
`unknown`, registra `ResizeObserver` no `frameElement` e `MutationObserver` no
documento. A primeira transição reconhecida emite o snapshot tipado, encerra
ambos os observadores e não inicia polling. Os arquivos da implementação são
`work/tce-extractor/portable/extensao-complementar-ato/content/portal-navigation.js`
e `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-navigation.test.mjs`.

Não houve abertura de `MeusProcessos.asp`, `APPLY_FIELDS`, alteração de campo,
preenchimento, envio ou finalização. Não houve push; a publicação e a
integração permanecem sob responsabilidade do controlador. As alterações
documentais já existentes no worktree foram preservadas e não entraram no
commit.
