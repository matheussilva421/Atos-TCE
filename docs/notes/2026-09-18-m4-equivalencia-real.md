# Equivalência real da análise (M4) contra o acervo canônico

**Data:** 2026-09-18 · **Branch:** `codex/mesa-local-refactor`

Este é o gate real de M4 ("equivalência real em 10 processos") executado sem
portal e sem tocar o acervo canônico: uma visão isolada em `tmp/` recebe
hardlinks dos PDFs de 10 processos, o motor promovido roda sobre ela e o
resultado é comparado com os oráculos que a rodada legada deixou em
`work/tce-extractor/acervo-tce/`.

## O que foi comparado

| Medida | Resultado |
|---|---|
| Processos | 10 processos canônicos reais, 15 documentos cada |
| Status do processo (`partial`) | **10 de 10 iguais** |
| Campos extraídos | 70 |
| Campos iguais ao `form_value` do oráculo (`dados-complementar-ato.json`) | **70 de 70** |
| Campos iguais ao `source_value` bruto | 60 de 70 (as 10 diferenças são datas: o oráculo guardou a prosa "06 de marco de 2024" e o pipeline normalizou para "06/03/2024"; o valor de formulário coincide) |
| Classificação por documento contra `pdfs-alvo-manifest.json` | **20 de 20 iguais** |

Amostra (escolhida por ter campos preenchidos no oráculo e poucos documentos):
`100126/2026`, `100611/2025`, `100719/2025`, `101338/2026`, `101789/2026`,
`103694/2025`, `103700/2025`, `103855/2025`, `104103/2025`, `104260/2025`.
Cada processo levou entre 0,5 s e 1,0 s (PDFs com texto nativo; o OCR continua
disponível e é o mesmo runtime fixado no pacote).

## Dois defeitos encontrados e corrigidos no caminho

1. **O motor não enxergava nenhum processo canônico.** O pipeline promovido lê
   `archive/processos/<pasta>/processo.json` e `evento-*/evento.json`, e o
   importador de M1 escreve só os documentos. Resultado: `scan_archive` não
   encontrava processo algum e `analyze_one` falhava com `KeyError`. Corrigido
   com `app/analysis/execution_view.py`, que renderiza o manifesto a partir das
   linhas canônicas (o SQLite continua sendo o dono do estado) e é idempotente;
   o serviço agora passa processo e documentos ao adaptador antes de chamar o
   motor.
2. **Prefixo de caminho incompatível.** A tabela `documents` guarda
   `relative_path` relativo à raiz de dados (`archive/processos/...`), e o motor
   resolve contra a raiz do acervo: todo documento caía como `missing` e nenhum
   campo era extraído. O renderizador agora remove o prefixo `archive/`.

Os dois têm teste em `tests/test_analysis_execution_view.py` (8 testes), incluindo
um que exige que o motor resolva todos os documentos recebidos.

## Como reproduzir

```powershell
# visão isolada com hardlinks (não copia bytes, não toca o acervo canônico)
python tmp/m4-equivalencia/build_view.py    # script descartável usado no ensaio
python tmp/m4-equivalencia/run.py 10        # roda o adaptador promovido
python tmp/m4-equivalencia/compare.py       # compara com os oráculos legados
```

Os scripts ficaram em `tmp/` (fora do Git) porque são de ensaio; o que é
permanente é o código em `app/analysis/execution_view.py` e os testes.


## Ensaio pelo serviço da Mesa (caminho completo)

Depois do motor, o mesmo acervo isolado rodou pelo **serviço** da Mesa
(`AnalysisService.analyze_one`), que é o caminho do botão "Analisar": 11 linhas
`(processo, interessado)` — 10 processos, um deles com dois interessados — foram
registradas em banco novo, analisadas e lidas de volta.

| Medida | Antes da correção | Depois |
|---|---|---|
| Linhas analisadas | 11 | 11 |
| Campos persistidos | 91 (blocos fundidos) | 77 (um bloco por linha) |
| Campos iguais ao `form_value` | 85 de 91 | **77 de 77** |
| Linhas `PRONTO` | 11 | 9 (as 2 do processo ambíguo vão para REVISAR) |
| Campos com evidência e documento ligado | 63 | 63 |

A primeira passada expôs um defeito real: `normalize_analysis` fundia **todos**
os blocos na mesma linha, então cada linha `(process_key, interested)` recebia
campos dos dois interessados. Em `103700/2025` os nomes são quase iguais
("FRANCISCA DE ASSIS SOARES NOGUEIRA" e "... NOGUEIRA DE CASTRO") e os valores
apareciam trocados entre as linhas — o motor, porém, produzia os dois blocos
corretos, o que localizou o problema no normalizador.

Correção (TDD, 4 testes): o serviço passa o interessado da linha ao
normalizador, que mantém apenas o bloco do interessado canônico correspondente
(`app/core/identity.normalize_interested`); quando o resultado não traz o bloco
daquela linha, a linha fica **REVISAR** com aviso e sem campos de terceiros, em
vez de marcar PRONTO com dado alheio. Sem a dica de interessado (chamadas
antigas e testes de fixture), o comportamento anterior é preservado.
 ## Achados colaterais

- `dados-complementar-ato.json` tem 15 chaves de processo duplicadas (735
  registros para 720 chaves distintas); a comparação usou o registro com mais
  campos preenchidos.
- O oráculo `pdfs-alvo-manifest.json` cobre 20 documentos desses 10 processos; a
  classificação do motor bateu nos 20.
