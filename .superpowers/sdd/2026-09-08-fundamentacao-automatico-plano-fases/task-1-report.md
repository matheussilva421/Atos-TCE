# Relatório — Fase 1: contexto documental completo e compatível

Data: 2026-09-08
Branch: `codex/fundamentacao-automatico`
Brief: `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/task-1-brief.md`

## Status

Implementação local da Fase 1 concluída, com testes focais verdes e sem
qualquer ação no portal. O matcher JavaScript da Fase 0 permanece
intencionalmente RED. O commit solicitado será registrado após este relatório
ser incluído no conjunto de mudanças.

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
75 testes executados; 75 passaram; 0 falharam.
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
de implementação é `feat: publish versioned legal evidence context`.

Retomada: confirmar o SHA final deste commit, revisar o diff limitado aos
arquivos listados, e somente então decidir a fase/autoridade para incluir o
novo módulo no pacote portátil. Não corrigir o matcher nesta retomada.
