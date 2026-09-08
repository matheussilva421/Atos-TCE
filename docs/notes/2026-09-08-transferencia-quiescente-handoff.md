# Handoff — transferência portátil quiescente — 08/09/2026

## Resumo

Foi fechada a corrida entre coleta/serviço local e `prepare_transfer`. A
transferência agora reserva `dados-locais/bridge/.operation.lock` e recusa
gerar ZIP quando encontra serviço ou coleta ativos. O coletor e o serviço
usam o mesmo lease; locks e marcadores obsoletos podem ser recuperados quando
o PID não está mais vivo. Falhas de empacotamento liberam o lease em `finally`.

Esta implementação usa recusa segura e retry explícito, não encerra processo,
não força parada e não afirma que o coordenador externo foi drenado.

## Arquivos alterados

- `work/tce-extractor/portable/app/prepare_transfer.py`
- `work/tce-extractor/portable/app/local_service.py`
- `work/tce-extractor/portable/app/menu.ps1`
- `work/tce-extractor/portable/Coletar-Processos-TCE.ps1`
- `work/tce-extractor/test_prepare_transfer.py`
- `work/tce-extractor/tests/Test-TcePortable.ps1`
- `work/tce-extractor/tests/Test-PortableMenu.ps1`

## Contrato resultante

- serviço e coletor disputam um lock exclusivo fora do acervo;
- `prepare_transfer` não sobrescreve destino e não cria ZIP com runtime ativo;
- `service.json` e `collector.json` com PID vivo bloqueiam a transferência;
- PID morto permite remover marcador/lock obsoleto e prosseguir;
- remoção do lock exige o token do lease atual;
- `dados-locais` continua excluído do pacote;
- o menu não inicia o serviço quando há operação de transferência em curso.

## Testes

- `python -m unittest test_prepare_transfer test_local_service test_bridge_auth -q`
  — 16 pass, 0 falhas;
- `tests/Test-TcePortable.ps1` — 84 pass, 0 falhas;
- `tests/Test-PortableMenu.ps1` — 74 pass, 0 falhas;
- parser PowerShell do coletor — OK;
- regressão focada Python (estado, serviço, geometria, pipeline, mesa, pacote e
  QA fixture) — 177 pass, 0 falhas, 2 skips ambientais.

A suíte Python completa na worktree nova não pôde usar os quatro artefatos
ignorados de runtime/licenças (`portable/runtime-manifest.json` e
`portable/licenses/README.md`); isso é uma limitação da worktree, não falha
introduzida pelo patch. A suíte completa deve ser repetida no checkout com o
runtime local materializado.

## Pendências

- revisão do coordenador de download/OCR ainda é feita por recusa segura, não
  por uma API formal de pausa e drenagem;
- QA autenticado no portal, benchmark de 20 processos e segundo PC continuam
  gates externos;
- integrar a branch somente após a regressão completa no checkout principal.

## Retomada

Na branch `codex/transfer-quiescence`, conferir `git diff --check`, executar a
regressão completa no checkout principal e então integrar o commit. Se houver
serviço/coleta ativo, pará-lo pelo fluxo explícito e repetir a transferência;
nunca remover manualmente lock com PID vivo.
