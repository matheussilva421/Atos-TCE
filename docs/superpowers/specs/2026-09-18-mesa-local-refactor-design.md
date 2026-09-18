# Design — Refatoração arquitetural do Atos-TCE com Mesa Local central

**Data:** 2026-09-18  
**Repositório:** `matheussilva421/Atos-TCE`  
**Status:** design aprovado em conversa; implementação ainda não iniciada

## 1. Objetivo

Simplificar o projeto Atos-TCE sem perder as automações que já entregam valor operacional.

O fluxo obrigatório a preservar é:

1. analisar a Área Restrita do TCE/RN e identificar atos que precisam ser complementados;
2. relacionar esses atos aos processos correspondentes;
3. coletar e baixar automaticamente os documentos no e-Contas;
4. extrair, classificar e validar os dados necessários à complementação;
5. permitir conferência de dados, documentos e evidências em uma Mesa Local;
6. preencher os atos na Área Restrita por meio da extensão;
7. manter a confirmação/envio final sob revisão humana no fluxo normal.

O problema principal do sistema atual não é excesso de funcionalidade, mas excesso de centros de controle: menu PowerShell, serviço local, HTML gerado, sidepanel, controlador de automação, snapshots, lotes, jobs, manifests e empacotadores mantêm partes sobrepostas do mesmo workflow.

A refatoração deve reduzir essa fragmentação sem reescrever, de uma vez, os componentes que já provaram funcionar em portal real.

## 2. Decisões aprovadas

### 2.1 Produto central

A **Mesa Local** será a interface e o coordenador principal do sistema.

A extensão Chrome/Edge deixa de ser uma segunda aplicação completa e passa a ser um adaptador entre a Mesa e a Área Restrita.

### 2.2 Área Restrita

O caminho principal para leitura e interação com a Área Restrita continua sendo a extensão instalada no navegador autenticado do operador.

CDP/Playwright permanece como fallback técnico para:

- diagnóstico;
- compatibilidade;
- observação;
- investigação de mudanças do portal.

CDP/Playwright não é o controlador primário do fluxo diário.

### 2.3 Preenchimento

A Mesa terá a ação principal **Preencher ato**, que solicita à extensão localizar o ato, abrir o formulário, selecionar o interessado, preencher os campos e reler o DOM para confirmar os valores.

Também existirá fallback manual:

- o operador abre o ato manualmente;
- a extensão detecta o formulário;
- o operador usa **Preencher formulário atual**.

Os dois caminhos usam a mesma implementação de preenchimento.

### 2.4 Envio final

No fluxo normal, o sistema:

- prepara;
- preenche;
- relê;
- confirma visualmente o estado do formulário.

O clique final de conclusão permanece sob responsabilidade do operador.

A infraestrutura de autoenvio existente não faz parte do produto principal da nova arquitetura. O histórico permanece recuperável via Git, mas `AUTO_SUBMIT`, qualificação para envio real e estados de envio automático deixam o caminho ativo da aplicação.

### 2.5 Portabilidade

O projeto continua entregando um ZIP portátil para Windows.

O ZIP, porém, será **artefato de distribuição**, não estrutura de desenvolvimento.

Código-fonte e pacote distribuído deixam de compartilhar a mesma organização interna.

### 2.6 Persistência e acervo

Metadados, estados, histórico e workflow serão centralizados em SQLite.

PDFs continuam como arquivos no filesystem.

O acervo será híbrido:

- **HOT/ACTIVE**: PDFs disponíveis localmente para uso frequente;
- **ARCHIVED**: metadados permanecem no SQLite, mas PDFs podem estar em outro local;
- **MISSING**: metadados existem, mas o documento não está acessível.

Os aproximadamente 700 processos atuais serão tratados como **acervo inicial a preservar**. A migração poderá deduplicar cópias físicas redundantes, mas não deve descartar processos lógicos por aparecerem em builds, versões ou snapshots antigos.

## 3. Princípios arquiteturais

Duas regras são obrigatórias:

1. **A Mesa é a única dona do workflow e do estado persistente.**
2. **A extensão nunca decide o que fazer com um processo; ela apenas observa o portal ou executa uma instrução específica.**

Regras complementares:

- build não contém dados operacionais por padrão;
- atualização do aplicativo não duplica o acervo;
- uma função de negócio deve ter um único dono;
- arquivos de runtime não devem servir simultaneamente como código-fonte;
- complexidade técnica pode existir internamente, mas não deve aparecer no fluxo do operador;
- funcionalidades antigas só são removidas após equivalência comprovada.

## 4. Arquitetura alvo

```text
Atos-TCE
│
├── Mesa Local
│   ├── workflow
│   ├── processos
│   ├── downloads
│   ├── análise
│   ├── documentos/PDF
│   ├── evidências
│   ├── histórico
│   └── armazenamento
│
├── e-Contas
│   ├── localizar processo
│   ├── enumerar documentos
│   └── baixar PDFs
│
├── Extensão
│   ├── analisar Área Restrita
│   ├── navegar
│   ├── detectar formulário
│   └── preencher formulário
│
└── Packaging
    └── gerar ZIP portátil
```

A Mesa coordena o fluxo. e-Contas e extensão são adaptadores externos.

## 5. Estrutura de repositório alvo

```text
Atos-TCE/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── server.py
│   │   ├── health.py
│   │   ├── processes.py
│   │   ├── area_restrita.py
│   │   ├── acquisition.py
│   │   └── documents.py
│   │
│   ├── core/
│   │   ├── models.py
│   │   ├── workflow.py
│   │   ├── store.py
│   │   ├── jobs.py
│   │   └── reconciliation.py
│   │
│   ├── econtas/
│   │   ├── collector.py
│   │   ├── browser.py
│   │   └── downloader.py
│   │
│   ├── analysis/
│   │   ├── pipeline.py
│   │   ├── documents.py
│   │   ├── extraction.py
│   │   ├── legal.py
│   │   ├── evidence.py
│   │   └── validation.py
│   │
│   ├── archive/
│   │   └── manager.py
│   │
│   └── web/
│       ├── index.html
│       ├── app.js
│       ├── pdf-viewer.js
│       └── app.css
│
├── extension/
│   ├── manifest.json
│   ├── background/
│   │   └── router.js
│   ├── content/
│   │   ├── scan-area.js
│   │   ├── navigate.js
│   │   ├── detect-form.js
│   │   └── fill-form.js
│   ├── lib/
│   │   ├── api.js
│   │   ├── protocol.js
│   │   └── portal-matcher.js
│   └── sidepanel/
│
├── tests/
│   ├── core/
│   ├── econtas/
│   ├── analysis/
│   ├── extension/
│   └── integration/
│
├── packaging/
│   ├── build-portable.ps1
│   ├── verify-package.ps1
│   ├── runtime-manifest.json
│   └── licenses/
│
├── scripts/
│   ├── diagnose.ps1
│   └── migrate-legacy.py
│
├── docs/
├── START.cmd
└── README.md
```

Dados locais ficam fora da árvore versionada:

```text
data/
├── atos-tce.db
├── archive/
├── backups/
└── logs/
```

## 6. Responsabilidades por componente

### 6.1 `app/core`

É o domínio da aplicação.

Responsável por:

- processo;
- interessado;
- status;
- jobs;
- workflow;
- histórico;
- contratos de dados;
- reconciliação entre Área Restrita, acervo e e-Contas.

Não sabe clicar no navegador.

### 6.2 `app/econtas`

Responsável exclusivamente por aquisição.

Entrada:

- processo/chave canônica;
- escopo;
- contexto de coleta.

Saída:

- documentos encontrados;
- PDFs baixados;
- resultado da aquisição;
- falhas por item.

A lógica já comprovada em `Coletar-Processos-TCE.ps1`, `TcePortal.Driver.js` e módulos associados deve ser migrada gradualmente, não reescrita de uma vez.

### 6.3 `app/analysis`

Recebe documentos e produz:

- texto nativo;
- OCR quando necessário;
- classificação documental;
- campos propostos;
- validações;
- evidências;
- citações/fontes;
- estado `READY` ou `REVIEW`.

Regras jurídicas e de validação pertencem aqui, não à extensão.

### 6.4 `app/api`

Expõe a Mesa e endpoints locais.

A API orquestra chamadas, mas não contém regras de negócio.

O atual `local_service.py` será progressivamente desmembrado.

### 6.5 Extensão

A extensão terá responsabilidade estreita:

- observar a Área Restrita;
- navegar;
- detectar telas e formulários;
- mapear controles reais do DOM;
- preencher campos autorizados;
- reler os valores preenchidos;
- devolver resultado à Mesa.

Não será responsável por:

- OCR;
- lotes;
- aquisição;
- histórico global;
- acervo;
- regra jurídica;
- decisão de workflow;
- estado persistente;
- autoenvio.

### 6.6 Sidepanel

O sidepanel será reduzido para suporte operacional:

```text
ATOS TCE

● Mesa conectada
● Área Restrita detectada

Processo atual:
102390/2026

[Preencher formulário atual]
[Abrir Mesa]

Diagnóstico
```

Ele não será dashboard principal.

### 6.7 Packaging

`packaging/` é completamente isolado do runtime normal.

Responsável por:

- runtime Python;
- Tesseract;
- dependências;
- hashes;
- licenças;
- staging;
- geração do ZIP;
- smoke offline.

## 7. Workflow operacional

Estados normais:

```text
PENDENTE
  ↓
IDENTIFICADO
  ↓
BAIXANDO
  ↓
BAIXADO
  ↓
ANALISANDO
  ↓
REVISAR ou PRONTO
  ↓
PREENCHIDO
  ↓
CONCLUÍDO
```

Estados excepcionais:

- `ERRO`
- `BLOQUEADO`
- `DIVERGENCIA`

Lotes, filas, checkpoints e jobs podem continuar existindo como detalhes internos, mas não são conceitos que o operador precisa manipular.

## 8. Fluxo diário da Mesa

### 8.1 Inicialização

`START.cmd`:

1. verifica runtime;
2. inicia o backend;
3. verifica a extensão;
4. abre a Mesa.

A interface mostra:

- Área Restrita conectada ou aguardando login;
- e-Contas disponível ou aguardando login;
- extensão conectada;
- acervo disponível.

### 8.2 Analisar Área Restrita

A Mesa solicita à extensão:

- origem/escopo;
- marcador;
- processos;
- interessados;
- ação observada;
- necessidade de complementação.

A extensão percorre as páginas da Área Restrita autenticada.

Se falhar, a Mesa pode acionar modo de compatibilidade via CDP/Playwright.

### 8.3 Reconciliação

A Mesa cruza:

- pendências da Área Restrita;
- acervo local;
- histórico;
- dados do e-Contas.

Exemplo de apresentação:

```text
290 pendentes
183 já no acervo
92 precisam ser baixados
11 precisam ser reanalisados
4 apresentam divergência
```

### 8.4 Aquisição

O operador usa uma ação simples:

**Baixar processos pendentes**

A Mesa calcula quais processos realmente faltam.

Os lotes permanecem internos.

### 8.5 Análise incremental

Assim que um processo termina de baixar, sua análise começa.

Não é necessário esperar o lote completo.

### 8.6 Revisão

A tela do processo reúne:

- dados extraídos;
- campos faltantes;
- documentos;
- PDF viewer;
- evidências por campo;
- histórico.

Cada campo deve permitir acesso à fonte que sustenta o valor.

### 8.7 Preenchimento

A Mesa envia um único processo e seus campos à extensão.

A extensão:

1. localiza o processo;
2. abre Complementar Ato;
3. seleciona o interessado;
4. mapeia os controles;
5. preenche;
6. relê;
7. devolve resultado.

Se a navegação automática falhar, o operador abre manualmente e usa o mesmo preenchimento no formulário atual.

## 9. Persistência SQLite

Tabelas iniciais mínimas:

### `processes`

- id
- process_key
- interested
- interested_normalized
- source_scope
- marker
- status
- created_at
- updated_at

### `documents`

- id
- process_id
- event
- title
- relative_path
- sha256
- page_count
- classification
- storage_state

### `fields`

- id
- process_id
- field_name
- value
- status
- confidence
- document_id
- page
- evidence

### `workflow_events`

- id
- process_id
- event_type
- payload
- created_at

### `jobs`

- id
- job_type
- status
- total
- completed
- failed
- started_at
- finished_at

SQLite substitui progressivamente a multiplicidade de snapshots, filas persistidas, relatórios de estado e JSONs usados para controlar workflow.

JSON continua permitido quando for formato de integração/fixture, não como banco operacional principal.

## 10. Política de armazenamento

### 10.1 Separação obrigatória

```text
CÓDIGO
├── app/
├── extension/
└── packaging/

DADOS
└── data/
    ├── atos-tce.db
    └── archive/

DISTRIBUIÇÃO
└── dist/
    └── Atos-TCE-portable.zip
```

### 10.2 Um único acervo operacional

O mesmo conjunto de PDFs não deve ser copiado para cada versão do programa.

Atualizar a aplicação não toca em `data/`.

### 10.3 ZIP portátil padrão

O ZIP padrão contém:

- aplicação;
- extensão;
- runtime;
- launchers;
- assets.

Não contém o acervo de processos.

### 10.4 Backup completo

Quando necessário, uma função explícita gera um backup completo contendo:

- SQLite;
- PDFs;
- metadados necessários para restauração.

Esse artefato é **backup**, não release.

### 10.5 Retenção de builds

Em `dist/`, manter apenas:

- build atual;
- build anterior.

Versões históricas do código ficam no Git.

### 10.6 `Versions/`

A pasta `Versions/` deixa de ser armazenamento permanente.

Testes de ZIP extraem para diretório temporário, executam os gates e removem a extração após sucesso.

Em falha, a extração pode ser preservada temporariamente para diagnóstico.

### 10.7 Staging

Staging é efêmero.

Fluxo:

```text
build → staging → validação → ZIP → apagar staging
```

Evidências de build devem ser metadados pequenos, não cópias completas do pacote.

### 10.8 Acervo inicial atual

Os cerca de 700 processos presentes no pacote/acervo atual serão migrados para o novo modelo.

A deduplicação deve priorizar:

1. chave canônica do processo/interessado;
2. identificador do documento quando disponível;
3. SHA-256 do PDF;
4. caminho lógico/evento como apoio.

A migração nunca apaga a última cópia conhecida de um documento antes de comprovar que outra cópia equivalente está preservada.

## 11. Componentes atuais: destino

### Ficam e são promovidos

- reconciliação Área Restrita ↔ e-Contas;
- coleta autenticada;
- processamento incremental;
- OCR/texto nativo;
- classificação e extração;
- evidências;
- visualizador PDF;
- navegação real da Área Restrita;
- detecção de formulário;
- preenchimento do DOM;
- testes de comportamento real;
- validações fail-closed relevantes.

### São desmembrados

- `local_service.py` → API + core + serviços;
- `automation-controller.js` → scanner/navegação/preenchimento, com workflow removido;
- `panel.js` → sidepanel mínimo;
- `html_generator.py` → view models/API + frontend da Mesa;
- `messages.js` e `automation-schema.js` → protocolo enxuto.

### Migração gradual

- `Coletar-Processos-TCE.ps1`;
- `TcePortal.Driver.js`;
- módulos de lote/fila/checkpoint.

Esses componentes permanecem atrás de wrappers até equivalência comprovada.

### Saem do caminho ativo

- autoenvio;
- piloto de envio real;
- qualification para auto-submit;
- estados `send_intent`, `send_issued`, `send_confirmed` etc.;
- menus históricos como interface principal;
- launchers duplicados;
- extrações versionadas permanentes;
- relatórios intermediários usados como armazenamento de estado.

## 12. Testes

### 12.1 Área Restrita

Cobrir:

- paginação;
- marcador;
- processo/interessado;
- detecção de Complementar Ato;
- seleção de interessado;
- abertura do formulário;
- preenchimento;
- releitura;
- fallback manual.

### 12.2 e-Contas

Cobrir:

- localizar processo;
- escopo correto;
- download apenas da fila solicitada;
- retomada;
- deduplicação;
- falha isolada;
- contagem e hashes.

### 12.3 Análise

Cobrir:

- classificação;
- texto nativo;
- OCR fallback;
- extração;
- regra jurídica;
- campos obrigatórios;
- divergências;
- evidência.

### 12.4 Core

Cobrir:

- workflow;
- SQLite;
- reconciliação;
- jobs;
- retomada;
- histórico.

### 12.5 Packaging

Smoke principal:

```text
build
↓
extrair ZIP limpo
↓
START.cmd
↓
Mesa responde
↓
runtime OK
↓
extensão válida
↓
SQLite criado
↓
PDF viewer OK
```

Gates autenticados de Área Restrita/e-Contas são executados separadamente e de forma supervisionada.

## 13. Migração em fases

### Fase 0 — Baseline

- criar tag `pre-mesa-refactor`;
- registrar fixtures sanitizadas;
- registrar comportamento mínimo funcional atual.

### Fase 1 — Nova estrutura

Criar a nova árvore do repositório sem reescrever as rotinas críticas.

Wrappers podem chamar implementações antigas.

### Fase 2 — SQLite

Introduzir o banco central e migrador do legado.

### Fase 3 — Nova Mesa somente leitura

Nova UI lê SQLite e acervo real.

A automação antiga continua executando o trabalho.

### Fase 4 — Área Restrita pela Mesa

Mesa passa a iniciar a análise do portal e persistir o snapshot no SQLite.

Sidepanel ainda pode manter fallback temporário.

### Fase 5 — Aquisição comandada pela Mesa

Mesa calcula downloads pendentes e chama o coletor existente.

Depois, lógica de PowerShell é migrada gradualmente.

### Fase 6 — Pipeline de análise centralizado

Download concluído dispara análise automaticamente.

### Fase 7 — Preenchimento comandado pela Mesa

Mesa envia um processo por vez à extensão.

Fluxo automático e fallback manual usam o mesmo filler.

### Fase 8 — Enxugar extensão

Remover workflow global, lotes, aquisição, análise jurídica e histórico da extensão.

### Fase 9 — Acervo híbrido

Implementar HOT/ARCHIVED/MISSING e movimentação de PDFs sem perder metadados.

### Fase 10 — Novo portátil

Packaging constrói o ZIP a partir da árvore de fonte.

Dados ficam fora do pacote.

### Fase 11 — Remover legado

Somente após equivalência, testes e uso real supervisionado.

Criar tag `mesa-migration-complete` antes da remoção final.

## 14. Critério para remover código legado

Um componente antigo só pode ser apagado quando:

1. a função correspondente existir no sistema novo;
2. testes automatizados passarem;
3. uma fixture real produzir resultado equivalente;
4. houver pelo menos uma execução real supervisionada bem-sucedida quando aplicável;
5. não houver mais chamadas ao componente antigo.

## 15. Critérios de sucesso

A refatoração está concluída quando:

- o operador usa `START.cmd` e a Mesa como interface principal;
- a Mesa analisa pendências da Área Restrita;
- a Mesa calcula e inicia os downloads necessários no e-Contas;
- análise começa automaticamente após cada download;
- dados e evidências são revisáveis por processo;
- preenchimento é iniciado pela Mesa;
- fallback manual funciona;
- envio final continua sob revisão humana;
- o sidepanel não é um dashboard paralelo;
- SQLite é a fonte de verdade do workflow;
- os ~700 processos atuais estão preservados no novo acervo;
- updates do aplicativo não duplicam PDFs;
- ZIP padrão não contém o acervo;
- builds temporários são descartados após validação;
- não existe dependência operacional da estrutura `work/tce-extractor/portable`;
- o ZIP portátil continua funcionando em Windows 10/11 com Chrome/Edge.

## 16. Fora de escopo desta refatoração

Não faz parte do objetivo inicial:

- automatizar o clique final de envio;
- criar serviço em nuvem;
- publicar dados privados;
- substituir SQLite por banco cliente-servidor;
- reescrever coleta e navegação em um único passo;
- redesenhar regras de negócio que não sejam necessárias à consolidação;
- transformar o projeto em produto multiusuário.

## 17. Estratégia de risco

A migração é um **strangler refactor**.

Nenhuma implementação comprovada é removida antes de sua substituta estar validada.

Até a Fase 7, o fluxo legado permanece disponível como fallback.

Após estabilização:

```text
Mesa nova = padrão
legado = fallback
```

Depois de execuções reais bem-sucedidas:

```text
legado removido
```

Esse desenho prioriza redução de complexidade, preservação do conhecimento já adquirido sobre os portais e controle do risco operacional.
