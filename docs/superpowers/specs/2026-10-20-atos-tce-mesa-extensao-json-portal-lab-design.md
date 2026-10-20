# Atos-TCE — Arquitetura consolidada da Mesa, extensão JSON e laboratório da Área Restrita

**Data:** 2026-10-20  
**Repositório:** matheussilva421/Atos-TCE  
**Classificação Superpowers:** Architectural  
**Estado:** SPEC PARA REVISÃO HUMANA — sem aprovação de implementação  
**Branch documental:** codex/2026-10-20-atos-tce-mesa-extension-spec  
**Base de código examinada:** main, commit 6e1acd50e7be8895b415d40bae4376e169e05ee1 (2026-10-13).  
**Autoridade:** 29 decisões arquiteturais aprovadas em conversa de 2026-10-20 e revisão adicional expressa que exclui fundamentação legal e incorpora a investigação com REA e demais ferramentas.  
**Natureza deste commit:** documentação apenas; nenhum arquivo de runtime, teste, extensão, distribuição ou dado foi alterado.

## 1. Objetivo, escopo e critérios de sucesso

Criar uma versão operacionalmente simples e confiável do Atos-TCE para complementar atos do TCE/RN, combinando:

1. Mesa Local modernizada a partir da identidade visual de complementar-ato.html, com visualizador PDF à esquerda, conferência à direita, separador ajustável e áreas auxiliares dedicadas.
2. Extensão MV3 compacta, que reconhece o formulário já aberto na Área Restrita e, após clique humano em **Preencher campos**, preenche localmente cinco campos a partir de um lote JSON previamente importado.
3. Acompanhamento automático e rápido da última aba da Área Restrita usada pelo operador, sem transformar a disponibilidade da Mesa em pré-requisito para preenchimento quando o registro existe no JSON.
4. Exceções restritas, auditáveis e fail-closed para consulta à Mesa quando o processo ou interessado estiver ausente do JSON.
5. Rascunhos locais protegidos, estados de conclusão de atos baseados em evidência inequívoca do portal e encerramento global de processos sempre manual.
6. Laboratório de engenharia reversa da Área Restrita que reutiliza REA, Chrome DevTools MCP, Playwright CLI e, apenas se justificado e autorizado, mitmproxy para descobrir problemas, produzir evidências sanitizadas e orientar melhorias.
7. Conservação integral dos controles do Reliability Reset e do REA, inclusive qualificação consecutiva real e impossibilidade de envio, assinatura, tramitação ou conclusão final automáticos.

**Não objetivos:** reescrever todo o acervo; recriar lógica jurídica de fundamentação; acrescentar automação de login; burlar autenticação; iniciar nova sessão profissional; alterar valores do JSON sem reimportação; executar a ação final do portal; criar segundo mapa de seletores ou depender de LLM/MCP/Playwright no produto portátil.

**Critério central:** a extensão consegue preencher um registro presente no JSON, com a Mesa completamente desligada, respeitando identidade, conflitos, leitura pós-escrita e clique humano. A conexão à Mesa continua servindo ao acompanhamento e às exceções.

## 2. Precedência, compatibilidade e limites

Esta spec é o contrato prospectivo para os fluxos aqui redesenhados. Em qualquer conflito de comportamento de preenchimento, visual ou JSON com documentos anteriores, as 29 decisões de 2026-10-20 e a exclusão expressa de fundamentação legal prevalecem. As antigas specs continuam como evidência histórica e como fonte de requisitos ainda compatíveis.

Referências existentes:
- docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md
- docs/superpowers/specs/2026-09-24-area-restrita-lab-design.md
- docs/superpowers/specs/2026-09-30-area-restrita-reliability-reset-design.md
- docs/notes/2026-09-24-area-restrita-current-state.md
- devtools/area-restrita/README.md
- .agents/skills/area-restrita/SKILL.md
- .agents/skills/area-restrita/references/safety.md

**Compatibilidade crítica com Reliability Reset:** o documento de 30/09 permitia explorar um Portal Controller Playwright/CDP e até avaliar sua promoção ao runtime. Esta spec escolhe a extensão MV3 com JSON local como caminho funcional de produção. Controller e ferramentas CDP continuam experimentais e podem ser avaliados apenas dentro de gates existentes. Sua promoção ao runtime, troca de controlador ou inclusão de Playwright no pacote requer nova decisão arquitetural e spec aprovada; a mera aprovação deste documento NÃO autoriza essa promoção. A regra de congelamento de novas funcionalidades enquanto capacidades estiverem UNQUALIFIED impede ativação em produção antes da qualificação pertinente. Melhorias são desenhadas e implementadas em sequência controlada, mas funções não qualificadas permanecem bloqueadas.

A fonte de verdade do runtime deve ser provada no HEAD no início do writing-plans, seguindo START.cmd e packaging. A árvore raiz app/, extension/, tests/, packaging/ é a candidata observada; work/tce-extractor não pode virar segunda implementação sem evidência de build. Não se copiarão correções entre árvores por semelhança.

## 3. Modelo de atores e fronteiras de confiança

**Operador:** autentica-se pessoalmente na Área Restrita, escolhe formularios e interessados, aciona Preencher campos na extensão, revisa o resultado e realiza exclusivamente por si a conclusão final no portal. Decide manualmente quando um processo inteiro foi encerrado na Mesa.

**Mesa:** possui workflow, SQLite, documentos, evidências, histórico, estado oficial e versão de dados; exibe conferência; gera lote imutável; mantém rascunhos isolados; recebe observações e eventos; resolve consultas excepcionais usando somente dados oficiais.

**Extensão MV3:** possui um único lote ativo no armazenamento local, reconhece formulários, compara identidade e valores, efetua apenas escritas explícitas nos cinco campos, relê o DOM, transmite eventos mínimos e mantém fila de conclusões inequivocamente confirmadas enquanto não entregues.

**Área Restrita:** única autoridade para os controles do formulário e para confirmar a conclusão real de um ato. A extensão não imita um servidor de portal nem decide que um ato foi concluído pela simples mudança de tela.

**Portal Lab:** desenvolvimento e QA exclusivamente; observa sessões que o operador autenticou. Não substitui autenticação nem tem permissão para concluir atos. Dados sensíveis reais nunca entram em fixtures versionadas.

**Sessões:** uma sessão profissional autenticada do operador por perfil de trabalho no portal, sem login paralelo automatizado. A Mesa tem sua própria sessão local, distinta da sessão profissional; a conexão entre elas não encaminha credenciais do portal. Um perfil Chrome QA dedicado, se usado em laboratório, não constitui autorização para criar ou reutilizar a sessão profissional em outro navegador.

## 4. Arquitetura e responsabilidades

Fluxo de dados:

    SQLite oficial / PDFs
          |
          +--> Mesa Local (UI, revisão, exportação)
          |         |
          |         +--> Exportação manual de lote JSON v2
          |         |         |
          |         |         +--> Importação manual atômica na extensão
          |         |                    |
          |         |                    +--> correspondência exata + botão preencher
          |         |
          |         +<-- observações e resultados leves via canal autenticado
          |         +<--> consultas excepcionais de registros ausentes
          |
          +--> rascunhos protegidos por computador (fora do acervo oficial)

    Formulário ativo no navegador profissional
          |
          +--> extensão: observar aba/frame/documento
          +--> extensão: escrever e reler cinco campos, após clique humano
          +--> operador: concluir manualmente
          +--> extensão: observar confirmação inequívoca, se disponível

O armazenamento do JSON na extensão e a comunicação com a Mesa são **canais separados**. A leitura de JSON nunca exige HTTP à Mesa; uma consulta excepcional nunca modifica o lote ativo. A escolha do PDF nunca participa da autorização de escrita no portal.

Unidades e donos únicos:
- app/core + persistência atual: registros oficiais, versionamento, status e auditoria.
- app/analysis: propostas e extração dos cinco campos, sem obrigação jurídica no caminho novo.
- app/web: apresentação, rascunhos e projeção do acompanhamento; não executa preenchimento.
- app/api: endpoints autenticados de consulta excepcional e eventos; não controla a sessão do portal.
- extension/background/router.js: protocolo MV3, identidade de aba/frame e mediação da conexão.
- extension/content/detect-form.js: leitura estrita do formulário e identidade.
- extension/content/fill-form.js: escrita limitada, transacional no sentido de preflight + reconciliação, nunca promessa de rollback do DOM.
- extension/lib/area-snapshot.js: proprietário canônico das assinaturas e seletores estruturais compartilhados da Área Restrita.
- extension/sidepanel: UI operacional e importação.
- devtools/area-restrita e scripts/portal-lab: documentação, capturas, sanitização, contrato e fixtures de laboratório.

Atualizações de interfaces devem manter os limites desses donos; não criar motores paralelos de matching ou leitura de portal.

## 5. Contrato de campos — exclusão de fundamentação legal

O novo fluxo escreve **exatamente cinco campos**:
1. modalidade;
2. data_publicacao_doe;
3. cargo;
4. matricula;
5. data_nascimento.

**tipo_processo** é metadado classificatório em Mesa e JSON: jamais enviado à escrita do portal.

**fundamento_legal** está expressamente FORA do novo contrato de exportação, matching, preflight, proposta, escrita, readback obrigatório, status PRONTO e requisitos de conclusão operacional da extensão. Seu valor não pode ser recuperado pelo fallback para completar o formulário, nem voltar a ser obrigatório indiretamente via código legado.

**genero** não integra a nova allowlist de escrita e não pode ser escrito pela extensão nesse fluxo; dados históricos permanecem preservados conforme política de migração. A especificação não pressupõe autorização para preencher outros campos.

A presença estrutural do controle txtFundamentoLegal no DOM do portal pode continuar sendo observada em metadados de compatibilidade, quando necessário para distinguir um formulário real de um frame transitório. Isso **não** autoriza ler seu valor, propor seleção ou manipulá-lo. Remover esse seletor de um sentinela estrutural só é permitido após demonstração de equivalência de detecção em fixtures e amostras autorizadas.

Se o portal exigir fundamentação para concluir, o operador fará essa parte manualmente; o sistema não poderá anunciar conclusão bem-sucedida com base apenas no preenchimento dos cinco campos. Não modificar a aplicação do TCE nem seus controles.

Impacto no código já identificado na base:
- app/analysis/__init__.py ainda define seis campos obrigatórios, inclusive fundamento_legal.
- app/area_restrita/preflight.py ainda apresenta conjunto de selects e lógica jurídica.
- extension/content/detect-form.js ainda mapeia fundamento_legal e genero.
- extension/lib/area-snapshot.js ainda contém txtFundamentoLegal no reconhecimento estrutural.
- app/web/portal-current.js e demais contratos podem conter premissas antigas.
- testes e documentação de legal-foundation-v3/v4 permanecem históricos; não podem reger o novo fluxo.

Migração: manter integridade do banco e audit trail, criar esquema/adapter novo que não exponha fundamento no operacional, converter categorias/estados legados com procedimento idempotente, backup e possibilidade de reversão do upgrade. Não executar DELETE massivo de histórico; não reativar pipelines jurídicos legados no caminho novo.

## 6. Exportação e importação do lote JSON v2

**Formato lógico de um lote:**
- schema_version: 2;
- identificador único do lote;
- timestamp de geração UTC;
- versão do exportador e especificação de canonicalização;
- lista integral e não truncada de processos explicitamente escolhidos para o lote, inclusive com zero interessados identificados;
- lista separada de registros de interessados, cada um com identidade composta e referência ao processo do inventário;
- tipo_processo e os cinco campos de preenchimento em cada registro conforme aplicável;
- estados de ausência/incompletude em vez de fabricar valores;
- resumo de contagens e hash SHA-256 canônico.

A identidade canônica do processo usa número e ano textuais, preservando zeros significativos, mais eventuais discriminantes oficiais necessários para impedir colisão. A do interessado deve ser resolvida de forma inequívoca a partir do portal, sem depender de posição na lista nem normalização que faça duas pessoas distintas colidirem. Quando o portal não oferecer evidência suficiente, impedir a escrita.

Os valores de data e matrícula não são convertidos em números de ponto flutuante; preservam representações canônicas controladas por esquema e validadores específicos. O formato final de data deve ser validado com o controle real do portal e fixtures, nunca presumido a partir de locale.

Canonicalização: definir e congelar no contrato v2 o algoritmo efetivo para ordenação, encoding UTF-8, tratamento de Unicode, chaves, arrays e exclusão do próprio campo de hash; gerar vetores golden idênticos em Python e JavaScript antes de exportações reais. Não reutilizar sem teste uma implementação histórica de SHA. A importação deve checar esquema, unicidade, integridade, índices, referências cruzadas, tipos, limites e conflitos.

A extensão aceita um lote v2 após validação completa. Se inválido, mantém o lote ativo anterior sem qualquer mutação. Se houver escrita em curso, o lote válido fica staged e só é ativado após finalização/reconciliação daquela operação; existe apenas **um lote ativo**. Importação é manual, não watcher de filesystem, e não atualiza oficialmente a Mesa.

Lotes v1 antigos devem ser rejeitados para uso operacional v2 com mensagem explícita de reexportação, jamais convertidos em silêncio nem parcialmente aceitos. Documentar migração de uso e conservar arquivos legados sem reescrevê-los.

O conjunto exportado corresponde ao **lote escolhido**, não à pesquisa/filtro visual da Mesa; filtros de UI não podem silenciosamente remover processos do arquivo.

## 7. Resolução de registros e consulta excepcional

Dado um formulário visível com identidade verificada:

1. Buscar no lote JSON ativo a correspondência exata do processo e interessado.
2. Registro exato encontrado: usar exclusivamente seus valores, mesmo se incompletos. Não consultar a Mesa para complementar ou substituir esse registro.
3. Processo inexistente no JSON: consultar excepcionalmente a Mesa.
4. Processo existe, mas interessado exato inexiste: consultar excepcionalmente a Mesa, automaticamente ao observar o formulário.
5. Consulta excepcional sem resposta válida, identidade ambígua, timeout, erro de autenticação ou mismatch: bloquear preenchimento; permitir inspeção manual sem inventar dados.

As consultas excepcionais são in-memory, single-flight por formulário exato, com TTL curto configurado e documentado, timeout, backoff e invalidação imediata na troca de formulário/aba/documento/geração. Resposta atrasada não pode revalidar uma identidade que se tornou obsoleta. Nova confirmação de identidade é obrigatória no clique Preencher campos.

O fallback lê somente dados **oficiais persistidos** da Mesa, nunca rascunhos. Não escreve no JSON nem inicia exportação. Uma Mesa offline não impede os preenchimentos resolvidos pelo JSON.

## 8. Detecção da Área Restrita, múltiplas abas e sincronização

Acompanhamento somente após o formulário de Complementar Ato estar **efetivamente aberto**; telas LIST e INTERESTED não devem fazer a Mesa seguir processos.

O destino observado é a última aba profissional da Área Restrita utilizada pelo operador, preservada quando o foco vai para a Mesa. Trocar para uma outra aba contendo formulário válido muda a seleção automaticamente. Se duas estruturas visíveis competirem sem desambiguação confiável, bloquear a observação como AMBIGUOUS: não escolher por índice/ordem.

Identidade do formulário deve combinar, conforme disponibilidade real:
- tabId e frameId apropriados;
- identidade exata de processo e interessado;
- identificador inequívoco do ato;
- fingerprint do documento/formulário e nonce;
- geração monotonamente controlada ou equivalente que invalide respostas antigas;
- assinatura estrutural de formulário visível.

A extensão mantém observação orientada por eventos com deduplicação e debounce, usando o canal existente autenticado à Mesa; uma verificação periódica moderada serve apenas como recuperação. A Mesa atualiza a ficha **antes** de abrir/carregar PDF e deve acompanhar mesmo durante edição, preservando-a como rascunho.

Perda de observação por form fechado, sessão expirada, ambiguidade ou TTL mantém a última ficha/PDF visíveis com sinalização inequívoca **ACOMPANHAMENTO SUSPENSO**. Ações que exigem formulário ativo ficam desabilitadas. Alternar para a Mesa sem fechar o formulário não implica suspensão.

Implementação de transporte de baixa latência: primeiro reutilizar o canal autenticado e capacidades atuais do MV3 e do backend; se falta um caminho push Mesa, acrescentar transporte mínimo de observações autenticadas com fallback periódico sem polling agressivo. Não transmitir cookies, token do portal nem valores de campos nos eventos. Uma medida preliminar de latência de detecção e atualização deve anteceder a fixação de metas P50/P95; o plano deve fixar metas e testes de regressão verificáveis.

## 9. Preenchimento: algoritmo e resultado

Acionamento: exclusivamente após clique do operador em **Preencher campos** no painel da extensão. Não existe preenchimento por simples detecção, troca automática de processo, importação de JSON ou consulta excepcional.

Preflight:
- reconhecer o formulário exato, o ato e o interessado; conferir aba, frame, nonce e geração;
- validar que a origem dos dados é JSON ativo ou fallback excepcional autorizado, sem mesclar ambas;
- validar disponibilidade e domínio real de cada controle, incluindo opções de select atuais;
- construir plano só para os cinco campos; campo ausente ou sem valor válido permanece intocado;
- comparar valores existentes no portal: equivalentes canônicos são no-op; qualquer divergência real bloqueia **toda a operação** antes da primeira escrita e apresenta side-by-side somente nesse caso;
- nenhum preenchimento se a identidade estiver ambígua ou houver mudança de geração;
- não apresentar preview geral obrigatório quando não houver divergências.

Escrita:
- realizar apenas os campos elegíveis; não preencher vazios com defaults falsos;
- revalidar alvo/generation nas fronteiras de segurança;
- após escrita, reler os controles e comparar ao plano; contabilizar written/preserved/missing/failed e estado COMPLETE, PARTIAL, BLOCKED ou FAILED;
- uma falha após escrita parcial exige releitura/reconciliação e relatório visível; jamais alegar atomicidade do DOM ou rollback garantido;
- nenhuma ação de submit, conclusão, assinatura ou tramitação.

A extensão pode permanecer operacional com a Mesa offline se o registro existir no JSON. Os resultados comuns de preenchimento são enviados por evento leve e não bloqueante, e sua perda não torna a escrita local uma falha.

## 10. Eventos leves e confirmação de conclusão

Existem conceitos distintos:

1. **FILL_RESULT**: preenchimento/releitura da extensão, contendo identidade técnica mínima, contagens e resultado; sem valores dos cinco campos; entrega best effort, perda tolerada.
2. **ACT_CONFIRMED_COMPLETED**: ato com conclusão inequívoca reconhecida a partir de evidência do portal após clique final **humano**; identidade exata necessária, durável e entregue com idempotência.
3. **PROCESS_CLOSED**: ação humana na Mesa para marcar o processo inteiro como encerrado; independente da existência de conclusão de atos e nunca inferida automaticamente.

Observar encerramento não significa clicar ou preparar o botão final. Desaparecimento do formulário, troca de frame ou retorno à lista isoladamente não são prova. Se o portal não oferecer confirmação positiva verificável, emitir **COMPLETION_UNCONFIRMED**, sem evento durável de sucesso.

Eventual confirmação de ato requer identidade exata do ato; se o portal não fornecer identificador inequívoco em todo cenário, manter bloqueado e registrar limitação REA, sem equiparar automaticamente processo+interessado a um ato singular.

### 10.1 Recuperação restrita de conclusão (decisão 29)

Se a Mesa estiver desconectada após confirmação verdadeira, a extensão protege uma fila local limitada apenas com eventos de conclusão ainda não reconhecidos pela Mesa.

Requisitos:
- ID único por conclusão/ato/geração de confirmação, ack explícito, armazenamento idempotente no backend e retransmissão com backoff;
- entrega at-least-once + aplicação efetivamente once por chave idempotente; deduplicação persistente na Mesa e avaliação exata da identidade;
- dados mínimos; nunca conter valores dos cinco campos, screenshots, cookies, sessão do portal ou JSON completo;
- criptografia autenticada em repouso quando existir material sensível de identidade: usar WebCrypto para cifrar o envelope com chave pública vinculada e autenticada da Mesa; chave privada guardada no contexto do usuário por proteção do sistema operacional (por exemplo DPAPI). Nunca assumir que chrome.storage.local oferece criptografia por si;
- fila armazenada apenas como ciphertext e metadados não identificáveis, com limite explícito no plano de até 512 eventos e retenção operacional máxima de 7 dias, sem descarte silencioso de itens pendentes ao atingir limite ou prazo: sinalizar bloqueio/reconciliação manual;
- se não houver chave confiável ou o armazenamento protegido falhar, não declarar durabilidade; avisar o operador e oferecer reconciliação manual, sem criar falsa evidência;
- após ack validado e persistência na Mesa, remover somente o evento correspondente.

O contrato do eventual armazenamento seguro, ciclo de chaves e política de retenção precisa ser verificado com testes de reinício do service worker e do navegador, perda de conexão, repetição, corrupção, troca de computador e expiração.

A conclusão geral do processo continua manual. Se houver atos pendentes ou não confirmados, a Mesa apresenta diagnóstico e exige justificativa humana explícita sem fabricar conclusões dos atos.

## 11. Mesa Local e UX modernizada

Fonte visual: HTML legado complementar-ato.html. A decisão 23-C autoriza modernização, mantendo azul-marinho/cobre, tons creme, hierarquia documental e separação PDF/ficha. Não é cópia de scripts legados nem licença para retirar funcionalidades atuais.

Estrutura:
- cabeçalho com busca, seleção de processo, filtros e acesso a áreas auxiliares;
- corpo de duas colunas: PDF à esquerda e ficha/conferência à direita, com divisor redimensionável;
- sem terceira coluna nem sidebar obrigatória;
- áreas dedicadas por navegação: Mesa, Aquisição, Lotes/JSON, Diagnósticos, Configurações;
- operações rápidas no contexto da ficha, mantendo menus e diálogos acessíveis;
- navegação entre áreas não interrompe rastreamento de formulário e não descarta rascunhos.

PDF:
- seleção de processo e ficha sempre precede renderização de documento;
- carregamento assíncrono/cancelável por token de geração de seleção; resposta obsoleta nunca atualiza painel;
- se houver escolha anterior durante a sessão, reabrir esse documento se ainda válido;
- sem escolha anterior, abrir documento principal quando a classificação for inequívoca;
- classificação ambígua -> seleção humana, sem primeiro arquivo arbitrário;
- manter documentos HOT/ACTIVE, ARCHIVED e MISSING semanticamente distintos;
- PDFs não transitam pelo JSON e jamais participam do caminho crítico do preenchimento.

UX:
- avaliação visual em resoluções de desktop e janela menor, captura de referência contra HTML original;
- medição de layout, contrastes, teclado, foco, mensagens de conflito e estados de carregamento;
- alterações modernas explicitadas em vez de afirmar equivalência pixel a pixel;
- painel da extensão compacto, com FORM, ORIGEM, ESTADO e botão **Preencher campos**; importação JSON e diagnósticos secundários.

## 12. Rascunhos e concorrência

Quando a Mesa mudar automaticamente de processo durante edição, capturar rascunho local indexado por processo+interessado+versão base. Não gravá-lo como dado oficial. Retorno à ficha restaura edição e sinaliza pendência de salvar.

Persistência aprovada: por computador, durável e protegida, **fora do workspace portátil** e do JSON exportado. O plano deve reaproveitar proteção de estado por usuário já existente ou adotar pasta dedicada ao usuário com ACL restritiva e criptografia em repouso via Windows DPAPI, com gravação atômica, journaling/recovery e teste de queda/restart. Não garantir recuperação entre computadores.

Conflito de versão:
- guardar snapshot base/revisão e campos modificados;
- comparar base x rascunho x oficial atual;
- valores alterados só no rascunho entram em proposta de mesclagem;
- valores alterados oficialmente e independentes são preservados;
- campo alterado dos dois lados com valores diferentes exige resolução humana explícita;
- nada é gravado enquanto o operador não clicar Salvar;
- salvar sob verificação otimista de versão; se a versão oficial mudar novamente, reabrir reconciliação.

Rascunhos nunca são retornados nas consultas excepcionais à Mesa nem exportados para o JSON. A falha de persistência de rascunho deverá ser visível antes de alternar de contexto: nunca indicar protegido se não há evidência de gravação.

## 13. Laboratório da Área Restrita — REA + DevTools + Playwright

**Reutilizar, não duplicar:** devtools/area-restrita/, scripts/portal-lab/, .agents/skills/area-restrita/, contrato e fixtures existentes. Chrome dedicado e CDP apenas em loopback; autenticação sempre manual; sem captura bruta versionada.

Papéis:
- **REA (Reverse Engineer Anything; referência estudada morluto/rea):** método/ferramenta auxiliar para analisar estrutura e comportamento de sistemas e organizar hipóteses; sua compatibilidade com o portal, plataforma, licenciamento e alcance operacional deve ser validada antes de usá-lo, sem supor acesso implícito a browser autenticado.
- **Chrome DevTools MCP:** instrumento prioritário de leitura de DOM/frame tree, logs, console, rede e sinais estruturais do Chrome QA.
- **Playwright CLI:** sequência única de transição permitida, snapshots comparativos, reprodução e preparação de testes.
- **mitmproxy:** opcional e não habilitado por padrão; apenas em ambiente controlado e autorizado, para metadados HTTP não sensíveis. Não fazer interceptação HTTPS do tráfego profissional autenticado, instalar CA em perfil profissional ou capturar cookies/tokens.
- **REAs/agent tools:** jamais dependências do ZIP e jamais controladores autorizados de conclusão final.

Níveis:
- L0 OBSERVE: páginas, frames, sentinelas, metadados estruturais e estados; não coletar valores de campos, headers, corpos, cookies ou credenciais.
- L1 READ_NAV: uma transição de paginação/abertura por vez com gate, baseline verde e supervisão.
- L2 PREPARE: selecionar interessado/preencher com identidade exata e aprovação própria, operador presente e antes/depois, sem concluir.
- L3 FINALIZE: proibido para agentes, scripts, REA, DevTools MCP e Playwright; somente humano conclui no portal.

**Regra de investigação:** observação reproduzível -> sanitização -> contrato/fixture -> teste RED -> correção mínima no dono único -> GREEN -> amostra real controlada -> review independente. Se três hipóteses/correções distintas para mesma classe de falha não eliminarem o problema, parar e reavaliar fronteira/arquitetura; não empilhar delays/retries.

Investigação obrigatória, sem afirmar que já ocorreu nesta versão:
1. descobrir os cinco controles reais, tipos, seletores, opções, máscaras e validações, além de eventual requisito manual de fundamentação para concluir;
2. observar variação de frames visíveis/ocultos, formulário real versus INTERESTED, última aba e identidades por ato;
3. verificar sem clique final quais sinais permitem inferir sucesso após ação final realizada exclusivamente pelo operador;
4. reproduzir, de maneira sanitizada, erro de modalidade ASP/VBScript, paginação e delays registrados historicamente;
5. comparar baseline do filler MV3 e latência da Mesa sem PDF, produzindo perfis de tempo;
6. validar se o portal permite confirmar múltiplos atos por interessado e se há ID inequívoco;
7. produzir matriz de recomendações de desempenho/correção com custo e risco, sem acionar produção antes de gates.

No repositório há histórico de fixtures de frames irmãos (formulário visível e ocultos), inconsistência de paginação e erro VBScript na modalidade. Esses relatos são evidências históricas, não comprovação de inspeção live em 2026-10-20.

## 14. Privacidade, segurança e retenção

Invariantes:
- nenhum token, cookie, CPF, matrícula, interessado ou número de processo real em commit, fixture versionada, URL de exemplo ou log divulgado;
- não utilizar hash simples de identificadores pessoais como anonimização irreversível: usar identidades fictícias, IDs efêmeros ou HMAC com chave não versionada quando correlação técnica for indispensável;
- recursos CDP acessíveis exclusivamente em 127.0.0.1 no Chrome de QA dedicado;
- mínimo de permissões MV3 e validação de origem, aba, frame, nonce, generation e sessão Mesa para mensagens;
- nenhum preenchimento com resultado de origem desconhecida; nenhuma ação final por automação;
- qualquer mudança de política de captura, armazenamento ou rotina L1/L2 requer gate explícito;
- não adicionar Node, Playwright CLI, Chrome DevTools MCP, REA, mitmproxy, .agents, devtools, snapshots, HAR, caches ou perfis ao ZIP distribuível;
- persistências no perfil do usuário e workspace respeitam sua respectiva fronteira: rascunhos protegidos por computador, histórico oficial em SQLite, JSON da extensão como snapshot, queue protegida de conclusão separada.

## 15. Tratamento de falhas

| Condição | Resultado obrigatório |
| --- | --- |
| JSON inválido, truncado, hash errado ou versão antiga | Recusar novo lote, manter ativo anterior; instruir reexportação |
| Importação enquanto há escrita | Validar/stage; ativar só após reconciliação |
| Processo ou interessado exato ausente | Consultar Mesa excepcionalmente; sem resposta segura, BLOCKED |
| Registro do JSON incompleto | Preencher apenas campos seguros do próprio JSON; não mesclar Mesa |
| Conflito de campo do portal | Bloquear operação inteira antes de escrever e mostrar divergência |
| Formulário/aba/frame/generation muda | Recusar ou reconciliar; jamais escrever em alvo stale |
| Múltiplos candidatos visíveis | AMBIGUOUS; nunca escolher primeiro |
| Mesa offline | JSON local continua funcionando; fallback indisponível |
| Event FILL_RESULT perdido | Não bloquear preenchimento; resultado local continua disponível |
| Clique final humano sem prova conclusiva | COMPLETION_UNCONFIRMED, sem ACT_CONFIRMED_COMPLETED |
| Conclusão confirmada e Mesa offline | Fila protegida, ack/dedup; nunca marcar sem evidência |
| Fila cheia, falha de chave ou expirada | Diagnóstico explícito e reconciliação humana; sem perda silenciosa |
| PDF do processo antigo chega tarde | Descartar resposta atrasada |
| Sem formulário válido | Manter última ficha/PDF e indicar acompanhamento suspenso |
| Rascunho não persistiu | Informar falha, não mostrar protegido |
| Rascunho em conflito com dados oficiais | Merge proposto, revisão de conflito, save humano com rechecagem |
| Portal solicita fundamentação legal | Operador decide manualmente no portal; extensão não preenche |

## 16. Estratégia de testes, métricas e qualification

### 16.1 Testes offline obrigatórios

Matriz com fixtures sintéticas/sanitizadas:
- v2 válido/inválido, SHA golden Python/JS, contagens, duplicidade e referências cruzadas;
- lote zero interessados, múltiplos interessados, interessado homônimo e IDs com zeros;
- importação válida/ruim, em repouso/durante fill, reinício MV3;
- JSON completo/incompleto, fallback excepcional, cache TTL, single-flight, stale response;
- divergências em qualquer dos cinco campos, select não compatível, empty/no-op, falha parcial + readback;
- múltiplas abas, foco na Mesa, frames invisíveis, session expired, candidate ambiguous, nonce/generation alterados;
- eventos best-effort e fila durável de conclusão, ACK perdido, duplicação, browser restart, perda de chave e limite de fila;
- rascunhos por computador, restart, conflito campo-a-campo, salvamento otimista e falha de escrita;
- PDFs atrasados, ausentes, arquivados e classificação ambígua;
- nenhuma escrita em fundamento_legal, genero ou tipo_processo; zero submit automático.

### 16.2 Reliability Reset: gate inegociável

Preservar vocabulário de capacidades UNQUALIFIED, EXPERIMENTAL, QUALIFIED, PRODUCTION. Toda capacidade afetada só pode ser promovida por evidência controlada e review:

- baseline offline verde, com testes de integração e packaging;
- **20/20 execuções reais consecutivas na mesma build** por capacidade qualificada; qualquer falha técnica reinicia contagem após correção;
- **20/20 execuções reais consecutivas no artefato portátil/Chrome normal** antes do estado PRODUCTION, para capacidades habilitadas nesse ambiente;
- zero identidade errada, zero ação final automática, zero reload técnico e zero intervenção DevTools nos cenários de qualificação;
- composição de capacidades somente depois da qualificação das capacidades de base aplicáveis, respeitando AR-1 a AR-6 onde relevantes;
- incidentes reais regressivos rebaixam estado; nem mock, nem uma execução isolada, nem revisão documental substituem esses gates.

Não reinterpretar "20/20" como 20 testes unitários, nem converter casos negativos não observados em evidência live. O escopo da nova UX e do JSON deve ser habilitado progressivamente com interfaces protegidas enquanto Reliability Reset continuar ativo.

### 16.3 Métricas e critérios de UX

Medir início de detecção, observação estável, atualização da ficha, início/fim do PDF, prontidão do botão e duração da escrita/readback. Reportar P50/P95/pior caso por cenário e origem JSON versus Mesa.

O writing-plans deverá estabelecer e justificar limites quantitativos verificáveis após benchmark no baseline atual; não prometer milissegundos não medidos nesta spec. Em caso de latência superior, investigar evento/DOM/frames/API antes de aumentar timers.

QA visual com screenshots pareados do HTML antigo e Mesa atual nos viewports de referência; revisão de contraste, teclado, foco, feedback de erro, responsividade e divisor.

### 16.4 Gates de entrega

- auditoria source-of-truth e baseline no HEAD;
- contratos RED/GREEN e revisão de privacidade;
- gates Python, JS extensão, JS web e pacote portátil;
- verificação do ZIP em extração limpa sem ferramentas de desenvolvimento;
- review adversarial independente de cada frente;
- evidência real permitida e explicitamente classificada;
- aceite humano do comportamento e promoção explícita por capacidade.

## 17. Decomposição para writing-plans futuro

A implementação é grande: **não gerar plano monolítico com todas as alterações em uma única task**. O writing-plans deverá produzir fases sequenciais com interfaces congeladas:

1. **Fundação / contrato:** inventário do runtime, migração compatível, cinco campos, desligamento jurídico, schema JSON v2, integridade e golden vectors.
2. **Extensão autônoma:** importação atômica, matching, preenchimento seguro, painel compacto, fallback single-flight, fixtures e offline QA.
3. **Observação e integração:** rastreamento da última aba, eventos de baixo custo, suspensão e readback, sem dependência de PDF.
4. **Mesa e rascunhos:** UI duas colunas, cabeçalho e áreas auxiliares, viewer de PDF com cancelamento, rascunhos protegidos, merges.
5. **Conclusões e reconciliação:** prova inequívoca, fila criptografada, ACK/idempotência, conclusão individual e encerramento geral humano.
6. **Portal Lab/REA e Qualification:** antes e durante as fases relevantes, investigação L0; L1/L2 apenas após gates; matriz 20/20+20/20, revisão independente e avaliação de desempenho. Nenhum L3 por ferramentas.

Cada fase terá contrato de entrada, TDD, critérios de parada, critérios de reversão, riscos, snapshots de evidência não sensível e gate humano. Decisões que dependam da observação real (e.g. prova positiva de conclusão, tipos reais de select) permanecem **capabilidades condicionais bloqueadas até evidência**, não requisitos inventados como já satisfeitos.

Não invocar writing-plans nem implementar antes de aceite humano desta spec.

## 18. Rastreabilidade integral das 29 decisões

| ID | Decisão aprovada | Seção |
| --- | --- | --- |
| 1-A | Mesa sempre segue automaticamente mesmo durante edição | 8, 12 |
| 2-A | Seguir apenas formulário de Complementar Ato aberto | 8 |
| 3-B | Evento imediato + verificação periódica fallback | 8 |
| 4-A | Match exato e fill por clique sem preview universal | 7, 9 |
| 5-B | Preenchimento parcial elegível, sem inventar valores | 9 |
| 6-A | JSON snapshot imutável; reexportar/reimportar | 6 |
| 7-C | Processo ausente -> consulta excepcional à Mesa | 7 |
| 8-B | Importação atômica com stage durante fill | 6 |
| 9-B | Divergência no portal bloqueia write; comparação pontual | 9 |
| 10-A | tipo_processo classifica e nunca preenche | 5, 6 |
| 11-A | JSON traz inventário integral inclusive sem interessados | 6 |
| 12-C | Interessado ausente no processo do JSON -> Mesa automática | 7 |
| 13-B | Consulta single-flight em memória com TTL e invalidação | 7 |
| 14-B | FILL_RESULT leve e não bloqueante para Mesa | 10 |
| 15-B | Observar conclusão portal após clique humano inequívoco | 10 |
| 16-C | Ato individual observado; encerramento geral manual | 10 |
| 17-B | Encerramento geral com pendências exige justificativa | 10 |
| 18-B | Rascunho preservado por processo/interessado ao seguir | 12 |
| 19-B | Rascunho durável e protegido por computador | 12 |
| 20-C | Merge de alterações independentes e conflito humano | 12 |
| 21-C | Ficha imediata; PDF carregado em paralelo | 11 |
| 22-C | Último PDF em sessão, fallback principal ou escolha humana | 11 |
| 23-C | Modernizar com identidade do HTML legado | 11 |
| 24-A | Mesa com duas colunas e navegação no cabeçalho | 11 |
| 25-B | Funções auxiliares em áreas dedicadas | 11 |
| 26-A | Painel único e compacto da extensão | 11 |
| 27-B | Última aba da Área Restrita utilizada | 8 |
| 28-B | Ficha/PDF mantidos com acompanhamento suspenso | 8 |
| 29-B | Fila durável limitada para conclusões confirmadas | 10 |

**Revisão adicional de 20/10:** fundamentação legal excluída de todo o novo fluxo operacional, com preservação histórica e sem escrita no portal; REA e ferramentas complementares são instrumentos do Portal Lab, nunca licença para varredura invasiva ou submit.

## 19. Checklist de aceite desta spec

A revisão humana deve confirmar explicitamente:
- [ ] Somente cinco campos podem ser escritos; fundamento_legal, genero e tipo_processo não são preenchidos.
- [ ] O portal real pode continuar exigindo preenchimento manual de campos fora do fluxo.
- [ ] JSON v2 é completo por lote selecionado, atômico, imutável e principal fonte de preenchimento.
- [ ] Consultas à Mesa são excepcionais apenas para registro ausente e nunca para completar JSON parcial.
- [ ] A Mesa segue a última aba/formulário válido, sem impedir edições e sem depender do PDF.
- [ ] Rascunhos são persistentes/protegidos por computador, mesclagem exige save humano.
- [ ] Eventos de fill podem se perder, mas conclusão inequívoca deve ser recuperada sem falso positivo.
- [ ] Nenhuma conclusão final, assinatura, envio, tramitação ou login profissional automatizado.
- [ ] REA/DevTools/Playwright permanecem ferramentas de investigação, sujeitas a gates.
- [ ] Reliability Reset 20/20 + 20/20 continua obrigatório para promoção de capacidades.
- [ ] Nenhum código, testes, banco ou runtime alterado pela criação desta spec.
- [ ] Writing-plans somente após aprovação documental.

**Estado de handoff:** documento pronto para revisão humana; ausência de aceite impede writing-plans e implementação.
