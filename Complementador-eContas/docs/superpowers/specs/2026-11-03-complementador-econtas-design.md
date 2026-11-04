# Complementador e-Contas — Especificação de design (Superpowers)

- **Data:** 03/11/2026
- **Estado:** DESIGN APROVADO PELO OPERADOR EM 03/11/2026 — plano de implementação em elaboração; implementação ainda não iniciada
- **Produto:** extensão Google Chrome independente para complementação assistida de atos de pessoal no e-Contas do TCE/RN
- **Referência funcional:** `https://processos.tce.rn.gov.br/` (origem a confirmar na F0)
- **Autonomia:** repositório, código, configuração, testes e distribuição separados de `%USER%/Atos-TCE`

## 1. Problema e intenção

O operador mantém, no **mesmo perfil do Chrome**, uma janela/aba com os autos de um processo e outra com o formulário **Complementar Ato**. O operador navega manualmente pelos eventos até encontrar o documento correto, deixa esse documento aberto no visualizador e retorna ao formulário. Ao clicar em **⚡ Preencher**, deseja extrair os dados de **todas as páginas do documento atualmente aberto**, preencher os campos pertinentes e conferir o resultado antes de complementar o ato manualmente.

Nenhuma leitura de conteúdo de PDF, extração, OCR ou preenchimento deve ocorrer antes do clique explícito. O número do evento não é fixo. O operador não precisa selecionar texto, baixar manualmente o arquivo ou alternar novamente de janela depois do clique.

## 2. Decisões já aprovadas

1. **Produto autônomo**: não integrar código, banco de dados, acervo, runtime nem operações ao antigo Atos-TCE. Documentação anterior é apenas referência técnica.
2. **Solução prioritária**: extensão Chrome **Manifest V3** enxuta e 100% local, sem Python, banco, backend próprio, serviço externo, nuvem ou IA obrigatória.
3. **Gatilho único**: somente o clique em **Preencher** ativa o ciclo completo de leitura → extração → validação → preenchimento → readback. O reconhecimento de rota necessário para exibir o botão não autoriza inspecionar conteúdo antecipadamente.
4. **Fonte controlada pelo operador**: um único documento, selecionado manualmente e visível na aba de autos do processo; o evento pode mudar livremente.
5. **Sem conclusão automática**: nunca clicar em **Complementar Ato**, salvar modalidade ou emitir POST/PUT de conclusão; somente preencher controles editáveis e entregar a revisão final ao operador.
6. **Regra operacional específica da data**: o campo da interface **Data de publicação no DOE** receberá **a data da resolução administrativa**, convertida para `DD/MM/AAAA`, quando esta data for identificada de forma inequívoca. A equivalência é uma instrução operacional do usuário, **não** uma conclusão de que houve publicação efetiva na mesma data. Exibir discretamente a origem do valor e mantê-lo sujeito à conferência.
7. **REA obrigatório como fase F0**: inspecionar o e-Contas, a tela de autos/visualizador, o formulário e a ponte de abas antes de escolher o adaptador concreto.
8. **Velocidade sobre complexidade**: preferir caminho de texto direto e regex/regras determinísticas; OCR, LLM e infraestrutura local adicional ficam fora do MVP, salvo futura decisão expressa após evidência da F0.
9. **Confidencialidade**: conteúdo dos processos não vai para APIs externas, repositório, logs persistentes ou telemetria.

## 3. Abordagens consideradas

| Alternativa | Ganho | Custo/risco | Decisão |
|---|---|---|---|
| A. Extensão MV3 autônoma, JavaScript, leitura e preenchimento via abas | Pouca instalação, zero serviço, comunicação do próprio navegador | Viewer PDF pode impor restrições | **Aprovada como baseline** |
| B. Extensão + serviço local Python | Mais opções de PDF/OCR | Serviço, runtime, instalação e manutenção adicionais | Reservada para reavaliação futura, não implementar |
| C. Userscript Tampermonkey/Violentmonkey | Spike simples | Menor controle de distribuição/permissões e manutenção | Rejeitada como produto principal |

O adaptador de leitura da alternativa A deve ser decidido **pelas evidências da F0**, sem pressupor que `PDFViewerApplication` ou `.textLayer` estarão acessíveis. Preferir leitura nativa autorizada do conteúdo do visualizador; se inviável, obter o mesmo PDF por mecanismo legítimo da sessão e processar localmente com PDF.js. **Não** interceptar credenciais, contornar CORS, mecanismos de autorização, MFA ou políticas do portal.

## 4. Arquitetura proposta

```text
Chrome — mesmo perfil
  ├─ Aba A: /#/dashboard/processos/:idProcesso/autos
  │    └─ content script de leitura, inativo até solicitação
  ├─ Aba B: /#/dashboard/complementar-ato/:idProcesso
  │    └─ botão ⚡ Preencher + adaptador DOM do formulário
  └─ Service worker MV3
       ├─ localiza abas autorizadas por URL/ID
       ├─ envia requisição única à Aba A após clique
       ├─ recebe texto das páginas + proveniência mínima
       ├─ extrai campos localmente (regras determinísticas)
       ├─ valida processo, pessoa, documento e catálogo
       └─ entrega proposta apenas à Aba B, com readback
```

### 4.1 Módulos lógicos mínimos

- `background`: roteamento e controle de uma transação por clique; sessões efêmeras.
- `autos`: resolução inequívoca do PDF aberto; extração de todas as páginas e detecção de mudança durante leitura.
- `extract`: parser determinístico com indicação do trecho/origem; identificação de datas, cargo, matrícula, interessado e modalidade.
- `form`: leitura do DOM, identificação de pessoa/processo, catálogo atual, escrita por setter nativo/eventos, readback dos cinco campos e proteção contra submissão.
- `ui`: um botão contextual e feedback sucinto (preenchidos, preservados, não localizados, bloqueados, ambiguidades).

A pasta/linguagem final é escolha do implementador após F0. Preferência por JavaScript simples, sem framework de UI e sem bundle pesado quando possível. Dependências externas devem ser mínimas, fixadas em versões e auditadas.

### 4.2 Matching e concorrência

- Na aba de complementação, obter o `idProcesso` da rota hash e o número/ano efetivamente apresentados.
- Localizar **somente** abas de autos autorizadas e com mesmo `idProcesso`; quando existirem 0 ou 2+ candidatas sem diferenciação segura, **não** escolher por ordem/última atividade: exibir diagnóstico/seleção explícita.
- Conferir o processo, interessado selecionado e, quando disponível, um identificador de pessoa; modalidade é **do processo**, os quatro outros campos são **por interessado**.
- Se o PDF não contiver identidade suficiente para relacioná-lo com segurança à pessoa selecionada, não atribuir campos personalizados; em processo com vários interessados, exigir correspondência inequívoca.
- Registrar somente em memória um `requestId` efêmero, rota, identidade e referência temporal do documento. Ao mudar processo/aba/documento/pessoa durante o ciclo, cancelar sem aplicar propostas obsoletas.
- Nenhum valor existente, bloqueado ou somente leitura será sobrescrito. Divergência com valor preenchido vira aviso.

## 5. Contrato de campos

| Campo da interface | Fonte preferida | Conversão e validação | Política de falta/ambiguidade |
|---|---|---|---|
| Modalidade do ato (por processo) | Nome e contexto da concessão da aposentadoria/pensão/revisão na resolução | Resolver contra **opção única do catálogo real** do e-Contas; nunca escolher por aproximação vaga | Não alterar; indicar pendência |
| Data de publicação no DOE (por interessado) | **Data da resolução administrativa** (regra do operador) | `DD/MM/AAAA`; conferir dia/mês/ano e semântica da data do ato; não confundir com nascimento, parecer, assinatura digital ou datas citadas | Não preencher, se houver datas candidatas inconciliáveis; evidenciar a regra aplicada |
| Cargo (por interessado) | Trecho da resolução referente ao interessado | Normalizar sem inventar abreviaturas; respeitar limite do controle | Não preencher se incerto |
| Matrícula (por interessado) | Identificador funcional do interessado | Preservar `/`, zeros e sufixos; validar formato e limite do controle | Não preencher se incerto |
| Data de nascimento (por interessado) | Texto do documento atual, se presente | `DD/MM/AAAA`, calendário válido; compatibilidade com controle real | Preservar valor existente; senão, deixar manual |

**Nota sobre data:** não assumir que a data de publicação oficial coincide juridicamente com a data da resolução. A extensão apenas materializa a regra de entrada indicada pelo operador, exibindo claramente `Origem: data da resolução` e nunca afirmando ter verificado o Diário Oficial. Se houver efetiva data de publicação distinta no PDF, sinalizar a discrepância para revisão, sem substituir silenciosamente a opção do usuário.

**Nota de UI:** investigação histórica identificou Angular com `tce-input-field`, elemento `type=text` e diretiva `bsDatepicker` para campos rotulados como datas, e seleção de modalidade por catálogo de IDs. Confirmar novamente na F0 antes de codificar. A escrita deve disparar os eventos necessários e reler o valor renderizado/estado do formulário; nenhuma automação deve acionar eventos ou botões de gravação explicitamente.

## 6. Fluxo de interação

1. Usuário faz login normalmente, abre os autos e localiza manualmente o documento correto em qualquer evento.
2. Mantém o documento aberto; na segunda aba, abre **Complementar Ato** para o mesmo processo e seleciona o interessado correto, quando aplicável.
3. Clica **⚡ Preencher**.
4. Extensão identifica a aba fonte e resolve o PDF atual. Lê todo o documento somente agora; não percorre outros eventos.
5. Extrator produz propostas com origem e confiança operacional simples (`exato`, `ambíguo`, `ausente`), sem IA na primeira versão.
6. Valida identidade, catálogo, valor atual e editabilidade; escreve apenas campos comprovados e vazios, sem comandos de conclusão.
7. Realiza readback e mostra resultado compacto: preenchidos, preservados, pendências e eventuais discrepâncias.
8. O operador revisa o formulário e, se julgar correto, usa os controles normais do portal para concluir o ato.

Falhas devem ser reversíveis: nunca apagar controles, salvar automaticamente, alterar a seleção de interessado, renovar a página ou iniciar download não autorizado. Quando texto não estiver acessível, mostrar mensagem compreensível em vez de inventar conteúdo.

## 7. Fases e gates

### F0 — Reconhecimento técnico do e-Contas com REA (obrigatória antes da implementação)

**Objetivo:** reduzir incertezas do visualizador/SPA com observação controlada e sem modificar processos.

- Ler o relatório histórico `2026-10-21-econtas-l0-discovery-handoff(1).md` como antecedente, **não** como prova do estado atual.
- Identificar versão/estrutura atual de autos, evento e PDF, elemento visualizador, `iframe`, `textLayer`, canais de arquivo e disponibilidade de texto em **todas** as páginas.
- Identificar rotas, titularidade do `idProcesso`, identidade do interessado, modalidade, inputs/datepicker, limites e reatividade do formulário.
- Usar **REA (Reverse Engineer Anything)** para inspeção passiva de aba autorizada, idealmente via CDP loopback já acessível; caso indisponível, registrar a limitação e usar observação de interface/DevTools permitida, sem reiniciar/reconfigurar o navegador profissional sem autorização.
- Não fazer PUT/POST, login automatizado, disparo do botão final, captura de cookies/tokens/CPF em logs ou salvar screenshots contendo dados pessoais.
- Entregar relatório sanitizado: hipótese → evidência → limite, viabilidade da extração, matriz de campos, riscos e caminho mais rápido recomendado; critério go/no-go para seguir com extensão apenas.

**Gate F0:** o método de obtenção autorizada do documento está demonstrado, ou a limitação está documentada com alternativa mínima definida para decisão do operador; não alegar que PDF.js é acessível sem testar.

### F1 — Extensão MV3 mínima

- Criar repositório **novo** somente após autorização de implementação, sem copiar a árvore antiga.
- Botão contextual, permissões restritas ao portal, roteador único e leitura das rotas.
- Ensaiar comunicação entre duas abas/duas janelas no mesmo perfil usando páginas de teste e processos fictícios.
- Recusar múltiplas abas, processos cruzados, DOM desatualizado, service worker reiniciado.

**Gate:** comunicação após clique e isolamento entre processos comprovados; nenhum acesso/parse de PDF antes do clique.

### F2 — Leitura e extração

- Implementar adaptador de texto escolhido na F0 (texto acessível → PDF.js local se necessário).
- Ler todas as páginas do **documento atual**, não os demais eventos.
- Extrator determinístico para os cinco campos, incluindo data numérica da resolução e associação a interessado.
- Testar tipos de resolução, datas conflitantes e documentos sem texto.

**Gate:** fixtures sintéticas e documentos autorizados demonstram campos corretos com evidência de origem; ambiguidades produzem pendência, nunca inferência silenciosa.

### F3 — Preenchimento assistido

- Adaptador ao formulário real constatado na F0; modalidade única por processo, demais campos por interessado.
- Setters/eventos adequados ao Angular, controle de datepicker, validação de opção disponível, preservação de preenchidos/readonly.
- Readback e feedback compactos; não acionar salvar ou concluir.
- Em página real, testar **escrita apenas nos campos da UI, sem salvar**, somente após autorização explícita adicional de L2; se qualquer mecanismo de autosave for encontrado, abandonar esse ensaio real.

**Gate:** testes de formulário e readback sem chamadas de conclusão, com autorização explícita para qualquer ensaio em processo real.

### F4 — Qualidade, velocidade e distribuição

- Medir tempo total clique → resultado com `performance.now()` (amostras e percentis p50/p95) em PDF texto e documentos maiores; não anunciar SLA sem medir.
- Testar mudança de documento durante a leitura, abas duplicadas, vários interessados, modal existente, campos parcialmente preenchidos, erro de PDF, rota divergente, datas múltiplas e travamento/restart de MV3.
- Fazer revisão de permissões, privacidade, vazamento de dados e teste negativo de rede/gravação.
- Entregar pasta instalável em `chrome://extensions` e instruções de instalação/rollback.

**Gate:** demonstração manual supervisionada, suíte verde, nenhuma submissão/salvamento automático e relatório de tempos reais.

## 8. Metas de desempenho

- **Meta de produto:** um clique para iniciar e, quando o documento permitir, preenchimento praticamente imediato.
- **Meta experimental:** buscar até ~1 segundo para documentos nato-digitais pequenos, **a ser medida**, não garantida.
- Sem pré-processamento de documento antes do clique.
- Sem servidor local, LLM ou OCR na V1. Quando o documento exigir OCR, informar limitação, não executar processamento remoto.
- O botão deve refletir estado `Lendo…`/`Preenchendo…` e impedir cliques concorrentes; permitir nova tentativa após erro seguro.

## 9. Segurança, privacidade e conformidade

- Respeitar perfis, login e autorização normais do portal e diretrizes institucionais do TCE/RN; não burlar controles, cabeçalhos, proteção de PDF ou endpoint privado.
- Dados de processos permanecem no Chrome local e são descartados ao fim do pedido, sem persistir nomes, CPF, matrícula, PDF ou texto em `chrome.storage`, IndexedDB, logs, Git, screenshots ou telemetria.
- Content scripts restritos a `https://processos.tce.rn.gov.br/*`, sujeito à confirmação na F0; permissões mínimas.
- Proibido requisitar/usar diretamente endpoints de escrita `PUT`/`POST` do e-Contas, concluir atos, alterar modalidades existentes sem concordância manual ou executar navegação automática por outros eventos.
- Sempre preferir falha fechada à atribuição de dados potencialmente errados a pessoas diferentes.
- Nenhum dado real em fixtures; usar dados sintéticos em testes automatizados.

## 10. Critérios de aceite verificáveis

- [ ] Abrir qualquer evento com documento e usar duas janelas do mesmo perfil, sem seleção de texto.
- [ ] Nenhuma leitura do conteúdo documental antes do clique em **Preencher**.
- [ ] Identificar `idProcesso` igual nas abas e pessoa selecionada, com falha segura diante de ambiguidade.
- [ ] Processar integralmente o documento atualmente aberto, não outros eventos.
- [ ] Preencher apenas os campos ausentes de cinco conceitos; preservar valores existentes.
- [ ] Normalizar corretamente `7 de novembro de 2025` para `07/11/2025`, conforme regra da resolução administrativa.
- [ ] Não confundir datas alternativas, aniversários, assinaturas ou datas de outros documentos; se a data do ato não for inequívoca, sinalizar.
- [ ] Modalidade deve corresponder a uma única opção real da lista.
- [ ] Inputs Angular/datepicker refletirem alterações após eventos e readback.
- [ ] Não criar chamada de conclusão, PUT/POST, salvar modalidade ou clicar no botão final.
- [ ] Testes negativos de processos cruzados, múltiplos interessados, documentos ausentes, erros do PDF e alteração simultânea de rota.
- [ ] Velocidade medida com percentis e ambiente descritos, não presumida.
- [ ] Instalável como extensão independente, sem serviço/local do Atos-TCE.
- [ ] Nenhum dado privado em fontes, entregáveis ou logs.

## 11. Referências e limites de conhecimento

- **Base histórica (não o estado live atual):** `2026-10-21-econtas-l0-discovery-handoff(1).md`, investigação L0/L1. Registrou Angular 10.0.14 / e-Contas 2.6.17, estrutura de cinco campos e CDP/REA indisponível em 21/10/2026. Não confirma o PDF viewer dos autos nem a escrita L2.
- **Produto legado:** `https://github.com/%USER%/Atos-TCE`, consultado apenas como referência; seu preenchimento da Área Restrita não atende automaticamente a rota nova do e-Contas.
- **REA oficial:** `https://github.com/morluto/rea`; a inspeção web exige configuração/autorizações e, geralmente, endpoint CDP loopback.
- **Chrome extensions:** mensagens entre abas são mecanismo previsto por Manifest V3, mas acesso ao visualizador interno de PDF não é garantido; F0 decide viabilidade.

### Decisões deixadas para o implementador após F0

Escolha do empacotamento mais simples, nomes exatos dos módulos, parser e padrões de regex, métricas de teste, UI mínima, mecanismo permitido de acesso ao PDF e detalhes de readback. Não escolher dependências antes da prova de necessidade.

### Gate de autorização

**Esta especificação foi aprovada pelo operador em 03/11/2026.** Sua aprovação autoriza elaborar o `superpowers:writing-plans`; não equivale a executar código no Chrome autenticado, editar campos reais, salvar ou concluir atos. A execução será iniciada apenas após o aceite do plano e do método de execução. Escrita real no DOM (L2) requer autorização explícita adicional; nenhum ato será salvo ou concluído automaticamente.


## 12. Condição operacional acrescentada após aprovação (03/11/2026)

Para a fase F0 e para os testes de integração subsequentes, o operador **deixará abertas no mesmo perfil do Chrome**: (a) uma aba/janela na tela **Complementar Ato** e (b) uma aba/janela na tela de **autos do mesmo processo, já posicionada no documento correto**. A ferramenta deverá usar as abas *existentes*, sem criar ou reiniciar sessão, sem modificar perfil, setor, filtros, evento, documento, processo ou pessoa selecionada, e sem realizar login. A inspeção inicial é observacional e não autoriza coleta persistente de dados pessoais. A disponibilidade das abas é uma condição da execução no computador do operador, **não** evidência de acesso a essas abas neste ambiente de planejamento.
