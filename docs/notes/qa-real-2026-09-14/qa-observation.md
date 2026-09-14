# Sessão real observacional — 2026-09-14

## Resultado

- Execução: `qa-20260914T144623037910Z`.
- Contrato: `qa-run-v1`.
- Browser: Chromium QA isolado, perfil privado `dados-locais/chrome-qa-profile`.
- Modo: `observe_only`.
- Estado: `BLOCKED` com observação real parcial; não promover a `PASS_REAL` enquanto os erros de rede/console não forem resolvidos e o fluxo não for repetido com preflight estável.
- Pacote: `TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`.
- Hash do pacote: `aa847c5173ba0bfee0a9b75ee0b0374eabddca8036c707f4f11406ca2a9478cf`.

## Evidência sanitizada

- 83 eventos estruturais: 31 navegações de frame, 25 cliques, 9 alterações, 14 `beforeunload`, 2 mensagens de console, 1 evento de inicialização do gravador e 1 falha de navegação do portal.
- Nenhum `submit_attempt` foi registrado.
- Nenhum valor de campo, texto digitado, cookie, token, cabeçalho ou senha aparece neste relatório.
- Rotas observadas incluem `telaPrincipalMenu.asp`, `ProcessonoSetor.asp`, `ComplementarAto.asp`, `frameSession.asp`, `telaDeTrabalho.asp` e páginas auxiliares do portal.
- Controles estruturais observados incluem `cmbMarcadorFiltro`, `escolha`, `txtModalidade`, `txtFundamentoLegal`, `txtDataDOE`, `txtCargo`, `txtMatricula` e `txtDataNascimento`.

## Divergências

- 6 falhas registradas no artefato privado: `ERR_INVALID_AUTH_CREDENTIALS`, requisições abortadas e erro de console com mensagens representadas somente por hash.
- A navegação inicial falhou, mas frames autenticados/portal foram observados posteriormente.
- O evento estrutural não registra o valor escolhido do marcador nem os valores dos sete campos; por segurança, isso exige uma segunda passagem de preflight controlado para comprovar igualdade exata.

## Artefatos privados

- Trace: `dados-locais/qa-runs/qa-20260914T144623037910Z/trace.zip`.
- HAR: `dados-locais/qa-runs/qa-20260914T144623037910Z/network.har`.
- Run JSON sanitizado: `dados-locais/qa-runs/qa-20260914T144623037910Z/run.json`.

Os arquivos acima permanecem fora do Git e não são incorporados ao ZIP ou aos relatórios públicos.

## Decisão de segurança

Nenhuma conclusão, envio, assinatura, tramitação ou repetição automática foi executada. O gate real permanece bloqueado até corrigir os erros observados, repetir três preflights reais consecutivos e obter autorização específica imediatamente antes de qualquer piloto.
