# Gate de benchmark dos mesmos 20 processos — handoff

Data: 2026-09-08

## Resultado

**BLOQUEADO — não medido.** Não há observações reais suficientes para declarar
baseline, ganho, OCR reutilizado, tempo de preparação, mediana/p95 de
sincronização ou contagem de cliques para os mesmos 20 processos.

O bloqueio não foi convertido em números estimados. O reprodutor permanece
pronto para uma execução posterior com uma amostra explicitamente identificada
e observações capturadas pelo operador.

## Evidência e limite

- O plano ainda marca como pendente a medição dos 20 processos no item da
  Fase 0 (`docs/notes/2026-09-08-fluxo-portatil-plano-implementacao.md:120`) e
  no gate comparativo da Fase 8 (`...plano-implementacao.md:331`).
- O handoff principal registra que o benchmark não foi comprovado e que a
  entrega continua candidata, não release validada
  (`docs/notes/2026-09-08-fluxo-portatil-execucao-handoff.md:215-223` e
  `:260`). Ele também registra que não houve coleta real no QA manual
  (`...execucao-handoff.md:77-80`).
- O snapshot portátil disponível contém `ordem-portal.json` com 227 processos,
  capturado em `2026-09-05T15:40:08.975038-03:00`; ele não é o lote de 20 nem
  possui a trilha temporal/humana do benchmark. A lista histórica
  `work/tce-extractor/processos-61.json` contém 61 processos. Nenhuma das duas
  foi tratada como “os mesmos 20”.
- A sessão autenticada do e-Contas estava acessível em leitura e mostrava 170
  processos na lista atual, com 100 visíveis na página; isso confirma acesso
  visual naquele instante, mas não identifica a amostra histórica de 20 e não
  foi usado para escolher arbitrariamente os primeiros 20.
- Não foram encontrados registros de início/primeiro resultado/preparação,
  comparação humana, cliques, reutilização de OCR ou amostras de sincronização
  em `work/tce-extractor/outputs`/`qa-mcp-live`. Hardware e rede da execução do
  benchmark também não foram observados em um run real.
- Não houve navegação de processo, download, coleta, preenchimento, envio ou
  finalização no portal durante este gate.

## Ferramenta criada

`work/tce-extractor/qa_benchmark_20.py`

O reprodutor:

- exige uma lista JSON explicitamente fornecida com exatamente 20 chaves
  canônicas únicas e preserva sua ordem;
- cria somente um template não medido (`status: template`), sem selecionar
  processos implicitamente;
- exige timestamps timezone-aware para cada processo e deriva as durações
  somente desses timestamps;
- exige contagem explícita de cliques, booleano explícito de OCR reutilizado e
  ao menos uma amostra explícita de sincronização por processo;
- rejeita runs que não estejam em `status: complete`, amostras incompletas ou
  ordens diferentes entre baseline e candidato;
- calcula mediana/p95 somente após validar os dados reais e deixa a fronteira
  de medição no JSON de resumo;
- não acessa o portal, não chama código de produção e não modifica o acervo.

Execução futura, após obter a lista exata e medir o fluxo autorizado:

```powershell
python -B work\tce-extractor\qa_benchmark_20.py init `
  --process-list <lista-exata-de-20.json> `
  --mode baseline `
  --network "<rede-observada>" `
  --output <baseline.json>

# preencher as observações reais e mudar status para complete
python -B work\tce-extractor\qa_benchmark_20.py validate --run <baseline.json>
python -B work\tce-extractor\qa_benchmark_20.py summarize `
  --baseline <baseline.json> `
  --candidate <candidate.json> `
  --output <benchmark-summary.json>
```

O script bloqueia explicitamente as listas existentes de 61 e 227 processos;
os testes executados confirmaram que nenhum arquivo de saída é criado nesses
casos.

## TDD e validação

RED observado antes da implementação: `--self-test` falhava porque os
contratos `validate_process_keys` e `derive_process_metrics` ainda não
existiam.

GREEN e verificações:

- `python -B work\tce-extractor\qa_benchmark_20.py --self-test`: **5 testes,
  5 passaram, 0 falharam**.
- `python -B -m py_compile work\tce-extractor\qa_benchmark_20.py`: **verde**.
- `init` com `processos-61.json`: bloqueio esperado, exit code 2, sem saída.
- `init` com o `ordem-portal.json` do snapshot: bloqueio esperado, exit code 2,
  sem saída.
- `rg` confirma uma única definição de `main` no reprodutor.

Os testes são de contrato do reprodutor e não constituem benchmark de portal,
OCR ou hardware.

## Arquivos deste gate

- Criado: `work/tce-extractor/qa_benchmark_20.py`.
- Criado: este arquivo de handoff separado.
- Handoff principal: **não alterado**.
- Código de produção: **não alterado por este gate**.
- Alterações pré-existentes e não relacionadas no working tree foram
  preservadas; não fazem parte deste gate.

## Retomada

1. Obter ou registrar a lista canônica dos mesmos 20 processos do baseline;
   não usar os primeiros 20 de uma listagem diferente.
2. Em uma sessão autorizada, registrar no template os eventos reais do fluxo
   existente e do candidato, incluindo rede, hardware, modo, OCR, sincronização
   e cliques.
3. Marcar cada run como `complete`, executar `validate` e então `summarize`.
4. Só atualizar o resultado comparativo se os dois runs tiverem a mesma ordem e
   as 20 observações completas. Até lá, o gate deve permanecer **não medido**.
