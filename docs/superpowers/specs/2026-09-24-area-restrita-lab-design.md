# Design — Laboratório de Engenharia Reversa da Área Restrita do Atos-TCE

**Data:** 2026-09-24  
**Repositório alvo:** `matheussilva421/Atos-TCE`  
**Status:** arquitetura aprovada em conversa  
**Relação com o design principal:** extensão aditiva a `docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md`

## 1. Objetivo

Criar uma infraestrutura exclusivamente de desenvolvimento para observar, compreender e testar a Área Restrita do TCE/RN como um portal legado orientado a estados, frames e JavaScript, sem introduzir qualquer dependência de IA, MCP, Playwright CLI ou agente no runtime distribuído do Atos-TCE.

O laboratório deve permitir que um agente de desenvolvimento:

1. conecte-se a um Chrome dedicado já autenticado;
2. enumere páginas, frames, URLs, controles e eventos relevantes;
3. observe rede, console e navegações;
4. execute transições deliberadas e limitadas;
5. compare o estado antes/depois;
6. gere contratos e fixtures sanitizados;
7. transforme observações reais em testes automatizados;
8. altere o runtime somente quando a evidência demonstrar uma divergência.

O produto final continua sendo:

```text
START.cmd
  -> Mesa Local
  -> backend local
  -> extensão MV3
  -> Área Restrita / e-Contas
```

Sem Codex, ChatGPT, MCP, LLM ou Playwright CLI em execução.

## 2. Problema técnico

A Área Restrita é um portal legado com comportamento já observado no projeto:

- Classic ASP;
- frames aninhados e frames irmãos;
- `ProcessonoSetor.asp`;
- `ComplementarAto.asp`;
- `botoesNOVO.asp`;
- JavaScript inline;
- `addtabsinformacao`;
- `NumeroPagina.value=...`;
- controles e formulários que surgem após transições;
- substituição de frames durante navegação;
- delays e estados transitórios;
- necessidade de `webNavigation.getAllFrames()`;
- falhas como `SCREEN_NOT_NAVIGABLE` que hoje agregam causas distintas.

O problema deve ser tratado como engenharia reversa de um protocolo de UI, não como automação visual oportunista.

## 3. Princípios obrigatórios

### 3.1 Desenvolvimento e runtime são mundos separados

Ferramentas permitidas apenas no desenvolvimento:

- Codex;
- Superpowers;
- Chrome DevTools MCP;
- Playwright CLI;
- Skills do agente;
- traces;
- HAR;
- capturas estruturais;
- scripts de investigação.

Runtime suportado:

- `app/`;
- `extension/`;
- `runtime/`;
- `START.cmd`;
- arquivos explicitamente permitidos pelo packaging.

O ZIP padrão nunca contém o laboratório.

### 3.2 Chrome dedicado

A depuração remota deve usar um perfil exclusivo do Atos-TCE.

O operador não deve utilizar, no mesmo perfil, Gmail, bancos, redes sociais ou outras sessões pessoais.

A porta CDP deve ficar apenas em loopback.

### 3.3 Fail-closed

Nenhuma ferramenta de investigação pode, por padrão:

- concluir ato;
- enviar formulário;
- assinar;
- tramitar;
- alterar marcador;
- alterar cadastro;
- executar ações fora do allowlist de observação.

As ações são divididas em níveis:

- **L0 — OBSERVE:** DOM, frames, rede, console, screenshot estrutural.
- **L1 — READ_NAV:** paginação e abertura de telas sem escrita de campos.
- **L2 — PREPARE:** selecionar interessado e preencher campos em sessão supervisionada, sem conclusão.
- **L3 — FINALIZE:** proibido pelo laboratório e pelo protocolo de desenvolvimento.

### 3.4 Um único dono do conhecimento do portal

`extension/lib/area-snapshot.js` continua sendo o dono versionado dos seletores e assinaturas do portal usados em runtime.

O laboratório pode descobrir conhecimento novo, mas não cria um segundo conjunto de seletores operacionais.

O fluxo correto é:

```text
observação real
  -> portal-contract
  -> fixture sanitizada
  -> teste RED
  -> atualização de area-snapshot/navigate/router
  -> teste GREEN
```

### 3.5 Evidência antes de timeout

Mudanças no runtime devem preferir sinais estruturais:

- URL/rota do frame;
- presença/ausência de sentinelas;
- identidade processo/interessado;
- estado de carregamento;
- mudança de frame tree;
- evento de navegação;
- estabilidade de snapshot.

Timeouts continuam existindo apenas como limite superior.

## 4. Arquitetura

```text
                         DESENVOLVIMENTO

Codex / agente
    |
    +-- Skill area-restrita
    |
    +-- Chrome DevTools MCP --------------------+
    |                                           |
    +-- Playwright CLI -------------------------+--> Chrome Atos-TCE
    |                                                  |
    +-- scripts/portal-lab/                            +--> Área Restrita autenticada
              |
              +--> captura estrutural privada
              +--> contrato sanitizado
              +--> fixture sanitizada
              +--> comparação before/after
              +--> testes

                         RUNTIME

Mesa -> extensão MV3 -> Área Restrita
          |
          +--> area-snapshot.js
          +--> navigate.js
          +--> detect-form.js
          +--> fill-form.js
          +--> router.js
```

## 5. Estrutura proposta

```text
devtools/
└── area-restrita/
    ├── README.md
    ├── chrome-devtools-mcp.example.json
    ├── portal-contract.schema.json
    ├── portal-contract.json
    └── fixtures/
        ├── list-page.json
        ├── interested.json
        ├── form.json
        └── buttons.json

.agents/
└── skills/
    └── area-restrita/
        ├── SKILL.md
        └── references/
            ├── safety.md
            ├── workflow.md
            └── portal-states.md

scripts/
└── portal-lab/
    ├── Start-AtosChrome.ps1
    ├── Test-CdpEndpoint.ps1
    ├── capture-structure.js
    ├── sanitize-capture.py
    └── compare-captures.py

tmp/
└── portal-lab/
    └── <sessao>/
        ├── raw/
        └── sanitized/
```

`tmp/portal-lab/raw` nunca é versionado nem empacotado.

## 6. Modelo de estados

Estados normais:

```text
LIST
  |
  +-- OPEN_ACT --> INTERESTED
                     |
                     +-- SELECT_INTERESTED --> FORM
                                               |
                                               +-- FILL --> FORM_FILLED
```

Estado auxiliar:

```text
BUTTONS
```

Estados transitórios/indeterminados:

```text
TRANSITIONING
UNKNOWN
AMBIGUOUS
```

Assinaturas mínimas conhecidas:

### LIST

- rota compatível com `ProcessonoSetor.asp` ou equivalente suportado;
- rows reconhecíveis;
- marcador detectável;
- paginação detectável.

### INTERESTED

- rota compatível com `ComplementarAto.asp`;
- `input[name=escolha]` presente;
- formulário completo ainda ausente.

### FORM

- `ComplementarAto.asp`;
- sentinelas de processo;
- `txtModalidade`;
- `txtFundamentoLegal`;
- `txtDataDOE`;
- `txtCargo`;
- `txtMatricula`;
- `txtDataNascimento`;
- identidade confirmada.

### BUTTONS

- rota `botoesNovo.asp`;
- contexto correspondente à tela ativa.

## 7. Portal Contract

O arquivo versionado `portal-contract.json` contém apenas estrutura não sensível:

- versão do contrato;
- rotas conhecidas;
- estados;
- sentinelas;
- relações de frames;
- eventos/transições;
- controles conhecidos;
- invariantes;
- observações de charset/paginação.

Nunca contém:

- CPF;
- nome real de interessado;
- processo real;
- cookie;
- token;
- cabeçalho de autenticação;
- URL temporária de documento;
- valor real preenchido.

## 8. Segurança e privacidade

Chrome DevTools MCP deve ser configurado com:

- `--browser-url=http://127.0.0.1:9222`;
- `--no-usage-statistics`;
- `--no-performance-crux`.

A porta de debugging não deve ser exposta em `0.0.0.0`.

O laboratório não faz upload automático de HAR, trace ou capturas.

Artefatos raw ficam sob `tmp/portal-lab/`.

A sanitização deve ocorrer antes de qualquer fixture ser movida para uma pasta versionada.

## 9. Portabilidade obrigatória

O pacote distribuído deve continuar funcionando em outro computador que tenha apenas os requisitos normais do Atos-TCE.

Não são requisitos de runtime:

- Node.js;
- npm;
- `chrome-devtools-mcp`;
- `playwright-cli`;
- `.agents/skills`;
- Codex;
- ChatGPT;
- chave/API de LLM.

O packaging deve reprovar a inclusão acidental desses itens.

## 10. Critérios de sucesso

O trabalho está concluído quando:

1. o agente consegue conectar ao Chrome Atos-TCE e inspecionar a Área Restrita;
2. existe mapa versionado de estados/frames/transições;
3. fixtures sanitizadas representam os estados principais;
4. divergências reais produzem teste RED antes da correção;
5. `SCREEN_NOT_NAVIGABLE` deixa de esconder causas estruturalmente distinguíveis quando houver evidência para diferenciá-las;
6. a navegação usa evidência estrutural como sinal principal;
7. nenhuma ação final é automatizada;
8. `packaging/verify-package.ps1` prova que o laboratório não entra no ZIP;
9. uma extração limpa do ZIP roda sem Node, MCP, Playwright ou IA;
10. a automação pode ser usada normalmente em outro PC sem qualquer agente.