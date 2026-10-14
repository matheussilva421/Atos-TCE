# Atos-TCE + REA — Especificação arquitetural de investigação, confiabilidade e runtime portátil

**Data:** 2026-10-14  
**Estado:** APROVADA PELO OPERADOR EM 2026-10-14 — ESCRITA DE PLANOS AUTORIZADA; IMPLEMENTAÇÃO AINDA NÃO AUTORIZADA  
**Método:** Superpowers / brainstorming arquitetural, decisões 1–10 aprovadas em conversa.  
**Repositório:** matheussilva421/Atos-TCE  
**Escopo principal:** Área Restrita; observação investigativa, navegação, preenchimento assistido e qualificação.  
**Subprojeto separado:** atualização transacional e rollback do aplicativo.

## 1. Propósito, resultados e precedência

Reconstruir a confiabilidade da complementação assistida da Área Restrita, usando REA e Codex para investigação automatizada em laboratório, sem impor IA, REA, MCP, Playwright CLI, Node global ou outras ferramentas de desenvolvimento ao runtime portátil. A automação deverá selecionar exclusivamente o processo e interessado corretos, reconhecer estados do portal mediante evidências estruturais, preencher somente campos autorizados, reler os resultados e deixar a conclusão de cada ato para clique humano.

**Resultado verificável:** capacidades promovidas apenas pelos respectivos gates reais do Reliability Reset, com execução normal no ZIP portátil e no Chrome comum; falhas diagnosticáveis, nenhuma escrita em identidade incorreta e fallback manual funcional.

Esta especificação **complementa e não revoga**:
- docs/superpowers/specs/2026-09-30-area-restrita-reliability-reset-design.md
- docs/superpowers/plans/2026-09-30-area-restrita-reliability-reset-phase-1.md, como plano histórico a reconciliar, não como autorização de novas tarefas
- docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md
- docs/notes/2026-09-30-area-restrita-runtime-source.md
- AGENTS.md e os contratos efetivamente implementados em app/, extension/ e packaging/.

Em conflito, **prevalecem as restrições de segurança e qualificação existentes**; mudanças nelas exigem nova decisão humana explícita. Esta spec não declara QUALIFIED, PRODUCTION, nem que houve testes no portal real.

## 2. Registro vinculante das dez decisões

| Nº | Opção aprovada | Decisão vinculante |
|---|---|---|
| D1 | B | Integração REA para investigação + MV3 atual + Portal Controller Playwright/CDP experimental; vencedor escolhido por benchmark, não por preferência. |
| D2 | C | Investigação tecnicamente automatizada pelo Codex com REA e Playwright/CDP em cenários previamente autorizados; não automatiza login nem atos finais. |
| D3 | B | Máquina de estados determinística baseada em evidências, reaproveitando os contratos canônicos de identidade e formulário. |
| D4 | B | Recuperação controlada por evidências: observar, classificar, reconciliar e só agir quando comprovadamente seguro. |
| D5 | B | Chrome QA dedicado, CDP loopback e controle exclusivo por operação; nenhuma escrita/navegação concorrente. |
| D6 | B | Evidence Gateway local com sanitização **antes** de qualquer saída para Codex/modelo ou GitHub. |
| D7 | B | Benchmark controlado MV3 × Controller, matrizes reais equivalentes quando possível e gates independentes de 20/20 + 20/20 por capacidade. |
| D8 | B | Navigation Adapter com apenas um controlador operacional ativo, preservando Mesa, semântica de preenchimento e fallback manual. |
| D9 | B | Atualização transacional com versões isoladas, workspace persistente e rollback de código separado de restauração de dados. |
| D10 | B | Implementação incremental por fases, worktrees, TDD RED→GREEN, handoffs, revisão independente e autorização humana entre fases. |

**Invariantes irrenunciáveis:** login humano; seleção fail-closed; zero ações em alvo ambíguo; zero escrita em identidade diferente; clique final Complementar Ato exclusivamente humano; sem SUBMIT, SEND, AUTO_SUBMIT, COMPLEMENT_ACT, FINALIZE, assinatura, tramitação ou envio pelo aplicativo; não contornar permissões; sem dados privados versionados; sem dependência de IA/REA no ZIP; 20/20 + 20/20 reais por capacidade.

## 3. Fonte de verdade, fronteiras e exclusões

A fonte do produto portátil é a **árvore raiz**: app/, extension/, packaging/, START.cmd, testes e scripts de produto necessários. A árvore work/tce-extractor/ é legado/verificação, não destino de correções duplicadas. A Mesa e seu SQLite continuam donos de processos, identidade, comandos, planejamento jurídico, preflight, acervo e seleção de campos; o e-Contas continua reservado à aquisição de documentos, não à complementação no portal.

A extensão MV3 já contém leitura de formulário e guards; seus predicados canônicos de visibilidade, identidade composta, generation e documentNonce não serão substituídos por seletores independentes e divergentes. O current-selection mantém observações de uso único, TTL e recusa de observações obsoletas. O motor jurídico e a política best-effort existente não serão duplicados no Controller.

**Fora do escopo do primeiro ciclo:** reescrita do motor jurídico, alterações na aquisição e-Contas, novas funcionalidades não relacionadas à confiabilidade, automação de credenciais, finalização de atos, migração imediata para Controller, distribuição de ferramentas de laboratório e implantação do atualizador transacional antes de sua especificação própria.

## 4. Arquitetura e fluxo de dados

Fluxo de investigação (somente laboratório):

    Operador autentica manualmente o Chrome QA autorizado
        -> Browser Control Coordinator concede lease exclusivo
        -> Investigador local executa cenários REA/Playwright delimitados
        -> Evidence Gateway intercepta TODAS as saídas técnicas
        -> projeções estruturais allowlisted + validação de segurança
        -> Codex recebe somente evidência sanitizada
        -> hipótese única -> fixture RED -> correção mínima GREEN
        -> repetição real autorizada e relatório sanitizado

Fluxo do produto (sem REA ou modelo):

    Mesa/SQLite -> identidade exata + plano/preflight
        -> Navigation Adapter -> controlador único qualificado
        -> observar estado/identidade/frames/geração/nonce
        -> navegar, quando a capacidade estiver disponível
        -> preencher, quando AR-1 e dependências permitirem
        -> reler + conferir
        -> operador revisa e executa manualmente Complementar Ato

O laboratório não integra o pacote de produção. Só algoritmos determinísticos validados e dependências indispensáveis à arquitetura vencedora podem atravessar essa fronteira. Contratos e fixtures compartilhados devem eliminar a duplicação de mapas manuais de seletores.

## 5. D2 — Investigação automatizada com supervisão operacional

O Codex pode planejar e executar autonomamente capturas, classificação de estados, comparação de execuções, análise de código, testes, relatório de causa-raiz e propostas de correção. A autonomia não é autorização geral para modificar a sessão: cada cenário real precisa ter escopo e operações previamente autorizadas, com origem/aba de destino determinada e sem ações finais ou escrita em dados administrativos não necessária ao teste autorizado.

A sessão é autenticada manualmente pelo operador. Testes reais de qualificação seguem a exigência preexistente de **operador presente e um comando de portal por vez**. Investigações sobre estado ambíguo, acesso negado ou sessão expirada não devem fabricar falhas mediante adulteração de dados oficiais.

Apenas um executor pode deter capacidade de mutação por vez. Rea capture_browser_scenario em attach-mode pode não observar eventos anteriores à conexão, e a cobertura incompleta deve ser registrada como tal. Rede, scripts intrusivos, navegação, downloads e alterações de storage não são tratados como observação inofensiva; exigem escopo e autorização explícitos.

## 6. D5 — Browser Control Coordinator e exclusividade

**Ambiente de laboratório:** Chrome QA em perfil separado do uso pessoal, CDP apenas em loopback com porta explícita; verificar endpoint real em vez de inferir prontidão pelo arquivo DevToolsActivePort. Não matar automaticamente instâncias Chrome nem remover locks de perfil, cookies ou sessão. O REA em connect-mode deve desconectar sem fechar o navegador externo.

**Contrato proposto para lease:** session_id, owner, operation_id, target_ref, fencing_token, lease_expires_at e estado. O coordenador deve rejeitar mutações quando owner, contexto, token ou lease não coincidirem; deve correlacionar tab/frame e build. A exclusividade deve ser efetivada nos adaptadores que emitem comandos, e não só no painel. Leases vencidos não tornam segura a repetição de ações incertas; a reconciliação vem antes da troca de owner. Um Chrome fechado, perfil em conflito, intervenção humana, troca de aba inesperada ou conexão perdida invalida a autorização de mutação até inspeção segura.

Codex, REA, Controller e MV3 não podem clicar simultaneamente na mesma sessão. Observações que instrumentem a página ou possam interferir em eventos também dependem do controle exclusivo. Em produção, o coordenador necessário será **local e determinístico**, sem MCP, agente ou REA.

## 7. D6 — Evidence Gateway e proteção contra exfiltração

O Gateway é uma fronteira obrigatória de egressos do laboratório. Na sessão real, o Codex NÃO terá acesso direto ao retorno bruto do MCP/CLI do REA, ao CDP irrestrito, a HAR, trace, DOM completo, screenshots, arquivos privados, stdout/stderr não filtrados ou relatórios locais que possam contornar o Gateway. O runner local deve restringir tanto as operações de captura quanto todos os caminhos de resposta ao modelo; a simples redação posterior de prompts não satisfaz D6.

**Padrão:** captura mínima por cenário; metadados de frames, predicados, classe de estado, contagens, tempos, resultado, códigos de erro permitidos, HMAC/identificadores opacos, versão e limitações. Bodies HTTP, header_values, cookies, local/session storage e screenshots reais ficam desabilitados por padrão. DOM bruto, quando imprescindível e autorizado, pode ser analisado somente em processo local restrito e reduzido a projeção tipada antes de qualquer egress. A redação nativa do REA não substitui este Gateway.

**Contrato de saída:** schema estrito e allowlist de campos; campos desconhecidos falham fechados ou são descartados; URLs sem query/fragment/userinfo; logs e erros filtrados; nomes de interessados, processos, CPF, matrícula, documentos, valores, tokens e cabeçalhos secretos não saem. Hashes de identidade exigem chave local, preferencialmente HMAC, evitando correlacionabilidade indevida por hashes triviais de PII. Uma evidência marcada incomplete, redaction_failed, origin_unknown ou contaminated não é enviada ao Codex nem conta como confirmação de estado.

Capturas restritas excepcionalmente necessárias exigem autorização, armazenamento local fora do Git com ACL restrita, prazo curto de retenção definido no plano, limpeza verificável e proibição de exportação. Testes adversariais com sentinelas devem cobrir campos, texto livre, URLs, base64/JSON, logs, respostas HTTP e erros. O Modo Diagnóstico conserva seu contrato próprio e sua retenção atual; o Gateway só recebe projeções permitidas, nunca acesso irrestrito ao recorder.

**Não versionar:** PDF, banco, acervo, HTML privado, HAR, trace, screenshots reais, perfis, tokens, credenciais, values de formulário e Evidence bruto. Nenhum mecanismo de sanitização é garantia absoluta sem isolamento de ferramentas e auditoria de egressos.

## 8. D3 — Máquina de estados determinística

Preservar o vocabulário do Reliability Reset: PORTAL_MENU, LIST, OPENING_ACT, INTERESTED, FORM, FORM_FILLED, LOGIN_REQUIRED, ACCESS_DENIED, TRANSITIONING, AMBIGUOUS, SESSION_EXPIRED e UNKNOWN. Os estados de current-selection (por exemplo MATCHED, NO_ACTIVE_FORM e AMBIGUOUS) continuam contrato distinto, mapeado explicitamente e sem renomeação silenciosa.

Uma transição válida exige, conforme a capability: estado de origem reconhecido, alvo de identidade exata, frame ativo visível e não obsoleto, correspondência entre processo/interessado/ato, generation e documentNonce válidos, observação de estado pós-comando e releitura quando houver escrita. Seletores ou respostas HTTP isoladas não provam sucesso. Timeout é limite máximo de espera; nunca gera sucesso nem autoriza repetição.

Contratos por operação padronizam preconditions, allowed_action, postconditions, result_code, observation_id, session_ref, generation, document_nonce e evidência de sucesso. As implementações MV3 e Controller podem executar passos internos diferentes, mas devem satisfazer o mesmo predicado estrutural canônico.

Casos de frame oculto com formulário antigo, duas linhas com mesma identidade normalizada, troca de frame, HTTP 200 mostrando login/acesso negado, sessão suspensa e perda de resultado precisam de fixtures negativas. Toda ambiguidade recusa a ação sem escolher a primeira ocorrência.

## 9. D4 — Recuperação controlada por evidências

Sequência obrigatória: OBSERVE -> CLASSIFY -> RECONCILE -> SAFE_CONTINUE ou BLOCK.

| Resultado observado | Política |
|---|---|
| Leitura transitória sem alteração de estado | Pode repetir somente observação read-only dentro do limite documentado |
| FORM_NOT_AVAILABLE ou SCREEN_NOT_NAVIGABLE | Reobservar frames e classificar; não clicar novamente no escuro |
| accepted_unconfirmed ou comando com resultado perdido | Não reenviar; verificar efeitos atuais e identidade, ou bloquear |
| STALE_FORM / STALE_SELECTION | Invalidar snapshot; nova observação exata antes de eventual ação distinta |
| SESSION_EXPIRED ou LOGIN_REQUIRED | Parar; login humano |
| ACCESS_DENIED | Parar; jamais contornar autorização |
| Identidade inconsistente, AMBIGUOUS, UNKNOWN persistente | Bloquear sem escrita |
| Falha após fill | Reler e reconciliar; não repetir escrita não comprovada |

Ações não idempotentes não admitem retry cego, inclusive após expiração de lease e reinício de MV3. Continuação após efeito comprovado **não é** repetição da ação. O evento recuperado deve permanecer classificado como recuperação técnica; não pode ser lançado como sucesso normal do gate 20/20. Modo Diagnóstico observa sem influenciar decisões funcionais ou promoção.

## 10. D7 — Benchmark e Qualification Ladder

**Gates imutáveis para cada capability e build:**
- QUALIFIED: 20/20 execuções **reais consecutivas** em desenvolvimento, mesma build, operador presente, sem reload técnico, reinício corretivo, DevTools para consertar estado ou recuperação técnica contabilizada como sucesso.
- PRODUCTION: outras 20/20 reais consecutivas sobre o artefato distribuível verificado, em extração limpa, Chrome normal e sem Codex, REA, MCP, scripts ou ferramentas de laboratório.
- Qualquer falha na sequência é registrada e invalida a sequência vigente; após correção, reiniciar a contagem para a build corrigida. Regressão reproduzível desqualifica a capability afetada.
- OFFLINE GREEN nunca qualifica o portal real. Não misturar hashes de build, ambientes, versões de extensão ou controladores. Não fabricar casos perigosos no portal para testes.

**Ordem e dependências:**
- AR-1 manual_form_fill: operador abre ato; detectar FORM, identidade, preflight, fill, readback, revisão. Independente de navegação automática; primeiro gate útil e primeiro a validar no pacote.
- AR-2 open_act: partir de LIST preparada manualmente; abrir identidade exata; comprovar INTERESTED ou FORM.
- AR-3 select_interested: de INTERESTED para FORM com correspondência exata, zero clique em alvo ambíguo.
- AR-4 pipeline: compor somente AR-1/2/3 qualificadas; abrir, selecionar quando preciso, preencher, reler, sem clique final.
- AR-5: return_to_list e next_page são **subcapacidades independentes**, cada qual exige seu próprio 20/20 e posteriormente 20/20 portátil; cobrir same-page, cross-page quando seguro, frame replacement e limites.
- AR-6 next_process: apenas compor capacidades AR-2 a AR-5 qualificadas, 20/20 do fluxo composto; cross-page não observado com segurança permanece explicitamente não qualificado.

O benchmark compara **MV3 e Controller**, prioritariamente AR-2 e AR-3, com matrizes equivalentes quando viáveis e execuções sequenciais sob controle exclusivo. Não forçar o mesmo ato duas vezes apenas para emparelhar amostras. Registrar: tentativas, sucesso, falhas por classe, median/p95 descritivos, frame perdido, sessão perdida, reload técnico, ambiguidade, estado não classificado, intervenção, recuperação, build, browser e limitações. Relatórios parciais não declaram vencedor.

**Critério hierárquico:** segurança de identidade -> gates reais -> estados não classificados -> necessidade de recuperação -> Chrome normal/portabilidade em outro PC -> complexidade operacional -> latência. Se ambos passarem, preferir o mais simples; MV3 recebe preferência somente quando houver equivalência comprovada. Se Controller vencer, ele segue experimental até cumprir packaging e qualificação aplicáveis. Se nenhum passar, bloquear a promoção e manter fallback manual.

As amostras do benchmark são distintas do ledger formal de qualificação, salvo quando cada execução cumprir integralmente o protocolo da qualificação; não transformar 20 tentativas comparativas em QUALIFIED por conveniência.

## 11. D8 — Navigation Adapter, execução e UX

Interface conceitual: observe_state(), open_act(exact_identity), select_interested(exact_identity), return_to_list() e next_page(). Cada método retorna resultado tipado, evidência sanitizada e classificação terminal; não conhece fundamento jurídico nem inventa plano de campos. Só capacidades habilitadas pelo Reliability Reset podem ser expostas ao operador. Não há método de submit, send ou finalize.

Apenas um controlador ativo executa comandos de navegação em produção; **não existe failover automático** entre MV3 e Controller após falha. O outro permanece apenas candidato de laboratório ou alternativa não ativa. O fallback operacional é humano: operador navega manualmente e usa AR-1 no FORM correto, se a capability estiver habilitada e as guardas passarem. O sistema nunca mascara capacidades UNQUALIFIED como prontas.

Se MV3 vencer, preservar o layout de empacotamento atual. Se Controller vencer, promover apenas componentes de produção determinísticos; pinagem de versões, hashes, licenças, smoke e suporte ao Chrome normal em outro PC. Não exigir instalação global de Playwright/Node, nem runtime REA/Codex/MCP. O verificador do ZIP deve recusar artefatos privados e ferramentas de laboratório.

## 12. D9 — Atualização transacional e rollback (subprojeto independente)

Aprovado como **objetivo arquitetural separado**, não como mudança automática do launcher no primeiro plano. Preservar os mecanismos existentes build-portable.ps1, verify-package.ps1, rotate-builds.py e backup.py, conciliando seus contratos com um futuro updater.

O desenho proposto separa versões imutáveis do programa de workspace durável de dados: SQLite, acervo/PDFs, configurações, journals, diagnósticos e ledger de qualification. Exclusividade de escrita entre versões/instâncias.

Estados: PREPARED -> BACKED_UP -> STAGED -> VERIFIED -> QUIESCED -> ACTIVATED -> COMMITTED. Ativação só após integridade de pacote, compatibilidade schema/runtime, backup verificado, quiescência de comandos e validação de health; falha não ativa versão parcial. Um comando remoto com efeito incerto exige reconciliação antes da quiescência; não matar Chrome nem perder operação ativa.

**Rollback de código** exige compatibilidade da versão antiga com o schema e estado atuais. **Restauração de dados** é diferente, potencialmente destrutiva e exige autorização humana específica, validação de backup e avaliação de alterações posteriores. Migrar SQLite transacionalmente não implica reversibilidade. Se a compatibilidade não estiver comprovada, bloquear rollback automático e apresentar procedimento de recuperação sem sobrescrever dados.

Não herdar QUALIFIED/PRODUCTION entre builds alteradas; evidências permanecem vinculadas a build e capabilities específicas. O backup do acervo existente NÃO deve ser tratado como prova de que toda telemetria, settings ou journals estão incluídos; isso deverá ser coberto na spec própria do updater. O retention policy do recorder permanece válida.

## 13. D10 — Programa de execução e revisão por fases

**Gate inicial:** antes de código, conferir branch, commits atuais e fonte de produção; preservar alterações não commitadas e não editar árvores legadas em paralelo. Cada plano deve ter tarefas pequenas, interfaces, arquivos, RED antes do GREEN, testes focados e amplos, commit rastreável, handoff e revisão independente. Não fazer merge automático no main, force-push nem apagar worktrees com trabalho não incorporado. Codex pode executar autonomamente tarefas internas de plano **já aprovado**; avanço entre planos exige revisão e autorização humana.

**Decomposição em specs/planos executáveis menores:**

| Fase | Objetivo | Gate de saída |
|---|---|---|
| 0 | Reconciliação de branches, fonte real, baseline e testes existentes | SHA/base documentada e gates offline reproduzidos |
| 1 | Laboratório REA, Browser Control Coordinator e Evidence Gateway | Provas de isolamento/egresso com sentinelas, fixtures sintéticas, integração sem dados privados vazados |
| 2 | AR-1 e diagnósticos de causa-raiz | Gate real AR-1 20/20 dev + 20/20 portátil; nenhuma promoção por offline |
| 3 | AR-2/AR-3, máquina de estados, recuperação e benchmark MV3 × Controller | Gates de capacidade, comparação sanitizada e escolha documentada da arquitetura |
| 4 | Navigation Adapter, packaging vencedor e composição AR-4/AR-5/AR-6 | Gates próprios reais e portáteis das capacidades expostas; fallback manual |
| 5 | Atualizador transacional e rollback, como subprojeto com spec/plan próprios | Testes de compatibilidade, não perda de dados e autorização separada |

AR-4/5/6 não entram no primeiro plano do Reliability Reset; decisões de promoção dependem das capacidades que os compõem. Se três correções diferentes da mesma classe de falha não restabelecerem confiabilidade real, interromper a linha e reavaliar a fronteira arquitetural, sem multiplicar heurísticas.

**Handoff mínimo de cada fase:** branch/worktree, SHA, diff, source-of-truth, testes RED e GREEN, gates offline e packaging, verificações de privacidade/comandos proibidos, resultados reais por build/capability/ambiente ou indicação explícita de NÃO EXECUTADO, limitações, evidência sanitizada, decisão de revisão e riscos residuais.

## 14. Matriz mínima de testes e aceitação

| Fronteira | Casos obrigatórios e comportamento esperado |
|---|---|
| Privacidade | Dados canário, URLs secretas, DOM/HTML, cabeçalhos, bodies e erros codificados não passam Gateway; ferramenta bruta não acessível pelo Codex |
| Exclusividade | Duas tentativas de mutação concorrentes: somente um owner; fencing expirado não autoriza replay; perfil bloqueado não é encerrado |
| Identidade | Alvo incorreto, duas correspondências, frame oculto, stale generation/nonce => zero clique/escrita |
| Sessão | HTTP 200 com LOGIN_REQUIRED/ACCESS_DENIED, navegador desconectado => interrupção classificada |
| Estados | Timeout e accepted_unconfirmed => sem sucesso presumido ou retry cego |
| Recuperação | Read-only retry controlado, reconciliação sem reenviar ação incerta; recuperação não conta como gate |
| Preenchimento | Plano/preflight existentes preservados; catálogo select válido; readback coerente; jamais submit |
| Benchmark | MV3 e Controller sujeitos aos mesmos pós-predicados, sem concorrência, sem resultados inventados |
| Portabilidade | Clean extraction + START.cmd + Chrome normal; sem Node/Playwright global, REA, Codex, MCP ou dados privados no pacote |
| Upgrade (spec própria) | Rollback de código seguro; restore de dados nunca implícito; migração incompatível bloqueia downgrade |
| Qualificação | 20/20 + 20/20 consecutivos por capability/build, relatórios OFFLINE/REAL/PORTABLE separados |

**Critério de aceitação da arquitetura:** cada decisão D1–D10 rastreável em contrato e teste; nenhuma promessa de confiabilidade sem evidência real; nenhuma ação final automatizada; a execução portátil não requer laboratório; falha apresenta classificação e alternativa manual segura.

## 15. Pendências explicitamente resolvidas por precedência e gates

- Não se instala REA/Playwright, não se roda investigação em portal real e não se edita código por força desta aprovação do brainstorming.
- O controle automatizado D2 refere-se à **investigação autorizada**; não substitui operador presente durante a qualificação nem autoriza finalização.
- O Evidence Gateway D6 antecede qualquer compartilhamento de saída real com modelo; sem garantia de egressos, investigação real automatizada fica bloqueada, mas estudos sintéticos podem prosseguir.
- A avaliação do candidato vencedor ocorre após AR-3 com dados reais; não se escolhe Controller hoje.
- Se um controlador dependente de Playwright vencer, a independência significa ausência de **instalações globais e ferramentas de laboratório**, não proibição abstrata de um runtime Playwright determinístico devidamente empacotado.
- O status de qualificação deve ser consultado no ledger da build; handoffs históricos não representam sucesso presente. No handoff de 2026-10-02, AR-1 aparecia com 0/20 dev e 0/20 portátil, o que não prova o estado atual.
- A Decisão 9 é vinculante, mas seu updater ganha spec e plano separados: implementação simultânea não autorizada.

## 16. Gate documental Superpowers

As dez decisões de brainstorming e esta especificação formal foram **explicitamente aprovadas pelo operador em 2026-10-14**. A aprovação autoriza invocar Superpowers writing-plans e publicar um plano detalhado das Fases 0/1 para revisão. **Não autoriza executar o plano, instalar dependências, migrar dados, alterar código, testar o portal real ou realizar merge.** Um plano escrito precisará de sua própria aprovação explícita antes da implementação.
