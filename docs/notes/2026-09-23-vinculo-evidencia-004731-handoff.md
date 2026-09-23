# Handoff: vínculo das fontes de `004731/2024`

Data: 2026-09-23

## Resultado

Corrigida a associação entre os campos analisados de `004731/2024` e o PDF
fonte. A causa era uma diferença de pontuação no título: a análise registrou
`Volume Digitalizado - 1`, enquanto o acervo registra `Volume-Digitalizado-1`.

`app/analysis/normalize.py` agora compara títulos ignorando espaços e
pontuação. A resolução preserva o comportamento fail-closed: títulos que
colidem após normalização e eventos com mais de um documento sem título
identificável continuam sem vínculo. A Mesa não escolhe um arquivo arbitrário.

No banco local, seis campos encontrados foram associados ao documento `14733`
(`Volume-Digitalizado-1`): `cargo`, `data_nascimento`, `data_publicacao_doe`,
`fundamento_legal`, `matricula` e `modalidade`. As páginas preservadas são 90
ou 93; o PDF local tem 128 páginas. A chamada `evidence_for_field` retorna
documento e página para os seis campos. O snapshot anterior do SQLite está em
`data/atos-tce.before-source-link-004731-20260923.db` (dados locais ignorados
pelo Git).

`genero` permanece `missing` sem fonte, e o estado do processo permanece
`ERRO`: esse estado vem de uma falha anterior de navegação ao preencher o ato,
fora do escopo deste reparo.

## Arquivos e testes

- Alterados: `app/analysis/normalize.py`, `tests/test_analysis_service.py`.
- Teste focado: `python -m unittest tests.test_analysis_service -q` — 27
  aprovados, 0 falhas.
- Suíte da Mesa: `python -m unittest discover -s tests -p 'test_*.py' -q` —
  571 executados, 1 ignorado, 0 falhas.
- Gate `work/tce-extractor/verify-project.ps1` — 1.258 executados, 1.256
  aprovados, 2 ignorados, 0 falhas.
- Descoberta Python legada em `work/tce-extractor` — 528 executados, 9
  ignorados, 1 erro no teste de drenagem de `collector.json` durante limpeza
  concorrente (`test_prepare_transfer...`). A repetição isolada do teste passou
  (1/1). Não houve alteração nesse módulo legado.
- PDF verificado localmente: página 90 existe. Nenhum teste ou ação acessou o
  portal autenticado.

## Git e retomada

Commit `1afd57348211b6f3d66cc99abb2c4744985428ee` (`fix: link analysis fields
to normalized PDF titles`) foi enviado com sucesso para
`origin/codex/mesa-local-refactor`. O branch ficou alinhado com o remoto. O
arquivo não rastreado `work/tce-extractor/.codex-live-pilot.py` foi preservado
e não foi incluído no commit.

O `START.cmd` atual executa `app.main` e o README identifica `app/` como a Mesa
suportada; o `AGENTS.md` ainda descreve o layout legado em
`work/tce-extractor`. A validação do legado foi executada separadamente para
respeitar ambos os contextos sem alterar a árvore antiga.

Para conferir a interface depois de iniciar a Mesa, abrir um processo e clicar
em **ver fonte** em um dos seis campos. O serviço não estava escutando na porta
18743 durante este trabalho; para iniciá-lo no diretório do projeto:

```powershell
.\START.cmd --data-root data --port 18743
```
