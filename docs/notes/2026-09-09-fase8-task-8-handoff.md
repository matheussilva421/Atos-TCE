# Handoff — Fase 8: painel, execução e histórico

## Estado

Fase 8 foi integrada localmente em 09/09/2026. O painel preserva o caminho
manual, acompanha estado durável sem duplicá-lo no DOM e consulta histórico sem
enviar comandos de retomada. O envio real continua desabilitado.

Commit da integração: `f095545 feat: integrate phase 8 panel redesign`.

## Arquivos centrais

- Interface: `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.html`, `panel.css`, `panel-tokens.css`, `panel-view.js`, `panel.js`.
- Bridge/worker: `lib/bridge-client.js`, `background/service-worker.js`, `manifest.json`, `lib/schema.js`.
- Serviço: `portable/app/automation_store.py`, `portable/app/local_service.py`.
- QA: `tests/panel-view.test.mjs`, `tests/panel.test.mjs`, `tests/bridge-client.test.mjs`, `tests/service-worker.test.mjs`, `test_panel_redesign_browser.py`, `test_automation_api.py`, `test_extension_browser.py`, `test_extension_zip_packager.py`.
- Documentação/pacote: `portable/GUIA-RAPIDO.md`, `portable/GUIA-RAPIDO.html`, `portable/README.md`, `empacotar-extensao-complementar-ato.ps1`.

## Contratos de retomada

1. `GET /api/v1/automation/runs?limit=20&before=<cursor>` lista somente
   resumos do banco da raiz corrente; `before` é opaco.
2. `GET /api/v1/automation/runs/<id>/events?after=<seq>&limit=100` carrega
   cronologia autenticada. Abrir detalhes e carregar mais são somente GETs.
3. Relatórios HTML/CSV continuam sob a raiz do serviço e exigem Bearer token;
   o cliente usa `arrayBuffer()` e nunca inclui o token na URL.
4. O watchdog do worker chama apenas `status({refresh:true})`; `AUTO_STOP`
   limpa o alarme. O polling do painel é `unref` e não impede o fechamento.
5. O modo automático exige início explícito e mantém `real_send_enabled=false`.
   Um resultado `unconfirmed` bloqueia retomada e não exibe `resend`.

## Validação

- JS completo: 248/248.
- Python focal de serviço/API/browser/pacote: 40/40, 1 skip ambiental.
- Recuperação portátil: 4/4.
- Chrome descartável: redesign 1/1 e smoke da extensão 5/5.
- Nenhum portal real, clique real, envio real ou token publicado.
- GitHub: checkout sem remoto configurado; não houve push.

## Próxima etapa

Executar a Fase 9 com portal simulado integrado, reinício separado de worker/
serviço/navegador, duas abas, 25 atos, pendências e timeout. Qualquer gate real
deve parar antes de envio até existir autorização e evidência de confirmação
posterior. Depois disso, revisar a Fase 10 e o pacote final.
