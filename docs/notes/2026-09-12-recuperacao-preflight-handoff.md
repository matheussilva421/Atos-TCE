# Recuperação do preflight real — 2026-09-12

> **ENCERRADO POR MUDANÇA DE ESCOPO DO USUÁRIO.** Automação cancelada. A entrega vigente é o ZIP manual registrado em `2026-09-12-pacote-manual-handoff.md`. Não seguir as instruções de retomada de pilotos abaixo. Bridge piloto encerrada e nenhum ato enviado.

## Escopo e estado inicial

Usuário autorizou analisar, testar na Área Restrita e corrigir o bloqueio. Teste limitado à preparação/releitura, sem envio ou finalização. Preservar Chrome pessoal e originais. Trabalhar no Chrome isolado CDP 19232 e bridge piloto 18743 já existentes.

Confirmado nesta sessão: main em b8c0024, origin configurado; 8 arquivos modificados herdados (3 módulos, 3 testes, handoff anterior e ledger). Baseline `npm test`: 359 executados, 359 aprovados, 0 falhas. Bridge PID 20564 e Chrome PID 28564 vivos. Portal acessível com 12 molduras; broadcast de snapshot respondeu role unknown. Evidência privada: tmp/fase41/session7-probe.json; log de testes: tmp/fase41/session7-baseline-node.log.

## Em andamento

Reproduzir sessão sem pareamento, recuperar conexão e testar os três preflights 100065/2026, 100273/2025 e 103795/2025. Cada novo defeito de comportamento exige RED/GREEN. A suíte local verde não fecha Tarefa 4.2.

## Retomada

## Bloco 1 — reprodução e correções

- Pareamento vencido reproduzido pelo painel; restart local em modo piloto e pareamento fresco resolveram a conexão. Reload de extensão invalida os content scripts antigos: a lista deve ser recarregada pelo Consultar após reload. Nenhuma alteração no Chrome pessoal.
- Defeito confirmado: tabs.onUpdated nativo não possui frameId/navigationToken. O mock anterior fabricava ambos. Durante abertura/seleção do ato real, estado recebia manual navigation detected. Correção usa webNavigation.onBeforeNavigate (moldura principal 0) e ignora loading agregado quando essa API existe. Dois testes RED (2 falhas esperadas), depois 61/61 GREEN.
- Run real run-854af1eee9e04581b075e0ee07b28955 chegou a item_prepared e fields_verified (7 campos, sem envio), mas retorno automático fechou a moldura e causou portal frame unavailable. Não conta ainda como conferência visual final.
- Novo contrato: piloto autoSubmit=false pausa de forma persistida após fields_verified e deixa formulário aberto. Teste RED confirmou fechamento anterior (completed em vez de paused); implementação mínima adicionada. Ajustar teste de retomada para o mesmo contrato e repetir gates antes de promover live.
- Bridge atual após restart: PID 30052, 18743, real_send_enabled=false/pilot_enabled=true. Run acima ainda necessita stop antes de novo piloto. Evidência privada temporária session7-live-private.json é sobrescrita pela sonda: copiar por candidato para preservar os resultados finais.

GitHub: nenhum commit/push ainda. Tarefa 4.2 continua em execução, não marcada PASS.

Ler este documento e o handoff anterior; conferir estado vivo antes de executar scripts de tmp/fase41. Não reutilizar códigos de pareamento vencidos. Não iniciar runs concorrentes. Não enviar/finalizar atos. Inspecionar scripts antes de executar; apenas staging nominal de código e documentação sanitizada. GitHub ainda sem novo commit/push nesta sessão.
