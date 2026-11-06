# Segurança final — Complementador e-Contas (F5)

Data: 05/11/2026
Escopo: permissões, mensagens, storage, cache, diálogo, dados pessoais e limites de homologação.

## Superfície da extensão

- Manifest V3, versão 0.1.1, mínimo Chrome/Edge 110.
- Permissão única: `storage`.
- Hosts: `https://processos.tce.rn.gov.br/*` e `https://novaarearestrita.tce.rn.gov.br/as/consultaprocessotemp/*`.
- Sem `all_urls`, `downloads`, `webRequest`, `debugger`, `cookies`, `scripting`, IndexedDB, localStorage, sessionStorage, WebSocket ou telemetria.
- Todo `fetch` de PDF passa pelo service worker, com origem, caminho, tipo, tamanho e assinatura PDF validados.

## Mensagens e identidade

- Comandos de lote exigem `sender.id === chrome.runtime.id`.
- Comandos de formulário exigem a rota `complemento` e `processId` igual ao da rota.
- `BATCH_SAVE` revalida cinco campos, interessado único, erros visíveis e processo imediatamente antes do clique.
- Aba de Autos responde apenas ao processo esperado; duas abas de processos distintos não se cruzam (spec de navegador).
- Lista de processos só é lida na rota verificada; a fila é congelada por IDs visíveis.

## Salvamento

- Três controles independentes. O build seguro mantém todos fechados; o ZIP funcional 2.0.3 habilita execução e salvamento no build, mas o lote só começa com clique explícito em Start:
  - `BATCH_EXECUTION`: liga o processamento do lote.
  - `BATCH_FILL_ONLY`: preenche e mantém abas, forçando salvamento desligado.
  - `BATCH_SAVE`: habilita a capacidade de salvamento.
- A autorização é persistida no lote (`saveAuthorized`); lote antigo/sem autorização não salva.
- Checkpoint `SAVE_ARMED` é gravado antes do clique; tentativa única por `attemptId`.
- Exceção, timeout, ACK sem readback ou resposta vazia resultam em `SAVE_UNCERTAIN`/`SUSPENDED`; nunca segundo clique.
- Diálogo aceito apenas com `role="dialog"` (ou `ngb-modal-window` com `aria-modal`), título **Complementar ato**, confirmação **sim, complementar** e cancelamento **NÃO**. Variação falha fechado.
- Verificação pós-salvamento abre uma aba nova controlada, confere a rota/processo, exige formulário renderizado e ausência do botão. Sem essas condições, permanece `unknown`.

## Storage

- `chrome.storage.local` guarda somente:
  - diário do lote: IDs, rótulos, estados, contadores, motivos e `{cause, fields}`;
  - preset de filtros.
- `chrome.storage.session` guarda cache documental (`processHash`, ids de evento, `updatedAt`), marcador de sessão MV3 e diagnóstico L1.
- Nenhum PDF, texto, nome, CPF, matrícula, nascimento, cookie, token ou URL assinada é persistido.
- `setAccessLevel('TRUSTED_CONTEXTS')` restringe o storage local quando disponível.
- Cache de documento é vinculado ao hash do processo; alternar entre dois processos invalida os ids anteriores.

## Evidências

- `tests/unit/security.test.mjs`: permissões, ausência de APIs proibidas, ausência de rede externa, sem submit, sem PII em fontes/docs/pacote.
- `tests/unit/document-cache.test.mjs`: cache por processo e alternância entre dois processos.
- `tests/browser/batch-autos.spec.mjs`: duas abas de processos distintos não respondem uma pela outra.
- `tests/unit/batch-save-adapter.test.mjs`: diálogo estrutural e falha fechada.
- Suíte final: 332 unitários PASS; 25 navegador PASS.

## Riscos e pendências

- **Autosave do portal: UNKNOWN.** Não foi observado durante digitação real; se existir, o preenchimento em lote pode persistir antes do clique. Não testar no portal real sem autorização específica.
- **Chrome profissional: NOT_RUN.** Nenhuma instalação, recarga ou inspeção no perfil institucional.
- **Abas:** processos CONFIRMED fecham as duas abas de trabalho após o ACK; revisão/incerteza permanecem abertas. A limpeza é testada em unitários e navegador.
- **Preferência de abas:** persistida em `chrome.storage.local` e aplicada no início do lote; incerteza nunca fecha abas.
- **Filtros:** presets são separados por rota (`processos-no-setor` e `meus-processos`), evitando aplicar filtros de uma listagem na outra.
- **MV3 físico: PARTIAL.** A lógica de suspensão/reentrada tem testes puros e verificação estática; o kill real do service worker via CDP travou o navegador e foi removido.
- **Verificação pós-save:** a melhor evidência disponível é rota/processo corretos + formulário renderizado + ausência do botão. Não é um ACK formal do portal; por isso a confirmação automática continua conservadora.
- O portal pode mudar DOM, status ou diálogo; seletores e textos observados exigem revalidação antes de novo gate real.
