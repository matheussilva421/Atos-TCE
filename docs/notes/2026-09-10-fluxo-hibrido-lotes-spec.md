# Especificação — análise híbrida e lotes de Complementar Ato

**Data:** 10/09/2026
**Status:** aprovada para implementação por fases
**Escopo:** complementar a automação existente sem substituir os gates de segurança do portal real.

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
