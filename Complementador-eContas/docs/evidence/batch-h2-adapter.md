# F7 — H2 adaptador: salvamento real automático (GATE A)

Data: 06/11/2026
Estado: `H2_ADAPTER_PASS`

O adaptador executou salvamentos reais no Chrome QA, com checkpoint, clique único, diálogo homologado e verificação independente. Resultado: **10 atos salvos e 10/10 verificados**, nenhum `SAVE_UNCERTAIN`.

## Evidência

- Build QA: `work/qa-save-build-2026-11-05`, background SHA-256 `C69E92C062FE810F3C98F63CF8FDCCAC6F21FC2BE60C5F5EB23537B2A832CBDB`.
- Filtros: Mutirão - Educação; ATO COMPLEMENTADO = Não; ProcessosNoSetor; semDistribuicao.
- Primeira execução 1/1: processo com múltiplos interessados, 0 salvos.
- Segunda execução 25/10: 25 examinados, 10 salvos, 15 revisão, 0 incertos, 10 `SAVE_ACK`.
- Verificação independente: 10/10 abas do Complementar Ato sem o botão “Complementar ato”, com formulário renderizado e rota/processo corretos.
- Nenhum segundo clique; nenhum ato antigo reaberto.

## O que foi usado

- Diálogo estrutural: **Complementar ato** / **sim, complementar** / **NÃO**.
- Checkpoint `SAVE_ARMED` antes do clique; tentativa única; `SAVE_UNCERTAIN` sem retry.
- Verificação em aba nova com rota/processo/formulário/ausência do botão.
- Limpeza pós-`CONFIRMED`: as duas abas de trabalho do processo salvo são fechadas; revisões/incertezas permanecem abertas.

## Limitações

- O kill físico do service worker/reinício do navegador não foi executado (`MV3_WORKER_KILL_TEST_NOT_RUN`).
- Autosave do portal continua `UNKNOWN`.
- O build 2.0.4 difere do build homologado por limpeza pós-save, Meus Processos, presets por rota e tempos ampliados; o caminho de preenchimento/salvamento é o mesmo.
- O Chrome profissional não foi tocado.

## Veredito

`H2_ADAPTER_PASS` com 10 atos reais verificados. O gate F8 pode ser considerado aprovado pelo lote 25/10 documentado em `batch-h3-adapter.md`.
