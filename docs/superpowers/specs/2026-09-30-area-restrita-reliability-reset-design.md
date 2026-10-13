# Atos-TCE — Design: Area Restrita Reliability Reset

**Data:** 2026-09-30  
**Repositório:** `matheussilva421/Atos-TCE`  
**Branch de design:** `codex/area-restrita-reliability-reset-spec`  
**Base observada:** `codex/atos-tce-unified@397553fe466af32a9478c3c7fbb8d3945eb4a0b8`  
**Escopo:** confiabilidade operacional da complementação de atos na Área Restrita.  
**Fora de escopo:** e-Contas/download, acervo, análise documental, automação do clique final **Complementar Ato**.

## 1. Problema

O Atos-TCE funciona de forma útil até a fronteira da Área Restrita, mas a automação responsável por abrir atos, acompanhar frames, selecionar interessado, confirmar formulário e preencher não apresenta confiabilidade operacional consistente no uso normal.

O repositório possui ampla cobertura offline, múltiplas correções de navegação e evidência live pontual de sucesso. Mesmo assim, o histórico real inclui resultados como:

- `FORM_NOT_AVAILABLE`;
- `SCREEN_NOT_NAVIGABLE`;
- `accepted_unconfirmed`;
- frame de trabalho vazio;
- sessão expirada durante a navegação;
- marcador divergente do snapshot;
- formulários antigos ainda montados em frames ocultos;
- `Acesso negado` em `pessoas-associadas`;
- necessidade de reload ou reconciliação manual;
- diferenças entre Chrome QA, Chrome normal e extensão empacotada.

Também existe evidência real de que o filler isolado consegue funcionar: em validações supervisionadas, `FILL_FORM` alterou e releu campos corretamente. Isso indica que o principal risco não é apenas a escrita de campos, e sim a cadeia completa de navegação e sincronização do portal.

Portanto, este design redefine a automação da Área Restrita como **UNQUALIFIED** até que suas capacidades sejam provadas de forma repetível.

## 2. Objetivo

Transformar a complementação assistida da Área Restrita em um fluxo operacional repetível, qualificando cada capacidade separadamente antes de compô-las.

O objetivo final é:

```text
operador inicia o Atos-TCE
        |
        v
Mesa Local
        |
        v
Área Restrita autenticada
        |
        v
navegação determinística
        |
        v
formulário correto confirmado
        |
        v
preenchimento + releitura
        |
        v
revisão humana
        |
        v
Complementar Ato manual
```

O sucesso não será definido por unit tests, mocks, fixtures ou uma execução live isolada. Uma capacidade só será considerada confiável depois de passar uma matriz real consecutiva no fluxo normal do operador.

## 3. Decisão arquitetural

Adotar estratégia **híbrida progressiva**.

Não substituir imediatamente a extensão MV3 e não continuar adicionando heurísticas indefinidamente à arquitetura atual.

A implementação seguirá duas linhas:

1. qualificar primeiro o menor fluxo útil, com o formulário aberto manualmente;
2. construir um `Portal Controller` experimental para comparar objetivamente a navegação controlada por processo local com a navegação atual da extensão.

A arquitetura vencedora será escolhida por evidência real, não por preferência prévia.

### 3.1. Arquitetura atual

```text
Mesa
  -> backend
  -> fila de comandos
  -> MV3 service worker
  -> webNavigation
  -> tabs/frames
  -> content scripts
  -> DOM legado
```

Essa arquitetura permanece suportada durante a investigação.

### 3.2. Arquitetura experimental

```text
Mesa
  -> Portal Controller local
  -> Playwright/CDP
  -> Chrome autenticado
  -> Área Restrita
```

A extensão pode permanecer como:

- UI/side panel;
- bridge de status;
- fallback;
- superfície manual de preenchimento;

mas não será presumida como controladora definitiva da navegação.

### 3.3. Portabilidade

O projeto continua devendo funcionar sem IA.

É aceitável reavaliar a antiga restrição “Playwright nunca pode fazer parte do runtime” se a evidência demonstrar que um controller local empacotável é substancialmente mais confiável.

Mesmo nesse cenário, o produto final continua sem depender de:

- ChatGPT;
- Codex;
- MCP;
- LLM;
- API externa de IA.

## 4. Reset de confiança

Todas as capacidades da Área Restrita passam a usar os estados:

```text
EXPERIMENTAL
QUALIFIED
PRODUCTION
UNQUALIFIED
```

Definições:

- **EXPERIMENTAL:** implementada, mas sem matriz real suficiente.
- **QUALIFIED:** passou o gate real consecutivo da capacidade.
- **PRODUCTION:** QUALIFIED e validada em instalação portátil limpa/Chrome normal.
- **UNQUALIFIED:** falhou em uso real, regressou ou ainda não foi qualificada.

No início deste trabalho:

```yaml
manual_form_fill: UNQUALIFIED
open_act: UNQUALIFIED
select_interested: UNQUALIFIED
return_to_list: UNQUALIFIED
pagination: UNQUALIFIED
next_process: UNQUALIFIED
area_restrita_end_to_end: UNQUALIFIED
```

Testes offline continuam obrigatórios, mas não promovem estado de capacidade.

### 4.1. Promoção de estado

A promoção é sempre explícita:

```text
EXPERIMENTAL
  -> 20/20 real consecutivo na mesma build
  -> QUALIFIED
  -> 20/20 real consecutivo no artefato distribuível/Chrome normal
  -> PRODUCTION
```

Se uma capability PRODUCTION falhar de forma reproduzível no fluxo normal, ela volta para `UNQUALIFIED` até nova investigação e requalificação. Não existe grandfathering por release anterior.

## 5. Fonte de runtime

O plano de implementação deve começar com um gate de source-of-truth antes de alterar código.

Existe histórico de divergência documental entre a árvore raiz (`app/`, `extension/`, `tests/`, `packaging/`) e `work/tce-extractor`. Portanto:

1. identificar qual árvore o `START.cmd` e o builder portátil realmente empacotam no HEAD de execução;
2. identificar onde vivem os testes que validam esse runtime;
3. escolher **uma única árvore de produção** para as mudanças deste Reliability Reset;
4. tratar a outra apenas como verifier/legado, salvo instrução autoritativa posterior;
5. nunca aplicar a mesma correção manualmente nas duas árvores para “mantê-las parecidas”.

Nenhuma Task de runtime começa antes de esse gate estar documentado no handoff.

## 6. Escopo congelado

Enquanto o Reliability Reset estiver ativo, ficam congelados:

- novas features da Área Restrita;
- novas otimizações de “Próximo processo”;
- novas heurísticas de frame;
- correções baseadas apenas em aumento de timeout/retry;
- automação do clique final;
- expansão para submit/send/finalize;
- refactors sem relação direta com confiabilidade.

São permitidos:

- instrumentação;
- reprodução;
- fixtures sanitizadas;
- testes RED;
- root-cause fixes;
- controller experimental;
- qualification;
- packaging necessário para testar a abordagem vencedora.

## 7. Regra de investigação

Toda falha real deve seguir:

```text
reprodução real
  -> evidência sanitizada
  -> fronteira exata que falhou
  -> hipótese única
  -> teste mínimo
  -> fixture/teste RED
  -> correção mínima
  -> GREEN
  -> repetição real
```

Não adicionar uma correção se a causa não estiver identificada.

Depois de três tentativas de correção diferentes para a mesma classe de falha sem resolver a confiabilidade real, parar e reavaliar o desenho daquela fronteira.

## 8. Observabilidade

Cada tentativa real deve produzir um registro sanitizado de transições, sem dados pessoais.

Modelo mínimo:

```json
{
  "run_id": "uuid-ou-sequencial",
  "capability": "manual_form_fill",
  "browser_session_id": "sanitized-id",
  "portal_state_before": "FORM",
  "portal_state_after": "FORM_FILLED",
  "route": "/SISTEMAS/PROCESSO/ComplementarAto.asp",
  "tab_ref": "sanitized",
  "frame_ref": "sanitized",
  "expected_identity_hash": "sha256",
  "observed_identity_hash": "sha256",
  "generation_before": 7,
  "generation_after": 7,
  "result_code": "SUCCEEDED",
  "elapsed_ms": 1530
}
```

Nunca registrar em artefato versionado:

- processo real;
- interessado real;
- CPF;
- matrícula;
- cookies;
- tokens;
- credenciais;
- request/response body privado;
- HTML bruto com dados.

### 8.1. Fronteiras que devem ser distinguíveis

A telemetria deve permitir dizer se a falha ocorreu em:

```text
Mesa
API
command queue
browser session
tab selection
frame discovery
portal state detection
identity confirmation
interested selection
form readiness
fill
reread
return navigation
pagination
```

Códigos genéricos como `SCREEN_NOT_NAVIGABLE` podem continuar existindo apenas quando a estrutura realmente não permitir classificação mais específica.

## 9. Máquina de estados do portal

O Reliability Reset adota o vocabulário:

```text
PORTAL_MENU
LIST
OPENING_ACT
INTERESTED
FORM
FORM_FILLED

LOGIN_REQUIRED
ACCESS_DENIED
TRANSITIONING
AMBIGUOUS
SESSION_EXPIRED
UNKNOWN
```

Nenhuma transição deve depender apenas de tempo.

Exemplo:

```text
LIST
  -> OPENING_ACT
  -> INTERESTED | FORM | ACCESS_DENIED | SESSION_EXPIRED | UNKNOWN
```

O controlador só avança depois de observar um predicado estrutural correspondente ao estado esperado.

Timeout é limite superior da espera, não detector de sucesso.

## 10. Qualification Ladder

A automação deve ser reconstruída como composição de capacidades qualificadas.

### AR-1 — Preenchimento assistido

Fluxo:

```text
operador abre manualmente o ato correto
  -> detectar formulário
  -> confirmar identidade
  -> preencher
  -> reler
  -> operador revisar
```

Não inclui navegação automática.

**Gate de qualificação: 20 execuções reais consecutivas.**

Critérios:

- 20/20 formulário detectado;
- 20/20 identidade exata confirmada;
- 20/20 fill request terminal;
- 20/20 releitura coerente;
- 0 formulário errado;
- 0 reinício de extensão/controller;
- 0 reload técnico;
- 0 DevTools necessário;
- 0 ação final automática.

Após passar em ambiente de desenvolvimento, repetir amostra de produção em instalação portátil limpa antes de promover para PRODUCTION.

### AR-2 — Abrir ato

Pré-condição: lista correta preparada pelo operador.

Fluxo:

```text
LIST
  -> open_act(exact_identity)
  -> INTERESTED ou FORM
```

Gate: **20/20 execuções reais consecutivas**.

Falhas de identidade, frame ambíguo, acesso negado, sessão e timeout contam como falha da sequência e reiniciam o contador de qualificação após correção.

### AR-3 — Selecionar interessado

Fluxo:

```text
INTERESTED
  -> selecionar identidade exata
  -> FORM
```

Gate: **20/20 execuções reais consecutivas**.

Requisitos:

- nunca usar primeira correspondência arbitrária;
- duas correspondências válidas = `AMBIGUOUS`;
- identidade relida no formulário deve ser a mesma solicitada;
- zero clique em interessado diferente.

### AR-4 — Pipeline de complementação

Compor somente AR-1, AR-2 e AR-3 já qualificadas:

```text
LIST
  -> OPEN_ACT
  -> INTERESTED
  -> FORM
  -> FILL
  -> REREAD
```

Gate: **20/20 execuções reais consecutivas**.

Não inclui clique final.

### AR-5 — Retorno e paginação

Subcapacidades:

```text
FORM -> LIST
LIST(page N) -> LIST(page N+1)
```

Validar:

- retorno nativo;
- marcador/contexto preservado ou restaurado de forma comprovada;
- same-page;
- cross-page;
- frame replacement;
- sessão expirada;
- end of page.

As duas capabilities positivas são independentes e cada uma exige **20/20**:

- `return_to_list`: 20/20;
- `next_page`: 20/20.

Casos negativos raros (por exemplo sessão expirando exatamente durante a troca de página) podem permanecer cobertos por testes sintéticos quando não surgirem naturalmente com segurança, mas isso deve ser marcado como `NOT_OBSERVED_REAL` e não pode ser apresentado como evidência live.

### AR-6 — Próximo processo

Somente depois de AR-2 a AR-5 QUALIFIED.

Gate: **20/20 execuções reais consecutivas** do fluxo composto na mesma build. Para promover a PRODUCTION, repetir **20/20** no artefato distribuível em Chrome normal. A amostra deve conter navegação same-page e cross-page; se cross-page não puder ser observado com segurança, a capability cross-page permanece não qualificada e não deve ser exposta como suportada.

`Próximo processo` não terá lógica própria de navegação além de compor capacidades qualificadas:

```text
resolve exact target
  -> return_to_list
  -> locate exact identity
  -> paginate if required
  -> open_act
  -> select_interested if required
  -> confirm FORM
```

O clique não preenche automaticamente.

## 11. Benchmark MV3 × Portal Controller

AR-2 e AR-3 serão executadas pelas duas abordagens quando tecnicamente possível:

- extensão MV3 atual;
- Portal Controller experimental.

Métricas mínimas:

| Métrica | MV3 | Controller |
|---|---:|---:|
| tentativas | 20 | 20 |
| sucesso |  |  |
| falhas |  |  |
| mediana de tempo |  |  |
| p95 de tempo |  |  |
| frame perdido |  |  |
| sessão perdida |  |  |
| reload técnico |  |  |
| ambiguidade |  |  |
| intervenção técnica |  |  |

### 11.1. Critério de decisão

A abordagem de produção será escolhida após AR-3.

Preferir a solução que:

1. cumpra 20/20;
2. tenha menor número de estados não classificados;
3. precise de menos recuperação especial;
4. funcione em Chrome normal;
5. seja empacotável e reprodutível em outro PC;
6. mantenha identidade fail-closed.

Se ambas passarem, preferir a de menor complexidade operacional.

## 12. Portal Controller experimental

Estrutura sugerida:

```text
app/area_restrita/controller/
├── __init__.py
├── session.py
├── states.py
├── browser.py
├── navigation.py
├── form.py
└── telemetry.py
```

Responsabilidades:

### `session.py`

- ciclo de vida da conexão com Chrome;
- detectar sessão ausente/expirada;
- nunca manipular credenciais.

### `states.py`

- classificar estados estruturais;
- sem ações.

### `browser.py`

- tabs, frames e conexão;
- abstrair Playwright/CDP.

### `navigation.py`

- `open_act(identity)`;
- `select_interested(identity)`;
- `return_to_list()`;
- `next_page()`.

### `form.py`

- `read_form(identity)`;
- `fill_form(plan)`;
- usar a mesma política de identidade e best-effort já existente;
- não duplicar motor jurídico.

### `telemetry.py`

- emitir somente eventos sanitizados de reliability.

Essa estrutura é proposta de design; o plano deverá reconciliá-la com o código real antes de criar arquivos.

## 13. Ownership e reutilização

Não duplicar lógica de negócio.

Continuam como fontes existentes:

- backend/Mesa escolhe processo e próximo alvo;
- `legal-foundation-v4` escolhe fundamento;
- preflight decide o plano de campos;
- identidade canônica continua fail-closed;
- o filler best-effort existente continua sendo referência de semântica;
- `area-snapshot.js` continua referência estrutural enquanto a extensão estiver ativa.

Se o Portal Controller precisar reproduzir um predicado estrutural já documentado, o plano deve escolher uma fonte canônica ou gerar contrato compartilhado; não manter dois mapas manuais divergentes de seletores.

## 14. Segurança

Invariantes:

1. identidade incompatível nunca escreve;
2. formulário ambíguo nunca escreve;
3. interessado ambíguo nunca é selecionado;
4. session expiry não é tratado como página válida;
5. `ACCESS_DENIED` nunca recebe retry cego;
6. generation stale nunca é ignorada;
7. valor de select fora do catálogo atual nunca é escrito;
8. nenhuma capability pode clicar **Complementar Ato**;
9. nenhuma capability pode assinar, tramitar ou enviar;
10. automação nunca manipula credenciais do operador.

## 15. Testes offline

Cada root-cause fix exige RED antes da implementação.

Manter e ampliar:

- Python unit/integration;
- extensão Node;
- web;
- portal-contract/fixtures;
- packaging;
- clean smoke.

Mas relatórios devem separar:

```text
OFFLINE GREEN
REAL QUALIFICATION
PRODUCTION QUALIFICATION
```

É proibido concluir “Área Restrita funciona” apenas porque OFFLINE GREEN.

## 16. Testes reais

### 16.1. Regras

- um comando de portal por vez;
- operador presente;
- clique final manual;
- nenhuma fabricação de estado real inseguro;
- não alterar banco para produzir ambiguidade/stale;
- registrar apenas evidência sanitizada.

### 16.2. Sequência consecutiva

Uma sequência de 20 é válida somente se:

- mesma build;
- nenhuma alteração de código durante a sequência;
- nenhuma intervenção técnica;
- nenhum DevTools para corrigir estado;
- nenhum reinício corretivo;
- failures contam e encerram a sequência.

Depois de uma correção, o contador volta a zero.

## 17. Qualificação em outro PC

Uma capability QUALIFIED só vira PRODUCTION depois de teste no artefato distribuível.

O ambiente deve representar uso normal:

- extração limpa;
- `START.cmd`;
- dados configurados pelo fluxo suportado;
- Chrome normal;
- extensão/controller do pacote;
- sem Codex;
- sem DevTools MCP;
- sem scripts de laboratório;
- sem edição manual de banco.

AR-1 é o primeiro gate obrigatório nesse ambiente.

Para qualquer capability exposta como PRODUCTION, o gate portátil é novamente **20/20 consecutivo**, sem DevTools, Codex, MCP, scripts de laboratório, reinício corretivo ou reload técnico.

## 18. Packaging

Se MV3 vencer o benchmark, preservar o modelo atual.

Se o Portal Controller vencer, o plano deve definir runtime pinado e verificável.

O pacote nunca pode depender de instalação global de Playwright/Node feita pelo operador.

Se Playwright/Chromium fizer parte da produção:

- runtime deve ser empacotado ou bootstrapado de forma determinística;
- versão deve ser pinada;
- verificador deve testar presença/hash/compatibilidade;
- smoke deve provar inicialização em extração limpa;
- o usuário não instala ferramentas de desenvolvimento.

## 19. UX

Durante Reliability Reset, a UI deve comunicar capability real.

Exemplos:

```text
Preencher formulário atual       QUALIFIED
Abrir ato automaticamente        EXPERIMENTAL
Próximo processo                 INDISPONÍVEL
```

Não oferecer como ação normal uma capability UNQUALIFIED.

O sistema deve preferir fallback manual funcional a automação aparentemente disponível que falha de forma imprevisível.

## 20. Critério global de conclusão

O Reliability Reset termina quando:

```text
[ ] AR-1 PRODUCTION
[ ] AR-2 QUALIFIED ou substituída por abordagem vencedora
[ ] AR-3 QUALIFIED ou substituída por abordagem vencedora
[ ] benchmark MV3 x Controller concluído
[ ] arquitetura de navegação decidida por evidência
[ ] AR-4 QUALIFIED
[ ] AR-5 QUALIFIED dentro da cobertura real disponível
[ ] AR-6 QUALIFIED
[ ] clean portable qualification concluída
[ ] nenhuma ação final automatizada
[ ] offline gates verdes
[ ] reliability report final documentado
```

Se AR-2/AR-3 mostrarem que a arquitetura MV3 não atinge a confiabilidade necessária e o controller também não atingir, o projeto deve parar antes de AR-4 e revisar a estratégia do portal; não mascarar a falha com mais heurísticas.

## 21. Resultado esperado

Ao final, o projeto terá uma afirmação verificável:

> A automação da Área Restrita não é considerada funcional por existir ou por passar em mocks. Cada capacidade exposta ao operador foi qualificada em execuções reais consecutivas, e o fluxo distribuído foi validado em ambiente portátil normal.

Esse é o novo critério de verdade da complementação de atos.
