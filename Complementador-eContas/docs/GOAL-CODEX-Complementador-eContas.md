# GOAL ÚNICO — CODEX DESKTOP | COMPLEMENTADOR E-CONTAS

**Data-base:** 03/11/2026  
**Modo:** execução autônoma integral da especificação e do writing-plan Superpowers, com checkpoints verificáveis  
**Produto:** extensão Google Chrome Manifest V3 INDEPENDENTE para o e-Contas do TCE/RN  
**Status das autorizações:** design e plano aprovados; implementação do projeto novo autorizada por este GOAL; observação passiva das duas abas preparada pelo operador; escrita em formulário profissional real (L2) **NÃO** autorizada por este GOAL; salvar/concluir ato **PROIBIDO**.

## MISSÃO — executar, não apenas analisar

Execute integralmente, na ordem de dependências e com TDD, as **11 tarefas das fases F0–F4** do plano `docs/superpowers/plans/2026-11-03-complementador-econtas-implementation.md`, implementando o design aprovado em `docs/superpowers/specs/2026-11-03-complementador-econtas-design.md`. Seu objetivo é entregar uma extensão instalável, documentada, testada e o mais rápida e simples possível, independente de qualquer outro projeto.

**Não pare ao concluir F0 nem entregue só recomendações, esqueleto ou prova de conceito.** Prossiga autonomamente nas tarefas viáveis, inclusive quando uma parte da integração real não puder ser comprovada; use fixtures sintéticas, registre a lacuna e deixe o produto no melhor estado verificável sem alegar êxito real indevido. Não transforme ausência de autorização L2 em bloqueio do desenvolvimento e dos testes sintéticos.

## 0. FONTE DA VERDADE E PREPARAÇÃO

1. Identifique o diretório aberto no Codex Desktop e inventarie arquivos, Git, HEAD e `git status` **sem alterar nada**. Se o workspace aberto for `Atos-TCE`, qualquer pasta, worktree ou cópia dele, **não implemente ali**. Use um diretório novo e independente, preferencialmente `Complementador-eContas`, fora da árvore do Atos-TCE; não renomeie, mova ou limpe nenhum repositório existente. Se o ambiente impedir criar o novo workspace, preserve os originais e informe o bloqueio específico.
2. Certifique-se de que estes dois arquivos estão presentes no **novo** projeto, nos caminhos relativos EXATOS:
   - `docs/superpowers/specs/2026-11-03-complementador-econtas-design.md`
   - `docs/superpowers/plans/2026-11-03-complementador-econtas-implementation.md`
   Eles são fornecidos no mesmo pacote que este GOAL; **leia integralmente os dois antes de executar**. Se a pasta estiver em um ZIP fornecido pelo operador, extraia-a somente no novo workspace, sem tocar no Atos-TCE. Não substitua os documentos aprovados por resumos nem invente conteúdo quando ausentes.
3. Ordem de precedência: segurança, autorização e políticas institucionais > design aprovado > writing-plan > este GOAL para orquestração > escolhas de implementação. Inconsistências não críticas: faça uma decisão mínima e registre como `Ruling` no ledger; não promova suposições a evidência.
4. Aplique as skills oficiais **Superpowers**: `using-superpowers`, `subagent-driven-development` quando suportado e oportuno; ou `executing-plans` se a execução nativa for mais eficiente/única disponível. Carregue `test-driven-development`, `systematic-debugging` para defeitos e `verification-before-completion`, além de `requesting-code-review` no encerramento. Não simule ferramentas/subagentes indisponíveis.
5. Inicie no workspace novo um ledger durável em `.superpowers/sdd/<nome-do-plano>/progress.md` (ou caminho exigido pela skill) e `docs/notes/handoff.md`, com fases, tarefas, commits, testes, evidências, decisões, bloqueios e próximos passos. Retome estado existente verificado antes de refazer tarefas. Preserve arquivos ignorados e dados do operador.
6. Preserve a história da investigação L0/L1 de **21/10/2026** apenas como antecedente técnico: e-Contas Angular 10.0.14/versão 2.6.17 naquela data, modalidade por processo, demais quatro campos por interessado, data visual com `bsDatepicker`, e L2 não executado. **Não trate isso como prova do portal atual**. Consulte a referência sanitizada incluída no pacote, se presente.

## 1. CONDIÇÃO OPERACIONAL DO CHROME — LEIA ANTES DE QUALQUER TESTE

O operador **deixará abertas duas abas ou janelas do MESMO perfil Chrome**, já autenticadas e posicionadas manualmente:

- **Fonte:** `https://processos.tce.rn.gov.br/#/dashboard/processos/:idProcesso/autos`, com o documento correto do evento correto **já aberto no visualizador**, independentemente do número do evento;
- **Destino:** `https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/:idProcesso`, no mesmo processo, com o interessado correto selecionado pelo operador.

**Use essas abas existentes.** Na investigação não abra/feche/atualize abas, não navegue para outro evento/processo/interessado, não altere filtros, marcadores, setor ou login, não reinicie o Chrome, não altere flags, não crie outro perfil, não solicite credenciais e não modifique estado profissional. O simples fato de as abas estarem abertas **não** é autorização para escrever nos controles.

A F0 é **observacional/read-only** e deve verificar versão e comportamento real do site, estrutura DOM, catálogo, visualizador, seleção do documento, URL/ID, número de páginas e método legítimo de acesso ao texto ou bytes do arquivo. Não é permitido registrar nomes, CPF, matrícula real, documento, conteúdo de PDF, cookies, tokens, HAR, screenshot de processo ou URL autenticada com query nos relatórios, no Git ou em serviços externos.

Se precisar de ação humana indispensável (por exemplo, para habilitar um endpoint CDP que não existe, instalar extensão no perfil institucional ou autorizar L2), registre o gate com instrução mínima. Continue todo trabalho sintético independente enquanto isso. Não contorne o gate nem afirme que executou teste real.

## 2. F0 — REA E INSPEÇÃO DO E-CONTAS (TASKS 1 E 2)

### Task 1 — investigação de evidência real

1. Verifique se o **REA oficial, Reverse Engineer Anything**, está disponível, com referência `https://github.com/morluto/rea`, pacote `rea-agents` e documentação oficial `docs/browser-observation.md`. Confirme requisitos da versão e as ferramentas disponíveis, sem presumir acesso. A investigação via REA deve utilizar, se viável, o Chrome existente e um **CDP loopback já disponibilizado legitimamente**.
2. Preferir `list_browser_targets`, `inspect_web_page`, `analyze_web_bundle` e outras operações de observação passiva estritamente necessárias e permitidas. Se o CDP não existir, registrar `REA_CDP_UNAVAILABLE`; não reabrir Chrome com `--remote-debugging-port` nem iniciar outro perfil como se fosse a sessão do usuário. Usar somente vias alternativas de leitura autorizadas; documentar qual ferramenta observou o quê.
3. Investigue separadamente **autos/visualizador** e **Complementar Ato**. Confirmar rotas Angular hash, relação entre IDs, identificação de documento atual, totalidade das páginas, disponibilidade de `.textLayer`, PDF.js ou recurso PDF legítimo, iframes, troca de documento, form controls, opções reais da modalidade, estado readonly, pessoa selecionada e reatividade dos campos de data. A aparência visual não prova que o PDF inteiro esteja acessível.
4. Descubra o caminho MAIS SIMPLES que consiga ler, **sob demanda e em todas as páginas**, apenas o documento que está aberto. Prefira texto já acessível; quando indisponível, investigar recuperação **autorizada** dos bytes do mesmo PDF e extração com biblioteca local fixada. Nunca utilizar endpoints de escrita, burlar MFA/autorização/CORS ou coletar credenciais.
5. Produza `docs/evidence/f0-sanitized.md`: matriz `OBSERVED/HYPOTHESIS/UNKNOWN`, assinatura/versão observada, mecanismo efetivamente comprovado, alternativas descartadas, limitações e decisão `F0_GO` ou `F0_NEEDS_OPERATOR_DECISION`. Se não houver acesso real, declare-o; **não marque REAL_VIEWER_VERIFIED**.

### Task 2 — fixtures/contrato observável

Crie as fixtures e o contrato DOM previstos no plano (`tests/fixtures/...`, `docs/evidence/dom-contract.md`) com dados 100% sintéticos. Cubra pelo menos um interessado, múltiplos interessados, evento variável, documento com múltiplas páginas, resolução com data textual e datas conflitantes, modalidade já existente, campos vazios/readonly. Registre explicitamente quais detalhes são simulados por ausência de observação. Não use dados da captura real como fixture.

## 3. F1 — EXTENSÃO MÍNIMA AUTÔNOMA (TASKS 3 E 4)

### Task 3 — Manifest V3 e vínculo seguro entre abas

Implemente repositório Git novo e uma extensão local com MV3, JavaScript ES modules, build mínimo (esbuild **somente se necessário**), testes com `node:test` e browser fixtures Playwright. Não use React, backend, Python, SQLite, nuvem, IA, LLM, OCR, Chrome Web Store, banco, CI ou Actions no MVP.

Implemente os contratos exatos do writing-plan: `parseRoute`, `selectSourceTabs`, `sameProcess`, protocolo serializável e gerenciamento de transação. Identifique as abas **entre janelas diferentes do mesmo perfil**, rejeite origem externa e IDs inválidos, valide que `idProcesso` coincide. Se houver duas candidatas, recuse em vez de escolher a mais recente. Permissões mínimas: nada de `<all_urls>`; pedir apenas as efetivamente necessárias e justificadas pela F0.

### Task 4 — um botão, sem leitura antecipada

Injete na rota de complementação um botão discreto **⚡ Preencher** e uma indicação compacta de status. Não altere o layout profissional além do necessário. O service worker faz `REQUEST_FILL → READ_DOCUMENT → APPLY_PLAN → RESULT` com `requestId` efêmero, timeout controlado, transação única, proteção contra clique duplo e cancelamento se pessoa, processo, aba, rota ou documento mudarem. **Nenhum texto de PDF deve ser lido, extraído ou pré-processado antes do clique**. Nenhum evento de navegação/detecção pode disparar extração.

## 4. F2 — LEITURA E EXTRAÇÃO (TASKS 5 E 6)

### Task 5 — ler somente o documento correto, todas as páginas

Implemente `readCurrentDocument` do plano usando **um único adaptador principal comprovado na F0**, não três mecanismos hipotéticos em paralelo. Retorne estrutura com `documentKey`, `processId`, `pages[]`, `sourceKind`, `observedAt`; valide identidade e estabilidade antes/depois; detecte mudança do documento ou leitura parcial e **falhe fechado** sem escrever nada. Não percorra outros eventos, não faça download manual obrigatório e não persista PDF/texto em `chrome.storage`, IndexedDB ou disco. Sem OCR no MVP. Se o visualizador real bloquear a leitura, entregue fluxo sintético funcional e marque claramente `REAL_VIEWER_UNVERIFIED`, sem fingir produção.

### Task 6 — parser determinístico com proveniência

Implemente `parseResolutionDate` e `extractFields` com regras locais/regex e resultados `exact/absent/ambiguous`, sempre com fonte mínima de cada valor:

- **Modalidade:** por processo; mapear somente para um ID único e habilitado do catálogo real do e-Contas; não selecionar por aproximação ambígua.
- **Cargo:** fiel ao trecho do interessado, sem inventar abreviações ou aplicar de outra pessoa.
- **Matrícula:** preservar zeros iniciais, `/`, hífen e sufixos; validar limites do formulário.
- **Data do DOE no formulário:** regra operacional do usuário: usar **a data inequívoca da resolução administrativa**, normalizada para `DD/MM/AAAA`. Exemplo sintético: `Natal, 7 de novembro de 2025` → `07/11/2025`. Mostrar `Origem: data da resolução administrativa` para conferência; **não** declarar que a publicação oficial ocorreu naquela data. Não confundir com data de nascimento, publicação distinta, assinatura eletrônica, despacho, referência histórica nem outra data incidental. Se houver conflito ou dúvida, deixar sem preenchimento e avisar.
- **Data de nascimento:** preencher apenas se estiver expressa no documento e corresponder à pessoa correta; caso contrário preservar ou deixar manual.

Documento com várias pessoas não autoriza atribuir dados ao interessado selecionado sem correspondência segura. Não inventar valores com heurística frágil; se incerto, mostrar pendência.

## 5. F3 — PREENCHIMENTO SEGURO, SEM ENVIO (TASKS 7 E 8)

### Task 7 — ler, escrever e reler controle por controle

Confirme no DOM atual a divisão **modalidade por processo** e **quatro campos por interessado**. Leia o `revisionMarker`, identificação de pessoa e estado dos campos. `createFillPlan` aceita apenas propostas `exact`, campos vazios/editáveis e opção de modalidade de correspondência única. Preserve todos os existentes/readonly e não altere modalidade já selecionada. Use setters nativos e eventos específicos suficientes para componentes Angular/`bsDatepicker`, não eventos que salvem dados. Antes de CADA escrita, revalide rota, processo, interessado e versão do formulário; após cada escrita, faça readback. Se o portal aparentar autosave na digitação, **interrompa qualquer teste L2 real** e reporte o risco.

### Task 8 — orquestração integral e feedback

Implemente o ciclo completo de **um clique**: detectar aba de autos do mesmo processo → obter documento aberto → extrair todas as páginas → preparar propostas → aplicar somente campos admissíveis → reler → mostrar `preenchido / preservado / não encontrado / ambíguo / erro` e tempo decorrido. Mantenha conteúdo documental somente em memória pelo tempo da transação. Alteração de documento/rota/pessoa cancela e descarta; nunca reaplique plano antigo. Não acione Enter, botão `Complementar Ato`, `Salvar modalidade`, `Confirmar`, `form.submit`, requisições PUT/POST ou outras ações de gravação.

## 6. F4 — TESTES, PERFORMANCE E ENTREGA (TASKS 9, 10 E 11)

### Task 9 — regressões e segurança

Produza testes unitários e de navegador com **fixtures sintéticas** para:
- não ler PDF antes do clique, impedir cliques concorrentes e abortar ao mudar documento;
- duas abas fonte, processo divergente, vários interessados e pessoa divergente;
- documento sem texto, páginas incompletas, evento variável e datas ambíguas;
- campos preenchidos/readonly, modalidade já selecionada, dropdown sem opção única;
- `bsDatepicker` e confirmação de estado após setter/eventos;
- restart do service worker, timeout e falha de leitura;
- **zero auto-submit, zero chamadas de escrita, zero vazamento de dados, zero armazenamento pessoal e zero chamadas a serviços externos**.

Revise o bundle e as permissões; testes devem falhar antes da correção (RED→GREEN). Use um ciclo objetivo de diagnóstico com no máximo duas rodadas de correção por falha antes de registrar bloqueio real; evite loops.

### Task 10 — medição e validação de sessão real (somente read-only enquanto L2 não autorizado)

Meça desde o clique até o readback por `performance.now()`, registrando tamanho/ambiente das fixtures, amostras e percentis p50/p95. **~1 segundo em PDF nato-digital curto é meta experimental, NÃO garantia.** Otimize primeiro a rota curta e mantenha a extensão simples.

Se a sessão profissional continuar disponível, faça **somente teste de leitura/inspeção passiva** sem mudar abas ou contexto. A escrita real em campos UI da página profissional é um gate **L2 separado**, que NÃO foi autorizado por este GOAL. Sem essa autorização: registrar `L2_NOT_AUTHORIZED`, concluir testes com páginas sintéticas e não anunciar `REAL_FILL_VERIFIED`. Em hipótese nenhuma salvar, complementar ou concluir ato.

### Task 11 — build e entrega

Entregue pasta `dist/` com extensão Manifest V3 pronta para **Carregar sem compactação**, README em português claro com instalação, uso, limites, atualização, remoção e rollback, documentação mínima e package verificável. O ZIP de distribuição da extensão, se gerado, deve conter exclusivamente arquivos públicos do produto, sem dados de processo, credenciais, perfis, PDFs, HAR ou logs. Instalação na sessão profissional exige presença/anuência do operador; não instale silenciosamente.

## 7. REGRAS DE EXECUÇÃO AUTÔNOMA E GATES

1. **Rode TODO o plano de 11 tarefas** sem solicitar aprovação entre F1–F4 para trabalho local/testes sintéticos; este GOAL já é a autorização para implementar no repositório **novo**. Pergunte somente quando um gate realmente exigir a decisão do operador: instalar/modificar navegador profissional, habilitar CDP, alterar campos de processo real (L2), acesso institucional proibido, operações destrutivas, push/merge/publicação ou mudança importante de escopo.
2. Se REA/CDP não estiver acessível, registre a causa e os testes passivos alternativos realmente realizados; continue F1–F4 com fixtures. Se o PDF não for legível no portal, **não** implemente bypass: marque a integração real como `BLOCKED/UNVERIFIED`, mas conclua o restante funcionalmente verificável.
3. Não instale extensões, não execute `npx` com aquisição automática de dependências em contexto institucional e não modifique configurações globais sem verificar procedência e autorização. Dependências de desenvolvimento do novo projeto podem ser instaladas em ambiente local autorizado, com versões fixadas; REA segue ferramenta de investigação, fora do runtime entregue.
4. Mantenha a spec aprovada como fonte de verdade. Se precisar de ajuste do plano por achado F0, registre a decisão e atualize os documentos de forma auditável, sem expandir para OCR, IA, serviço local ou banco sem aprovação explícita.
5. Git limpo e simples: repositório novo, commits pequenos e verificáveis; sem GitHub Actions, branches/PRs desnecessários, force push, push ou publicação sem autorização. Não altere qualquer arquivo, HEAD, branch, worktree, stash, token, acervo ou asset do `Atos-TCE`.
6. Ao fim de cada tarefa, rode testes específicos e registre o resultado com comando, saída resumida e commit. Se a tarefa não tiver evidência, marque PARTIAL/BLOCKED, nunca PASS por interpretação. Aplique revisão independente quando ferramenta disponível e um passe de correções fundamentadas em testes; não crie ciclo infinito de revisões.
7. Se o ambiente tiver limite de sessão, priorize manter artefatos e ledger em disco com uma etapa exata de retomada, sem apagar intermediários necessários. Não chame pendência de concluída nem entregue um esqueleto como produto final.

## 8. CRITÉRIOS DE ACEITE — DEMONSTRÁVEIS

- [ ] Produto em novo repositório, sem runtime ou código dependente do Atos-TCE.
- [ ] As duas abas no mesmo perfil e janelas diferentes comunicam-se quando o operador clica.
- [ ] Evento variável e documento escolhido pelo operador; não lê outros eventos.
- [ ] Nenhuma leitura, parser, download ou OCR antes de `⚡ Preencher`.
- [ ] O documento fonte é lido em todas as páginas por método comprovado; caso não viável, gate real indicado explicitamente.
- [ ] Identidade do processo e do interessado protegida, múltiplas fontes geram bloqueio seguro.
- [ ] Modalidade única por processo e quatro campos por interessado; preservação de valores existentes.
- [ ] Data da resolução convertida para `DD/MM/AAAA` com origem declarada, sem afirmar publicação efetiva.
- [ ] Angular e controles de data atualizam corretamente e o readback comprova os valores em fixtures.
- [ ] Zero submissão, zero salvamento, zero PUT/POST, zero alterações em dados reais sem L2.
- [ ] `npm test`, `npm run test:browser`, `npm run build`, `git diff --check` executados com resultados reais documentados.
- [ ] Benchmark p50/p95, relatório F0, contrato DOM, auditoria de segurança, instalação e rollback presentes.
- [ ] Testes de privacidade e inspeção do pacote não expõem dados sensíveis.
- [ ] Status de validação real (`REAL_READ_PASS`, `L2_NOT_AUTHORIZED`, `REAL_FILL_VERIFIED`, `REAL_VIEWER_UNVERIFIED`, `BLOCKED`, etc.) corresponde estritamente às evidências.

## 9. RELATÓRIO FINAL OBRIGATÓRIO

Responda com:

1. **Veredito verificável** (por exemplo `MVP_SYNTHETIC_VERIFIED_REAL_READ_PENDING_L2_NOT_AUTHORIZED`, ou estado real observado, nunca inventado).
2. **Novo repositório local:** caminho, branch, HEAD completo, `git status`, commits criados e se existe remoto (não inventar URL).
3. **Matriz F0–F4 e Tasks 1–11:** PASS/PARTIAL/BLOCKED, motivo e referência de evidência.
4. **F0 com REA:** ferramenta/versão realmente usada, estado CDP, abas observadas, detalhes técnicos sanitizados, limites de observação e caminho do leitor PDF.
5. **Suítes:** comandos, contagem de PASS/FAIL/SKIP, readback e testes negativos de submit/escrita/privacidade.
6. **Performance:** amostras, duração total, p50/p95, gargalos e limitações.
7. **Entregáveis:** caminhos reais do `dist/`, ZIP se houver, spec, plano, README, relatórios e instruções para instalar/retirar extensão.
8. **Gates pendentes reais:** L2 NÃO autorizado, inspeção de browser não disponível ou acesso ao PDF não comprovado, com instrução mínima de como resolver, sem pedir repetidamente.
9. **Decisões/Rulings e riscos remanescentes:** principalmente data operacional distinta de publicação oficial e eventuais mudanças do portal.
10. **Confirmação de preservação:** Atos-TCE intocado, zero publicação, zero escrita ou conclusão de ato pelo sistema.

**Condição de sucesso:** executar o máximo tecnicamente verificável das 11 tarefas e entregar uma extensão independente de um clique, simples e segura, sem inventar acesso ao portal real e sem ultrapassar os gates de autorização. **Comece pela leitura integral da spec e do plano, auditoria do workspace e F0 com REA em observação; depois continue autonomamente até F4.**
