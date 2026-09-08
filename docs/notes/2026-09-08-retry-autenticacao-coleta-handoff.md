# Handoff — retry e autenticação da coleta portátil — 08/09/2026

## Resumo

Implementado o contrato de download da Fase 6 no fluxo portátil. O coordenador continua sendo o único componente que grava hash, deduplicação, versões e checkpoint; runspaces executam somente o downloader autenticado.

- HTTP 429 respeita `Retry-After`, tenta no máximo três vezes e sinaliza `reduce_concurrency`.
- Após 429, chamadas posteriores reduzem `MaxDownloads` efetivo para 1.
- HTTP 401 retorna `auth_required` sem retry; HTTP 403 retorna `suspended` sem retry.
- HTTP 400 permanece erro documental explícito, sem retry.
- Mensagens, resultados e checkpoints removem URLs/tokens/credenciais.
- O coletor avisa o operador, registra falha sanitizada e para novos processos quando a sessão exige login ou suspensão; o modo completo também não analisa processos não coletados após essa parada.
- Se autenticação falhar no primeiro evento, eventos posteriores do mesmo processo não são baixados.

## Arquivos alterados

- `work/tce-extractor/portable/TcePortable.Core.psm1`
- `work/tce-extractor/portable/Coletar-Processos-TCE.ps1`
- `work/tce-extractor/tests/Test-TcePortable.ps1`

O contrato RED/GREEN foi inicialmente criado por worker Luna xhigh e revisado/integrado no checkout principal. Não houve chamada ao portal real.

## Testes executados

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\work\tce-extractor\tests\Test-TcePortable.ps1`
  - 114 passaram, 0 falharam.
  - Repetição em três execuções: 114/114 em todas.
  - Inclui 429, Retry-After, máximo de tentativas, redução de concorrência, 401/403, 400, ausência de segredo e parada após autenticação.
- `python -m unittest discover -s . -p 'test_*.py' -q`
  - 254 passaram, 0 falharam, 3 skips ambientais/fixture.
- `node --test --test-reporter=dot` em `portable/extensao-complementar-ato`
  - 118 passaram, 0 falharam.
- `node --test --test-reporter=dot` em `portable/app/web`
  - 4 passaram, 0 falharam.
- `tests/Test-PortableMenu.ps1`
  - 74 passaram, 0 falharam.
- `tests/Test-PortableReset.ps1`
  - 31 passaram, 0 falharam, 1 skip ambiental de symlink/reparse.
- `git diff --check`
  - verde.

## Decisões e limitações

- O limite global de downloads é uma recomendação de sessão: depois de 429, fica em 1 até o processo do coletor terminar.
- O coletor não tenta renovar login automaticamente; ele preserva o checkpoint parcial e pede retomada após autenticação manual.
- A parada é segura e cooperativa: downloads já iniciados no lote atual terminam; não há cancelamento forçado de requests.
- O teste de concorrência usa sequência protegida por mutex para não depender de relógio não monotônico entre runspaces.

## GitHub / retomada

- Alterações ainda precisam ser commitadas após a revisão final.
- `origin` não está configurado; push não é possível neste checkout.
- O ZIP isolado da extensão não muda com esta etapa:
  `artifacts/extensao-complementar-ato-2026-09-08-v4.zip`, SHA-256 `8B0BBBA813EA1D9B8156AAC60D374A85ED1D16D2AF1B55C77D1809ADCF61E46`.

## Próximos passos

1. Revisar o diff final e executar novamente os gates focados.
2. Atualizar o handoff integrado e o plano com os resultados.
3. Commitar as alterações locais.
4. Manter pendentes os gates externos: login/QA manual na Área Restrita, benchmark dos mesmos 20 processos, teste do ZIP em ambiente sem Python/Node no PATH e eventual segundo PC.
