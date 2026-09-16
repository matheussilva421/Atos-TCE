# Handoff — análise integral do projeto (16/09/2026)

## O que foi feito

Análise somente leitura do projeto inteiro, com foco na automação da
Complementação de Ato na Área Restrita, e execução dos gates offline
disponíveis. Nenhum login, preflight, `APPLY_FIELDS`, envio, purga ou
publicação de dado privado.

O relatório completo para o próximo agente é
`docs/notes/2026-09-16-relatorio-integral-projeto-analise.md`. Ele contém:
resumo executivo, mapa de camadas, análise do problema da Área Restrita
(obstáculos, contratos de segurança, bloqueios atuais e alternativas A–D),
inventário de problemas por severidade, backlog priorizado, evidência de testes
de hoje, riscos, runbook de retomada e decisões que dependem do usuário.

## Estado observado

- `main == origin/main == 2cb5a54791617df2e47d11eba40d7321e12252ca`, árvore limpa.
- Extensão: 406/406 em três execuções e 405/406 em uma (flake no teste de
  confirmação do envio automático, `tests/panel.test.mjs:1077`).
- Web: 6/6. Python da etapa oficial do verificador (`discover -s portable`):
  6 testes. Python de automação (fora do gate): 89 testes, OK, 1 skip.
- Matriz QA vigente: 24 `PASS_FIXTURE`, 1 `PASS_PACKAGE`, 5 `BLOCKED`,
  0 `PASS_REAL`.
- `acervo-tce/automacao/qualificacao.json` inexistente no checkout e na
  extração privada `Versions/...-2026-09-16-final-v2`.
- `work/tce-extractor/outputs/live-real-fase11h-sector-lot50` e `tmp/fase41/`
  não existem mais: o runbook antigo precisa ser substituído pelo do relatório.

## Arquivos criados nesta tarefa

- `docs/notes/2026-09-16-relatorio-integral-projeto-analise.md`
- `docs/notes/2026-09-16-analise-integral-handoff.md` (este arquivo)

## Problemas novos ou confirmados hoje

1. **P1** — flake no painel: `render()` zera incondicionalmente o checkbox
   `automation-auto-submit` (`sidepanel/panel.js:540`) e o teste espera a
   carga de capabilities com orçamento fixo de `setImmediate`.
2. **P1** — `verify-project.ps1` não descobre os 49 módulos `test_*.py` da raiz
   de `work/tce-extractor` (automação, serviço local, qualificação).
3. **P1** — `real_portal_session.py:188` ainda usa `--ignore-certificate-errors`.
4. **P2** — runbook de 12/09 aponta para artefatos inexistentes neste checkout.
5. **P2** — `GUIA-RAPIDO.md` diz "sem automação de atos" enquanto o restante do
   projeto trata a automação como em qualificação.
6. **P2** — o handoff de 12/09 registra cancelamento da automação que os
   documentos de 16/09 contradizem; confirmar escopo com o usuário antes de
   qualquer acesso ao portal.
7. **P3** — estado privado e oito montagens `.package-staging-*` permanecem no
   checkout; `staging-task5-verified` não pode ser removida sem checar o
   empacotador.
8. **P3** — Tarefas 9.2/9.3 do plano pressupõem quarentena e benchmark do
   checkout antigo, que não existe mais.

## Testes executados (resumo)

```text
npm test (extensão)                                        -> 406/0, 406/0, 406/0 e 405/1 (flake)
node --test tests/*.test.mjs (web)                         -> 6/6
python -m unittest discover -s portable -p "test_*.py" -q  -> Ran 6 tests, OK
python -m unittest test_automation_api test_automation_qualification +  test_automation_store test_automation_report test_local_service -q
                                                           -> Ran 89 tests, OK (skipped=1)
```

Não executados: suíte PowerShell, `TESTAR-PACOTE.ps1`, `qa_matrix_runner.py`,
empacotamento, qualquer acesso autenticado, preflight ou envio.

## GitHub

- Branch `main` alinhada com `origin/main`; commit e push deste relatório e
  handoff registrados no fechamento desta tarefa (ver rodapé de publicação).

## Pendências e próximos passos

1. Confirmar com o usuário o escopo vigente da automação (P2-3).
2. Corrigir P1-1 e P1-2 (painel + gate Python) com TDD e rodar os gates amplos.
3. Remover o bypass de TLS do runner ou trocar a observação para o gravador
   Playwright.
4. Reconciliar documentação (README, GUIA-RAPIDO, nota de supersessão no handoff
   de 12/09).
5. Reconstruir a superfície de piloto a partir de `Versions/...-final-v2`,
   subindo o serviço com `--automation-pilot` e mantendo `--enable-real-send`
   desabilitado.
6. Só então repetir observação e executar os três preflights reais; o primeiro
   envio supervisionado exige autorização imediata e específica.

## Limites mantidos

`autoSubmit=false` e `real_send_enabled=false` continuam sendo a fronteira
segura até a qualificação real: nenhuma fixture, ZIP ou matriz substitui
evidência de efeito no portal.
