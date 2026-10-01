# Portal Atual + Preenchimento Manual Best-Effort — Design

**Data:** 2026-10-01  
**Status:** aprovado em conversa; aguardando revisão deste documento antes do plano de implementação  
**Branch:** `codex/area-restrita-reliability-reset`

## 1. Contexto

O fluxo atual da Área Restrita ainda mistura duas decisões diferentes:

1. **segurança de identidade** — saber com certeza qual processo/interessado/formulário está aberto; e
2. **completude da análise** — o processo estar marcado como `PRONTO` ou `PREENCHIDO`.

Hoje `app/area_restrita/fill_service.py` restringe `request_manual_fill()` a `FILLABLE_PROCESS_STATUSES = {"PRONTO", "PREENCHIDO"}`. Isso impede o preenchimento manual assistido de processos `PENDENTE`, `REVISAR`, `ERRO` ou outros estados mesmo quando a análise já encontrou campos úteis.

Ao mesmo tempo, a Mesa atual possui detalhe de processo, documentos, campos, histórico, visualizador de PDF e resultados de preenchimento, mas não acompanha automaticamente o formulário que o operador abriu manualmente na Área Restrita. A UI histórica em `work/tce-extractor/html_generator.py` já demonstrou um padrão útil de “registro selecionado”, campos para colar, pendências e acompanhamento do portal. Esse conceito será reaproveitado na Mesa atual sem ressuscitar o runtime legado.

## 2. Objetivo

Entregar dois comportamentos integrados:

1. **Preenchimento manual best-effort independente do status local.** Quando o operador já abriu o formulário correto na Área Restrita, a automação deve preencher todos os campos encontrados que puder escrever com segurança, mesmo se o processo não estiver `PRONTO`. Campos ausentes, conflitantes, desabilitados ou não resolvidos permanecem como pendências para correção manual.

2. **Aba “Portal atual” com acompanhamento automático.** Quando a extensão identificar de forma inequívoca o processo/interessado do formulário aberto, a Mesa deve localizar o registro local correspondente, selecioná-lo automaticamente enquanto o acompanhamento estiver ativo e exibir uma visão focada com PDF/evidências, campos encontrados e pendências.

O clique final **Complementar Ato** continua exclusivamente humano.

## 3. Não objetivos

Este trabalho **não** deve:

- automatizar `Complementar Ato`, submit, envio, assinatura ou tramitação;
- implementar AR-2/AR-3, `Próximo processo` ou navegação automática Mesa → portal;
- escolher processo “parecido” quando a identidade não for exata;
- sobrescrever silenciosamente valor não vazio divergente já presente no portal;
- criar uma segunda base de dados de processos/evidências;
- ressuscitar `work/tce-extractor` como runtime de produção;
- remover os guards de identidade, geração, frame/formulário ou ambiguidade.

## 4. Princípio central

A mudança separa **falta de dados** de **falta de identidade segura**:

> **Faltou dado:** preencher o que existe e deixar pendência.  
> **Não sabemos com certeza qual ato é:** não escrever nada.

O status local deixa de ser autorização para preenchimento manual. A segurança passa a depender da identidade e do formulário observados.

## 5. Fluxo principal

### 5.1. Acompanhamento Portal → Mesa

```text
Área Restrita
    ↓
extensão detecta exatamente um formulário visível
    ↓
processKey + interestedNormalized + portalActId? + generation
    ↓
background/service worker
    ↓
POST /api/v1/portal/current-selection
    ↓
Mesa resolve a identidade local
    ↓
MATCHED / NOT_FOUND / AMBIGUOUS / INVALID
    ↓
GET /api/v1/portal/current-selection
    ↓
Mesa UI
    ↓
followPortal ativo?
  ┌──────────────┴───────────────┐
  sim                            não
  ↓                              ↓
seleciona processo               preserva navegação manual
abre/atualiza “Portal atual”     mostra acompanhamento pausado
```

A direção é deliberadamente **Portal → Mesa**. Selecionar um processo na Mesa não abre ou navega automaticamente o portal neste trabalho.

### 5.2. Preenchimento manual assistido

```text
operador abre o formulário correto
        ↓
extensão lê um único formulário
        ↓
Mesa resolve identidade exata
        ↓
status local NÃO é gate
        ↓
preflight campo a campo
        ↓
campos found e graváveis → preencher
campos ausentes/conflitantes/desabilitados → warning
        ↓
releitura
        ↓
resumo parcial/completo
        ↓
operador revisa/corrige
        ↓
Complementar Ato permanece manual
```

## 6. Contrato de identidade e segurança

A extensão nunca envia um `process_id` interno como fonte de verdade. Ela publica apenas identidade observada no portal:

- `processKey`;
- `interestedNormalized`;
- `portalActId`, quando disponível;
- `generation`;
- estado/screen estrutural necessário ao acompanhamento.

O backend reutiliza a resolução autoritativa existente, incluindo `resolve_process_identity()`.

Resultados possíveis:

- **MATCHED** — exatamente um registro local compatível;
- **NOT_FOUND** — nenhum registro local corresponde;
- **AMBIGUOUS** — mais de um candidato ou identidade insuficiente para escolher;
- **INVALID** — payload/generation/screen estrutural inválido;
- **NO_ACTIVE_FORM** — nenhum formulário ativo recente.

Nunca escolher por similaridade, ordem visual ou “mais provável”.

### 6.1. Guards que continuam obrigatórios para escrita

O preenchimento permanece bloqueado se houver qualquer condição como:

- nenhum processo local identificado;
- processo/interessado ambíguo;
- identidade do formulário divergente do processo resolvido;
- dois formulários visíveis candidatos;
- generation ausente, inválida ou stale;
- identidade mudar entre preflight, write e readback;
- alvo estrutural de frame/form não puder ser confirmado.

## 7. Status do processo e elegibilidade

### 7.1. Manual fill

`request_manual_fill()` deixa de recusar apenas porque o processo não está em `PRONTO` ou `PREENCHIDO`.

Estados como:

- `PENDENTE`;
- `IDENTIFICADO`;
- `BAIXADO`;
- `REVISAR`;
- `ERRO`;
- `PRONTO`;
- `PREENCHIDO`;

podem participar do preenchimento manual best-effort quando a identidade do formulário for exata.

`BLOQUEADO` e `DIVERGENCIA` também podem ser exibidos na aba “Portal atual”. O rótulo do status, sozinho, não é motivo suficiente para impedir best-effort. Porém, se o motivo subjacente for uma condição de identidade insegura, os guards de identidade acima continuam bloqueando a escrita.

### 7.2. Fluxo automático

Esta mudança **não altera** a elegibilidade de `request_fill(process_id)` nem autoriza navegação automática. O relaxamento é para o fluxo manual em que o operador já abriu o formulário.

## 8. Semântica best-effort dos campos

O preflight atual já possui o comportamento desejado e deve ser preservado:

- utiliza somente propostas de campos conhecidos com `status == "found"` e valor não vazio;
- avalia cada campo independentemente;
- campo sem proposta vira warning;
- controle ausente, unreadable, disabled ou read-only vira warning;
- valor não vazio equivalente é preservado;
- valor não vazio divergente é preservado e vira warning;
- campos independentes continuam sendo planejados mesmo se outro campo falhar;
- fundamento legal e modalidade continuam usando os resolvers/catálogos atuais;
- o filler nunca inventa valor ausente.

### 8.1. Zero campos encontrados

Se a identidade for segura, zero propostas não devem ser tratadas como erro de identidade. O fluxo pode produzir um plano vazio e um resumo de pendências, sem escrever nada. A UI deve explicar que não havia dados aproveitáveis.

### 8.2. Resultado parcial

A conclusão de uma `fill_request` significa que a tentativa de escrita terminou; não significa que o processo local se tornou completo.

Um processo que começou em `REVISAR`, por exemplo, não deve ser artificialmente convertido em `PRONTO` só porque alguns campos foram escritos.

A UI deve diferenciar claramente:

- **preenchimento completo** — todos os campos obrigatórios do plano foram satisfeitos;
- **preenchimento parcial** — algum campo foi alterado/preservado, mas há pendências;
- **sem dados aproveitáveis** — nenhum campo foi escrito;
- **bloqueado por segurança** — identidade/formulário não seguro.

## 9. Estado transitório “Portal atual”

O acompanhamento do portal é um estado operacional transitório, não uma nova fonte de verdade do domínio.

O backend mantém a última observação resolvida com dados mínimos, por exemplo:

```json
{
  "state": "MATCHED",
  "process_id": 1234,
  "process_key": "100443/2025",
  "generation": 17,
  "screen": "form",
  "observed_at": "2026-10-01T..."
}
```

Esse estado:

- não altera `process.status`;
- não grava HTML do portal;
- não grava cookies/tokens;
- não replica documentos/campos;
- não escolhe processo aproximado;
- expira automaticamente.

### 9.1. TTL

Uma observação ativa deve expirar após aproximadamente **10 segundos** sem renovação válida.

Após expirar:

```text
state = NO_ACTIVE_FORM
```

A Mesa mantém a seleção manual atual e apenas informa que nenhum formulário ativo está sendo observado.

## 10. API proposta

### 10.1. `POST /api/v1/portal/current-selection`

Uso: extensão/background publica observação sanitizada.

Autenticação: reutilizar autenticação existente da extensão; não criar novo esquema.

Payload conceitual:

```json
{
  "identity": {
    "processKey": "100443/2025",
    "interestedNormalized": "nome normalizado",
    "portalActId": "opcional"
  },
  "generation": 17,
  "screen": "form"
}
```

O endpoint valida o payload, resolve a identidade e atualiza o estado transitório.

Para viabilizar o botão **Preencher dados encontrados** sem criar navegação automática, a observação ativa também pode transportar o snapshot sanitizado que `readCurrentForm()` já produz. Esse snapshot fica **somente em memória**, associado à observação e sujeito ao mesmo TTL de 10 segundos. Ele não entra em SQLite, logs, reliability telemetry nem na resposta do GET público da seleção.

Respostas não devem ecoar PII desnecessária.

### 10.2. `GET /api/v1/portal/current-selection`

Uso: Mesa UI consulta o estado observado.

Autenticação: sessão normal da Mesa.

Resposta conceitual MATCHED:

```json
{
  "state": "MATCHED",
  "process_id": 1234,
  "process_key": "100443/2025",
  "generation": 17,
  "screen": "form",
  "observed_at": "..."
}
```

Outros estados não devem inventar `process_id`.

### 10.3. `POST /api/v1/portal/current-selection/fill`

Uso: Mesa UI solicita o preenchimento manual best-effort da observação MATCHED que ainda esteja dentro do TTL.

Autenticação: sessão normal da Mesa.

O backend deve:

1. exigir uma seleção MATCHED e não expirada;
2. recuperar o snapshot transitório mantido apenas em memória;
3. revalidar identidade/generation através do fluxo normal de `request_manual_fill()`;
4. criar a `fill_request` manual existente;
5. devolver `fill_request_id` e estado.

O endpoint não cria `OPEN_ACT`, `OPEN_NEXT_ACT` ou qualquer navegação. Se a observação expirar entre a renderização e o clique, a solicitação falha fechada e nenhuma escrita ocorre.

## 11. Detecção automática na extensão

A sincronização não pode depender do sidepanel estar aberto.

O portal já possui `content/heartbeat.js`, que acorda o MV3 worker a cada ~1,5 s. Esse caminho deve acionar observação read-only do formulário atual.

Comportamento:

1. heartbeat acorda o worker;
2. worker usa o leitor existente para identificar o formulário atual;
3. somente exatamente um formulário válido pode produzir MATCHED;
4. worker calcula uma assinatura da observação;
5. mudanças relevantes são publicadas imediatamente;
6. observação idêntica é deduplicada;
7. heartbeat leve renova TTL sem gerar spam desnecessário.

Assinatura conceitual:

```text
processKey + interestedNormalized + portalActId + generation + screen
```

O sidepanel continua podendo mostrar a identidade atual, mas não é o dono do acompanhamento.

## 12. UX da Mesa

### 12.1. Nova aba

Adicionar ao detalhe:

```text
Dados | Documentos | Histórico | Portal atual
```

Quando o acompanhamento está ativo e o portal muda para outro processo, a Mesa seleciona o novo processo e leva a visão para “Portal atual”.

Se o usuário apenas trocar de subaba dentro do mesmo processo, a UI não deve roubar o foco a cada poll. A aba “Portal atual” é reaberta automaticamente quando o processo observado muda ou quando o usuário usa **Retomar acompanhamento**.

### 12.2. Acompanhar / pausar

Estado inicial:

```text
● Acompanhando portal
[Pausar acompanhamento]
```

Se o operador selecionar manualmente outro processo na lista:

```text
○ Acompanhamento pausado
[Retomar acompanhamento]
```

Ao retomar:

- `followPortal = true`;
- a Mesa seleciona o último `portalProcessId` MATCHED ainda válido;
- abre a aba “Portal atual”.

### 12.3. Layout “Portal atual”

Reaproveitar os dados e componentes da Mesa atual:

- coluna de PDF/evidência à esquerda;
- cabeçalho com processo, interessado e status;
- indicação de qualidade/completude;
- cards de campos encontrados;
- ações **Copiar valor** e **Ver evidência**;
- lista de pendências;
- resumo do último preenchimento;
- ação **Preencher dados encontrados**.

Não criar novo PDF renderer. Reutilizar o viewer atual.

### 12.4. Classificação visual

A aba pode derivar um indicador visual sem alterar `process.status`:

- **COMPLETO** — todos os campos obrigatórios disponíveis/satisfeitos;
- **PARCIAL** — há pelo menos um campo útil e também pendências;
- **SEM DADOS** — nenhum campo aproveitável;
- **CONFLITO** — existem divergências que exigem revisão.

Essa classificação é informativa; não é gate de preenchimento.

### 12.5. Campo encontrado

Exemplo conceitual:

```text
MATRÍCULA                              ENCONTRADO
110.331-8/1

[Copiar valor] [Ver evidência]
```

### 12.6. Campo pendente

```text
GÊNERO                                 PENDENTE
Não localizado com segurança
```

### 12.7. Valor divergente no portal

```text
DATA DE NASCIMENTO                     REVISAR
Encontrado: 27/11/1968
Portal atual: 28/11/1968
```

O valor já existente é preservado; os outros campos continuam.

## 13. Evidências e documentos

“Portal atual” usa `GET /api/v1/processes/<id>` e as APIs/evidências já existentes.

Ao selecionar **Ver evidência**:

1. abrir o documento ligado ao campo;
2. navegar para a página de evidência quando conhecida;
3. preservar o processo atual;
4. destacar geometria/retângulo se a evidência existente disponibilizar coordenadas.

Nenhuma evidência nova precisa ser persistida apenas por causa do acompanhamento do portal.

## 14. Estados de erro da aba

### NOT_FOUND

```text
Processo identificado no portal, mas não encontrado no acervo local.
```

Não selecionar processo parecido.

### AMBIGUOUS

```text
Correspondência ambígua. Nenhum processo foi selecionado automaticamente.
```

### NO_ACTIVE_FORM

```text
Área Restrita conectada · nenhum formulário aberto.
```

A seleção manual da Mesa permanece intacta.

### INVALID/STALE

Mostrar diagnóstico estrutural curto e sanitizado; não escrever campos.

## 15. Interação com o Reliability Reset

Esta feature altera a semântica de AR-1 e modifica código de produto.

Consequências:

- o AR1_BUILD antigo `e059793a412f3fe4c8b403fb3a58cfa02e26553c` deixa de ser a build a qualificar após a implementação;
- o ZIP congelado correspondente deixa de ser o artefato de qualification;
- como ainda não existem runs reais AR-1 válidos, não há evidência a perder;
- após implementação, review e gates completos, deve ser criado um novo AR1_BUILD;
- deve ser gerado novo ZIP com provenance;
- `manual_form_fill` volta/permanece `EXPERIMENTAL`;
- a sequência real começa novamente em 0/20.

AR-2, AR-3 e Tasks 6–10 continuam fora de escopo até AR-1 atingir `PRODUCTION` na nova semântica.

## 16. Privacidade

Não persistir ou versionar:

- nome real de interessado em logs de reliability;
- CPF;
- matrícula pessoal fora do banco funcional já existente;
- cookies;
- tokens;
- Authorization;
- HTML privado bruto;
- HAR/traces privados;
- Chrome profile;
- payload integral do formulário em telemetria.

O estado “Portal atual” deve guardar somente o mínimo operacional necessário para resolver e apresentar o processo local.

## 17. Testes obrigatórios

### 17.1. Manual best-effort

Cobrir pelo menos:

- `REVISAR` com quatro campos `found` → os quatro entram no plano;
- `PENDENTE`, `ERRO`, `BAIXADO` e `PREENCHIDO` → não recusados apenas por status;
- zero campos `found` → plano vazio/warnings, sem write inventado;
- campo ausente → demais campos continuam;
- campo disabled/read-only → demais continuam;
- valor existente divergente → preservado e warning;
- identidade divergente → bloqueada;
- identidade ambígua → bloqueada;
- generation inválida/stale → bloqueada.

### 17.2. Current selection backend

Cobrir:

- MATCHED resolve exatamente um processo;
- NOT_FOUND não produz process_id;
- AMBIGUOUS não escolhe arbitrariamente;
- payload inválido recusado;
- observação expira após TTL;
- status do processo não é alterado pela observação;
- dados privados não aparecem na resposta além do mínimo aprovado.

### 17.3. Extensão

Cobrir:

- heartbeat publica formulário válido mesmo com sidepanel fechado;
- mesma assinatura é deduplicada;
- mudança A → B publica B;
- zero formulários publica/permite expirar para NO_ACTIVE_FORM;
- múltiplos formulários não publicam MATCHED;
- nenhum novo comando proibido de submit/finalize aparece.

### 17.4. Mesa UI

Cobrir:

- MATCHED + follow ativo seleciona o processo;
- mudança de processo observado atualiza a seleção;
- seleção manual pausa follow;
- Retomar acompanhamento volta ao último processo observado;
- NOT_FOUND/AMBIGUOUS não selecionam registro aproximado;
- aba “Portal atual” usa os dados do detalhe existente;
- botão de best-effort permanece disponível para status não-PRONTO quando a identidade é segura;
- resultado parcial mostra contagem de alterados/preservados/pendências;
- troca manual de subaba no mesmo processo não é desfeita a cada poll.

## 18. Packaging e distribuição

Como haverá alteração de runtime:

1. implementar e revisar;
2. executar todos os gates do projeto;
3. congelar novo commit de produto;
4. gerar novo package-manifest/provenance;
5. construir ZIP limpo sem acervo;
6. verificar `-ExpectedBuildId`;
7. smoke do runtime e health build id;
8. reiniciar AR-1 real em 0/20.

O pacote continua sem acervo/processos pré-carregados quando destinado a instalação limpa.

## 19. Critérios de aceitação

A feature está pronta para entrar em qualification quando:

- abrir manualmente um formulário identificado no portal faz a Mesa localizar automaticamente o processo;
- a Mesa exibe a aba “Portal atual” com dados, campos, pendências e evidências do processo;
- o acompanhamento funciona com sidepanel fechado;
- selecionar manualmente outro processo pausa o acompanhamento;
- Retomar acompanhamento volta ao último formulário observado válido;
- processos não-PRONTO podem executar manual fill best-effort;
- campos ausentes ou com erro não impedem campos independentes;
- valores não vazios divergentes continuam preservados;
- identidade insegura continua fail-closed;
- nenhum clique final é automatizado;
- todos os testes focados e gates globais passam;
- novo build/ZIP com provenance é gerado antes de qualquer nova sequência AR-1 real.

## 20. Decisões congeladas

1. **Modo de acompanhamento:** automático por padrão, com pausa manual e Retomar acompanhamento.
2. **Direção:** Portal → Mesa somente.
3. **Fonte de verdade:** banco atual da Mesa; “Portal atual” é estado transitório.
4. **Resolução:** identidade exata; nunca fuzzy matching para selecionar processo.
5. **Status:** não é gate do manual best-effort.
6. **Campo divergente já preenchido:** preservar; não sobrescrever silenciosamente.
7. **Pendência de campo:** não bloqueia campos independentes.
8. **Identidade/formulário inseguros:** bloqueiam toda escrita.
9. **Viewer/evidências:** reutilizar componentes e APIs atuais.
10. **Finalização do ato:** sempre manual.
11. **Reliability Reset:** implementação invalida o AR1_BUILD anterior para nova qualification.
12. **AR-2/AR-3/Próximo processo:** permanecem fora deste escopo.
