# Complementador e-Contas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Atualização 04/11/2026:** o operador autorizou a descoberta automática da Resolução Administrativa e da Guia Financeira/Taxação de Proventos nos cartões de evento. Onde este plano disser "nunca varrer eventos adicionais" ou "somente o documento atual", prevalece esta atualização.

**Goal:** Construir uma extensão Chrome independente que, após um único clique em **⚡ Preencher** na aba Complementar Ato, leia integralmente o documento que o operador deixou aberto na outra aba do mesmo perfil, extraia informações em regras locais, preencha os campos admissíveis e não salve/conclua o ato.

**Architecture:** Manifest V3, JavaScript sem framework de interface e roteamento entre duas abas pelo service worker. O adaptador de documento será escolhido após investigação passiva F0 com REA, sem pressupor acesso a `.textLayer`/`PDFViewerApplication`; o extrator e o formulário têm contratos puros/testáveis, com confirmação de identidade e verificação após escrita. Nenhum processamento de PDF antes do clique.

**Tech Stack:** Chrome/Chromium Manifest V3, JavaScript (ES modules), Node.js com `node:test`, esbuild apenas para empacotar se necessário, Playwright para testes sintéticos em navegador; REA (`morluto/rea`, `rea-agents`) exclusivamente como ferramenta de investigação F0, fora do runtime. Sem Python, SQLite, LLM, OCR, serviço local, cloud, banco ou CI no MVP.

**Spec:** `docs/superpowers/specs/2026-11-03-complementador-econtas-design.md` (aprovada em 03/11/2026). **Este plano depende da especificação: entregar ambos ao Codex.**

## Global Constraints

1. **Projeto novo, independente:** não modificar `matheussilva421/Atos-TCE`, nenhum de seus worktrees, PDFs, perfis, branches, banco, extension ou pacotes. Reaproveitar apenas conhecimento documentado, nunca código ou estado privado sem revisão/autorização.
2. **Entrada humana pré-posicionada:** o operador **deixará abertas** no **mesmo perfil do Chrome** duas abas/janelas: **Complementar Ato** e **Autos do mesmo processo, já exibindo o documento correto**. A extensão e REA devem inspecionar **essas abas já abertas**, sem exigir que o usuário selecione texto, escolha número fixo de evento ou baixe manualmente PDF.
3. **Não interromper sessão profissional:** não fazer login, reload, fechamento/abertura de abas, navegação de evento, mudança de interessado/setor/marcador/filtro, restart de Chrome, flags, mudança de perfil ou sessão CDP sem autorização expressa. Se CDP loopback não estiver disponível, documentar e usar a via observacional permitida; nunca improvisar takeover.
4. **Somente clique dispara trabalho:** detectar rota/mostrar botão sem leitura de PDF, OCR, parse ou extração. Após clique: leitura total do **documento selecionado atualmente**, validação, escrita seletiva, readback. Nunca varrer eventos adicionais.
5. **Data operacional:** converter **data da resolução administrativa** para **`DD/MM/AAAA`** e propor para o campo UI **Data de publicação no DOE**, com legenda `Origem: data da resolução` e conferência humana; não afirmar publicação jurídica nessa data. Datas conflitantes/ambíguas: campo não preenchido.
6. **Campos e cardinalidade:** `modalidade` por processo; `data_publicacao_doe`, `cargo`, `matricula`, `data_nascimento` por interessado. Modalidade corresponde a um único ID do catálogo atual do e-Contas; datas exigem interpretação explícita e controle `bsDatepicker` pode estar presente.
7. **Somente alterações de UI e somente quando autorizado:** jamais clicar `Complementar ato`, `Salvar modalidade`, `Confirmar` ou enviar `PUT/POST` de complementação. Não sobrescrever campos já preenchidos/readonly. **L2 no portal real (digitar nos controles sem salvar) requer autorização humana separada**; a aprovação deste plano não é L2.
8. **Privacidade:** nenhum PDF, texto integral, identificador pessoal, CPF, matrícula, nome, token, cookie, screenshot profissional, HAR ou URL autenticada com query em Git/relatórios/logs/telemetria; usar fixtures sintéticas e metadados sanitizados. Não chamar APIs externas.
9. **Implementação enxuta:** sem arquitetura de fila, autenticação extra, sincronização, processo batch, mecanismo de autoatualização ou frameworks não necessários. Permissões da extensão mínimas e limitadas à origem confirmada na F0.
10. **Qualidade:** TDD (ver teste falhar, corrigir, ver verde), commits pequenos após gates, nenhum GitHub Actions/CI, push/PR/merge/publicação apenas com autorização específica. Métricas de tempo **medidas**, não garantidas; preferência por caminho rápido sem OCR.

## Pre-work: source of truth e preparação do operador

- Documento de referência histórico, somente leitura: `2026-10-21-econtas-l0-discovery-handoff(1).md` (L0/L1 em 21/10/2026; Angular 10.0.14, e-Contas 2.6.17 no estado então observado). Não assumir que a versão atual é idêntica.
- Referência oficial REA: <https://github.com/morluto/rea> e <https://github.com/morluto/rea/blob/main/docs/browser-observation.md>. REA Web Observation usa CDP e um endpoint de depuração explícito; eventual instalação em estação institucional depende de permissão e revisão do operador. Confirmar requisitos da versão instalada, nunca instalar via pacote de origem duvidosa.
- As duas abas que o operador **prometeu deixar abertas** são uma **condição de execução futura no equipamento dele**; não afirmar que este planejamento já tem acesso a elas.
- Estado de inspeção permitido sem nova autorização: **observação passiva L0/L1 das abas abertas**, respeitando regras institucionais. Não inspecionar dados de processos alheios, não persistir conteúdo sensível. A escrita L2 é gate separado.

## Target file map (somente no NOVO repositório, após o aceite deste plano)

```text
Complementador-eContas/
├── package.json                   # build/teste locais (sem CI)
├── .gitignore                     # dist/, traces/, capturas/, perfis/, segredos/
├── README.md                      # instalar, usar, desinstalar e limites
├── extension/manifest.json        # MV3 com permissões mínimas
├── scripts/build.mjs              # gera dist/ de forma reproduzível
├── src/shared/routes.mjs          # parseRoute(url): tipo/idProcesso
├── src/shared/identity.mjs        # valida contexto processo/pessoa/documento
├── src/shared/protocol.mjs        # mensagens REQUEST_FILL/READ_DOCUMENT/APPLY_PLAN/RESULT
├── src/background/bridge.mjs      # selecionar abas e orquestrar uma transação
├── src/background/index.mjs       # entry service worker Chrome
├── src/autos/document-reader.mjs  # adapter escolhido em F0; todas as páginas
├── src/autos/content.mjs          # listener de leitura (sem pré-leitura)
├── src/extract/dates.mjs          # data da resolução, validação e DD/MM/AAAA
├── src/extract/fields.mjs         # extrator com fonte/status por campo
├── src/form/form-reader.mjs       # processo, interessado, inputs e catálogo
├── src/form/form-writer.mjs       # setter/eventos e readback, jamais submit
├── src/form/content.mjs           # botão contextual e feedback mínimo
├── tests/fixtures/               # HTML/PDF ou texto TODOS sintéticos
├── tests/unit/                   # node:test (funções puras e DOM mock)
├── tests/browser/                # fluxos sintéticos no Chrome
├── docs/evidence/f0-sanitized.md # achados Rhea/REA sem dados pessoais
├── docs/superpowers/specs/...    # spec aprovada
├── docs/superpowers/plans/...    # este plano
└── docs/notes/handoff.md         # estado real, gates, evidências e bloqueios
```

**Decisão de implementação:** preferir ES modules e bundle mínimo com esbuild para content scripts; **não** introduzir servidor ou UI framework. `dist/` é gerado, não fonte. Cada entrada da extensão somente ativa o código apropriado à rota; não fazer leitura em `DOMContentLoaded`/`MutationObserver`/install/evento de navegação.

## Contracts: stable interfaces (definir antes de codificar)

- `parseRoute(url: string): { kind: 'autos'|'complemento', idProcesso: string } | null` — somente rotas `https://processos.tce.rn.gov.br/` confirmadas; hash routing. Rejeitar URL de outra origem e ID malformado.
- `selectSourceTabs(tabs: BrowserTab[], targetId: string): {ok:true,tabId:number}|{ok:false,code:'SOURCE_NOT_FOUND'|'SOURCE_AMBIGUOUS'|'INVALID_TARGET'}` — **não** selecionar por aba mais recente quando 2+ candidatos.
- `readCurrentDocument(ctx: {expectedProcessId:string,requestId:string}): Promise<DocumentRead>` em `src/autos/document-reader.mjs`, onde `DocumentRead={documentKey:string, processId:string, pages:string[], sourceKind:'viewer-text'|'pdf-bytes', observedAt:number}`. Retornar **erro tipado** e não texto incompleto/silencioso; se mecanismo não viável, recusar e reportar `DOCUMENT_NOT_READABLE`.
- `parseResolutionDate(text: string): {status:'exact',dateBr:string,source:string}|{status:'absent'|'ambiguous',candidates?:string[]}` — aceitar somente data inequivocamente ligada à resolução; converter `7 de novembro de 2025` em `07/11/2025`; validar calendário.
- `extractFields(doc: DocumentRead, ctx: {selectedInterested:string, processId:string}): ProposedFields` — cada campo traz `{status:'exact'|'absent'|'ambiguous',value?:string,source?:string}`; não inferir nascimento, DOE efetivo ou modalidade sem evidência.
- `readForm(document: Document): FormSnapshot` — `processId`, `interestedKey`, `values`, `editable`, `modalities: [{id,label,disabled}]`, `revisionMarker`; fonte DOM da página **atual**, com validações de unicidade e carregamento.
- `createFillPlan(proposals: ProposedFields, form: FormSnapshot): FillPlan` — somente valores `exact` para controles vazios/editáveis e identidade confirmada; `modalidade` resolve correspondência **única** no catálogo. Nascimento ausente fica manual. Não alterar modalidade já selecionada.
- `applyFillPlan(document: Document, plan: FillPlan, expected: {processId:string,interestedKey:string,revisionMarker:string}): FillReport` — setter nativo + eventos e leitura pós-escrita; `filled/preserved/skipped/error` por campo, nenhuma submissão. Antes de cada campo, revalidar identidade e doc/rota, abortando se mudarem.
- Mensagens serializáveis com `requestId` efêmero; após clique uma transação ativa por formulário, timeout limitado, cancelamento por mudança de rota/aba/pessoa/documento e descarte de texto/planos em memória ao terminar.

**Nota:** referências aos IDs DOM e modo de obter `interestedKey` dependem de F0, não inventar seletores. Um documento de um único interessado não autoriza atribuição a outra pessoa em processos com múltiplos interessados.

## Review Focus — cinco riscos que exigem teste específico

1. **Documento muda depois do clique:** teste `document_switch_aborts_without_write` (Tasks 4 e 8); não aplicar plano antigo.
2. **Múltiplos interessados ou abas de autos:** testes `wrong_interested_never_receives_values` e `two_source_tabs_are_ambiguous` (Tasks 3 e 7).
3. **Datas concorrentes/semântica diversa:** testes `resolution_date_not_birth_or_other_date` e `conflicting_resolution_dates_are_ambiguous` (Task 6).
4. **Angular/bsDatepicker, modal já selecionado, campo readonly:** testes `datepicker_readback_matches_ui` e `existing_or_readonly_values_preserved` (Task 7).
5. **Submissão involuntária / vazamento de dados:** testes `no_submit_commands_or_network_writes` e `no_personal_data_persisted` (Task 9).

---

## F0 — Investigação obrigatória com Rhea/REA (somente observação, antes do código)

### Task 1: Reconhecer com REA as DUAS abas já abertas pelo operador

**Files:** Create `docs/evidence/f0-sanitized.md`; update `docs/notes/handoff.md` (no novo repositório quando existir; se ainda não existir, produzir documentos locais e migrar após autorização).

**Interfaces:** Consumes abas reais posicionadas pelo operador. Produces matriz de evidência `OBSERVED/HYPOTHESIS/UNKNOWN` sobre rotas, DOM, visualizador, seleção de documento, compatibilidade do REA e ausência de mudanças; não exporta conteúdo pessoal.

- [ ] **Step 1: Preparar pré-condições em leitura:** confirmar que existem duas abas e janelas do **mesmo perfil**: `complementar-ato/:idProcesso` e `processos/:idProcesso/autos` com o documento correto visível; conferir IDs sem registrar dados pessoais. Não abrir outra aba/alterar processo/evento/pessoa/seleção.
- [ ] **Step 2: Verificar ferramentas sem efeitos colaterais:** consultar o REA instalado, `list_browser_targets` e capacidade de CDP loopback preexistente; não alterar flags/perfil e não iniciar novo Chrome. Se não houver CDP, registrar `REA_CDP_UNAVAILABLE` e continuar inspeção observacional permitida por navegador/DevTools; não afirmar que REA observou quando não observou.
- [ ] **Step 3: Inspecionar DOM e recursos de forma passiva:** aba autos (evento ativo, viewer, iframe, textLayer, referência do PDF, total de páginas, mudança de documento) e aba complemento (rota, processo, interessado, catálogo modalidade, quatro campos, componente de datas, editabilidade); comparar com L0/L1 de 21/10/2026. Não extrair conteúdo pessoal persistente nem gravar HAR/screenshots do processo.
- [ ] **Step 4: Documentar caminho autorizado de leitura:** verificar se texto de **todas as páginas** é acessível; senão, verificar se o PDF atual é obtível por acesso legítimo permitido (sem bypass de auth/DRM/CORS e sem chamadas de gravação). Registrar opção técnica, limitações, versão/assinatura do portal e como detectar documento desatualizado; não inferir sucesso por aparência de PDF.js.
- [ ] **Step 5: Aceite F0:** gerar `docs/evidence/f0-sanitized.md` com tabela `pergunta | evidência observada | hipótese | limite | decisão` e recomendação de adapter. Marcar `F0_GO` somente com leitura permitida comprovada; caso contrário `F0_NEEDS_OPERATOR_DECISION` e manter avanço apenas em fixtures/mocks, **não simular que o fluxo real está funcional**.

### Task 2: Produzir fixtures sintéticas e contrato do DOM atual

**Files:** Create `tests/fixtures/form-complemento.html`, `tests/fixtures/autos-viewer.html`, `tests/fixtures/resolucao-natodigital.txt`, `tests/fixtures/resolucao-ambigua.txt`, `docs/evidence/dom-contract.md`.

**Interfaces:** Produces seletores/convenções verificadas (sem dados reais) para Tasks 4–8. Se F0 não confirmou um componente, registrar explicitamente a suposição e testar apenas mock.

- [ ] **Step 1: Registrar o contrato do DOM observado** (labels, controles, `ng-version`, diretiva `bsDatepicker`, valor/id da modalidade, status dos interessados) sem valores pessoais e sem cookies; diferenciar evidência atual de versão histórica.
- [ ] **Step 2: Montar fixtures fictícias** com duas abas, ID de processo falso idêntico, um interessado e variante de dois interessados; resolução fictícia contendo `Natal, 7 de novembro de 2025`, cargo e matrícula sintéticos; uma segunda com datas em conflito.
- [ ] **Step 3: Verificar fixtures sem navegador institucional**: conferência estrutural e teste `fixture_does_not_contain_real_identifiers` (procura somente dados fictícios e sem dados do caso real). Documentar os elementos não comprovados.
- [ ] **Step 4: Commit apenas quando houver repositório novo e autorização de execução.** Critério: as fixtures permitem repetir cada teste sem acessar o e-Contas real.

## F1 — Produto mínimo de um clique

### Task 3: Criar MV3 e resolver rotas/abas sem ler PDF

**Files:** Create `package.json`, `.gitignore`, `extension/manifest.json`, `scripts/build.mjs`, `src/shared/routes.mjs`, `src/shared/identity.mjs`, `src/shared/protocol.mjs`, `src/background/bridge.mjs`, `tests/unit/routes.test.mjs`, `tests/unit/bridge.test.mjs`.

**Interfaces:** Produces `parseRoute`, `selectSourceTabs`, `sameProcess` e mensagens tipadas/constantes; consumes estrutura do portal em F0. Nenhuma leitura do conteúdo documental.

- [ ] **Step 1: Escrever testes falhando** `parse_route_autos_and_complemento`, `reject_foreign_origin`, `two_source_tabs_are_ambiguous`, `different_process_is_rejected`, `cross_window_same_profile_resolves`, `no_pdf_read_on_route_detection`.
- [ ] **Step 2: Rodar** `npm test -- --test-name-pattern='parse_route|reject_foreign|two_source|different_process|cross_window|no_pdf_read'` (ou `node --test tests/unit/routes.test.mjs tests/unit/bridge.test.mjs`) e registrar FAIL antes da implementação.
- [ ] **Step 3: Implementar as quatro interfaces** e Manifest V3 mínimo. Sem permissões amplas (`<all_urls>`, captura de tela, `downloads`, `webRequest`) salvo evidência real F0. `tabs`/`scripting` ou host permission apenas se necessário e justificadas; regras de match por origem real confirmada.
- [ ] **Step 4: Rodar** `npm test` e `npm run build`; esperado PASS e `dist/manifest.json` com entrypoints presentes, sem conteúdo privado.
- [ ] **Step 5: Commit** `feat: scaffold independent chrome extension and match process tabs` em repositório novo.

### Task 4: Implementar botão contextual e ciclo de mensagens sob demanda

**Files:** Create `src/form/content.mjs`, `src/autos/content.mjs`, `src/background/index.mjs`, `tests/unit/protocol.test.mjs`, `tests/browser/one-click.spec.mjs`; modify `extension/manifest.json` e `scripts/build.mjs`.

**Interfaces:** Consumes `parseRoute`, `selectSourceTabs`; produces `REQUEST_FILL`, `READ_DOCUMENT`, `APPLY_PLAN`, `RESULT` com `requestId` efêmero e timeout. `READ_DOCUMENT` só é enviado após clique. Sem parser real nesta Task: usar resposta sintética injetada/mocks.

- [ ] **Step 1: Escrever testes falhando** `button_only_on_complement_route`, `only_click_starts_read`, `double_click_is_single_transaction`, `document_switch_aborts_without_write`, `worker_restart_aborts_without_replay`.
- [ ] **Step 2: Rodar** `node --test tests/unit/protocol.test.mjs` e teste de navegador sintético, confirmar falha.
- [ ] **Step 3: Implementar botão** pequeno sem alterar layout central; estado `Pronto → Lendo → Preenchendo → Concluído/Parcial/Erro`, mensagens com `requestId`, timeouts e garantia de operação única. Alterações de rota/contexto abortam; não percorrer eventos.
- [ ] **Step 4: Rodar** `npm test` e `npm run test:browser` contra fixtures locais; esperado nenhuma leitura antes do clique, zero submissões e recuperação limpa após erro.
- [ ] **Step 5: Commit** `feat: trigger isolated cross-tab workflow on click`.

## F2 — Documento e extração determinística

### Task 5: Adaptador mínimo de leitura integral do documento atual

**Files:** Create `src/autos/document-reader.mjs`, `tests/unit/document-reader.test.mjs`, `tests/fixtures/document-switch.json`; modify `src/autos/content.mjs`.

**Interfaces:** Produces `readCurrentDocument(ctx): Promise<DocumentRead>` conforme contrato. O adapter real é o caminho **comprovado na F0**: (1) texto acessível de todas as páginas, ou (2) bytes do **mesmo PDF** obtidos legitimamente e lidos por biblioteca local fixada. Não implementar mecanismos hipotéticos em paralelo.

- [ ] **Step 1: Escrever testes falhando** `all_pages_extracted`, `only_current_document_read`, `document_switch_aborts_without_write`, `blank_or_partial_document_returns_error`, `document_not_readable_fails_closed`, `no_reader_before_click`.
- [ ] **Step 2: Rodar** `node --test tests/unit/document-reader.test.mjs`; confirmar FAIL.
- [ ] **Step 3: Implementar adapter escolhido**; incluir prova do identificador do PDF e do processo antes/depois da leitura, ordem das páginas, limite razoável e cancelamento. Não armazenar bytes/texto em `chrome.storage`; liberar buffers ao concluir.
- [ ] **Step 4: Rodar** testes dirigidos, `npm test` e integração em fixture autorizada; PASS. Se obtenção do PDF em produção não foi provada, registrar `REAL_VIEWER_UNVERIFIED` e **não prometer integração real**.
- [ ] **Step 5: Commit** `feat: read only the operator-selected document on demand`.

### Task 6: Parser com evidência e a regra da data administrativa

**Files:** Create `src/extract/dates.mjs`, `src/extract/fields.mjs`, `tests/unit/dates.test.mjs`, `tests/unit/fields.test.mjs`.

**Interfaces:** Produces `parseResolutionDate(text)` e `extractFields(doc,ctx)`; em `ProposedFields`, cada campo identifica `exact/absent/ambiguous` e `source`. Não acrescentar inferências via LLM.

- [ ] **Step 1: Escrever testes falhando** `seven_november_to_07_11_2025`, `resolution_date_not_birth_or_other_date`, `conflicting_resolution_dates_are_ambiguous`, `preserve_matricula_slash_and_zeros`, `cargo_not_inferred_from_unrelated_section`, `birth_not_invented`, `interest_mismatch_drops_person_fields`, `unmapped_modality_is_ambiguous`.
- [ ] **Step 2: Rodar** `node --test tests/unit/dates.test.mjs tests/unit/fields.test.mjs` e confirmar FAIL.
- [ ] **Step 3: Implementar regras locais**: data do ato por associação textual e validação real de calendário; regras de matrícula/cargo/modalidade com trecho de origem; seleção vinculada ao interessado; data de nascimento apenas quando expressa. **Não** transformar a data da resolução em comprovação de publicação: saída carrega `source='data da resolução administrativa'`.
- [ ] **Step 4: Rodar** testes dirigidos e `npm test`, conferir fixtures de ambiguidade e possíveis variantes; PASS.
- [ ] **Step 5: Commit** `feat: extract resolution fields with provenance and explicit date rule`.

## F3 — Preenchimento verificado, nunca submissão

### Task 7: Ler e escrever formulário real com proteção de identidade

**Files:** Create `src/form/form-reader.mjs`, `src/form/form-writer.mjs`, `tests/unit/form-reader.test.mjs`, `tests/unit/form-writer.test.mjs`, `tests/fixtures/form-multi-interested.html`; modify `src/form/content.mjs`.

**Interfaces:** Produces `readForm(document)`, `createFillPlan(proposals,form)` e `applyFillPlan(document,plan,expected)` conforme contratos; `form-reader` lida com Angular e `bsDatepicker`, com ID do catálogo de modalidades presente no DOM; dados pessoais nunca são logados.

- [ ] **Step 1: Escrever testes falhando** `modalidade_process_level`, `four_fields_per_interested`, `wrong_interested_never_receives_values`, `existing_or_readonly_values_preserved`, `unique_catalog_option_only`, `datepicker_readback_matches_ui`, `not_loaded_or_invalid_form_refused`, `recheck_identity_before_each_write`.
- [ ] **Step 2: Rodar** `node --test tests/unit/form-reader.test.mjs tests/unit/form-writer.test.mjs`; confirmar FAIL.
- [ ] **Step 3: Implementar leitura de controles efetivos** verificados na F0 (não inventar IDs). Implementar setter nativo e somente eventos necessários de `input/change/blur`, conversão explícita para datepicker, readback após cada campo e cancelamento de mudanças de processo/interessado/rota. Não acionar Enter, formulário submit, eventos de botão ou endpoints de gravação.
- [ ] **Step 4: Rodar** `npm test` + `npm run test:browser` em fixtures locais. Esperado: valores refletidos no DOM e nos estados de UI; somente campos vazios e sem ambiguidade alterados; campo divergente preservado.
- [ ] **Step 5: Commit** `feat: fill editable act controls with guarded readback`.

### Task 8: Integrar o clique ao parser e ao formulário

**Files:** Modify `src/background/bridge.mjs`, `src/autos/content.mjs`, `src/form/content.mjs`; create `tests/browser/full-flow.spec.mjs`.

**Interfaces:** Consumes `readCurrentDocument`, `extractFields`, `readForm`, `createFillPlan`, `applyFillPlan`. Produces relatório sintético `{requestId,status,fieldResults,elapsedMs}` sem conteúdo sensível persistente.

- [ ] **Step 1: Escrever testes falhando** `full_click_to_read_to_fill`, `document_switch_aborts_without_write`, `process_switch_aborts`, `multiple_interested_requires_exact_match`, `partial_fill_reports_missing_values`, `no_retry_stale_plan`.
- [ ] **Step 2: Rodar** `npm run test:browser -- full-flow` e confirmar FAIL.
- [ ] **Step 3: Implementar coordenação sem caches persistentes**: um clique, uma coleta completa, um conjunto de propostas, um conjunto de escritas elegíveis, readback, feedback discreto. No erro, descartar dados efêmeros e permitir nova tentativa segura.
- [ ] **Step 4: Rodar** `npm test && npm run test:browser && npm run build` e conferir zero POST/PUT/submit em mocks.
- [ ] **Step 5: Commit** `feat: complete single-click assisted fill without submit`.

## F4 — Gates, desempenho, distribuição

### Task 9: Segurança, regressão e auditoria de privacidade

**Files:** Create `tests/unit/security.test.mjs`, `tests/browser/negative-cases.spec.mjs`, `docs/evidence/security-audit.md`; modify apenas arquivos necessários por falhas verificadas.

**Interfaces:** Consumes extensão compilada; verifies nenhum auto-submit, nenhuma rede externa, nenhuma persistência de dados reais, proteção cross-process e nenhuma leitura antes do clique.

- [ ] **Step 1: Escrever testes falhando** `no_submit_commands_or_network_writes`, `no_personal_data_persisted`, `no_external_network`, `no_read_before_click`, `cross_process_refused`, `two_source_tabs_are_ambiguous`, `readonly_preserved`.
- [ ] **Step 2: Rodar** `npm test` e testes de navegador sintéticos; documentar FAIL relevante antes de corrigir.
- [ ] **Step 3: Corrigir somente falhas reproduzidas** e revisar manualmente `manifest.json`, APIs de rede, listeners, storage, console e build; jamais coletar HAR/screenshot de processos reais.
- [ ] **Step 4: Rodar** `npm test && npm run test:browser && npm run build && git diff --check`; PASS exigido, com logs sem PII.
- [ ] **Step 5: Commit** `test: verify privacy, identity boundaries and no-submit behavior`.

### Task 10: Benchmark e teste real supervisionado sem submissão

**Files:** Create `docs/evidence/benchmarks.md`, `docs/evidence/live-verification.md`; modify `docs/notes/handoff.md`.

**Interfaces:** Produces relatório p50/p95 e matriz de testes `MOCK_PASS / REAL_READ_PASS / L2_NOT_AUTHORIZED / L2_PASS / BLOCKED`. A meta ~1 segundo para PDF nato-digital pequeno é **experimental**.

- [ ] **Step 1: Medir** em fixtures sintéticas (PDF curto e mais longo), cronômetro `performance.now()` do clique até readback; registrar ambiente, tamanho, amostras e p50/p95 sem alegar SLA.
- [ ] **Step 2: Na sessão do operador, usar exclusivamente as DUAS abas deixadas abertas** e verificar leitura em modo observacional/sem escrita, se permitido. Não alterar o documento escolhido, não navegar, reiniciar, exportar ou coletar conteúdo pessoal.
- [ ] **Step 3: Verificar autorização L2 explícita SE obtida** para preencher apenas campos de UI no processo concreto; se ausente, registrar `L2_NOT_AUTHORIZED` e executar o fluxo completo somente com fixtures sintéticas. Detectar autosave/requisições de escrita e interromper imediatamente se presentes; nunca salvar/concluir.
- [ ] **Step 4: Consolidar evidências** com tempos verificados, limitações do PDF e comportamento do Angular. Não marcar `REAL_FILL_VERIFIED` só por testes com mocks. Se componente real estiver indisponível, declarar gate pendente, sem inventar aceite.
- [ ] **Step 5: Atualizar handoff** com SHA, testes, flags, comando de rollback, necessidade eventual de ação humana, sem screenshot/HAR/tokens/identidades.

### Task 11: Pacote instalável e documentação curta

**Files:** Create `README.md`, `docs/notes/handoff.md`; modify `scripts/build.mjs`, `.gitignore`, `extension/manifest.json` conforme necessidade; output gerado `dist/`.

**Interfaces:** Produces pacote unpacked instalável pelo operador em `chrome://extensions` e instruções de atualização, desativação e rollback. Não inclui PDF, perfis, tokens nem logs pessoais.

- [ ] **Step 1: Adicionar teste do pacote** `build_has_manifest_and_scripts`, `manifest_permissions_limited_to_portal`, `package_has_no_personal_data`.
- [ ] **Step 2: Rodar** `npm test`, confirmar FAIL antes de correção necessária.
- [ ] **Step 3: Finalizar build** para gerar somente arquivos da extensão, com versão fixada e dependências vendorizadas em bundle quando necessárias; README com instalação por `Carregar sem compactação`, uso em duas janelas do mesmo perfil, falhas comuns e remoção.
- [ ] **Step 4: Rodar** `npm test && npm run test:browser && npm run build && git diff --check`, inspecionar `dist/` manualmente e registrar hashes. Validar instalação em **perfil de teste isolado**; instalação no perfil profissional exige operador presente/anuência.
- [ ] **Step 5: Commit** `docs: package standalone e-contas complementer with safe rollback`. Não fazer push/PR/publicação sem autorização.

## Delivery gates and rollback

- **Gate F0 (read-only):** diagnóstico do REA/inspeção daquelas duas abas reais; prova ou limitação do acesso ao PDF atual; sem manipular a sessão.
- **Gate F1/F2:** testes de rotas/mensagens e parser em dados sintéticos, antes de integração no portal.
- **Gate F3:** preenchimento em fixtures com readback; L2 live **não presumida** pela aprovação do plano.
- **Gate F4:** relatório de desempenho, privacidade e pacote; resultado real só se comprovado com supervisão/autorização correspondente.
- **Rollback simples:** desabilitar/remover a extensão em `chrome://extensions` e recarregar manualmente a página quando o operador decidir; nenhuma alteração em servidor ou processo é feita pela extensão. Campos de UI eventualmente preenchidos e não salvos podem exigir descarte da edição pelo próprio operador; não automatizar reload para apagá-los.
- **Sem loops de correção:** no máximo duas tentativas de correção por falha identificada; depois preservar evidência e classificar bloqueio real, sem declarar falsos PASS.
- **Final report required:** branch/HEAD/status do novo repo; comandos/testes e resultados reais; F0, F1–F4 (PASS/PARTIAL/BLOCKED); documentação; desempenho medido; prova negativa de não envio; pendências/gates; passos de instalação e rollback. Sem dados sensíveis.

## Self-review against approved spec

- [x] Projeto MV3 independente, sem Python/IA/servidor no MVP → Tasks 3, 4, 11.
- [x] Duas abas já abertas pelo operador no mesmo Chrome, sem mudar contexto → Tasks 1, 3, 4, 10.
- [x] Rhea/REA fase inicial obrigatória; sem CDP inventado → Task 1.
- [x] Um clique, nenhum processamento antes → Tasks 4, 5, 8, 9.
- [x] PDF atual, todas as páginas, evento variável → Tasks 1, 5.
- [x] Regra operacional da data da resolução `DD/MM/AAAA` → Task 6.
- [x] Modalidade por processo e outros campos por interessado; datepicker Angular → Task 7.
- [x] Preservação, match e readback, nunca submeter → Tasks 3, 7–9.
- [x] Cronometragem real, distribuição e rollback → Tasks 10–11.
- [x] Cinco riscos de Review Focus cobertos nos testes nominados → Tasks 3, 4, 6, 7, 9.

## Execution recommendation / handoff

**Método recomendado:** execução **subagent-driven** no Codex, com implementador e revisor independentes por Task, sem ampliar escopo, e revisão geral no final. O operador já manifestou preferência por autonomia de Codex; não criar PR/CI/Actions desnecessários. Antes da implementação, obter aprovação **deste** writing-plan e executar F0 respeitando a condição das abas abertas. O plano pode prosseguir em testes sintéticos mesmo se a conexão REA/CDP estiver indisponível, mas **não pode declarar integração real concluída** sem evidência. Não confundir autorização geral para implementar com autorização de escrever no formulário profissional do portal.
