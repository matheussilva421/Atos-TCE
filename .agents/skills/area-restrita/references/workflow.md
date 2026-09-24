# Workflow Playwright CLI — Portal Lab

Use o Playwright CLI somente depois de confirmar que o Chrome dedicado está
escutando em `127.0.0.1:9222`. O Chrome deve ser iniciado pelo script do Portal
Lab; `playwright-cli open` cria outro browser e não serve para esta sessão.

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

1. `attach` à instância dedicada;
2. capturar snapshot antes da observação;
3. executar no máximo uma transição autorizada por vez;
4. capturar snapshot depois da transição;
5. registrar e revisar o diff;
6. salvar a captura bruta em `tmp/portal-lab/<sessao>/raw/` e sanitizar antes
   de converter qualquer dado em fixture;
7. `detach` ao terminar.

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
  estritamente de leitura;
- `L1`: paginação e abertura de Complementar Ato somente após o gate definido
  para a observação;
- `L2`: seleção de interessado e preenchimento apenas depois da evidência L0/L1
  e com operador presente;
- conclusão, submit final, assinatura e tramitação são proibidos.

Não use `close`, `close-all`, `kill-all` ou `delete-data` em uma sessão anexada;
`detach` encerra a conexão do CLI e deixa o Chrome dedicado aberto. Não leia ou
salve cookies, headers, storage state ou corpos de requests do portal. Capturas,
snapshots e traces podem conter dados privados: mantenha-os fora do Git e nunca
trate arquivos de `.playwright-cli/` como fixture sanitizada.
