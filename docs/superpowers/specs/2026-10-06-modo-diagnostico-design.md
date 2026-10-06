# Atos-TCE — Design: Modo Diagnóstico sempre ativo

**Data:** 2026-10-06
**Repositório:** `matheussilva421/Atos-TCE`
**Branch:** `codex/area-restrita-reliability-reset`
**Base:** `1a687e8bdb980257a8bb94ad263bb286d1099199`
**Escopo:** observabilidade local, leve e sempre ON por padrão para o runtime portátil.

## 1. Problema e objetivo

Em outro PC, falhas, lentidão ou ausência de resposta podem desaparecer antes
que alguém consiga reproduzi-las. O diagnóstico deve guardar uma timeline local
que acompanhe o fluxo existente da Mesa pela extensão e portal até a detecção do
formulário, current-selection, preflight, comando, escrita, readback e resultado.

O modo nasce ativo a cada inicialização do runtime e continua ativo depois de
reinicializações. Durante uma execução, a Mesa permite pausar, retomar, limpar e
exportar o diagnóstico. Eventos registram tempo decorrido e marcam boundaries
lentos como `SLOW`.

## 2. Invariantes e limites

- O diagnóstico observa o fluxo e não controla identity resolution,
  qualification, capability gates, fill, AR-1, AR-2, AR-3 ou envio manual.
- O ledger `app/area_restrita/reliability.py` conserva seu schema estrito e seu
  papel exclusivo na qualification. A timeline diagnóstica não é escrita nesse
  ledger.
- O snapshot completo de current-selection continua transitório. O recorder
  recebe somente os campos explicitamente selecionados para diagnóstico; os
  metadados diagnósticos nunca são persistidos em SQLite nem adicionados ao
  resultado funcional de fill.
- Não registrar senha, cookie, `Authorization`, `Bearer`, extension token ou
  segredo equivalente. Nunca entregar cabeçalhos de autenticação ao recorder.
- Os dados ficam no data root local. Nenhum serviço externo recebe eventos.
  Exportar é uma ação explícita da pessoa operadora.
- Instrumentação e gravação são fail-open: erro no recorder não falha, atrasa
  intencionalmente, repete ou muda uma operação funcional.
- A automação continua sem ação de submit; o operador ainda conclui o ato
  manualmente no portal.

## 3. Abordagens consideradas

1. **Estender o reliability ledger.** Rejeitada: seus validadores e avaliador
   dependem de um vocabulário pequeno, sanitizado e sem identidade. Misturar
   diagnóstico alteraria a fronteira de qualification.
2. **Guardar logs somente na extensão.** Rejeitada: não observa com autoridade
   os resultados do backend, preflight, current-selection e ciclo de vida dos
   comandos, e dificulta exportar uma timeline coerente.
3. **Recorder local separado, integrado aos boundaries existentes.** Escolhida:
   um componente de armazenamento e exportação, com instrumentação no servidor e
   no roteador/filler da extensão. Metadados da extensão seguem junto aos
   pedidos de observação/resultados que já existem; não se cria um workflow ou
   canal paralelo de comandos.

## 4. Arquitetura

### 4.1 Recorder e sessão

Adicionar `app/area_restrita/diagnostics.py` com `DiagnosticRecorder`, criado
quando `MesaServer` inicia e compartilhado pelos handlers e `FillService`.
O recorder:

- grava em `<data-root>/diagnostics/`, fora do repositório e do ZIP;
- cria um `session_id` UUID por inicialização e acrescenta esse identificador
  aos eventos aceitos;
- carimba `timestamp` em UTC no servidor. Durações calculadas na extensão usam
  `performance.now()` e são enviadas como `elapsed_ms`, sem depender dos
  relógios dos dois processos;
- aceita somente o schema allowlisted da seção 5;
- fornece snapshot para a UI e monta o ZIP sob demanda;
- não usa SQLite nem importa/escreve no ledger de reliability.

`settings.json` em `diagnostics/` declara `diagnostic_enabled: true`. Na
inicialização o modo é ON; pausa é estado transitório do processo. Assim,
reiniciar recupera o padrão ON, inclusive após uma pausa anterior. Limpar apaga
as sessões guardadas e inicia um arquivo de sessão novo sem alterar o estado
ON/pausado vigente.

### 4.2 Integração com os fluxos existentes

- `app/api/server.py`: cria o recorder, expõe estado/controle/exportação para a
  Mesa autenticada e registra a chegada de heartbeat, publicação/limpeza de
  current-selection, comando enviado pelo endpoint atual e resultado/timeout.
  Eventos de API registram duração com relógio monotônico.
- `app/area_restrita/fill_service.py`: registra boundaries de tentativa,
  preflight, comando de fill, readback e resultado a partir dos códigos e dados
  já produzidos. `FillService` recebe um recorder opcional injetado; recorder
  ausente ou com erro não muda a lógica existente.
- `extension/background/router.js`: mede heartbeat, leitura da aba/formulário,
  varredura de frames e comando executado; anexa um objeto diagnóstico
  estritamente descritivo ao payload de observação atual ou resultado do
  comando, incluindo o boundary de comando recebido. A ausência/rejeição desse
  metadado não altera o payload funcional.
- `extension/content/fill-form.js`: mede escrita e reread por campo e devolve
  esses tempos dentro do objeto diagnóstico irmão de `field_results`, sem mudar
  os códigos, valores, guards ou decisão de preenchimento.
- O servidor associa metadados recebidos à sessão atual, grava cópias
  sanitizadas e remove o objeto diagnóstico antes de entregar/persistir o
  resultado funcional. Snapshot integral, headers, token e corpo HTTP nunca são
  passados ao recorder.

O identificador de sessão criado no servidor correlaciona eventos da Mesa e da
extensão. `observation_id`, `publisher_id`/`sequence` e identificador/tipo do
comando complementam a correlação entre boundaries sem substituir as regras de
ownership, TTL ou deduplicação existentes.

As etapas mínimas nomeadas na timeline são `portal_detected`, `frames_scanned`,
`form_detected`, `selection_published`, `preflight`, `command_sent`,
`fill_command_received`, `field_write`, `field_reread` e `result`. Ausência de
portal/form também produz resultado com o código existente, sem criar retry ou
mudar seleção.

### 4.3 API da Mesa

Adicionar rotas com autenticação de sessão Mesa:

- `GET /api/v1/diagnostics`: status e resumo mais recente para renderização;
- `POST /api/v1/diagnostics/control`: ações `pause`, `resume` ou `clear`;
- `GET /api/v1/diagnostics/export`: ZIP com nome datado e tipo
  `application/zip`.

Falha/recusa de rota diagnóstica não pode afetar o restante da Mesa. A extensão
continua autenticando exclusivamente pelas rotas existentes; o modo
diagnóstico não expõe seu token nem cria endpoint de autenticação.

### 4.4 UI

Adicionar um painel **Diagnóstico** em `app/web/index.html`, renderizado em
`app/web/app.js`, com refresh periódico compatível com a atualização atual da
Mesa. Mostrar:

```text
Diagnóstico        ATIVO/PAUSADO
Mesa               OK/estado
Extensão           OK/estado
Portal             OK/estado
Heartbeat          idade
Formulário         estado/código
Current selection estado/código
Último comando     tipo
Último resultado   code
Último erro        code
```

Exibir botões **Exportar diagnóstico**, **Limpar diagnóstico** e
**Pausar/Retomar**. Usar o status agregado do recorder e os últimos eventos;
capabilities continuam sendo lidas do `ReliabilityRecorder` existente, sem
duplicar seu estado.

## 5. Schema, lentidão e privacidade

Todo evento tem `timestamp`, `session_id`, `componente`, `etapa`,
`elapsed_ms` quando aplicável, e `resultado` e/ou `code`. A observação de
comando usa `comando_id`, `comando_tipo` e `comando_estado` (`SENT`,
`RECEIVED` ou `RESULT`), para distinguir o envio pelo servidor, o recebimento
pela extensão e o resultado retornado. Campos opcionais allowlisted:

```text
processo, interessado, tab, frame, url, rota, generation, documentNonce,
observation_id, publisher_id, publisher_sequence, comando_id, comando_tipo,
comando_estado, estado_fill,
campos_detectados, before, proposed, after, warnings, error
```

Os nomes são normalizados antes do filtro. Excluir recursivamente chaves
conhecidas de credenciais/headers/secrets; remover ocorrências de `Bearer`,
`Basic`, `Cookie`, `Set-Cookie` e `Authorization` de texto livre. Preservar o
texto completo de erros depois da redação. URL será reduzida a origem e caminho;
credenciais, query e fragmento são sempre removidos. Não registrar HTML, DOM,
corpo bruto de requisição/resposta ou objetos arbitrários.

O objetivo autoriza dados de processo/formulário. Registrar identidade e
valores `before`/`proposed`/`after` somente nos campos do contrato conhecido de
fill; chaves ou valores reconhecidos como credenciais são removidos mesmo
nesses campos. A lista de campos detectados é estrutural (nomes e estado), não
uma captura integral de formulário.

Boundary com duração `>= 2000 ms` recebe `severity: "SLOW"`; o valor fica em uma
constante simples, sem métricas, dashboards ou agregadores adicionais.

## 6. Persistência, retenção e exportação

Estrutura local:

```text
<data-root>/diagnostics/settings.json
<data-root>/diagnostics/sessions/<session-id>.jsonl
```

Manter no máximo cinco sessões. Limitar também cada timeline ativa a 8 MiB;
quando atingir o limite, remover as linhas mais antigas até voltar a 6 MiB e
registrar que houve truncamento. Aplicar retenção no startup, no append e após
clear. Arquivos temporários de exportação são removidos após a resposta.

Nome do ZIP: `diagnostico-atos-tce-YYYYMMDD-HHMMSS.zip`. Deve conter exatamente
estes artefatos de diagnóstico:

```text
resumo.txt
timeline.jsonl
ambiente.json
mesa.log
extensao.log
ultima-sessao.json
```

`resumo.txt` lista falhas, timeouts, boundaries SLOW, último estado conhecido,
build ID, versão da extensão e capabilities atuais. `timeline.jsonl` reúne as
sessões retidas em ordem temporal; os dois logs são projeções legíveis por
componente, usando os mesmos eventos sanitizados. `ambiente.json` contém apenas
proveniência e versões não secretas necessárias ao diagnóstico. O ambiente e a
exportação nunca incluem variáveis de ambiente arbitrárias, perfis, HAR, cookies
ou tokens.

## 7. Verificação

Testes automatizados RED→GREEN cobrem os requisitos mínimos do objetivo:

- nasce ON no primeiro start;
- continua ON após reinício;
- evento contém timestamp, componente, etapa e duração;
- duração acima do limiar recebe SLOW;
- eventos Mesa e extensão compartilham a sessão;
- erro preserva o code original;
- export gera os seis arquivos esperados;
- limpar remove sessões antigas;
- pausar impede novos eventos;
- retomar volta a registrar eventos;
- senha, cookie, Authorization, Bearer e extension token nunca aparecem nos
  arquivos de diagnóstico, nem como chave nem em texto livre;
- falha de gravação diagnóstica não altera respostas nem comandos funcionais.

Executar smoke sintético, sem login ou acesso à Área Restrita real, com
form-detected lento, `FORM_NOT_AVAILABLE`, `STALE_FORM`, `FILL_FORM` com write e
readback bem-sucedidos e timeout de comando. Exportar o ZIP e conferir que os
casos, códigos, durações e estados estão identificáveis, sem segredos.

Gates de implementação incluem a suíte Python da raiz, testes da extensão,
testes web, contrato/verificador de pacote e CI da branch. O pacote final será
construído depois do commit final a partir do SHA atual; validar ZIP e sidecar
SHA-256 e não reutilizar artefato anterior. Nenhum gate sintético qualifica
execução real, promove capabilities ou prova comportamento em portal real.

## 8. Critérios de conclusão

```text
[ ] Modo inicia ON e continua ON por padrão após reinício
[ ] Timeline correlaciona Mesa e extensão do heartbeat a resultado
[ ] Durações e marcação SLOW aparecem nos boundaries principais
[ ] UI mostra estados e permite pausar/retomar/limpar/exportar
[ ] ZIP contém os seis artefatos especificados e resumo útil
[ ] Dados de processo/formulário úteis, sem credenciais
[ ] Retenção de cinco sessões e limite de tamanho ativos
[ ] Os 12 comportamentos mínimos de diagnóstico cobertos por testes
[ ] Smoke sintético permite identificar os cinco cenários exigidos
[ ] Gates/CI verdes; comportamento funcional preservado
[ ] ZIP portátil novo inclui o modo e está verificado
[ ] Handoff final registra SHAs, testes, pacote, hash e pendências
```
