# Roteiro dos gates supervisionados (M2, M3 e M5)

**Data:** 2026-09-18 · **Branch:** `codex/mesa-local-refactor`

Os três gates que faltam dependem de portal autenticado e de decisão humana. Este
roteiro deixa cada um em poucos comandos, diz o que o operador faz à mão e onde a
evidência fica salva. Nada aqui digita credenciais, nada clica em conclusão de ato
e nada é enviado automaticamente.

## Antes de começar (uma vez por sessão)

1. Chrome (ou Edge) **fechado** e reaberto com depuração remota, num perfil que
   não seja o do dia a dia:

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\AtosTCE\perfil-qa"
```

2. Login humano na Área Restrita nessa janela (nunca por automação).
3. Mesa em execução, com a raiz real:

```powershell
.\START.cmd --data-root data --port 18743
```

4. Extensão `extension/` carregada em `chrome://extensions` (modo desenvolvedor,
   *Carregar sem compactação*) e pareada com o código que a Mesa imprime.

## M2 — varredura real: extensão × CDP no mesmo marcador

1. Na Mesa, clique em **Analisar Área Restrita** com o marcador em uso e espere o
   fim da varredura (a extensão é o caminho primário).
2. Rode o fallback CDP, que usa o mesmo scanner e só lê:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\scripts\scan-area-cdp.ps1 > data\logs\area-cdp.json
python scripts/compare-area-scans.py --cdp-json data\logs\area-cdp.json --db data\atos-tce.db --json data\logs\area-compare.json
```

3. **Critério:** código de saída 0 e `"equal": true`. Divergência de
   `process_key`, de classificação, de `portal_act_id`, de escopo ou de marcador
   bloqueia M2 — cole o JSON no handoff e trate antes de seguir.
4. Evidência a guardar: `data/logs/area-cdp.json` e `data/logs/area-compare.json`.

## M3 — download real limitado pelo e-Contas

1. Na Mesa, monte o plano e confira o lote interno (a Mesa não expõe número de
   lote: isso é interno por desenho).
2. Dispare a aquisição pelo botão da Mesa (ou `POST /api/v1/acquisition/jobs`) e
   acompanhe com `GET /api/v1/jobs/<id>`.
3. **Critério:** só as chaves pedidas foram baixadas; a contagem de itens do job
   fecha com o plano; falha de autenticação **pausa** o job em vez de continuar; o
   acervo de origem e o canônico não ganham PDF duplicado.
4. Evidência a guardar: o JSON do job (`/api/v1/jobs/<id>`), a lista de processos
   com `acquisition_state` alterado e o recibo em `data/logs/`.

Observação: hoje o acervo real tem 739 processos, todos `DOWNLOADED`, e o plano
volta com 0 lotes. Este gate só é exercitável quando uma varredura nova revelar
processos pendentes — nesse momento ele passa a ser o próximo passo natural.

## M5 — preenchimento real, sem envio

1. Comece pelo caminho **manual**, que é o mais simples de supervisionar: abra o
   ato à mão na Área Restrita, deixe o sidepanel ler o formulário
   (*Preencher formulário atual*) e acompanhe o pedido na Mesa.
2. Depois, se quiser, o caminho automático: na Mesa, com o processo `PRONTO`,
   dispare o preenchimento e acompanhe `GET /api/v1/fill-requests/<id>`.
3. **Critério:** a releitura do formulário confirma exatamente o proposto;
   qualquer divergência vira `BLOQUEADO`; falha do portal vira `ERRO`;
   `autoSubmit=false` e `real_send_enabled=false` continuam valendo e **o clique
   final de conclusão é seu**, no portal, à mão.
4. Evidência a guardar: o pedido (`/api/v1/fill-requests/<id>`), o evento
   `form_filled` do processo e o estado final do formulário na tela.

## Depois dos três gates

1. Atualize `docs/notes/2026-09-18-mesa-refactor-handoff.md` com o resultado de
   cada um (data, marcador, contagens, recibos).
2. Só então a retirada do legado faz sentido: `git tag pre-legacy-retirement`,
   push da tag, e a remoção por unidade conforme
   `docs/notes/2026-09-18-aposentadoria-legado-inventario.md`.
3. A limpeza de armazenamento continua sendo decisão sua: o dry-run atual aprova
   740.149 bytes (`work/outputs`, `work/tmp`, `work/tce-extractor/outputs`) e
   mantém `Versions`, `outputs` e `acervo-tce` recusados com motivo.

## Fronteiras que este roteiro não cruza

- Nenhuma credencial é digitada por automação; o login é sempre humano.
- Nenhum comando aqui envia, conclui ou finaliza ato.
- `Versions/`, `outputs/`, `dados-locais/` e o acervo privado não são tocados.
- As rotas `archive` e `restore` não entram na sessão: elas mexem em bytes do
  acervo e têm gate próprio.

