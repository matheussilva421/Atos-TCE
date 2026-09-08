# Fluxo portátil integrado — plano de implementação por fases

> Para o agente executor: use `superpowers:executing-plans` ou `superpowers:subagent-driven-development`, lendo primeiro este documento inteiro. Execute TDD por tarefa. Se usar subagentes, respeite a preferência explícita do usuário: somente Luna xhigh; se indisponível, trabalhe no agente principal, sem substituir silenciosamente.

**Objetivo:** diminuir espera de coleta e comparação entre PDF, HTML e extensão, preservando a conferência humana e o preenchimento deliberado.

**Arquitetura:** manter o coletor PowerShell, extrator Python e extensão MV3 existentes. Acrescentar serviço HTTP local, publicação incremental por processo e visualizador PDF.js offline com evidências geométricas. O serviço será a fonte de verdade do progresso portátil; a extensão continuará sendo o único componente que escreve nos sete campos autorizados do portal.

**Stack:** Windows PowerShell 5.1, Python/PyMuPDF/Tesseract já empacotados, JavaScript ES modules, Chrome MV3, PDF.js empacotado com versão/hash fixados.

**Especificação:** seção 1 deste documento consolida as decisões aprovadas na conversa. Não transformar este planejamento em autorização para enviar atos ou apagar o acervo.

**Raiz:** `C:\Users\slvma\Downloads\Github\Complementação de Atos`.

**Convenções:** caminhos abaixo relativos à raiz. `E` significa `work/tce-extractor`; `P` significa `work/tce-extractor/portable`; `X` significa `work/tce-extractor/portable/extensao-complementar-ato`. São abreviações documentais, não variáveis de ambiente. Nomes de arquivos novos são propostas; funções qualificadas como existentes foram inspecionadas em 08/09/2026.

## 1. Contrato de produto — decisões fechadas

1. Um ZIP privado transporta scripts, runtime, PDFs, HTML, JSON e progresso. Um PC ativo por vez. Login e pareamento são refeitos no destino.
2. O usuário pode escolher **progressivo** ou **completo** em cada execução. Ambos continuam coletando todos os eventos com arquivos; capas indisponíveis não bloqueiam uso.
3. HTML na outra tela. Resolução e Guia em abas, páginas completas, trechos amarelos sobrepostos. Nunca cortar nem sobrescrever PDFs originais.
4. Clicar num campo abre documento e página de sua evidência. Ausência de coordenadas confiáveis não autoriza destacar texto por aproximação.
5. HTML acompanha o processo/interessado da Área Restrita. Não navega no portal. Acompanhamento pode ser pausado para consulta manual.
6. **Preencher fica na extensão.** Não preencher ao trocar processo, clicar numa evidência, concluir download ou marcar conclusão.
7. Correções ficam somente no formulário do TCE. HTML não edita valores. Não sobrescrever correções silenciosamente.
8. Salvar, concluir análise e navegar permanecem manuais. Nenhuma automação clica no envio/ação final “Complementar Ato”.
9. **Concluído** é confirmação manual por processo, não recibo de salvamento no portal. Pode ser desmarcado explicitamente. Documentos novos não removem essa marca.
10. Ordem sempre igual à lista capturada do portal; concluídos não sobem/descem nem causam avanço automático.
11. Sete campos existentes: modalidade, fundamento, data DOE, cargo completo/classe, matrícula completa, nascimento e gênero explícito. Financeiros e conclusão da análise fora do escopo.
12. DOE usa a data da resolução em DD/MM/AAAA por regra operacional do usuário; preservar identificação dessa origem, sem afirmar publicação comprovada.
13. Modalidade/fundamento mantêm o mecanismo existente de correspondência mais parecida; empate mantém proposta da primeira opção e destaque amarelo. Não confundir aproximação de opção com certeza documental.
14. Extração só de Resolução Administrativa e Guia Financeira/Taxação, nos eventos posteriores ao primeiro. Documentos genéricos precisam de análise de conteúdo. Conflitos permanecem explícitos.
15. Serviço local permitido, sem instalação/admin, restrito ao próprio computador. Se bloqueado, HTML estático e importação de JSON continuam disponíveis; não fingir sincronização.

### Vocabulário

| Termo | Significado |
|---|---|
| Acervo | Arquivos, eventos, resultados e progresso locais |
| Processo | Número/ano canônico; unidade da marca Concluído |
| Interessado | Pessoa selecionada; unidade da extração/preenchimento |
| Ocorrência documental | Processo + identificador real do evento + identificador do documento |
| Versão documental | Ocorrência mais hash dos bytes; não somente número do evento |
| Em preparação | Dados preliminares; varredura ainda pode encontrar conflitos |
| Disponível | Resultado da análise acessível; não significa validado pelo usuário |
| Concluído | Declaração manual do usuário, independente de coleta e OCR |
| Revisado legado | Marca antiga da extensão; não equivale a Concluído |

## 2. Estado do código e riscos de integração

| Ponto existente | Comportamento observado | Consequência para implementação |
|---|---|---|
| `P/Coletar-Processos-TCE.ps1` | Resolve seleção e percorre processos sequencialmente; chama `Sync-TceProcessManifest` | Manter CLI; extrair coordenação antes de paralelizar |
| `P/TcePortable.Core.psm1::Sync-TceProcessManifest` | Identidade `processKey|eventId|document.id`, hash, deduplicação, versões e escrita de evento/processo/checkpoint | Workers não podem concorrer na gravação desses índices |
| `P/app/archive_index.py::scan_archive` | Reconstrói índice a partir de arquivos locais | Persistir ordem do portal explicitamente; ordem de diretórios não basta |
| `P/app/analysis_pipeline.py::run_local_pipeline` | Índice → classificação → manifest → `run_manifest` → HTML → exportação JSON do acervo | Não executar pipeline completo após cada PDF |
| `analysis_pipeline.py::_ocr_pdf_pages` | Retorna texto por página; Tesseract stdin/stdout, sem coordenadas | Acrescentar leitura estruturada e cache geométrico sem invalidar à toa texto existente |
| `E/tce_extractor.py::FieldEvidence` | Campo, valor, status, processo, evento, documento, página e candidatos; sem caixas | Propagar identidade/trecho até a saída; não localizar somente pelo valor normalizado |
| `E/batch_runner.py` | Serialização de evidência, assinatura de entrada, merge e retomada | Round-trip de novas referências precisa ser testado |
| `E/html_generator.py` | JS/CSS inline, iframe nativo, `localStorage` para concluídos; `selectDocument` busca por evento | Evento repetido pode escolher documento errado; usar ID documental |
| `P/app/extension_exporter.py`, `X/lib/schema.js` | JSON v1 com chaves estritas, rejeição de dados privados | Não inserir coordenadas/chaves extras no v1 |
| `X/content/form-detector.js` | `getFormSnapshot`, `applyFields`, `overrideField`, validação de identidade/visibilidade | Reutilizar guardas; não duplicar seletores do portal em outro componente |
| `X/sidepanel/panel.js` | `refresh`, `fillAvailableFields`, `setReviewed`; prévia e importação manual | Integrar bridge sem disparar preenchimento automático |
| `E/package_complete_archive.py` | `EXTENSION_FILE_ALLOWLIST` explícita; auditoria; exclusões | Arquivo novo pode sumir do ZIP se allowlist não for atualizada |
| `.gitignore` | Lista de permissão; `P/app` permite apenas py/ps1; docs permite notes | JS/CSS do novo HTML exigem exceções estreitas; não liberar acervo |

Não reorganizar a árvore `work/tce-extractor` nesta entrega: empacotadores dependem do layout relativo. Não apagar staging/runtime nem o último ZIP validado. O número atual de processos deve vir da coleta, nunca de uma constante 62/227.

## 3. Contratos de dados e coordenação

### 3.1 Compatibilidade

Manter `dados-complementar-ato.json` no schema v1 atual para modo manual. O serviço retorna o mesmo dataset num envelope versionado, sem modificar as chaves internas. Evidências geométricas e progresso ficam em arquivos separados. Isso evita migrar o importador antigo e permite rollback.

Novos arquivos privados em `acervo-tce`:

- `ordem-portal.json`: `{schema_version:1, captured_at, process_keys:[...]}`; ordem deduplicada da listagem atual. Processos históricos ausentes ficam em consulta separada “fora da lista atual”, sem misturar na ordem atual.
- `progresso.json`: `{schema_version:1, revision:0, processes:{}}`. Cada chave canônica aponta `{completed:boolean, updated_at:string}`. Sobrevive a nova coleta; reset do lote ativo não apaga o histórico de conclusões automaticamente.
- `evidencias-visuais.json`: `{schema_version:1, documents:{}, records:{}}`; sem caminhos absolutos. Documentos têm ID opaco, ocorrência, SHA256, caminho relativo validado e geometria de página. `records[record_id][field]` contém lista de `{document_id,page,quote,rects,method,status}`.
- `publicacoes/<revision>/`: snapshot coerente dos resultados; `publicacao-atual.json` aponta atomicamente para a última revisão completa. Retenção: atual e anterior; remover somente snapshots próprios já substituídos, nunca PDFs ou progresso.
- `dados-locais/bridge/`, fora do acervo: PID, porta, tokens, lock de execução. Excluído de qualquer ZIP.

IDs: `document_id = sha256(processKey + '|' + eventId + '|' + documentId + '|' + pdfSha256)`. Usar identificadores reais, sem derivar endpoints remotos. `record_id = sha256(processKey + '|' + interestedNormalized)`; se normalização colidir entre pessoas, bloquear sincronização desse registro e exigir seleção explícita, não acrescentar CPF ao exportador.

Coordenadas: retângulos `[x0,y0,x1,y1]` normalizados 0..1 sobre a página exibida após CropBox/rotação. Guardar largura/altura e rotação usadas. Adaptadores de PyMuPDF/OCR fazem a transformação uma vez; viewer aplica escala do viewport. Valores fora do intervalo ou hash diferente invalidam o destaque.

### 3.2 Serviço local proposto

Criar `P/app/local_service.py` usando biblioteca padrão Python e serviço multithread limitado. Escritas de estado passam por um único coordenador/lock; workers de OCR não escrevem progresso. Porta inicial 18743; tentar 18744..18752 se ocupada; anunciar porta escolhida. Nunca encerrar processo que já ocupa uma porta.

| Método/rota | Entrada/saída |
|---|---|
| GET `/api/v1/health` | Versão da API, sem dados pessoais; teste de disponibilidade |
| POST `/api/v1/pair` | Código temporário; devolve token vinculado à extensão |
| GET `/api/v1/state?since=N` | Revisão, ordem, conclusão, seleção atual, estados de preparação; `unchanged:true` quando igual |
| GET `/api/v1/dataset` | `{api_version:1,revision,dataset:<v1 existente>}` |
| GET `/api/v1/evidence/<record_id>` | Evidências e documentos desse registro |
| GET `/api/v1/pdf/<document_id>` | PDF validado pelo índice, `Range` suportado; sem caminho livre |
| POST `/api/v1/selection` | `{process_key,interested_normalized,tab_id,frame_id,sequence}` |
| PUT `/api/v1/progress/<process_key>` | `{completed,expected_revision}`; retorna revisão gravada; 409 em conflito |

Segurança: bind somente 127.0.0.1; validar Host com porta exata; negar Origin arbitrária, inclusive `null`; sem CORS `*`. Pairing de uso único, expira em 120s, cinco tentativas por código; aceita apenas Origin chrome-extension e vincula o token a ela. Exibir confirmação no iniciador antes da emissão. Código/token não vão em logs. Token em `chrome.storage.session`; manter em memória no servidor, inválido após reinício.

HTML autenticado por bootstrap de uso único em fragmento da URL, removido imediatamente com `history.replaceState`; troca por cookie HttpOnly SameSite=Strict, escopo local. Escritas do HTML exigem Origin local exata e token CSRF. CSP restrita a self e Referrer-Policy no-referrer. Servir assets públicos sem expor PDFs. Rejeitar traversal, reparse points e caminhos resolvidos fora do acervo. Nada de endpoints para comandos de shell.

Polling de estado no HTML/painel: 500ms quando visível, 2s quando oculto; evitar timers eternos no service worker MV3. Reconexão com backoff até 10s, exibindo desconectado. O painel pode reler snapshot a cada 500ms enquanto aberto; comparar identidade antes de publicar. Mensagens antigas por sequence são descartadas. Esses intervalos são parâmetros internos testáveis.

## 4. Fases de implementação

Cada fase: teste RED específico → mudança mínima → teste GREEN → regressão → handoff e commit somente dos arquivos da fase. Não afirmar QA real a partir de fixture. Parar se for necessária autenticação humana.

### Fase 0 — baseline e preparação (sem alteração funcional)

**Arquivos:** este plano; novo `docs/notes/YYYY-MM-DD-fluxo-portatil-execucao-handoff.md`.

- [x] Ler mudanças locais, scripts de empacotamento e testes antes de criar branch `feat/fluxo-portatil-integrado`; preservar alterações do usuário.
- [x] Resolver runtime local e registrar caminho/versão de Python, Node e Tesseract. Não presumir Python global nem instalar para contornar falha sem necessidade.
- [x] Executar baseline: `node --test` em X; `python -m unittest discover -s . -p 'test_*.py'` em E; scripts `tests/Test-TcePortable.ps1`, `Test-PortableMenu.ps1`, `Test-PortableReset.ps1` em E com Windows PowerShell 5.1.
- [x] Registrar falhas pré-existentes separadamente. Criar fixtures sintéticas, nunca versionar PDFs pessoais.
- [ ] Capturar medição do fluxo existente em 20 processos autorizados: primeiro resultado, preparação total, tempo humano de comparação e cliques. Não baixar novamente todo acervo só para benchmark.

**Gate:** baseline reproduzível e lista de limitações. Commit `docs: record integrated workflow baseline`.

### Fase 1 — persistência portátil e ordem

**Criar:** `P/app/workflow_state.py`, `E/test_workflow_state.py`.
**Alterar:** `P/app/archive_index.py`, `P/app/reset_archive.py`, `E/test_reset_archive.py`.

**Interfaces novas:** `WorkflowState(root: Path)`, `snapshot() -> dict`, `set_completed(process_key: str, completed: bool, expected_revision: int) -> dict`, `set_portal_order(keys: list[str]) -> dict`. Exceção `RevisionConflict` sem escrita parcial.

Teste RED inicial:

```python
def test_completion_survives_order_refresh(self):
    state = WorkflowState(Path(self.temp.name))
    state.set_completed('103439/2023', True, 0)
    state.set_portal_order(['103490/2023', '103439/2023'])
    result = WorkflowState(Path(self.temp.name)).snapshot()
    self.assertTrue(result['processes']['103439/2023']['completed'])
    self.assertEqual(result['process_keys'][0], '103490/2023')
```

- [x] Criar teste com `unittest.TestCase`, `TemporaryDirectory` em setUp e cleanup; executar `python -m unittest test_workflow_state` e confirmar ausência do módulo como RED.
- [x] Implementar snapshot defensivo, canonicalização número/ano reutilizando regras existentes, escrita temp+fsync+replace e cópia anterior válida. Nunca tratar JSON corrompido como acervo vazio silenciosamente.
- [x] Serializar escritores; segunda instância do serviço para a mesma raiz recusa iniciar. Testar revision conflict, reabertura, corrupção, falha antes do replace e pedido idempotente.
- [x] Preservar marcas em reanálise e reset do lote; migração de checks antigos é ação explícita, sem promoção de `reviewed:v1`.
- [x] Testar eventos novos e ordem nova sem alteração de conclusão. Gate GREEN dos testes de estado, índice e reset.

**Commit:** `feat: persist portable workflow progress and portal order`.

### Fase 2 — serviço e autenticação local

**Criar:** `P/app/local_service.py`, `P/app/bridge_auth.py`, `E/test_local_service.py`, `E/test_bridge_auth.py`.
**Alterar:** `P/app/menu.ps1`, `P/INICIAR.cmd`, `E/tests/Test-PortableMenu.ps1`.

**Interfaces novas:** `create_server(root: Path, host='127.0.0.1', port=18743)`, `BridgeAuth.issue_pairing_code()`, `BridgeAuth.redeem(code, origin)`. A camada HTTP consome WorkflowState, sem registrar conteúdo dos PDFs.

Teste RED inicial com servidor em porta efêmera durante testes:

```python
def test_private_state_requires_auth(self):
    with self.running_server() as base:
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + '/api/v1/state')
        self.assertEqual(error.exception.code, 401)
```

- [x] Criar harness `running_server` com contextmanager que inicia thread em `port=0`, retorna URL e garante shutdown/join em finally. Executar `python -m unittest test_local_service test_bridge_auth` RED.
- [x] Implementar rotas da seção 3, separar parser/autorização/handlers; JSON inválido=400, falta de autenticação=401, origem proibida=403, documento ausente=404, revisão conflitante=409.
- [x] No iniciador, iniciar helper oculto, abrir HTML local, manter comando explícito de parar. Não adicionar inicialização automática ao Windows nem criar regra de firewall.
- [x] Testar token expirado, código reutilizado, Origin/Host forjados, traversal codificado, link/reparse, Range válido/inválido (416), porta ocupada, execução duplicada, reinício e ausência de vazamento de tokens nos logs.
- [x] Se serviço falhar, mostrar modo manual e preservar o lote; não impedir HTML estático/JSON. Gate de segurança antes de conectar a extensão.

**Commit:** `feat: add authenticated loopback workflow service`.

### Fase 3 — evidências geométricas e identidade documental

**Criar:** `P/app/evidence_geometry.py`, `E/test_evidence_geometry.py`.
**Alterar:** `E/tce_extractor.py`, `E/batch_runner.py`, `P/app/analysis_pipeline.py`, `E/test_tce_extractor.py`, `E/test_extension_exporter.py`.

**Interfaces novas:** `read_page_words(pdf, page_number, *, tesseract, tessdata) -> dict` com words/text/geometry; `locate_evidence(words, quote) -> list[list[float]]`; `build_visual_evidence(records, documents) -> dict`.

Teste RED puro inicial:

```python
def test_repeated_quote_is_not_guessed(self):
    words = [
        {'text': '103.870-2/1', 'rect': [.1,.1,.3,.2]},
        {'text': '103.870-2/1', 'rect': [.1,.5,.3,.6]},
    ]
    self.assertEqual(locate_evidence(words, '103.870-2/1'), [])
```

- [x] Escrever testes puros e fixtures PyMuPDF geradas no teste. Executar `python -m unittest test_evidence_geometry` RED.
- [x] Capturar trecho original na extração; adicionar referências opcionais a FieldEvidence e serialização do batch_runner. Defaults mantêm checkpoints antigos legíveis. Nunca procurar campo apenas pelo valor normalizado.
- [x] Extrair palavras nativas via PyMuPDF; OCR retorna TSV com caixas e confiança, preservando texto agrupado por página. Reutilizar rasterização; não rodar um OCR só para texto e outro para caixas.
- [x] Cache geométrico separado, chave hash+versão de geometria+runtime OCR. Não interpretar cache de texto v2 como cache geométrico completo. Arquivo inalterado com cache válido não recebe novo OCR.
- [x] Transformar coordenadas considerando CropBox/rotação e dimensões raster. Destacar sequência única com contexto suficiente; se ambígua ou baixa confiança, retornar rects vazios e motivo, mantendo página.
- [x] Propagar identidade real até candidatos de conflito. Mesmo conteúdo duplicado pode compartilhar bytes, mas mantém ocorrências/eventos distintos.
- [x] Confirmar que exportação v1 continua validada, sem coordenadas, caminho absoluto ou novas chaves. Geometria somente no sidecar.
- [ ] Gate: datas/matrículas/cargo com classe preservados; PDF 1 página, escaneado, rotação 90/180/270, evento repetido, candidato múltiplo, hash modificado e round-trip de checkpoint.

**Commit:** `feat: add traceable PDF evidence geometry`.

### Fase 4 — mesa HTML integrada sem edição

**Criar:** `P/app/web/review-app.js`, `pdf-viewer.js`, `review.css`, `E/test_review_assets.py`; testes JS em `P/app/web/tests/`.
**Alterar:** `E/html_generator.py`, `E/test_html_generator.py`, `.gitignore` com exceções somente para assets/testes planejados.

**Interface JS nova:** `showEvidence({documentId,page,rects})`; `setSelection({processKey,interestedNormalized})`; `setFollowPortal(enabled)`.

Teste RED JS inicial (módulo de seleção puro):

```javascript
test('same event number does not select another document', () => {
  const docs = [{id:'a',event:9},{id:'b',event:9}];
  assert.equal(resolveDocument(docs, 'b').id, 'b');
});
```

- [x] Separar seleção/layout do viewer; criar `resolveDocument(documents,id)` exportada e testar RED com `node --test app/web/tests/*.test.mjs` executado em P.
- [x] Adicionar PDF.js a `P/app/web/vendor/pdfjs`, com licença, versão exata e SHA256 em manifesto de dependências. Escolher release estável compatível após verificar navegador alvo; não usar latest flutuante nem CDN. Registrar versão antes de implementar o adaptador.
- [x] Implementar canvas por página e camada de destaques; carregar página atual e vizinhas, cancelar render anterior ao trocar documento, liberar canvases antigos. Não carregar centenas de PDFs na memória.
- [x] Abas Resolução/Guia, seletor de múltiplos alvos e seção de outros eventos. Clique em campo usa document_id+page, nunca somente event.
- [x] Manter HTML offline existente como fallback nativo; assets integrados usados quando servido localmente. Mostrar claramente qual modo está ativo.
- [x] Lista segue ordem-portal; conclusões somente ícones. Seleção manual pausa acompanhamento até botão Retomar. Trocar para outra tela não altera foco no navegador do portal.
- [x] Valores somente leitura; campo ausente/conflictante permanece explícito. Não renomear status de extração para “validado”.
- [ ] Gate visual 900x1440 e desktop: divisor, zoom, páginas completas, fonte legível, ausência de overflow horizontal raiz. Scroll interno de PDF permitido; não prometer todos os documentos na tela simultaneamente.

**Commit:** `feat: add full-page evidence viewer to local review desk`.

### Fase 5 — bridge da extensão e conclusão unificada

**Criar:** `X/lib/bridge-client.js`, `X/tests/bridge-client.test.mjs`.
**Alterar:** `X/manifest.json`, `background/service-worker.js`, `sidepanel/panel.js`, `sidepanel/panel.html`, `lib/messages.js`, respectivos testes; `content/form-detector.js` somente se necessário para observação de identidade.

**Interface:** `createBridgeClient({fetchImpl,baseUrl,token})` com `getState(since)`, `getDataset()`, `publishSelection(selection)`, `setCompleted(processKey,completed,revision)`.

Teste RED inicial:

```javascript
test('selection update never applies fields', async () => {
  const calls = [];
  const bridge = createBridgeClient({baseUrl:'http://127.0.0.1:18743',token:'test',
    fetchImpl: async (url) => {calls.push(url); return {ok:true,json:async()=>({revision:1})};}});
  await bridge.publishSelection({process_key:'103439/2023',interested_normalized:'PESSOA TESTE',tab_id:1,frame_id:0,sequence:1});
  assert.equal(calls.length, 1);
  assert.match(calls[0], /\/selection$/);
});
```

- [x] RED `node --test tests/bridge-client.test.mjs` em X; implementar bridge com timeout e validação de envelope.
- [x] Adicionar host permission somente `http://127.0.0.1/*`; aceitar baseUrl apenas loopback e intervalo definido. Nunca aceitar URL passada pelo content script como destino livre de fetch.
- [x] Painel faz pareamento e associa sua aba/frame registrados. Se houver múltiplos formulários visíveis ambíguos, não escolher silenciosamente. Reutilizar descoberta existente.
- [x] Enquanto painel aberto, publicar mudanças de identidade com sequence monotônica. Ao suspender/reiniciar worker, reconstruir associação pela descoberta atual; não usar snapshot antigo para escrever.
- [x] Ao importar revisão do serviço, manter conclusão independente de batch.id; atualização automática não chama a rotina que zera reviewed legado.
- [x] Preservar `fillAvailableFields`, guardas `validateBeforeWrite` e confirmação individual de override. Revalidar identidade antes e durante aplicação; se mudar, abortar restantes. Manter clique explícito Preencher.
- [x] Adicionar controle Concluído nos dois clientes chamando mesma API; erro de gravação mostra não salvo e reverte check otimista. Correções no portal não são copiadas de volta ao dataset.
- [x] Modo desconectado mantém JSON manual; importar progresso antigo só mediante confirmação. `Revisado` não migra implicitamente.
- [x] Gate: troca rápida de processo, homônimos, nome com/sem acento, duas abas, iframe invisível, worker reiniciado, serviço caído, correção manual preservada e zero ações de envio.

**Commit:** `feat: synchronize review desk with extension without auto-fill`.

### Fase 6 — coleta concorrente limitada e publicação incremental

**Criar:** `P/app/incremental_pipeline.py`, `E/test_incremental_pipeline.py`.
**Alterar:** `P/Coletar-Processos-TCE.ps1`, `P/TcePortable.Core.psm1`, `P/app/analysis_pipeline.py`, `E/batch_runner.py`, `E/tests/Test-TcePortable.ps1`, `E/tests/Test-PortableMenu.ps1`.

**CLI nova:** `-ModoPreparacao progressivo|completo`, padrão progressivo; `-MaxDownloads 2`, limite 1..2. Preservar parâmetros existentes. `novos` mantém significado de coleta, não de conclusão humana.
**Interface Python nova:** `analyze_process(archive_root, process_key, *, tesseract, tessdata) -> dict`; `publish_results(archive_root, process_results) -> int`. Não chamar `run_local_pipeline` inteiro por documento.

Teste RED inicial:

```python
def test_publication_keeps_unaffected_process(self):
    publish_results(self.root, {'1/2023': {'status': 'partial'}})
    publish_results(self.root, {'2/2023': {'status': 'partial'}})
    self.assertEqual(set(self.current_results()), {'1/2023', '2/2023'})
```

- [x] Testar merge incremental e helper `current_results` lendo ponteiro/publicação; confirmar RED.
- [x] Refatorar `Sync-TceProcessManifest` em planejamento de documentos, download e commit, mantendo wrapper compatível. Runspaces limitados executam apenas downloader; coordenador único faz hash/dedup/versões/checkpoint.
- [x] Capturar ordem da listagem antes de filtrar seleção. Prioridade: títulos alvo após evento1, genéricos após evento1, outros documentos, capas. Não eliminar genéricos por título nem parar depois do primeiro alvo.
- [x] Sessões/URLs autenticadas só em memória dos workers; nenhum spool ou log com token. Em 401/403 suspender e pedir login; 429 respeita Retry-After, reduz a um download; máximo três tentativas para falhas transitórias. HTTP400 documental permanece erro explícito sem retry infinito.
- [x] Após arquivo validado, emitir evento local sanitizado para análise. Um worker OCR; evitar duas escritas simultâneas do cache-ocr. Publicar por processo quando houver resultado novo, com estado preparando enquanto varredura continua.
- [x] No modo completo, não abrir mesa automaticamente até término; em falha terminal, abrir resultado parcial somente com indicação clara. No progressivo, abrir com primeiro resultado e atualizar sem resetar documento/zoom do usuário.
- [x] Publicação: montar revisão em diretório temporário, validar datasets, mover snapshot e trocar ponteiro atomicamente. Leitor fixa revisão por leitura. HTML/JSON estáticos atualizados ao finalizar ou empacotar.
- [x] Assinatura de retomada inclui hashes de entrada e versão de extração; nunca declarar atualizado só porque existe checkpoint. Guardar alternativas surgidas depois sem modificar o formulário atual.
- [x] Gate: dois workers sem perda de registros, retomada após kill, dedup entre processos, versão modificada, arquivo inválido, título genérico, evento repetido, autenticação expirada e resultados equivalentes entre modos.

**Commit:** `feat: prepare process results incrementally with bounded downloads`.

### Fase 7 — transporte consistente e pacote completo

**Criar:** `P/app/prepare_transfer.py`, `E/test_prepare_transfer.py`.
**Alterar:** `E/package_complete_archive.py`, `P/app/package_audit.py`, `P/Empacotar-Acervo-Completo.ps1`, `P/app/menu.ps1`, empacotadores que copiam app/runtime, `E/test_package_complete_archive.py`, `E/test_package_audit.py`, `E/test_portable_end_to_end.py`.

**Interface:** `prepare_transfer(package_root: Path, destination: Path) -> dict` pausa coordenador, drena workers, sincroniza outputs e usa `build_complete_zip`. Pausa não cancela writes em andamento. Em timeout de 60s não gera ZIP incoerente: informa worker pendente e permite tentar depois.

Teste RED inicial:

```python
def test_transfer_excludes_pairing_but_keeps_progress(self):
    result = prepare_transfer(self.package, self.output)
    with zipfile.ZipFile(result['path']) as archive:
        names = archive.namelist()
        self.assertIn('acervo-tce/progresso.json', names)
        self.assertFalse(any('dados-locais/' in name for name in names))
```

- [x] Criar fixture de pacote mínimo a partir dos helpers de teste existentes; executar `python -m unittest test_prepare_transfer` RED.
- [x] Atualizar `EXTENSION_FILE_ALLOWLIST` para bridge-client e demais assets aprovados; atualizar fontes copiadas para `app`, assets vendor e licenças. Não confiar só na pasta de desenvolvimento.
- [x] Snapshot inclui progresso e revisão coerentes; não apagar dados para economizar espaço.
- [x] Bloquear novas escritas durante fechamento/exportação com lease compartilhado e liberar a operação em `finally` se o empacotamento falhar.
- [x] Excluir autenticação, browser profiles, bridge state, .part, backups e logs privados. ZIP novo em destino distinto, sem overwrite silencioso.
- [x] Auditoria exige arquivos novos, hashes PDF/progresso/JSON, referências resolvíveis e CRC. Processo parcial permitido com relatório; capa faltante não reprova pacote.
- [ ] Extrair ZIP em pasta nova com espaços/acentos. Iniciar sem Python/Node no PATH; instalar extensão unpacked do ZIP; parear novamente; verificar ordem e conclusão conservadas.
- [x] Atualizar README e guias HTML/Markdown com os dois modos, bloqueios de PCs restritos, transporte, modo manual e significado de conclusão. Nenhuma instrução de PATH manual obrigatório.

**Commit:** `feat: package consistent portable workflow snapshots`.

### Fase 8 — QA integrado, medição e entrega

**Criar:** `E/test_integrated_workflow.py`, `E/qa_integrated_workflow.py`; relatório em `docs/notes` sem dados pessoais.
**Reutilizar:** `E/test_qa_extension_runtime.py`, `E/test_extension_browser.py`, fixtures `E/tests/fixtures/complementar-ato-*.html`.

- [x] RED para preenchimento com identidade alterada entre prévia e clique; criar cenário antes de corrigir eventual regressão.
- [x] Executar todos os testes JS/Python/PowerShell do baseline, além dos novos. Contabilizar skips; nenhum skip de OCR/bridge pode ser tratado como validação dessa funcionalidade.
- [ ] QA em Chrome separado: usuário autentica; agente abre somente telas de leitura e formulário autorizado. Testar preenchimento em fixture primeiro. Em portal real, nunca clicar no envio/finalização e nunca recarregar formulário com edição pendente.
- [ ] Verificar HTML noutra janela acompanhando processo/interessado em até 2s, pause/resume, dois PDFs em abas, zoom/rotação, todos os sete links de evidência e marca Concluído sem navegar.
- [ ] Comparar os mesmos 20 processos/baseline: primeiro resultado, tempo de preparação, OCR reutilizado, mediana/p95 de sincronização e cliques. Registrar hardware/rede/modo; não prometer processos/hora com base em tempo de máquina.
- [ ] Meta: seleção duplicada zero; clique Preencher único por aplicação; nenhum envio; 100% das fontes resolvem o documento/hash/página correto ou mostram ausência explícita. p95 sincronização <=2s no ambiente registrado.
- [ ] Repetir QA sobre ZIP extraído, não apenas source tree. Testar serviço bloqueado e fallback; teste em segundo PC real requer usuário se não houver acesso.
- [x] Documentar limites, falhas de documentos e testes não executados. Se gate falhar, entregar como candidato, não release validada.
- [x] Commit final, verificar remoto, push somente se houver destino autorizado e sem dados privados. Não criar/publicar remoto automaticamente. Commit local `e041a93`; sem `origin`, portanto sem push.

## 5. Sequência, revisão e rollback

Dependências: 0 → 1 → 2; 0 → 3; (2,3) → 4 → 5; (1,2,3,5) → 6 → 7 → 8. Geometria pode ser implementada em paralelo com estado/serviço por agentes autorizados, mas não editar o mesmo arquivo em paralelo. Integração no agente principal, com revisão de cada gate.

Não substituir imediatamente o pacote atual. Construir candidato em diretório separado, preservando PDFs e último ZIP. JSON v1 e HTML estático permitem voltar ao modo manual. Restaurar código por commits/revert deliberado, nunca `git reset --hard` sobre trabalho do usuário. Snapshots anteriores não equivalem a backups do acervo inteiro.

Ao interromper: registrar última fase/tarefa verde, teste RED em aberto, arquivos tocados, processos ativos, caminho da montagem candidata e ação humana necessária. Nunca deixar servidor autenticado sem informação de como pará-lo.

### Evidências que devem acompanhar a entrega

- Resultados por comando: executados/aprovados/falhados/ignorados e motivo.
- Versões e hashes de dependências, inclusive PDF.js e OCR.
- Screenshot de PDF inteiro com destaque alinhado e processo correspondente, mantido fora do Git se contiver dados pessoais.
- Teste de ZIP extraído, manifesto e SHA256 do ZIP.
- Benchmark comparativo sem afirmar ganho não medido.
- Handoff, commits e status do remoto.

## 6. Notas para evitar regressões conhecidas

- Não usar número de evento como chave exclusiva: hoje o HTML faz isso em `selectDocument`; corrigir com teste antes da bridge.
- Não adicionar caixas ao JSON v1: ambos validadores rejeitam chaves extras. Sidecar é decisão deliberada de compatibilidade.
- Não fazer dois processos escreverem `checkpoint`/`cache-ocr` global ao mesmo tempo; atomic replace sozinho não impede atualização perdida.
- Não marcar manualmente concluído a partir de status complete da coleta; são domínios distintos.
- Não usar timestamp de lote como identidade persistente de conclusão.
- Não fazer “novos” significar processos pendentes de trabalho humano.
- Não deixar geometria extraída de versão antiga sobre PDF novo: exigir hash igual.
- Não procurar só datas/valores curtos para destacar; exigir evidência contextual única.
- Não pressupor que carregamento de extensão/serviço em um PC comprova funcionamento em todos os PCs restritos.
- Não ampliar permissões do Chrome para todos os sites.
- Não empacotar credenciais de pareamento junto com progresso.

## 7. Estado deste documento

Plano elaborado em 08/09/2026 a partir dos fontes existentes. A execução posterior implementou as fases 1–7 como candidato integrado e adicionou QA fixture-only na fase 8. A extensão continua sendo o único componente autorizado a escrever nos sete campos; o botão de Complementar Ato apenas envia o sinal tipado, e a pesquisa manual não altera a identidade do portal.

Evidências atuais: `docs/notes/2026-09-08-fluxo-portatil-execucao-handoff.md`, `docs/notes/2026-09-08-transferencia-quiescente-handoff.md`, commits locais `ca1e372`/`4d0153c`/`a0424ac`, suítes Python/Node/PowerShell verdes, teste de navegador local da mesa, empacotador oficial e smoke Chrome do ZIP v4 extraído, e `qa_integrated_workflow.py --fixture-only`. A mesa HTML e o painel da extensão agora usam a mesma API `/api/v1/progress/<processo>` quando o serviço está ativo; o modo `file:` permanece fallback local. O fechamento de transferência usa lease compartilhado e recusa segura enquanto serviço/coleta estiverem ativos.

Não estão autorizados nem comprovados neste checkout: login/QA no portal real, benchmark dos mesmos 20 processos, instalação/pareamento em um segundo PC e teste do ZIP extraído sem Python/Node no PATH. Esses gates dependem de acesso humano/ambiente externo e permanecem explicitamente como candidato, não release validada. Caminhos abreviados devem ser expandidos pelas convenções do cabeçalho. Release/version pin de PDF.js é um gate explícito da fase 4, dependente do navegador alvo, não autorização para buscar dependências flutuantes durante execução normal.
