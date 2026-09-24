# Workflow Playwright CLI — Portal Lab

Use o Playwright CLI somente depois de confirmar que o Chrome dedicado está
escutando em `127.0.0.1:9222`. O Chrome deve ser iniciado pelo script do Portal
Lab; `playwright-cli open` cria outro browser e não serve para esta sessão.
O Chrome DevTools MCP é a ferramenta primária para observar páginas e frames;
confirme o alvo antes de usar qualquer sessão autenticada.

## Inicialização

Uma vez por workspace, a skill oficial pode ser instalada com:

```powershell
playwright-cli install --skills=agents
```

Conecte uma sessão nomeada ao Chrome dedicado:

```powershell
playwright-cli -s=area-restrita attach --cdp=http://127.0.0.1:9222
```

O comando `attach --cdp` foi validado com Playwright CLI 0.1.13. O snapshot de
uma página de `chrome://new-tab-page/` e o `detach` foram testados sem acessar o
portal.

## Ciclo de observação

1. Leia `devtools/area-restrita/portal-contract.json` e o código atual.
2. Classifique a ação como L0, L1, L2 ou L3; recuse L3.
3. Anexe à instância dedicada e capture BEFORE estrutural.
4. Faça no máximo uma transição permitida e capture AFTER estrutural.
5. Guarde os brutos fora do Git; sanitize e compare antes de interpretar.
6. Revise o diff e crie apenas fixture sanitizada.
7. Para mudança de runtime, escreva um teste RED que reproduza a observação.
8. Só depois faça a menor mudança, rode GREEN + suíte e valide a fronteira do
   pacote.
9. Faça `detach` ao terminar; o Chrome dedicado deve continuar aberto.

```powershell
playwright-cli --s=area-restrita snapshot
# executar somente a transição aprovada para a fase atual
playwright-cli --s=area-restrita snapshot
playwright-cli --s=area-restrita detach
```

Não agrupe ações desconhecidas em `run-code`. Prefira comandos isolados para
cada transição e avalie o resultado antes de seguir.

## Limites da sessão

- `L0`: observação de páginas/frames, snapshots, console, requests e avaliações
  estritamente de leitura; requests significam metadados, sem headers nem
  corpos;
- `L1`: paginação, retorno à lista e abertura de Complementar Ato somente após
  o gate de observação;
- `L2`: seleção de interessado e preenchimento somente depois da evidência
  L0/L1 estável, identidade confirmada e operador presente;
- `L3`: ação final Complementar Ato, submit, assinatura e tramitação são
  proibidos para o agente; a pessoa operadora executa a ação final.

Não escolha o primeiro frame ou o primeiro controle em caso de ambiguidade.
Sem predicado estrutural testado, não aumente retries, delays ou timeouts como
correção. Mantenha seletores operacionais no módulo dono, atualmente
`extension/lib/area-snapshot.js`; contrato, Skill e scripts de laboratório não
são um segundo mapa de seletores.

Não use `close`, `close-all`, `kill-all` ou `delete-data` em uma sessão anexada;
`detach` encerra a conexão do CLI e deixa o Chrome dedicado aberto. Não leia ou
salve cookies, headers, storage state ou corpos de requests do portal. Capturas,
snapshots e traces podem conter dados privados: mantenha-os fora do Git e nunca
trate arquivos de `.playwright-cli/` como fixture sanitizada.

Para os detalhes dos estados documentados e os limites entre contrato e
comportamento realmente observado, consulte `portal-states.md`.
