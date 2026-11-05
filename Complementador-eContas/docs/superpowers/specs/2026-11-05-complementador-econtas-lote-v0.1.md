# Complementador e-Contas — Automação em Lote

Especificação formal Superpowers — v0.1 (aprovada em 05/11/2026)
Origem: arquitetura consolidada D01–D33, aprovada pelo usuário.
Plataforma: extensão Chrome Manifest V3, projeto Complementador-eContas/ do repositório matheussilva421/Atos-TCE, ramo de referência codex/complementador-e-contas.
Este documento é uma cópia operacional da especificação aprovada na conversa, organizada para acompanhar o plano. A aprovação não autoriza modificar código, instalar componentes nem salvar atos reais.

1. Objetivo
Manter o botão individual ⚡ Preencher e acrescentar ⚡ Rodar automação à listagem de processos do e-Contas. Após o usuário selecionar o marcador/filtros e definir limites, a extensão deve congelar a fila da página atual, processar um processo por vez, localizar Resolução Administrativa e Guia Financeira/Taxação de Proventos, preencher os cinco campos, validar, salvar, comprovar resultado, registrar andamento e prosseguir até um limite, esgotamento ou pausa segura.
2. Regra de negócio definitiva
- Um interessado corresponde a um ato no processo; um único interessado = um único ato elegível para esta automação.
- Dois ou mais interessados, nenhum interessado ou quantidade indeterminada = ignorar o processo inteiro, sem salvar (D01).
- Já complementados não serão complementados de novo; serão excluídos da fila inicial sem consumir o limite de examinados (D33).
- As antigas hipóteses de D30–D32 sobre múltiplos atos para um único interessado não têm efeito operacional. Preserve o histórico das decisões, aplique a correção posterior do usuário.
3. Dados e fontes documentais
Priorizar a Resolução Administrativa pertinente, a Guia Financeira/Taxação de Proventos pertinente e, somente quando necessário, outros documentos do mesmo processo. Falta ou conflito de dado => REVIEW_REQUIRED, sem salvar, prosseguindo para outro processo (D02). Nunca inferir informações não corroboradas, nem misturar autos de processos distintos.

Campos obrigatórios: modalidade, dataDoeEstado, cargo, matricula, dataNascimento. dataDoeEstado recebe a data da Resolução Administrativa por convenção operacional; não equivale a prova de publicação no DOE. Para o modo em lote, valores preexistentes compatíveis são mantidos, vazios são preenchidos, divergentes não são sobrescritos e impedem salvamento (D19). A validação pré-save é básica (cinco preenchidos e nenhum erro visível), somada às verificações de identidade, elegibilidade e divergência já definidas (D09).
4. Limites e fila
- Usuário define dois inteiros positivos: máximo de processos efetivamente examinados e máximo de atos com salvamento confirmado (D04).
- Parar ao atingir o primeiro limite ou esgotar fila. Nunca ultrapassar limites; não consumir quota de examinados para itens simplesmente capturados ou pré-excluídos.
- Capturar só os processos visíveis na página atual, sem paginação (D12), congelar IDs (D06), verificar elegibilidade/status novamente antes de cada operação.
- Mudança de ordenação ou de status não altera IDs congelados; mudança de marcador/filtros => pausa e conferência antes da retomada (D13).
- Exclusão de concluídos utiliza status real no portal, não somente cor vermelha/verde.
5. Arquitetura
Uma única extensão com dois modos (D17). Service worker MV3 coordena fila, limites, navegação, estados, salvamento e recuperação (D25); content scripts operam DOM; painel compacto opera na listagem (D10); diário local persistente mantém checkpoints (D07, D26). A suspensão normal do service worker não deve provocar perdas ou repetição de salvamentos. Usar duas abas de trabalho reutilizáveis (Autos + Complementar Ato), preservando a aba de listagem (D08), no mesmo perfil autenticado. Um processo por vez, sem paralelismo. Só um lote ativo por perfil; revalidar ato antes de salvar (D24). Não prometer exclusão mútua entre máquinas distintas.
6. Fluxo do lote
1. Conferir sessão, marcador/filtros, página atual, limites, quantidade visível e ausência de lote ativo (D29); clique único em Iniciar autoriza o lote conforme D03.
2. Congelar lista inicial e excluir já complementados.
3. Para cada processo ainda apto: revalidar processo/status, abrir Autos e formulário nas abas dedicadas, confirmar exatamente um interessado, selecionando-o automaticamente se necessário (D14).
4. Reutilizar extração documental existente e fazer fallback documental D02 quando necessário.
5. Preencher e conferir cinco campos; preservar compatíveis e bloquear divergentes.
6. Revalidar ato pendente e identidade imediatamente antes do salvamento.
7. Persistir estado de operação potencialmente irreversível antes de clicar em Complementar ato.
8. Aceitar apenas diálogos reais conhecidos e homologados; mensagens inesperadas não são confirmadas automaticamente (D20).
9. Confirmar conclusão por evidências suficientes do portal e do ato correto; contar somente salvamentos confirmados (D05).
10. Registrar resultado/checkpoint; avançar ou encerrar por limites, esgotamento, pausa/parada.
7. Estados e segurança
Lote: READY, RUNNING, PAUSE_REQUESTED, STOP_REQUESTED, PAUSED, SUSPENDED, COMPLETED, STOPPED.

Processo: QUEUED, EXAMINING, READING, FILLING, VALIDATING, SAVE_PENDING, VERIFYING, CONFIRMED; saídas alternativas SKIPPED, REVIEW_REQUIRED, FAILED, SAVE_UNCERTAIN.
- PAUSE_REQUESTED e STOP_REQUESTED: concluir o processo atual ou alcançar estado seguro, sem iniciar outro (D15).
- SAVE_UNCERTAIN: suspender e reconciliar pelo portal; não repetir automaticamente a ação irreversível (D05).
- Sessão expirada: pausar, preservar, aguardar login humano, revalidar contexto e só retomar após clique em Continuar (D21).
- Aba de trabalho alterada antes do salvamento: no máximo uma tentativa de restauração com verificação de identidade; caso contrário pausar. Se houve tentativa de salvamento, não tentar repetir (D23).
- Aguardar condições observáveis, não usar sleeps fixos longos; tentativas limitadas para falhas transitórias e pausas em falhas sistêmicas repetidas (D11, D27).
- Reativação do MV3: reconstruir estado; não retomar silenciosamente após reinício do navegador ou quando a D07 exigir confirmação explícita.
8. Persistência, relatório e privacidade
Diário local mínimo: identificadores estritamente necessários, fila, limites, estado do lote/processo, motivos, checkpoints e confirmação de resultado. Não persistir PDFs integrais, texto documental, nome, CPF, matrícula, data de nascimento, tokens nem credenciais. Dados pessoais só transitam pelo fluxo de extração e preenchimento. Limpeza controlada de lotes encerrados; preservar lotes interrompidos e salvamentos incertos até resolução segura (D28).

Painel compacto: dois limites, quantidade disponível, processo atual, contadores, Iniciar/Pausar/Parar/Continuar e resumo final (D10). Relatório (D18): capturados, pré-excluídos, examinados, confirmados, ignorados, revisão, falhas, incertos, motivo e link do processo no portal. Só confirmação comprovada pode ser rotulada de concluída.
9. Reconhecimento do portal
Codex deve investigar sem salvar no Chrome QA a listagem/marker/filtros, IDs estáveis, status, rotas, interessados, formulário, botão, diálogos, mensagens e prova pós-save possível. Usar REA/RHEA somente seletivamente quando DOM/observação não bastar (D22); documentação sanitizada, sem tokens, cookies ou dados pessoais reais. Nenhum seletor, rota da listagem, texto de modal, resposta de API ou semântica de status pode ser inventado.
10. Homologação progressiva
H1 sintético: testes unitários, integração e navegador simulado/QA sem salvamento institucional.
H2 real controlado: somente após autorização específica, um salvamento real com comprovação de processo/ato/resultado, respeitadas regras institucionais.
H3 lote pequeno supervisionado: somente após aprovação de H2 e nova autorização específica, verificar avanço e resultados com mais de um processo.
Lotes reais autônomos: somente após homologação e aceite pertinentes (D16).
11. Critérios de aceite (CA-01–CA-20)
- CA-01: modo individual não sofre regressão.
- CA-02: fila limitada à página atual.
- CA-03: já concluídos excluídos, sem gastar limite de examinados.
- CA-04: múltiplos interessados jamais salvos.
- CA-05: interessado único selecionado e confirmado.
- CA-06: documentos corretos, sem escolhas arbitrárias.
- CA-07: cinco campos preenchidos conforme regras.
- CA-08: preexistentes compatíveis mantidos; divergentes bloqueiam.
- CA-09: dois limites não excedidos.
- CA-10: só contar salvamentos comprovados.
- CA-11: jamais repetir cegamente um salvamento incerto.
- CA-12: pausa e parada em estados seguros.
- CA-13: suspensão MV3 não perde checkpoints nem duplica.
- CA-14: expiração permite retomada controlada após novo login.
- CA-15: falhas transitórias sem travamentos indefinidos.
- CA-16: apenas um lote por perfil.
- CA-17: relatório exato por processo/motivo.
- CA-18: diário sem PDFs e dados pessoais extraídos.
- CA-19: nenhum salvamento real sem autorizações e homologação.
- CA-20: retomada consistente após interrupções, reload ou reinício.
12. Requisitos não funcionais
Compatibilidade Chrome/Edge >= 110 conforme extension/manifest.json existente; JavaScript ESM; sem servidor externo, OCR/LLM/backend remoto, armazenamento de credenciais ou reestruturação desnecessária. Priorizar desempenho e reuso do mecanismo de extração/preenchimento já testado; falhar fechado diante de contexto ambíguo. Preservar main e o modo individual, com backup verificável e rollback. Manter rastreabilidade D01–D33.
13. Fronteira de autorização
A aprovação desta especificação autoriza somente escrever e revisar o plano Superpowers. Não autoriza executar etapas do plano, instalar dependências, publicar código, tocar Chrome institucional ou salvar atos reais. Os gates H2/H3 dependem de autorização explícita e separada.
