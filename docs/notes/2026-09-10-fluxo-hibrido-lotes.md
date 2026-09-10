# Plano consolidado — fluxo híbrido, análise prévia e lotes de Complementar Ato

**Data:** 10/09/2026  
**Status:** plano canônico para implementação por fases  
**Especificação reconciliada:** `docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md`

## Registro de reconciliação

Este é o único plano canônico do fluxo híbrido em `docs/notes/`. A
especificação existente e o plano de implementação originalmente salvo em
`docs/superpowers/plans/` foram confrontados porque tinham conteúdo diferente:

- `docs/superpowers/plans/2026-09-10-fluxo-hibrido-lotes.md` tinha 6.267 bytes
  na fotografia inicial. Ele forneceu a sequência de tarefas 1–10, os comandos
  focais, os gates e as atualizações de estado da implementação.
- `docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md` tinha 8.738 bytes na
  fotografia inicial. Ele forneceu objetivo, autoridades, contratos JSON,
  estados, prévia, operação, idempotência, erros, interface e critérios de
  aceite.

O primeiro arquivo permanece no local ignorado porque esta tarefa não pode
apagar nem mover arquivos. Ele está superseded por este plano e não é uma
segunda fonte de execução. A especificação permanece como documento de
requisitos; este plano incorpora seu conteúdo normativo e o roteiro do plano
ignorado. A checagem `work/tce-extractor/tests/Test-DocumentationTracking.ps1`
registra essa reconciliação pelos dois caminhos de origem e por esta seção.

O registro de 10/09 no plano de origem, anterior ao fechamento do lote, dizia
que ainda não havia download/OCR remoto real nem envio de ato validado naquela
rodada. Esse trecho é histórico e foi superseded pelas atualizações live abaixo:
o download/preparação do lote 1/50 foi comprovado, enquanto o envio continua
não qualificado e desligado.

## 1. Objetivo

Permitir que o operador escolha a origem da lista de processos na Área Restrita:

- **Processos no setor / Finalísticos / Proc./Doc. Eletrônicos**; ou
- **Meus Processos**.

A Área Restrita é a fonte autoritativa para descobrir o marcador, verificar a ação
disponível e decidir se o processo ainda precisa de Complementar Ato. O e-Contas
é uma fonte de aquisição/enriquecimento: baixa os documentos e eventos quando
disponíveis, sem poder promover um processo a elegível contra o estado observado
na Área Restrita.

O operador deve conseguir executar uma prévia, saber quantos atos estão
pendentes, dividir a fila em lotes (inclusive 50 ou 100) e acompanhar cada item
da aquisição ao resultado observado.

## 2. Decisões de autoridade

| Dado | Fonte primária | Regra em conflito |
|---|---|---|
| Escopo da lista | Área Restrita | execução pausa se a tela não confirmar o escopo solicitado |
| Marcador e valor selecionado | Área Restrita | texto/valor exatos; mudança durante paginação pausa |
| Ação `Complementar Ato` pendente | Área Restrita | ausência da ação não é “já concluído” sem estado explícito |
| Identidade do interessado | Área Restrita + chave do processo | homônimo ou chave ambígua vira `blocked_identity` |
| Documento/evento para OCR | e-Contas | falta, erro de autenticação ou chave divergente vira bloqueio |
| Campos documentais propostos | OCR/análise local | só valores com evidência e regras versionadas entram no preflight |
| Resultado da transmissão | Área Restrita observada após o comando | timeout/resultado ambíguo vira `unconfirmed`, sem reenvio |

Marcadores podem ser mostrados no painel com enriquecimento do e-Contas, mas o
contador de “precisa complementar” sempre usa o marcador/ação da Área Restrita.
Cada observação registra `source`, `observed_at`, valor textual normalizado e
hash da fotografia.

## 3. Modelo de execução

### 3.1 Especificação de execução

```json
{
  "schema_version": 2,
  "source_scope": "sector_finalistic" | "my_processes",
  "marker": {"label": "texto exato", "value": "valor_do_portal"},
  "acquisition_source": "econtas",
  "lot_size": 50,
  "analysis_only": true,
  "auto_prepare": true,
  "auto_submit": false,
  "dataset_sha256": "..."
}
```

`lot_size` aceita inteiro de 1 a 1000; a interface oferece atalhos 50 e 100.
`auto_submit` nunca é habilitado por `lot_size`, marcador ou reinício; depende
da qualificação versionada e do checkpoint explícito de envio já existente.

### 3.2 Item da fila

Cada interessado elegível é um item, mesmo que vários interessados pertençam ao
mesmo processo. O item contém apenas os dados necessários ao fluxo local e às
chaves do portal:

```json
{
  "ordinal": 1,
  "process_key": "numero/ano",
  "interested_key": "identificador normalizado",
  "area_restrita": {
    "scope": "sector_finalistic",
    "marker_label": "...",
    "marker_value": "...",
    "needs_complement": true,
    "action_observed": "Complementar Ato",
    "snapshot_hash": "..."
  },
  "econtas": {
    "match": "exact",
    "documents": [],
    "snapshot_hash": "..."
  },
  "state": "discovered"
}
```

Não persistir cookies, tokens, CPF bruto ou caminhos absolutos nos artefatos
transferíveis. Os identificadores pessoais existentes no acervo privado seguem
as regras atuais de distribuição.

### 3.3 Estados

```text
discovered
  -> eligibility_confirmed
  -> acquisition_pending -> downloaded
  -> ocr_pending -> ocr_ready
  -> ready_for_preflight -> prepared
  -> awaiting_send_confirmation -> send_intent
  -> send_issued -> outcome_observed
  -> confirmed | failed | unconfirmed | blocked
```

Falhas de aquisição/OCR são específicas do item e não saltam a fila. Falhas de
sessão, marcador, escopo, persistência ou resultado remoto pausam a execução.

## 4. Prévia e congelamento

A análise prévia executa a paginação inteira da origem escolhida e produz:

- `total_seen`;
- `needs_complement`;
- `already_complemented`;
- `without_action`;
- `identity_ambiguous`;
- `download_available`;
- `download_missing`;
- `ocr_ready`;
- `ocr_inconclusive`;
- `eligible`;
- `blocked`;
- `lot_count` e `lot_size`.

Quando a fotografia da Área Restrita ainda não possui documentos locais no
e-Contas, a prévia também expõe `acquisition_eligible`: esses itens podem ser
congelados como `acquisition_pending` para o lote de download/OCR, mas não
contam em `eligible` até o documento e o OCR estarem prontos.

O botão de criar lotes só é habilitado após a confirmação de que o marcador, a
origem e a última página foram observados. O congelamento grava a ordem do
portal, os hashes dos snapshots e o `dataset_sha256`; novos processos só entram
em uma nova análise.

## 5. Fluxo operacional

1. Selecionar a origem e o marcador na Área Restrita.
2. Paginar e capturar a prévia; não alterar o portal.
3. Confirmar a prévia e o tamanho do lote.
4. Congelar filas determinísticas.
5. Para cada lote, reconciliar chaves no e-Contas e baixar documentos.
6. Executar OCR/análise local e publicar evidências por documento/página.
7. Voltar à Área Restrita, abrir `Complementar Ato`, selecionar o interessado e
   preencher somente os sete campos permitidos.
8. Reler identidade e valores e executar preflight.
9. Parar no checkpoint imediatamente anterior ao botão externo no primeiro envio.
10. Após autorização explícita, emitir comando único, observar aceitação,
    reabrir/reler o ato e classificar o resultado.
11. Pausar em qualquer resultado incerto; nunca reenviar automaticamente.

## 6. Idempotência e retomada

- `analysis_id`, `lot_id`, `item_id`, `event_id` e `command_id` são estáveis e
  únicos.
- Repetir análise com a mesma fotografia é leitura idempotente.
- Repetir download usa hash/checkpoint e não baixa documento já íntegro.
- Repetir OCR usa o cache existente, invalidado por hash do documento e versão
  do runtime.
- Repetir o comando de envio devolve conflito depois do primeiro consumo.
- Reinício converte `send_intent` sem confirmação em `unconfirmed` e pausa a
  execução.

## 7. Contrato de erro

| Código | Significado | Ação |
|---|---|---|
| `SOURCE_SCOPE_MISMATCH` | tela não é a origem escolhida | pausar |
| `MARKER_MISMATCH` | marcador mudou/perdeu-se | pausar |
| `PROCESS_KEY_MISMATCH` | e-Contas não corresponde à Área Restrita | bloquear item |
| `AUTH_REQUIRED` | login expirou | pausar e pedir login |
| `DOCUMENT_UNAVAILABLE` | nenhum documento apto | bloquear item |
| `OCR_INCONCLUSIVE` | evidência insuficiente | bloquear item |
| `PORTAL_IDENTITY_CHANGED` | interessado mudou | pausar |
| `PORTAL_RESULT_UNCONFIRMED` | resultado remoto não determinável | pausar, sem retry |

## 8. Interface

O painel terá uma seção **Origem e análise** com:

- seletor de origem;
- seletor/texto exato do marcador;
- tamanho do lote;
- botão `Analisar sem alterar o portal`;
- resumo numérico e lista de bloqueios;
- botão `Congelar e criar lotes`.
- seletor de lote e botão `Baixar e preparar OCR do lote`, com status do job
  local; esta etapa não preenche nem envia atos.

A seção **Execução** exibirá lote atual, ordinal, estado por etapa, última
evidência e motivo de pausa. A seção **Ato atual** continuará separada para
preenchimento e revisão. A seção **Histórico** exibirá análises/lotes antigos
sem retomá-los automaticamente.

## 9. Critérios de aceite

1. Os dois escopos podem ser escolhidos e são confirmados pela tela real antes
   da varredura.
2. A prévia percorre todas as páginas, mostra totais e não confunde ausência da
   ação com conclusão.
3. O marcador é filtrado/verificado por valor exato e permanece no snapshot.
4. Lotes 50/100 têm ordem, hash, itens e retomada determinísticos.
5. Reconciliação e-Contas/Área Restrita detecta chave divergente e não mascara
   documento ausente.
6. Download, OCR, evidências e cache são executados por item, com falhas
   isoladas e relatório incremental.
7. Nenhum item sem preflight válido pode chegar ao comando de envio.
8. O envio final é único, observável, qualificado e pausável; resultado incerto
   não gera reenvio.
9. O pacote final contém BATs, guia, extensão e runtime, sem credenciais ou
   perfil autenticado.
10. Os testes unitários, de integração, pacote, Chrome descartável e gates
    reais documentados ficam verdes; gates não realizados permanecem explícitos.

## 10. Roteiro de implementação reconciliado

Executar em ordem. Para cada tarefa: escrever/atualizar teste primeiro,
executar RED pelo motivo esperado, implementar o mínimo, executar GREEN e
registrar o resultado no handoff de `docs/notes/`.

### Contexto e contratos

- Especificação: `docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md`.
- Plano-base: `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`.
- Raiz Python: `work/tce-extractor/portable/app`.
- Raiz da extensão: `work/tce-extractor/portable/extensao-complementar-ato`.
- Persistência: `AutomationStore` e serviço loopback existentes.
- Autoridade de elegibilidade: DOM sanitizado da Área Restrita.

### Tarefa 1 — contrato de origem, análise e lote

Criar `portable/app/batch_scope.py` e `portable/app/test_batch_scope.py`.
Definir enums/validadores para `sector_finalistic` e `my_processes`, marcador
exato, tamanhos 1..1000, métricas da prévia, item da fila e estados. Gerar
IDs/hash canônicos sem dados secretos. Rejeitar chaves extras e estados
impossíveis.

Comando: `C:\Python314\python.exe -m unittest portable.app.test_batch_scope -v`.

### Tarefa 2 — snapshot e reconciliação e-Contas

Criar `portable/app/source_reconciliation.py` e testes com fixtures sanitizadas.
Aceitar somente chaves canônicas; marcar `exact`, `missing`, `ambiguous` ou
`conflict`. Integrar documentos existentes ao `analysis_pipeline` sem duplicar
download/OCR e sem baixar se a prévia ainda não estiver congelada.

### Tarefa 3 — prévia e geração de lotes

Criar `portable/app/analysis_preview.py` e testes de paginação, contagem,
congelamento, divisão em 50/100, retomada e erro de marcador/escopo. Reutilizar
o estado/event store sem mudar o significado de `progresso.json`.

### Tarefa 4 — contrato JS da execução

Atualizar `lib/automation-schema.js`, `lib/messages.js` e seus testes para
`source_scope`, `marker.value`, `lot_size`, `analysis_id` e estados de prévia.
Manter compatibilidade explícita com RunSpec v1 quando nenhum campo novo for
usado; RunSpec v2 deve rejeitar `auto_submit` sem capacidades qualificadas.

### Tarefa 5 — navegação dos dois escopos na Área Restrita

Atualizar `content/portal-navigation.js` e `background/automation-controller.js`
com testes RED/GREEN para:

- localizar a lista de setor/finalísticos;
- localizar `Meus Processos`;
- verificar o escopo pelo título/rota/estrutura;
- aplicar marcador e confirmar o valor selecionado;
- percorrer todas as páginas preservando a ordem;
- retornar ao processo e ao interessado corretos.

Não ampliar origem por suposição e não usar e-Contas para decidir elegibilidade.

### Tarefa 6 — bridge/API de prévia e lotes

Adicionar ao `local_service.py`, `bridge-client.js` e testes endpoints/contratos
para criar análise, obter prévia, congelar fila, listar lotes e obter estado.
Todas as mutações exigem sessão local/origem permitida, revisão e IDs
idempotentes. O serviço não deve expor token ou caminho absoluto em respostas.

### Tarefa 7 — interface do painel

Atualizar `sidepanel/panel.html`, `panel-view.js`, `panel.js` e CSS/tests:
seletor de origem, marcador exato, tamanho 50/100, botão de prévia, métricas,
bloqueios e criação de lotes. Desabilitar execução quando a prévia não estiver
congelada ou houver conflito de versão. Manter Ato atual/Execução/Histórico
separados.

### Tarefa 8 — orquestração download/OCR

Integrar a fila congelada a `incremental_pipeline.py`, `analysis_pipeline.py`,
`batch_runner.py` e `extension_exporter.py`. Processar por lote, publicar
checkpoint por item, reaproveitar cache e emitir estados `downloaded`,
`ocr_ready`, `prepared` e `blocked`. Criar testes de falha 401/403/429,
documento ausente, OCR inconclusivo e reinício.

**Estado registrado em 10/09/2026, reconciliado com o handoff:** a fila
congelada chega ao coletor portátil por `-FilaCongelada`/`-NumeroLote`; a
reconciliação contra a lista atual do e-Contas preserva ordem e interrompe antes
do primeiro download quando há ausência ou duplicidade. O serviço autenticado
inicia o processo local e expõe o status do job; após a sincronização, o
coletor reutiliza `incremental_pipeline.py` para preparação/OCR por processo.
O download e a preparação reais do lote 1/50 foram posteriormente comprovados;
o envio de ato continua não qualificado nesta rodada.

**Atualização live em 10/09/2026:** a Área Restrita confirmou o marcador
`6189` com 549 processos em 19 páginas; a prévia somente leitura observou a
ação `Complementar Ato` em 549/549 linhas, equivalente a 11 lotes de 50 ou 6
de 100. A seleção de origem atravessa o serviço até o coletor por
`-EscopoPortal`, evitando que um lote `sector_finalistic` seja coletado pela
lista `my_processes`. O contador live não substitui o snapshot persistido pela
extensão nem prova, sozinho, download/OCR remoto.

### Tarefa 9 — preflight e execução real supervisionada

Adicionar testes e integração para garantir que cada item tenha identidade,
marcador, sete campos e hash antes de `send_intent`. Manter o botão final sob
confirmação imediata no primeiro envio. Depois do checkpoint autorizado,
observar resultado, reabrir/reler e produzir fixture sanitizada; resultado
incerto pausa o lote.

### Tarefa 10 — qualificação, documentação e empacotamento

Atualizar `qualification.py`, `README.md`, `GUIA-RAPIDO.md/.html`, BATs,
allowlist/diagnóstico e o plano-base com estado real. Gerar ZIP final, extrair
em pasta limpa, rodar `TESTAR-PACOTE.ps1`, smoke Chrome descartável e suítes
completas. Não incluir cookies, perfil, tokens, `dados-locais` ou logs privados.

## 11. Gates de verificação

```powershell
Push-Location 'work/tce-extractor/portable/extensao-complementar-ato'
npm test
Pop-Location

C:\Python314\python.exe -m unittest discover -s 'work/tce-extractor/portable' -p 'test_*.py' -q

git diff --check
git status --short
```

Gates reais serão registrados separadamente: DOM sanitizado dos dois escopos,
prévia de marcador, preflight de três atos, confirmação do primeiro envio,
observação/reabertura, fixture, qualificação e lote supervisionado de até cinco.
Nenhum gate sintético será apresentado como prova de efeito remoto.

## 12. Registro histórico preservado das fontes

Esta seção preserva metadados e redações que eram exclusivos das fontes
reconciliadas. Ela é histórica e informativa; a execução deve seguir as seções
anteriores e o estado atualizado do plano mestre.

### 12.1 Metadados da especificação

Fonte histórica: `docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md`.

> # Especificação — análise híbrida e lotes de Complementar Ato
>
> **Status:** aprovada para implementação por fases  
> **Escopo:** complementar a automação existente sem substituir os gates de segurança do portal real.

### 12.2 Trechos históricos do plano de implementação

Fonte histórica: `docs/superpowers/plans/2026-09-10-fluxo-hibrido-lotes.md`.

> # Plano de implementação — fluxo híbrido, análise prévia e lotes
>
> Executar em ordem. Para cada tarefa: escrever/atualizar teste primeiro,
> executar RED pelo motivo esperado, implementar o mínimo, executar GREEN e
> registrar o resultado no handoff de `docs/notes/`.

O plano de implementação registrava inicialmente este estado da Tarefa 8:

> **Estado em 10/09/2026: parcialmente implementada, com disparo local pelo
> painel concluído.** A fila congelada chega ao coletor portátil por
> `-FilaCongelada`/`-NumeroLote`; a reconciliação contra a lista atual do e-Contas
> preserva ordem e interrompe antes do primeiro download quando há ausência ou
> duplicidade. O serviço autenticado agora inicia o processo local e expõe o
> status do job; após a sincronização, o coletor reutiliza
> `incremental_pipeline.py` para preparação/OCR por processo. Ainda não há
> download/OCR remoto real nem envio de ato validado nesta rodada.

O mesmo registro histórico dizia, na atualização live, que o contador não
substituía o snapshot persistido nem provava download/OCR remoto:

> O contador live ainda não substitui o snapshot persistido pela extensão nem
> prova download/OCR remoto.

Para preservar também a redação e a quebra de linha da fonte original:

> de 100. A seleção de origem agora atravessa o serviço até o coletor por
> lista `my_processes`. O contador live ainda não substitui o snapshot persistido
> pela extensão nem prova download/OCR remoto.

> ## Gates de verificação

O conteúdo operacional desses gates está consolidado na seção 11 acima. O
registro histórico completo dos comandos permanece no arquivo fonte ignorado,
que não deve ser usado como segunda fonte de execução.
