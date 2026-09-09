# Task 8 — redesign operacional, execução e histórico

Data: 09/09/2026
Branch: `codex/fundamentacao-automatico`
Status: implementação local concluída; envio real continua bloqueado pela Fase 9.
Commit: `f095545 feat: integrate phase 8 panel redesign`

## Entrega

- O painel foi reorganizado em **Ato atual**, **Execução** e **Histórico**.
  A fundamentação, fonte documental, valor atual do portal, proposta e estado
  dos sete campos são apresentados em cartões, sem tabela larga.
- `panel-view.js` e `panel-tokens.css` isolam o modelo visual do estado
  operacional. A renderização usa `textContent`, tabs acessíveis, foco por
  setas/Home/End, cartões de campo, estado incerto sem ação de reenvio e
  cronologia persistida do histórico.
- `panel.js` integra capacidades, início explícito, pausa, retomada após
  conciliação, encerramento, relatório HTML, detalhe de eventos, paginação de
  20 execuções e polling de automação a cada 2 s. O preenchimento manual fica
  bloqueado enquanto há execução ativa.
- `bridge-client.js` agora baixa relatório binário autenticado sem colocar o
  token na URL. A API local expõe histórico paginado de execuções e eventos,
  com cursores opacos, limites 100/500 e autenticação.
- O worker usa `chrome.alarms` como watchdog de uma execução ativa; o alarme
  apenas consulta o estado e é removido após encerramento/conclusão. Não há
  clique, envio ou retentativa automática introduzidos por esse mecanismo.
- O smoke browser existente foi adaptado aos cartões; o gate visual sintético
  valida 320/360/480/640 px, sete campos, tabs, foco e histórico. Screenshots
  são temporários e não entram no repositório.
- Allowlist do ZIP, `README.md`, `GUIA-RAPIDO.md` e `GUIA-RAPIDO.html` foram
  atualizados para os módulos e estados do redesign.

## TDD e validação

- `npm test`: 248 testes executados, 248 aprovados, 0 falhas.
- `node --test tests/panel-view.test.mjs tests/panel.test.mjs`: 41/41.
- `python -m unittest test_automation_api test_local_service test_panel_redesign_browser test_extension_browser test_extension_zip_packager -q`: 40/40, 0 falhas, 1 skip ambiental.
- `python -m unittest test_automation_recovery -q`: 4/4.
- `python -m unittest test_panel_redesign_browser -q`: 1/1 no Chrome descartável.
- `python -m unittest test_extension_browser -q`: 5/5 em perfil descartável.
- `python -m unittest test_extension_zip_packager -q`: 1/1.
- `git diff --check` e validações de sintaxe/compilação: verdes nesta rodada.

As regressões cobertas incluem serviço antigo sem automação, ponte sem
pareamento, polling sem anúncios repetidos, foco de tabs, paginação sem
retomada, acesso autenticado ao relatório/histórico e ausência de token em
URLs ou projeções públicas.

## Limites

- Nenhuma sessão real do portal foi aberta ou alterada nesta fase.
- Nenhum botão real `Complementar Ato` foi clicado.
- `real_send_enabled=false`; o simulador e o worker local não constituem
  qualificação ponta a ponta.
- A Fase 9 ainda precisa executar a matriz local integrada e, somente com
  autorização/checkpoint separado, a observação real supervisionada.
- Não há remoto Git configurado; portanto não há push.

## Retomada

1. Conferir `git status --short` e o commit desta fase.
2. Reexecutar `npm test` e os testes Python focais se houver mudança no
   contrato de histórico/painel.
3. Iniciar a Fase 9 pelos testes locais de 25 atos, reinícios e duas abas.
4. Não habilitar envio real nem usar portal de produção sem o gate documentado
   na seção 14 do plano.
