# Handoff - Liberação do envio automático em lotes de até 100 atos (2026-09-18)

## Contexto

O operador pediu a liberação da **complementação e envio automáticos** (não
apenas o preenchimento dos campos), **em lotes de até 100 atos**. A fronteira
anterior - real_send_enabled=false até existir qualificação baseada em evento
real - foi substituída por decisão explícita do operador: a ativação passa a
ser um interruptor de linha de comando (--enable-real-send, exposto como
INICIAR.cmd envio-real) e o arquivo automacao/qualificacao.json passa a valer
como evidência registrada, sem bloquear a liberação.

## Mudanças (TDD)

### 1. Serviço (portable/app/local_service.py)

* --enable-real-send não exige mais qualificação válida; o motivo da inspeção
  fica em real_send_qualification e é publicado em
  dados-locais/bridge/service.json junto de real_send_enabled.
* Novo teto duro: AUTO_SUBMIT_MAX_LOT_SIZE = 100. auto_submit em modo batch com
  lot_size maior que 100 responde 400 AUTO_SUBMIT_LOT_LIMIT; lot_size é
  opcional e ausente mantém o padrão do worker (100).
* Sem o switch, tudo permanece fail-closed: 409 REAL_SEND_DISABLED antes de
  criar a execução.

### 2. Extensão

* lib/automation-schema.js: MAX_AUTO_SUBMIT_BATCH = 100, validação cruzada de
  autoSubmit com lotSize e helper exportado autoSubmitBatchLimit().
* background/automation-controller.js: a fila do lote automático para em
  min(lotSize, 100); as identidades excedentes ficam pendentes para o próximo
  lote; o limite é restaurado no rehydrate; analyze (somente leitura) segue sem
  limite.
* sidepanel/panel.js: o seletor de lote é limitado a 100 quando o opt-in está
  marcado, e a confirmação informa o tamanho efetivo do lote.
* sidepanel/panel.html: notas do lote e do opt-in atualizadas.

### 3. Launcher

* portable/app/menu.ps1: novos switches -EnableRealSend em
  Start-TcePortableMenu e Start-TceLocalService, que acrescentam
  --enable-real-send ao serviço.
* portable/INICIAR.cmd: novo comando envio-real (CRLF preservado).

### 4. Documentação

* README raiz e README portátil descrevem o opt-in, o teto de 100 e o comando
  INICIAR.cmd envio-real.
* Testes de documentação e de launcher atualizados para o novo contrato.

## Testes RED-GREEN

| Caso | Arquivo |
|---|---|
| Serviço libera com switch explícito sem qualificação | test_automation_api.py |
| Lote automático rejeita lot_size 101/300 e aceita 100 | test_automation_api.py |
| Schema rejeita autoSubmit com lotSize acima de 100 e expõe o helper | tests/automation-schema.test.mjs |
| Controlador congela fila de 2 atos e deixa 3 pendentes | tests/automation-controller.test.mjs |
| Launcher expõe envio-real e EnableRealSend | tests/Test-PortableMenu.ps1 |
| README declara envio desabilitado por padrão e o comando explícito | tests/Test-DocumentationTracking.ps1 |

## Gates executados

* verify-project.ps1: exit 0; 1251 executados, 1249 aprovados, 0 falhas,
  2 skips; estágios extension (479/479), web (6/6), python portable (6/6),
  powershell (596 executados, 0 falhas), package/audit (82 executados,
  2 skips), automation (81/81) e git diff --check verdes.
* test_local_service.py: 26 executados, 0 falhas, 1 skip.
* Correções durante o gate: INICIAR.cmd ficou com LF e quebrava
  test_portable_cmd_launcher_uses_windows_line_endings (normalizado para CRLF);
  test_transfer_requests_pause_and_waits_for_active_runtime_to_drain falhou uma
  vez por lock transiente de collector.json (WinError 32) e passou na
  reexecução.

## Pacote em uso

outputs/qa-extract-2026-09-17 foi sincronizado com os oito arquivos de código
alterados (INICIAR.cmd, README, app/local_service.py, app/menu.ps1,
automation-controller.js, automation-schema.js, panel.html, panel.js). O acervo
não foi tocado.

Verificação do pacote depois da sincronização:

* Serviço iniciado com --enable-real-send na própria pasta:
  metadata real_send_enabled=True qualificacao=missing; capabilities
  real_send_enabled=true; lote 101 responde 400 AUTO_SUBMIT_LOT_LIMIT; lote 100
  segue para a validação do dataset (409 DATASET_MISMATCH com hash sintético),
  ou seja, o gate de envio está liberado e o teto vale no artefato real.
* TESTAR-PACOTE.ps1: 6 de 7 passos verdes; a auditoria private acusa 9 achados,
  todos sob dados-locais/bridge (diretório, .operation.lock e service.json, com
  o código de pareamento gravado pelo uso do INICIAR.cmd). Não há achado em
  nenhum arquivo do código sincronizado. O empacotador exclui dados-locais do
  ZIP, então uma reconstrução pelo helper não carrega esses itens. Para deixar
  a pasta de trabalho auditável, basta remover dados-locais/bridge (o serviço
  recria no próximo início).

O ZIP privado de referência
(Atos-TCE-Professor-IPERN-completo-2026-09-17.zip, SHA-256 cf64e3f8...) não
contém esta liberação. Para distribuir, reempacotar com o próprio helper a
partir da pasta atualizada:

    Set-Location outputs\qa-extract-2026-09-17
    .\Empacotar-Acervo-Completo.ps1 -Destino ..\Atos-TCE-Professor-IPERN-completo-2026-09-18.zip

O helper reempacota a pasta inteira (acervo incluído) via prepare_transfer.py e
package_complete_archive.py, com auditoria e CRC, sem rebaixar nem reanalisar
nada. Não montar o ZIP manualmente: isso pularia as exclusões (dados-locais,
.part/.tmp, perfis/cookies) e a auditoria.

## Como usar

1. INICIAR.cmd envio-real (serviço com real_send_enabled=true).
2. Login manual na Área Restrita e marcador vigente selecionado.
3. Painel: importar o JSON, marcar **Concluir automaticamente os atos
   elegíveis** e confirmar.
4. Cada execução processa até 100 atos elegíveis; os demais ficam pendentes
   para o próximo lote. Resultado incerto pausa o lote sem reenvio.
5. INICIAR.cmd e INICIAR.cmd abrir-mesa continuam sem envio real.

## Risco conhecido

* A qualificação real deixou de ser pré-requisito; o observador de resultado
  por ato continua obrigatório e o fundamento legal continua fail-closed
  (contexto bloqueado não é preenchido nem substituído).
* O lote grande (100) ainda não foi exercitado contra o portal real; o smoke
  real deste fluxo está pendente.

## Pendências

* Smoke real supervisionado com envio-real e lote pequeno para observar
  send_intent, send_issued e send_confirmed no portal.
* Reempacotar o ZIP privado se for distribuir.
