# Política de acesso — Área Restrita

O Chrome DevTools MCP deve apontar exclusivamente para o Chrome dedicado em
`http://127.0.0.1:9222`. A sessão do portal é autenticada manualmente pela
pessoa operadora. Não automatize credenciais nem copie cookies, tokens ou
respostas brutas do CDP para o repositório.

## Níveis de ação

- **L0 — OBSERVE:** listar páginas/frames, snapshots, console, metadados de
  requests e avaliações estritamente de leitura. Não leia valores de campos,
  cookies, storage, headers ou corpos de requests/respostas.
- **L1 — READ_NAV:** paginação, retorno à lista e abertura de Complementar Ato,
  somente após o gate de observação e uma transição por vez.
- **L2 — PREPARE:** selecionar o interessado exato ou preencher campos, somente
  com L0/L1 estáveis, identidade confirmada, operador presente e gate aprovado.
- **L3 — FINALIZE:** clicar a ação final Complementar Ato, submeter, assinar ou
  tramitar. Proibido ao agente e às ferramentas do Portal Lab. A pessoa
  operadora executa o clique final manualmente.

Antes de qualquer sessão real, o gate local exige baseline verde, Chrome
dedicado, CDP em loopback, sanitizador testado e alvo do MCP comprovadamente
correspondente ao Chrome dedicado. Antes de L2, confirme também o processo de
teste escolhido, estabilidade de L0/L1 e presença do operador. Se alvo, estado,
identidade ou frame forem ambíguos, pare em L0.

## PERMITIDO POR PADRÃO

- listar páginas/frames;
- snapshot;
- console;
- network;
- evaluate de leitura;
- screenshot estrutural.

## EXIGE GATE L1

- paginação;
- abrir Complementar Ato.

## EXIGE GATE L2

- selecionar interessado;
- preencher campos.

## PROIBIDO

- executar a ação final Complementar Ato;
- clicar conclusão ou submit final;
- assinatura;
- tramitação.

Capturas brutas ficam em `tmp/portal-lab/<sessao>/raw/`, fora do Git. Somente
capturas revisadas e sanitizadas podem virar fixtures versionadas. Um CDP
conectado ou uma tela preenchida não qualifica envio real.
