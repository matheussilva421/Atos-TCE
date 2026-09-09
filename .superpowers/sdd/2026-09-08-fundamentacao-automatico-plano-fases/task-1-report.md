# Relatório — Fase 1: contexto documental completo e compatível

Data: 2026-09-08
Branch: `codex/fundamentacao-automatico`
Brief: `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/task-1-brief.md`

## Status

Implementação local da Fase 1 concluída, com testes focais verdes e sem
qualquer ação no portal. O matcher JavaScript da Fase 0 permanece
intencionalmente RED. Commit de implementação: `f0a72b5`.

## Fix round 1 — revisão da Fase 1

Data: 2026-09-08
Commit incremental: `e84ac95 fix: harden legal context evidence publication`

O round corrigiu somente os achados de publicação de contexto, sem tocar
empacotamento, `test_portable_end_to_end.py` ou o matcher:

1. O classificador agora conserva as páginas já lidas (page_texts) e o
   pipeline as entrega ao sidecar; a publicação não dispara OCR em GET ou
   seleção.
2. complete exige que o interessado normalizado apareça em uma página citada
   da resolução. Sem vínculo nominal verificável, o registro fica incomplete;
   divergência entre resoluções permanece conflict.
3. operative_text usa o último marcador resolve ancorado no início de linha,
   evitando um resolve histórico/preliminar. A versão de extração foi
   incrementada para legal-context-v2 e analysis-pipeline-v3.
4. page_count agora é preservado no manifesto e validado no sidecar. Lista
   truncada recebe páginas vazias citadas e bloqueia complete; quantidade
   excedente também marca a fonte como incompleta.
5. O caminho do temporário é registrado imediatamente após sua criação, então
   falhas em serialização, flush, fsync ou os.replace removem o arquivo
   parcial. Há testes para falhas de serialização e fsync.

### TDD do fix

RED antes da implementação:

    python -m unittest test_legal_context -q
    12 testes; 8 passaram; 4 falharam (interessado ausente, marcador
    operativo histórico e dois cleanups).

    python -m unittest test_analysis_pipeline.AnalysisPipelineTests.test_classification_records_page_count_from_native_and_ocr_pages test_analysis_pipeline.AnalysisPipelineTests.test_target_manifest_preserves_classified_page_count_for_sidecar_validation test_analysis_pipeline.AnalysisPipelineTests.test_local_pipeline_publishes_native_classification_pages_without_ocr -q
    3 testes; 0 passaram integralmente; 1 falhou e 2 falharam por ausência dos
    contratos ainda não implementados.

GREEN após a implementação e ajuste das fixtures sintéticas para declarar o
vínculo nominal e o page_count que a nova regra exige.

## Fix round 2 — revisão da Fase 1

Data: 2026-09-08
Commit incremental: `8b3a411 fix: preserve physical legal context coverage`

O round corrigiu somente os três achados solicitados:

1. A contagem física observada no leitor nativo é preservada como lower bound
   quando o cache OCR contém apenas duas de três páginas. O manifesto mantém
   page_count 3, o sidecar materializa a página descoberta sem texto e o
   contexto fica incomplete; não há declaração enganosa de duas páginas.
2. A vinculação do interessado compara sequências de tokens normalizados com
   fronteira inequívoca, impedindo ANA de casar com MARIANA. Fontes homônimas
   ficam conflict sem identificador; matrícula normalizada desambigua a fonte
   quando fornecida, inclusive com pontuação/separadores.
3. EXTRACTOR_VERSION voltou a analysis-pipeline-v2, preservando caches OCR
   válidos. A assinatura independente LEGAL_CONTEXT_VERSION=legal-context-v3
   identifica a lógica do sidecar sem invalidar globalmente o cache de
   extração; teste explícito prova a reutilização de cache antigo sem OCR.

### TDD do fix

RED antes da implementação:

    python -m unittest test_legal_context -q
    15 testes; 12 passaram; 3 falharam nos novos casos de identidade.

    python -m unittest test_analysis_pipeline.AnalysisPipelineTests.test_physical_page_count_is_lower_bound_when_ocr_cache_covers_only_two_of_three_pages test_analysis_pipeline.AnalysisPipelineTests.test_legal_context_version_is_separate_and_old_ocr_cache_remains_valid test_analysis_pipeline.AnalysisPipelineTests.test_classification_records_page_count_from_native_and_ocr_pages -q
    3 testes; 1 passou; 2 deram erro por contratos ainda não implementados.

GREEN após a implementação:

    python -m unittest test_legal_context test_tce_extractor test_analysis_pipeline test_extension_exporter -q
    87 testes; 87 passaram; 0 falharam.

    python -m unittest test_batch_runner -q
    19 testes; 19 passaram; 0 falharam.

O handoff global `docs/notes/2026-09-08-fundamentacao-automatico-handoff.md`
foi atualizado com o estado do round 2, ownership, gates e instruções de
retomada. O matcher permanece a única RED JavaScript conhecida (33/34).

## Implementação

Foi criado `portable/app/legal_context.py` com as interfaces:

- `build_legal_contexts(manifest, checkpoint, page_texts, dataset_sha256)`;
- `write_legal_contexts(path, contexts)`.

O sidecar tem `schema_version`, `dataset_sha256` e uma lista `records`. Cada
registro contém `schema_version`, `process_key`, interessado normalizado,
`dataset_sha256`, `resolution_status`, páginas com texto integral e citação
por página (`document_id`, `event_id`, `page`, `pdf_sha256`),
`operative_text` sem truncamento e `extraction_version`.

A resolução somente é considerada fonte quando a classificação é
`resolucao_administrativa`. Ausência de fonte resulta em `missing`; falha de
OCR, página ausente, hash incompatível ou vínculo incompleto resulta em
`incomplete`; textos operativos divergentes resultam em `conflict`. O trecho
operativo é derivado das páginas, não do `quote`/valor de campo que pode estar
truncado. Identificadores documentais são reduzidos a rótulos seguros, sem
paths absolutos ou URLs.

`portable/app/analysis_pipeline.py` foi alterado somente para publicar
`fundamentos-contexto.v1.json` depois do dataset v1, carregar páginas já
persistidas nos caches locais sem OCR adicional e vincular o sidecar ao
`batch.logical_sha256`. `PipelineSummary` expõe `legal_context_path`.

O dataset v1 e `extension_exporter.py` não foram alterados. Não foi criada API
HTTP, não houve leitura/escrita em portal e não foram processados dados reais.

## TDD — RED/GREEN

RED comportamental inicial, depois de eliminar apenas o erro de módulo ausente:

```text
python -m unittest test_legal_context -q
FAIL: 1 teste; 0 registros publicados, esperado 1 (0 != 1)
```

As fatias seguintes reproduziram fonte errada (`StopIteration`) e a integração
sem `legal_context_path` (`AttributeError`). Cada correção foi mínima e os
testes voltaram a passar. O teste multipágina mantém um `quote` sem §5, mas a
parte operativa contém §5 e é preservada no contexto.

## Testes executados

```text
python -m unittest test_legal_context test_tce_extractor test_analysis_pipeline test_extension_exporter -q
82 testes executados; 82 passaram; 0 falharam.
Aviso ambiental já conhecido: API fitz depreciada.
```

```text
python -m unittest test_batch_runner -q
19 testes executados; 19 passaram; 0 falharam.
```

```text
node --test tests/matcher.test.mjs tests/normalizer.test.mjs
34 testes executados; 33 passaram; 1 falhou.
Falha única conhecida e preservada: matcher escolhe
synthetic-ec41-without-p5 para texto sem sinal positivo, em vez de null.
```

```text
git diff --check
Passou.
```

O teste de pacote autocontido foi executado apenas para registrar a fronteira
de escopo. Ele falha porque o empacotador/teste portátil, deliberadamente
mantidos no HEAD `08cf8b9`, não incluem o novo `legal_context.py`; essa alteração
foi revertida conforme instrução e permanece uma pendência para autorização ou
fase apropriada.

## Arquivos alterados

- Criado `work/tce-extractor/portable/app/legal_context.py`.
- Criado `work/tce-extractor/test_legal_context.py`.
- Alterado `work/tce-extractor/portable/app/analysis_pipeline.py`.
- Alterado `work/tce-extractor/test_analysis_pipeline.py`.
- Criado este relatório.
- Alterado o handoff global `docs/notes/2026-09-08-fundamentacao-automatico-handoff.md` para registrar o fix round 1, os gates e a retomada.

Não foram mantidas alterações em `empacotar-coletor-portatil.ps1` ou
`test_portable_end_to_end.py`; ambos foram comparados ao HEAD `08cf8b9` e estão
exatos. Nenhum arquivo do matcher, portal ou exportador foi alterado.

## Concerns e pendências

1. O ZIP autocontido atual não carrega `legal_context.py`, pois a allowlist do
   empacotador ficou intencionalmente fora desta Fase 1. Antes de um release
   portátil, será necessário tratar essa dependência em uma fase/alteração
   autorizada e atualizar a cobertura de pacote correspondente.
2. A RED do matcher permanece para a Fase 2; não interpretar a suíte JavaScript
   33/34 como falha desta implementação Python.
3. O sidecar é local e sanitizado no contrato documental; não é uma autorização
   de envio automático. Contextos `missing`, `incomplete` e `conflict` devem
   continuar bloqueando elegibilidade futura.

## GitHub e retomada

O checkout não possui remoto configurado; nenhum push foi realizado. O commit
de implementação é `f0a72b5 feat: publish versioned legal evidence context` e o
fix round 1 é `e84ac95 fix: harden legal context evidence publication`.

Retomada: revisar o diff limitado aos arquivos listados e somente então decidir
a fase/autoridade para incluir o novo módulo no pacote portátil. Não corrigir o
matcher nesta retomada.

## Fix round 3 — revisão da Fase 1

Data: 2026-09-08
Commit incremental de código/testes: e85aa35 fix: close legal context evidence and cache gaps

O round corrigiu os três achados solicitados, mantendo o ownership da Fase 1:

1. Quando o manifesto contém resoluções concorrentes e somente uma possui
   page_texts, o sidecar não pode publicar complete. O registro preserva
   source_evidence para todas as fontes do processo, inclusive a fonte sem
   evidência com state=missing, e registra status_reasons com
   source_evidence_missing e seus identificadores seguros. A seleção de
   páginas desambiguada continua separada do inventário completo; a fonte
   desconhecida não é descartada silenciosamente.
2. Matrícula numérica só é reconhecida em valor contíguo sob rótulo de
   identificação (matricula, registro, inscricao, identificador ou id). Ano: 12
   e Página: 34 não são concatenados para formar 1234; separadores internos do
   próprio valor continuam aceitos.
3. EXTRACTOR_VERSION permanece monotônico em analysis-pipeline-v3 e continua
   compatível com caches OCR v3 do round anterior. A versão independente do
   sidecar avançou para LEGAL_CONTEXT_VERSION=legal-context-v4. O teste
   comprova que uma mudança apenas na lógica de contexto não rejeita o cache v3
   nem dispara OCR.

### TDD do fix

RED antes da implementação:

    python -m unittest test_legal_context test_analysis_pipeline.AnalysisPipelineTests.test_legal_context_version_is_separate_and_v3_ocr_cache_remains_valid -q
    18 testes; 15 passaram; 3 falharam nos novos contratos:
    fonte concorrente foi publicada como complete, grupos numéricos foram
    concatenados e EXTRACTOR_VERSION ainda estava em v2.

GREEN após cada slice e integração:

    python -m unittest test_legal_context test_tce_extractor test_analysis_pipeline test_extension_exporter -q
    89 testes; 89 passaram; 0 falharam.

    python -m unittest test_batch_runner -q
    19 testes; 19 passaram; 0 falharam.

    git diff --check
    Passou.

    git diff --exit-code 08cf8b9 -- work/tce-extractor/empacotar-coletor-portatil.ps1 work/tce-extractor/test_portable_end_to_end.py
    Passou; ambos os arquivos proibidos permanecem exatos.

### Self-review, concerns e retomada

- O comportamento ambíguo é fail-closed: evidência concorrente ausente ou
  incompleta mantém incomplete/conflict e explicita a razão.
- Nenhum arquivo de empacotamento, matcher, portal, dataset v1 ou exportador foi
  alterado. A RED conhecida do matcher permanece 33/34 e não pertence a este
  round.
- O teste de pacote autocontido continua sendo concern separado porque o
  empacotador preservado no HEAD 08cf8b9 não inclui legal_context.py.
- O handoff global
  docs/notes/2026-09-08-fundamentacao-automatico-handoff.md foi atualizado
  com este round, ownership, gates, concerns e instruções de retomada.
- O checkout não possui remoto configurado; nenhum push foi realizado.

## Fix round 4 — revisão da Fase 1

Data: 2026-09-08
Commit incremental de código/testes: d305ee6 fix: require unambiguous evidence identity

O round corrigiu os dois achados solicitados, sem alterar empacotamento ou
matcher:

1. A atribuição de página agora considera aliases somente quando a identidade
   documental é inequívoca. Para fontes com o mesmo event_id, uma chave de
   evento sem document_id e hash completos não é reutilizada; a página não é
   atribuída a nenhuma fonte e o sidecar registra source_alias_ambiguous em
   status_reasons. Payloads que carregam document_id, event_id e pdf_sha256
   compatíveis continuam sendo aceitos. A fonte concorrente permanece em
   source_evidence com seu estado e motivo.
2. No caminho padrão geometry_capable=True, cache textual v3 válido é consumido
   mesmo sem geometry cache e sem chamar OCR novamente. O resultado marca
   geometry_status=unavailable, o target manifest e o sidecar carregam essa
   indicação, e texto/citações são preservados. A evidência visual continua
   exigindo geometry cache/resultado geométrico quando a operação realmente
   depende de geometria.

### TDD do fix

RED antes da implementação:

    python -m unittest test_legal_context.LegalContextTests.test_does_not_reuse_page_through_ambiguous_event_alias test_analysis_pipeline.AnalysisPipelineTests.test_geometry_capable_reuses_v3_text_cache_without_ocr_for_legal_context -q
    2 testes; 0 passaram; 2 falharam nos contratos novos:
    alias event_id reutilizou uma página e o caminho geometry_capable=True
    chamou OCR apesar do cache textual v3.

GREEN após cada slice e integração:

    python -m unittest test_legal_context test_tce_extractor test_analysis_pipeline test_extension_exporter -q
    91 testes; 91 passaram; 0 falharam.

    python -m unittest test_batch_runner -q
    19 testes; 19 passaram; 0 falharam.

    git diff --check
    Passou.

    git diff --exit-code 08cf8b9 -- work/tce-extractor/empacotar-coletor-portatil.ps1 work/tce-extractor/test_portable_end_to_end.py
    Passou; ambos os arquivos proibidos permanecem exatos.

### Self-review, concerns e retomada

- O comportamento ambíguo é fail-closed: alias ambíguo, fonte desconhecida ou
  identidade incompleta mantém incomplete/conflict e deixa a razão observável.
- O teste existente de geometry cache e a evidência visual permaneceram verdes;
  não foi relaxado o gate que exige caixas/geometry para operações visuais.
- Nenhum arquivo de empacotamento, matcher, portal, dataset v1 ou exportador foi
  alterado. A RED conhecida do matcher continua 33/34 e não pertence a este
  round.
- O teste de pacote autocontido continua concern separado porque o empacotador
  preservado no HEAD 08cf8b9 não inclui legal_context.py.
- O handoff global docs/notes/2026-09-08-fundamentacao-automatico-handoff.md
  foi atualizado com este round, ownership, gates, concerns e retomada.
- BLOCKED: nenhum. O checkout não possui remoto configurado; nenhum push foi
  realizado.
