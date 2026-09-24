# Política de acesso — Área Restrita

O Chrome DevTools MCP deve apontar exclusivamente para o Chrome dedicado em
`http://127.0.0.1:9222`. A sessão do portal é autenticada manualmente pela
pessoa operadora. Não automatize credenciais nem copie cookies, tokens ou
respostas brutas do CDP para o repositório.

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

- clicar conclusão;
- submit final;
- assinatura;
- tramitação.

Capturas brutas ficam em `tmp/portal-lab/<sessao>/raw/`, fora do Git. Somente
capturas revisadas e sanitizadas podem virar fixtures versionadas. Um CDP
conectado ou uma tela preenchida não qualifica envio real.
