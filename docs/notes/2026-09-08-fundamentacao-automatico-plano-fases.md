# Fundamentação e complementação automática — plano de implementação em fases

> Para agentes executores: usar `superpowers:executing-plans` ou `superpowers:subagent-driven-development` para executar tarefa por tarefa, com revisão de integração. As caixas abaixo rastreiam implementação futura; a criação deste documento não significa que a funcionalidade foi implementada.

**Objetivo:** corrigir a seleção do fundamento legal, redesenhar a extensão para conferência e acompanhamento claros e executar a complementação sequencial dos atos disponíveis, com relatório incremental durável e retomada sem repetição cega de envios.

**Arquitetura:** reaproveitar a extensão Manifest V3 para operar o DOM do portal e o serviço Python local autenticado para dados, fila, eventos e relatórios. Separar interpretação documental, classificação jurídica operacional, navegação e envio. O banco local será a fonte do histórico de execução; HTML, CSV e painel serão projeções recuperáveis desse histórico.

**Tecnologias:** JavaScript ES modules no worker/painel, content scripts clássicos compatíveis com os testes atuais, Node `node:test`, Python `unittest`, `sqlite3` da biblioteca padrão, PowerShell 5.1 e ferramentas de navegador já utilizadas pelo projeto.

**Especificação:** seção 1 deste documento consolida as decisões da entrevista de 08/09/2026. O plano anterior na conversa é substituído por esta versão detalhada. Não depende de outro documento não salvo.

**Estado:** EM EXECUÇÃO. Fases 0–8 e os gates locais da Fase 9 foram implementados nesta branch; o envio real e a qualificação do portal permanecem bloqueados por checkpoint explícito. A Fase 10 recebeu a atualização local de allowlists, auditoria, versão e fixture de pacote; a publicação real continua pendente.

**Revisão de 09/09/2026:** a Fase 9 agora possui portal sintético servido em Chrome, navegação por páginas/seleção, frame de formulário e bloqueio de envio sem serviço; o journal cobre 25 atos, três pendências e timeout no ordinal exato. A Fase 10 passou a carregar os módulos de automação no pacote completo, reconhecer `alarms` e exigir a versão de extensão `1.1.0`. O painel também tem gate estático de contraste, idioma, IDs/labels e cópia de segurança. Nenhum teste local é evidência do portal real.

**Revisão de 08/09/2026:** redesign solicitado após a primeira versão. A fase 8 foi ampliada em cinco entregas de design e implementação, com wireframes, tokens, acessibilidade, testes e impactos no empacotamento. O redesign foi implementado no side panel; o gate real do portal permanece separado e pendente.

## 1. Decisões confirmadas e limites

| Tema | Comportamento acordado |
|---|---|
| Redação | Não exigir identidade literal entre resolução e catálogo. |
| EC 41 | Art. 6º ou art. 7º da EC 41/2003 identifica operacionalmente a família EC41; art. 7º isolado foi explicitamente aceito pelo usuário. |
| Variante de professor | Selecionar a variante com art. 40, § 5º somente se essa referência constar na resolução; caso contrário, selecionar a variante sem ela. Cargo de professor não substitui essa evidência. |
| EC 47 | Art. 3º da EC 47/2005 identifica a terceira opção citada. |
| Outras opções | Utilizar a opção de maior semelhança, inclusive sem equivalência jurídica completa, conforme preferência expressa do usuário. Registrar método, pontuação e motivos; isso não prova correção jurídica. |
| Empates e contradições | Não escolher por posição no catálogo: registrar pendência. Opção explicitamente contraditória não compete. Sem qualquer correspondência, registrar pendência. |
| Abrangência | Todos os processos disponíveis em Meus Processos Eletrônicos, no setor atual; não apenas a primeira página. |
| Dados insuficientes | Registrar e seguir ao próximo ato; não iniciar coleta externa implicitamente. |
| Divergência existente | Pular o ato e registrar os valores; não substituir automaticamente. |
| Campos | Apenas modalidade, fundamento legal, data DOE, cargo, matrícula, nascimento e gênero. |
| Envio | O usuário inicia o lote uma vez; os atos elegíveis são enviados sem confirmação individual. |
| Relatório | Pasta local e painel, atualizado incrementalmente. |
| Redesign | Reorganizar visual e navegação da extensão no mesmo plano, integrando conferência, execução e histórico. |
| Falhas sistêmicas | Pausar quando não for possível persistir, identificar a tela, manter a sessão ou determinar o resultado do envio. |

### 1.1 Opções canônicas do catálogo

Preservar os rótulos do portal no relatório e obter seus `value` do catálogo em cada formulário; não fixar índices nem IDs numéricos de opções.

1. **EC41_SEM_P5:** Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 2º da Emenda Constitucional nº 47/2005
2. **EC41_COM_P5:** Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 40, § 5º, Constituição Federal e artigo 2º da Emenda Constitucional nº 47/2005
3. **EC47_ART3:** Civil - Artigo 3º, incisos I a III e parágrafo único, da Emenda Constitucional nº 47/2005

### 1.2 Defaults de implementação explicitados

- A fila representa um retrato de todas as páginas no início da execução. Novos processos entram na próxima execução.
- Mais de um interessado: criar um item por interessado que tenha correspondência local inequívoca; homônimos sem identificador desambiguador geram pendência.
- Resolução faltante, ilegível, incompleta ou com identificação incerta nunca será interpretada como “não cita § 5º”.
- Se as referências centrais apontarem simultaneamente para famílias diferentes, gerar pendência; não resolver conflito pela frequência das três opções.
- Matrícula e gênero ausentes podem permanecer vazios se o portal não os exigir; fundamento é obrigatório para o automático, mesmo sem asterisco no portal. Demais obrigatoriedades são a união dos quatro campos marcados obrigatórios observados e das validações atuais da tela.
- Documento mais recente não substitui automaticamente outro apenas pela data. Múltiplas resoluções materialmente divergentes exigem identificar o ato vigente; sem evidência de substituição, pendência.
- Não alterar conclusão de análise, valores financeiros, distribuição, informações processuais ou outros atos administrativos.
- Fechar o painel não cancela um passo já despachado; a execução pertence ao worker e ao serviço. Reinício do navegador ou do serviço restaura a execução pausada.
- O recurso automatiza transcrição e seleção conforme regras operacionais fornecidas; não decide concessão, aprovação ou elegibilidade previdenciária.

## 2. Base de código e evidências verificadas

Raiz: `C:\Users\slvma\Downloads\Github\Complementação de Atos`.

Convenções de caminhos neste plano:

- **E** = `work/tce-extractor/portable/extensao-complementar-ato`
- **A** = `work/tce-extractor/portable/app`
- **P** = `work/tce-extractor`
- São abreviações documentais; os comandos usam caminhos concretos.

| Arquivo existente | Responsabilidade / ponto de integração |
|---|---|
| `P/tce_extractor.py` | `_narrative_evidence` extrai o trecho introduzido por “nos termos”/“com fundamento”; pode não representar toda a resolução. |
| `A/analysis_pipeline.py` | Classificação local, OCR seletivo, caches e publicação de artefatos; `write_visual_evidence` já relaciona documentos, hashes e páginas. |
| `A/extension_exporter.py` | Exporta sete campos; esquema fechado, rejeição de conteúdo inseguro e limite de 512 caracteres por valor. |
| `E/lib/schema.js` | Dataset versão 1, chaves exatas, sete campos permitidos. Não inserir contexto jurídico extra sem contrato separado. |
| `E/lib/normalizer.js` | `normalizeLegalText` e `extractLegalSignals`; sinais atuais consideram primeiro artigo/parágrafo e não uma árvore de referências. |
| `E/lib/matcher.js` | `rankPortalOptions`; pontuação por sinais e Dice, fallback atual pode devolver opção mesmo sem sinal positivo. |
| `E/background/service-worker.js` | `createServiceWorker`, `getMatch`, registro de frames e encaminhamento; `getMatch` atualmente passa `hints: {}`. |
| `E/content/form-detector.js` | `getFormSnapshot`, `applyFields`, `overrideField`, `installContentScript`; registro inicial depende de formulário completo. |
| `E/lib/messages.js` | Mensagens tipadas e validação de payload; ampliar sem permitir comandos genéricos ou JavaScript arbitrário. |
| `E/sidepanel/panel.js` | `fillAvailableFields`, `requestComplementarAto`; preenchimento e sinalização manuais. |
| `E/sidepanel/panel.html` e `panel.css` | Painel linear com configuração antes da prévia; tabela de seis colunas com `min-width:42rem` e rolagem horizontal; redesign detalhado na fase 8. |
| `E/lib/bridge-client.js` | Cliente autenticado loopback, portas 18743–18752, timeout e validação de envelopes. |
| `A/local_service.py` | `_WorkflowHTTPServer`, `_WorkflowHandler`, `create_server`; servidor multithread e autenticação existente. |
| `A/workflow_state.py` | `WorkflowState`; `progresso.json`, `ordem-portal.json`, revisões e escrita atômica. `completed` não é comprovante de envio. |
| `P/empacotar-extensao-complementar-ato.ps1` | Allowlist explícita de 11 arquivos; qualquer módulo novo precisa entrar na lista e no teste. |
| `P/test_extension_zip_packager.py` | Verifica conjunto exato de entradas e CRC do ZIP. |

### 2.1 Fragilidades observadas, ainda sem reprodução dos casos relatados

1. Ranking genérico permite sugestão de pontuação zero e desempate pela ordem.
2. Comparação não preserva associação completa artigo → parágrafo → diploma.
3. `extractDiplomas` devolve prefixos `ec`/`ece`, enquanto `diplomaIdentity` trabalha sobre normalização e colapsa famílias estaduais/federais. Testar esse contrato antes de reutilizá-lo.
4. O sinal `tce:complementar-ato` não equivale a clique nem a gravação. Testes existentes garantem justamente a ausência de ação final.
5. Worker descobre formulário, mas listagem, seletor de interessado e frame de botões precisam de reconhecimento próprio.
6. Marcas de revisão/progresso existentes não distinguem preparado, tentado e confirmado.

### 2.2 Inspeção manual já realizada na sessão

- Sessão autenticada: 170 processos, 20 por página, 9 páginas. Esses números são um snapshot, nunca constantes.
- Fluxo observado: Meus Processos Eletrônicos → Complementar Ato → rádio do interessado → formulário.
- Lista com `tbproc01`; seleção com `PessoasAssocicadas`; formulário com `tbcomplementarato`.
- Formulário em `SISTEMAS/PROCESSO/ComplementarAto.asp`; botões em frame separado `botoesNovo.asp`.
- Botão final: texto “Complementar Ato”, ID não exclusivo `botao`. Não localizar pelo ID sozinho.
- Três opções canônicas confirmadas; catálogo inclui também art. 6º-A e outras regras.
- Navegador devolvido à lista. Nenhum dado preenchido, nenhuma complementação enviada.
- **Não observado:** confirmação real de gravação, mensagens de validação após envio e identificador persistente do ato. A fase 9 contém o procedimento para obter essas evidências sem inventar seletores de sucesso.
- Baseline executada na sessão: `npm test`, 124 testes, 124 aprovados, 0 falhas. Reexecutar no início da implementação, porque o código pode mudar.

## 3. Ordem, dependências e entregas

| Fase | Entrega | Depende de | Pode liberar isoladamente? |
|---|---|---|---|
| 0 | Baseline, fixtures e matriz de rastreabilidade | — | Documentação/testes |
| 1 | Contexto documental verificável | 0 | Sim, sem envio |
| 2 | Novo resolvedor de fundamento | 1 | Sim, modo manual |
| 3 | Diário durável e projeção de relatórios | 0 | Sim, sem portal |
| 4 | API/cliente de automação | 1, 3 | Sim, contrato local |
| 5 | Navegação e formação da fila | 0, 4 | Sim, simulação |
| 6 | Validação e preenchimento automático | 2, 5 | Sim, sem envio |
| 7 | Envio único, confirmação e recuperação | 3, 4, 6 | Apenas no simulador até fase 9 |
| 8 | Redesign completo: Ato atual, Execução, Histórico e configurações | 4–7; especificação visual pode começar após 0 | Com envio real ainda bloqueado |
| 9 | Qualificação real e regressão | 1–8 | Gate de liberação |
| 10 | Pacotes, documentação e entrega | 9 | Release |

Fases 1/2 e 3 podem ser desenvolvidas em paralelo com proprietários distintos. Integrar mudanças compartilhadas em `service-worker.js`, `local_service.py`, `messages.js` e no painel sequencialmente. Não distribuir esses arquivos a dois executores simultâneos.

## 4. Contratos novos compartilhados

Os nomes e estruturas desta seção são o contrato da implementação futura. Datas de eventos: UTC ISO 8601; exibição local no painel. Chaves de processo seguem normalização atual. Nunca identificar interessado pelo texto completo da linha que contém CPF.

### 4.1 Contexto jurídico separado do dataset v1

Novo sidecar privado `fundamentos-contexto.v1.json`, publicado junto à revisão do dataset, sem alterar o formato estrito dos sete campos.

```typescript
type Citation = { document_id: string; event_id: string; page: number; pdf_sha256: string };
type LegalContext = {
  schema_version: 1;
  process_key: string;
  interested_normalized: string;
  dataset_sha256: string;
  resolution_status: 'complete' | 'missing' | 'incomplete' | 'conflict';
  pages: Array<{ text: string; citation: Citation }>;
  operative_text: string;
  extraction_version: string;
};
type LegalReference = {
  norm: 'CF' | 'EC' | 'ECE' | 'LC' | 'LCE' | 'LEI' | 'OUTRA';
  number: string | null;
  year: string | null;
  article: string;
  paragraphs: string[];
  incisos: string[];
  alineas: string[];
};
type LegalDecision = {
  status: 'selected' | 'pending';
  method: 'exact' | 'rule' | 'similarity' | 'none';
  rule_id: 'EC41_SEM_P5' | 'EC41_COM_P5' | 'EC47_ART3' | null;
  option_value: string | null;
  option_label: string | null;
  score: number;
  reasons: string[];
  candidates: Array<{value: string; label: string; score: number; excluded_reason: string | null}>;
  citations: Citation[];
};
```

`complete` exige todas as páginas da resolução selecionada extraídas com sucesso, fonte e interessado vinculados, trecho operativo identificado e ausência de conflito. Não certificar completude por comprimento de string. Texto de referência histórica ou de ato revogado não aciona regra; associação duvidosa gera `incomplete`/`conflict`. Hash ou revisão de contexto diferente do dataset impede automático.

### 4.2 Execução, eventos e comando

```typescript
type RunStatus = 'discovering' | 'running' | 'paused' | 'stopped' | 'completed';
type ItemState = 'queued' | 'prepared' | 'filled' | 'send_intent'
  | 'confirmed' | 'pending' | 'failed' | 'unconfirmed';
type Identity = { process_key: string; interested_normalized: string; portal_act_id: string | null };
type RunSpec = { tab_id: number; sector: string; dataset_sha256: string; rules_version: string };
type RunItem = { item_id: string; ordinal: number; identity: Identity; state: ItemState };
type EventInput = {
  event_id: string; expected_revision: number; item_id: string | null;
  type: string; payload: Record<string, unknown>;
};
type RunSnapshot = {
  run_id: string; revision: number; status: RunStatus;
  items: RunItem[]; last_confirmed_item_id: string | null;
};
type Command = {
  command_id: string; run_id: string; item_id: string;
  kind: 'send'; expected_identity: Identity; expected_fields_hash: string;
  frame_generation: string; expires_at: string;
};
```

`payload` é discriminado por `type` e validado com chaves explícitas no backend; não persistir objetos arbitrários recebidos da página. Eventos aceitos: `queue_frozen`, `item_prepared`, `fields_verified`, `send_intent`, `send_confirmed`, `item_pending`, `item_failed`, `send_unconfirmed`, `run_paused`, `run_resumed`, `run_stopped`, `run_completed`. `send_intent` armazena o comando e o hash dos campos antes de habilitar qualquer clique.

Não prometer exactly-once distribuído: o portal não oferece contrato de idempotência conhecido. A garantia local é não reemitir automaticamente um comando consumido ou de consumo incerto; situações de resultado incerto exigem conciliação de leitura. Intenção expirada comprovadamente nunca consumida pode ser encerrada como `item_pending` e voltar a preparação somente na retomada explícita, com novo comando e vínculo ao anterior.

## 5. Fase 0 — baseline e casos de regressão

**Arquivos:** ampliar `E/tests/matcher.test.mjs`, `E/tests/normalizer.test.mjs`; criar `P/tests/fixtures/legal-foundations.json` e `P/tests/fixtures/automatic-portal/` com HTML sanitizado. Atualizar handoff deste escopo.

- [ ] Registrar `git status`, HEAD, remoto e versões Node/Python disponíveis; trabalhar em `codex/fundamentacao-automatico` na implementação, preservando alterações anteriores.
- [ ] Executar baseline JS e testes Python de extração/exportação/serviço; guardar contagens resumidas.
- [ ] Montar catálogo sintético com as três opções, art. 6º-A, CF art. 40 § 1º II, opção militar e placeholder.
- [ ] Reproduzir erro concreto do matcher atual com texto abreviado; assertar a opção esperada, não apenas pontuação.
- [ ] Inspecionar amostra local de resoluções por família, sem modificar PDFs ou publicar nomes; montar fixtures sintéticas representativas. Se não houver exemplo real de uma família, documentar essa lacuna na matriz de QA.
- [ ] Criar fixtures distintas para lista paginada, pessoas, formulário, botões e resultado no simulador. Sucesso simulado deve ser identificado como simulado.

Exemplo de regressão a adicionar ao teste existente:

```javascript
test('não oferece uma opção sem sinal positivo', () => {
  const result = rankPortalOptions({
    field: 'fundamento_legal', documentaryValue: 'texto sem referências',
    options: [{value: 'x', label: 'Artigo 40, § 1º, II, Constituição Federal'}],
  });
  assert.equal(result.optionValue, null);
});
```

Comando: em E, `node --test tests/matcher.test.mjs tests/normalizer.test.mjs`. RED deve demonstrar escolha indevida; erro de importação/configuração não substitui reprodução comportamental.

**Aceite:** baseline documentada, pelo menos uma regressão real do comportamento reproduzida, nenhuma ação final no portal. Commit sugerido: `test: reproduce legal foundation selection failures`.

## 6. Fase 1 — contexto documental completo e compatível

**Criar:** `A/legal_context.py`, `P/test_legal_context.py`.
**Alterar:** `A/analysis_pipeline.py`; `P/tce_extractor.py` somente se a reprodução revelar truncamento na extração; `P/test_analysis_pipeline.py`, `P/test_tce_extractor.py` e testes de publicação integrada.

**Interface nova:** `build_legal_contexts(manifest: dict, checkpoint: dict, page_texts: dict, dataset_sha256: str) -> dict`; `write_legal_contexts(path: Path, contexts: dict) -> None`. Sidecar contém `schema_version`, `dataset_sha256`, `records` de `LegalContext`.

- [ ] Escrever testes de resolução multipágina, trecho com “ambos”, fonte errada, duas resoluções divergentes, OCR falho e hash de PDF incompatível.
- [ ] Confirmar RED com caso em que o trecho extraído omite § 5º presente na parte operativa.
- [ ] Reutilizar textos/cache do pipeline; não rodar OCR no GET HTTP nem durante cada seleção do painel.
- [ ] Separar texto completo de evidência e trecho operativo para classificação. Preservar citações por página, sem cortar silenciosamente em 512 caracteres.
- [ ] Publicar sidecar atomicamente na mesma geração de artefatos; somente anunciar revisão após todos os arquivos estarem consistentes.
- [ ] Dataset v1 e exportador continuam aceitando apenas os sete campos. Contexto ausente mantém modo manual, mas bloqueia envio automático do respectivo ato.
- [ ] Atualizar versão de cache quando a lógica mudar e recomputar apenas os documentos afetados.

Exemplo de teste do contrato:

```python
def test_failed_page_does_not_mean_paragraph_absent(self):
    contexts = build_legal_contexts(self.manifest, self.checkpoint,
                                   self.pages_with_second_page_failed, 'a' * 64)
    self.assertEqual(contexts['records'][0]['resolution_status'], 'incomplete')
```

Os objetos do fixture acima devem ser construídos no `setUp` com um processo sintético e resolução de duas páginas; a segunda tem falha explícita, sem texto substituto.

Comando em P: `python -m unittest test_legal_context test_tce_extractor test_analysis_pipeline test_extension_exporter -q`.

**Aceite:** resolução inteira disponível com vínculo verificável; ausência de contexto nunca promove elegibilidade; v1 permanece compatível. Commit: `feat: publish versioned legal evidence context`.

## 7. Fase 2 — resolvedor específico de fundamento

**Criar:** `E/lib/legal-foundation.js`, `E/tests/legal-foundation.test.mjs`.
**Alterar:** `E/lib/matcher.js`, `E/lib/normalizer.js`, respectivos testes; integração em `E/background/service-worker.js` e `E/sidepanel/panel.js` após fase 4.

**Interfaces:** `parseLegalReferences(text) -> LegalReference[]`; `resolveLegalFoundation({context, options}) -> LegalDecision`. `rankPortalOptions` mantém formato legado para modalidade e adapta fundamento para a estrutura antiga acrescida de `legalDecision`; testar consumidores do novo estado pendente.

### 7.1 Parsing e precedência

- [ ] Testar e implementar normalização de EC/ECE, CF, ordinais, algarismos romanos, “I a IV”, “parágrafo único”, “ambos”, “c/c”, “combinado com”, artigos com sufixo A e referências em ordem invertida.
- [ ] Não colapsar constituição estadual com federal, nem EC com ECE. Ano explícito divergente é contradição; ano ausente é informação incompleta, não divergência automática.
- [ ] Excluir placeholder e opções sem valor selecionável.
- [ ] Aplicar equivalência estrutural completa primeiro, exceto quando conflitar com a política específica de § 5º. Depois, regras operacionais; depois, semelhança.
- [ ] Regra EC41 aceita art. 6º ou 7º vinculado à EC 41/2003. Art. 6º-A não participa. EC47_ART3 exige art. 3º vinculado à EC 47/2005. Número solto não aciona essas regras.
- [ ] Dentro da família EC41, CF art. 40 § 5º deve estar no trecho operativo da resolução; menção histórica ou § 5º de outra norma não ativa a variante.
- [ ] Uma regra sem opção correspondente no catálogo resulta em pendência; não mudar silenciosamente para outra família.

### 7.2 Ranking residual fixado

Para opções restantes, comparar o trecho operativo com o rótulo normalizado: `score = 40 * referências completas coincidentes + 25 * diplomas coincidentes + 10 * artigos coincidentes + 5 * qualificadores coincidentes + Dice`, com `Dice` entre 0 e 10. Contar cada sinal único uma vez. Qualificadores: incisos, parágrafos e alíneas ligados à mesma referência. Coincidência de referência não pode ser montada juntando artigo de uma norma com diploma de outra.

- [ ] Excluir contradição explícita do mesmo dispositivo: norma/ano diferente, inciso ou parágrafo incompatível quando ambos explicitam o mesmo papel. Não considerar toda referência extra uma contradição.
- [ ] Maior score estritamente positivo e único pode ser aplicado automaticamente, sem limiar mínimo adicional, conforme preferência do usuário.
- [ ] Zero ou empate resulta em `pending`, `option_value: null`. Não usar ordem do catálogo como desempate.
- [ ] Guardar ranking completo e versão da regra para auditoria; painel apresenta “por semelhança”, nunca “confirmado juridicamente”.

```javascript
test('cargo não acrescenta §5 à resolução', () => {
  const result = resolveLegalFoundation({
    context: completeContext('Art. 6º da EC 41/2003. Cargo: PROFESSOR'),
    options: canonicalOptions,
  });
  assert.equal(result.rule_id, 'EC41_SEM_P5');
});
```

Definir `completeContext(text)` no próprio teste retornando todos os campos de `LegalContext` com documento sintético de uma página; `canonicalOptions` vem do fixture da fase 0.

**Casos obrigatórios adicionais:** art. 7º isolado; art. 6º + art. 40 § 5º; art. 3º EC47; art. 6º-A EC41; CF art. 40 §1º II; mesmo texto com opções reordenadas; fonte vazia; duas opções estruturalmente equivalentes; família conflitante; documento incompleto.

Comando em E: `node --test tests/legal-foundation.test.mjs tests/matcher.test.mjs tests/normalizer.test.mjs`.

**Aceite:** todas as regras cobertas; nenhum empate escolhe a primeira opção; modo manual mantém contratos de modalidade. Commit: `fix: resolve legal foundations from documentary references`.

## 8. Fase 3 — diário de execução e relatórios duráveis

**Criar:** `A/automation_store.py`, `A/automation_report.py`, `P/test_automation_store.py`, `P/test_automation_report.py`.
**Integrar posteriormente:** ciclo de vida em `A/local_service.py`, exportação/transferência em `A/prepare_transfer.py` e `A/package_audit.py`.

### 8.1 Persistência

Banco privado: `<workflow_root>/automacao/execucoes.sqlite3`. Relatórios: `<workflow_root>/relatorios/complementacao/<run_id>/relatorio.html` e `relatorio.csv`. Não colocar esses dados em `docs/`.

**Interfaces:** `AutomationStore(root: Path)`; `create_run(spec: dict) -> dict`; `freeze_queue(run_id: str, identities: list[dict], event_id: str, expected_revision: int) -> dict`; `append_event(run_id: str, event: dict) -> dict`; `snapshot(run_id: str) -> dict`; `get_events(run_id: str, after: int = 0) -> list[dict]`; `close() -> None`.

Na fase 7, acrescentar `consume_command(run_id: str, command_id: str, expected_revision: int) -> dict`. Consumo usa compare-and-set transacional de `issued` para `consumed`, incrementa revisão e grava evento `command_consumed`. Resposta de sucesso contém `dispatch_allowed: true` apenas na primeira chamada; qualquer repetição retorna 409 `COMMAND_ALREADY_CONSUMED`, mesmo se o primeiro ACK tiver sido perdido. Esse endpoint é deliberadamente diferente da repetição idempotente de eventos: reenviar evento pode confirmar persistência, mas nunca reautoriza clique.

Tabelas: `runs` (spec, status, revision, timestamps), `items` (identidade, ordinal, estado), `events` (run_id, seq, event_id, tipo, payload, timestamp), `commands` (command_id único, item_id, estado de intenção e consumo), `confirmed_acts` (identidade, hash dos dados, evento confirmador). `event_id` único global; `run_id + seq` único; `run_id + ordinal` único.

- [ ] Testar antes de implementar: reinício, revisão obsoleta, evento repetido, payload diferente com mesmo ID, transição inválida e duas execuções concorrentes.
- [ ] Configurar SQLite `journal_mode=DELETE`, `synchronous=FULL`, `foreign_keys=ON`, `busy_timeout=5000`. Usar conexão por operação com transação `BEGIN IMMEDIATE`, compatível com HTTP multithread. Rollback não pode avançar estado em memória.
- [ ] Persistir evento e projeção de estado na mesma transação. Mesmo `event_id` e payload devolve resultado anterior; payload diferente devolve conflito.
- [ ] Uma execução ativa por raiz do acervo; impedir corrida no banco, não apenas por variável JS.
- [ ] Ao iniciar serviço, qualquer execução `running`/`discovering` vira pausada; item com `send_intent` sem confirmação vira `unconfirmed`.
- [ ] Não migrar `progresso.json.completed=true` para `confirmed`. Marcas antigas continuam com significado anterior.

```python
def test_intent_survives_restart_as_unconfirmed(self):
    run, item = self.seed_filled_item()
    self.store.append_event(run['run_id'], self.send_intent(item, run['revision']))
    self.store.close()
    reopened = AutomationStore(self.root)
    snapshot = reopened.snapshot(run['run_id'])
    self.assertEqual(snapshot['status'], 'paused')
    self.assertEqual(snapshot['items'][0]['state'], 'unconfirmed')
```

Helpers do teste devem preparar transições reais `queue_frozen → item_prepared → fields_verified`, sem escrever diretamente tabelas para contornar validação.

### 8.2 Projeções legíveis

**Interface:** `render_run_reports(store: AutomationStore, run_id: str, output_root: Path) -> dict` retorna caminhos relativos e revisão renderizada.

- [ ] Registrar valores antes/depois, valores realmente relidos, decisão jurídica, citações, início/fim, erros, último confirmado e item interrompido.
- [ ] Relatório HTML com totais e detalhes por ato; CSV com uma linha por ato/campo, incluindo método e origem. Ordenação por fila, histórico por sequência.
- [ ] Escapar HTML e neutralizar células CSV iniciadas por `=`, `+`, `-`, `@`, tabulação e retorno. Testar nomes/textos maliciosos sem alterar o original no banco.
- [ ] Gerar arquivos temporários, flush, fsync e `os.replace`; falha na renderização preserva relatório anterior e banco atualizado.
- [ ] Renderizar após cada transição, antes de avançar a outro ato. Falha de projeção pausa e exibe revisão do último relatório; regeneração é idempotente.
- [ ] Excluir tokens, cookies, CPF e URLs de sessão; citações usam IDs de documentos e páginas, não caminhos arbitrários.

Comando em P: `python -m unittest test_automation_store test_automation_report -q`.

**Aceite:** crash e concorrência não perdem eventos confirmados; HTML/CSV podem ser reconstruídos do banco; integridade SQLite verificada no teste. Commit: `feat: persist automation events and incremental reports`.

## 9. Fase 4 — API local e compatibilidade da extensão

**Alterar:** `A/local_service.py`, `E/lib/bridge-client.js`, `E/lib/messages.js`, `E/background/service-worker.js`; testes existentes correspondentes.
**Criar:** `P/test_automation_api.py`, `E/lib/automation-schema.js`, `E/tests/automation-schema.test.mjs`.

Todas as rotas reutilizam autenticação existente e loopback. Respostas JSON: `{api_version: 1, ...}`. Erros: `{error: {code, message}}`. Chaves extras rejeitadas. Sem endpoint para executar script, abrir caminho ou requisitar URL arbitrária.

| Método e rota nova | Entrada / saída |
|---|---|
| `GET /api/v1/automation/capabilities` | `{automation_schema:1, legal_context_schema:1, rules_version, real_send_enabled}` |
| `GET /api/v1/legal-context?process_key=...&interested_normalized=...` | `{context: LegalContext}` ou erro tipado |
| `POST /api/v1/automation/runs` | `RunSpec` + `event_id`; retorna `RunSnapshot` |
| `POST /api/v1/automation/runs/<id>/queue` | `{identities,event_id,expected_revision}`; congela fila |
| `GET /api/v1/automation/runs/<id>` | snapshot, revisão e links relativos de relatório |
| `POST /api/v1/automation/runs/<id>/events` | `EventInput`; devolve revisão persistida |
| `POST /api/v1/automation/runs/<id>/commands/<command_id>/consume` | `{expected_revision}`; consumo único, resposta `{api_version:1,revision,dispatch_allowed:true}` ou 409 |
| `POST /api/v1/automation/runs/<id>/control` | `{action:'pause'|'resume'|'stop',event_id,expected_revision}` |
| `GET /api/v1/automation/runs/<id>/report?format=html|csv` | arquivo derivado, sem aceitar path do cliente |

Métodos do bridge client: `getAutomationCapabilities()`, `getLegalContext(identity)`, `createAutomationRun(spec,eventId)`, `freezeAutomationQueue(runId,body)`, `getAutomationRun(runId)`, `appendAutomationEvent(runId,event)`, `controlAutomationRun(runId,body)`.

Acrescentar `consumeAutomationCommand(runId,commandId,expectedRevision)` na fase 7. O content script pede `AUTO_CONSUME_COMMAND` ao worker; o worker valida `sender.tab.id`, `sender.frameId`, papel `buttons`, geração e execução antes de chamar a API. Token local nunca é enviado ao DOM. Acrescentar o evento `command_consumed` à enumeração da seção 4.2 ao implementar o schema; payload contém apenas `command_id` e identificação da geração autorizada.

- [ ] RED para chamadas sem token, origem inadequada, revisão obsoleta, dataset trocado e payload extra.
- [ ] Backend calcula hashes e valida identidade contra dataset/contexto; não confiar no hash declarado isoladamente pelo cliente.
- [ ] Acrescentar limite de corpo de 2 MiB e lote de no máximo 10.000 identidades; excesso devolve erro e mantém estado anterior. Contexto acima do limite gera pendência, sem truncar texto silenciosamente.
- [ ] Proteger rotas de relatório como demais dados privados; painel baixa via requisição autenticada e Blob, sem token em query string.
- [ ] Cliente antigo continua funcionando. Cliente novo com serviço antigo mantém manual e explica indisponibilidade do automático.
- [ ] Integrar contexto ao `getMatch` sem alterar schema v1; cache por processo/interessado/hash/regras. Mudança de revisão invalida cache.
- [ ] A API de `health` anuncia capacidades sem dados privados; contexto e operações exigem token. Raiz do serviço é vinculada ao acervo atual: não aceitar `workflow_root` ou caminho de relatório vindo do cliente.
- [ ] Novas mensagens do painel: `AUTO_START`, `AUTO_PAUSE`, `AUTO_RESUME`, `AUTO_STOP`, `AUTO_STATUS`. Somente páginas da extensão podem iniciar/controlar lote.

Teste representativo: POST de evento idêntico duas vezes aumenta revisão uma vez; mesmo ID com dados diferentes devolve 409. GET de contexto de outro interessado não retorna o primeiro registro encontrado.

Comandos: em P, `python -m unittest test_automation_api test_local_service test_bridge_auth -q`; em E, `node --test tests/automation-schema.test.mjs tests/bridge-client.test.mjs tests/service-worker.test.mjs`.

**Aceite:** contratos autenticados, compatibilidade v1 e idempotência local comprovados. Commit: `feat: expose authenticated automation API`.

### 9.1 Incidente de conexão observado no pacote portátil

- [ ] Reproduzir no pacote portátil real: `INICIAR.cmd` inicia o serviço e
  exibe um código de pareamento, mas a extensão permanece desconectada após o
  código ser inserido.
- [ ] Capturar, em fixture/teste local, a sequência completa
  `INICIAR.cmd` → `service.json`/código → `POST /api/v1/pair` → primeira
  chamada autenticada (`capabilities`), registrando status HTTP e erro tipado
  sem expor o código.
- [ ] Verificar a corrida entre o launcher oculto e a criação de
  `dados-locais/bridge/service.json`, a reutilização de um processo existente,
  expiração/consumo único do código, `Origin` da extensão e o token emitido.
- [ ] Corrigir a causa e adicionar uma regressão que prove que, após o
  pareamento, a extensão mostra conexão ativa e consegue consultar
  `capabilities`; manter fallback manual quando o serviço não estiver
  disponível.

**Gate do incidente:** não considerar o pareamento concluído apenas porque o
  código apareceu ou foi aceito pelo formulário; a conexão só passa com uma
  resposta autenticada válida de `capabilities` e teste automatizado da mesma
  sequência.

## 10. Fase 5 — navegação, frames e descoberta da fila

**Criar:** `E/content/portal-navigation.js`, `E/tests/portal-navigation.test.mjs`, `E/background/automation-controller.js`, `E/tests/automation-controller.test.mjs`.
**Alterar:** manifest, worker e messages; estender fixtures da fase 0.

O novo content script deve seguir o padrão clássico/CommonJS testável do `form-detector.js`; não inserir `import` estático em script declarado no manifest. Comunicação entre módulos via mensagens validadas, sem globals compartilhados desnecessários.

**Interface DOM:** `detectPortalScreen(documentRef)` retorna `list | interested | form | buttons | unknown`; `snapshotPortalScreen(documentRef)` retorna papel, geração, setor, identidades e ações observadas. `executeNavigation(documentRef,{action,identity,expected_generation})` aceita apenas `next_page`, `open_act`, `select_interested`, `return_list`.

**Interface worker:** `createAutomationController({chromeApi, bridge, ranker, clock})` retorna `start`, `pause`, `resume`, `stop`, `status`, `handlePortalEvent`. Injetar clock e dependências para testes; nenhum loop principal pertence ao painel.

- [ ] RED com 3 páginas de 2/2/1 processos, rerender de frames e números de linhas repetidos; fila deve conter cinco processos únicos.
- [ ] Detectar lista e pessoas mesmo sem os sete sentinelas do formulário. Registrar papéis de frames em `storage.session` e invalidar geração em navegação.
- [ ] Identificar links pelo processo na linha; nunca clicar o primeiro “Complementar Ato” globalmente.
- [ ] Enumerar todas as páginas usando controles observados; guardar identidades, não nós DOM nem URLs autenticadas. Detectar página repetida sem progresso e pausar.
- [ ] Abrir cada processo para descobrir interessados; vincular por processo + nome normalizado + ID do ato quando observável. Sem dados locais, registrar item pendente.
- [ ] Congelar fila deduplicada e versão do dataset antes da primeira escrita de campo. Identidade não resolvida não some dos totais.
- [ ] Reencontrar processo na lista após cada retorno; não depender de permanecer no mesmo índice de linha ou página.
- [ ] Detectar mudança de setor, aba fechada e navegação manual; pausar. Trocar para outra aba sem mexer na aba vinculada pode deixar o lote funcionando.
- [ ] Observar DOM com MutationObserver e espera por condição; timeout de navegação 30 s. Uma nova leitura é permitida; nunca repetir clique sem antes verificar o estado resultante.

Exemplo de contrato a testar:

```javascript
test('não confunde dois links de Complementar Ato', () => {
  const doc = listFixture(['100001/2020', '100002/2020']);
  executeNavigation(doc, {action:'open_act', identity:{process_key:'100002/2020'},
                         expected_generation:'g1'});
  assert.deepEqual(clickedProcessKeys(doc), ['100002/2020']);
});
```

Helpers usam DOM falso no padrão de `form-detector.test.mjs`, atribuindo geração `g1` ao fixture.

**Aceite:** descoberta completa no simulador e leitura real sem envio; fila não duplica nem perde processos quando a lista muda. Commit: `feat: discover and navigate automatic act queue`.

## 11. Fase 6 — preparação e preenchimento verificável

**Criar:** `E/lib/automation-preflight.js`, `E/tests/automation-preflight.test.mjs`.
**Alterar:** controller, form-detector, worker, testes correspondentes.

**Interface:** `prepareAutomaticAct({record,context,snapshot,legalDecision}) -> {eligible:boolean, fields:object, preserved:object, reasons:string[], evidence:object}`.

- [ ] Testar campos vazios, preenchidos equivalentes, divergentes, disabled/readOnly, datas inválidas e opção removida.
- [ ] Validar identidade antes de cada escrita. Snapshot deve pertencer ao processo/interessado da fila e à geração atual do frame.
- [ ] Comparar selects por valor da opção atual, datas por data civil e texto com normalização conservadora. Não considerar dois cargos diferentes equivalentes por semelhança.
- [ ] Divergência em qualquer dos sete campos com valor documental proposto cancela preparação do ato inteiro antes de preencher parcialmente.
- [ ] Campos obrigatórios sem proposta nem valor existente validável geram pendência. Campo existente sem fonte suficiente para validá-lo não torna o ato automaticamente elegível.
- [ ] Persistir `item_prepared` com valores atuais, propostas, contexto/hash e decisão. Reutilizar `applyFields`, mantendo allowlist; não chamar `overrideField` no lote.
- [ ] Reler todos os valores e opções após eventos `input`/`change` e estabilização do DOM. Persistir `fields_verified` somente se correspondem ao esperado.
- [ ] Campo que mudou sozinho, identidade trocada ou catálogo atualizado exige novo preflight; não enviar com a prévia antiga.
- [ ] Uma falha após preenchimento registra `failed`, sem envio; não apagar os dados preenchidos por tentativa de rollback não comprovada.

```javascript
test('divergência impede todas as escritas do ato', () => {
  const result = prepareAutomaticAct(divergentCargoFixture());
  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.ok(result.reasons.includes('EXISTING_VALUE_CONFLICT'));
});
```

Comando em E: `node --test tests/automation-preflight.test.mjs tests/form-detector.test.mjs tests/automation-controller.test.mjs`.

**Aceite:** identidade e sete campos relidos; divergências não produzem sobrescrita; zero cliques finais nesta fase. Commit: `feat: validate and verify automatic field preparation`.

## 12. Fase 7 — envio, confirmação e retomada

**Criar:** `E/content/portal-submit.js`, `E/tests/portal-submit.test.mjs`, `P/test_automation_recovery.py`.
**Alterar:** controller, manifest, messages, store e testes de integração.

### 12.1 Máquina de estados

```text
queued -> prepared -> filled -> send_intent -> confirmed
   |          |          |           |
   +----------+----------+           +-> unconfirmed -> confirmed por conciliação
              |                      +-> failed somente com falha comprovada
              +-> pending / failed

Execução: discovering -> running -> completed
Qualquer falha sistêmica -> paused; ação do usuário -> stopped
Retomada: paused -> running somente depois de reconciliar intenções anteriores
```

**Interface:** `submitVerifiedAct({documentRef,command,verifyCurrentState,consumeCommand}) -> Promise<{dispatched:boolean,command_id:string}>`; `classifyPortalOutcome(observation,expected) -> {status:'confirmed'|'failed'|'unconfirmed', evidence:object}`.

- [x] RED para botão com ID duplicado, frame errado, comando expirado, comando duplicado, mudança de identidade entre preflight e clique e pausa solicitada antes do clique.
- [x] Backend persiste `send_intent` e comando de envio de uso único antes de liberar ação. Prazo do comando: 15 s; expirado vira item não enviado com necessidade de nova preparação, desde que consumo não tenha ocorrido.
- [x] Content script do frame de botões solicita consumo do comando ao worker, que o persiste no backend antes do clique. Uma falha entre consumo e clique continua incerta, sem repetição automática.
- [x] Revalidar identidade/campos imediatamente antes do consumo e novamente antes do clique. Frame de botões deve pertencer à mesma árvore de frames do formulário e estar visível.
- [x] Clicar apenas botão com texto exato “Complementar Ato” habilitado no papel `buttons`. Mensagem de página não pode autorizar envio. Não alterar o comportamento do sinal manual legado para que passe a enviar silenciosamente.
- [ ] Aguardar até 30 s por resultado observado; uma leitura adicional sem clique é permitida. Timeout, diálogo desconhecido, queda de rede ou perda da página geram `unconfirmed` e pausam.
- [x] Confirmar somente com sinal real de aceitação e leitura posterior dos valores persistidos para a identidade esperada. Se o portal não fornecer prova suficiente, classificar como incerto.
- [ ] Registrar confirmação durável e atualizar relatório antes de abrir o próximo ato.
- [ ] Ao retomar, conciliar `send_intent`/`unconfirmed` por leitura. Valor persistido idêntico sem evidência suficiente de gravação não prova autoria da tentativa; registrar evidência e manter incerteza quando necessário.
- [ ] Atos previamente confirmados não são reenviados, mesmo em outro lote. Alteração posterior no documento vira pendência de revisão, não autorização de edição automática.
- [ ] Pausar/encerrar após clique aguarda classificação do resultado; não tentar desfazer gravação remota.

```javascript
test('comando consumido nunca gera um segundo clique', async () => {
  const harness = submissionHarness();
  await harness.dispatchOnce();
  await assert.rejects(harness.dispatchOnce(), /COMMAND_ALREADY_CONSUMED/);
  assert.equal(harness.clickCount(), 1);
});
```

Construir harness com store falso durável e mesmo `command_id` em ambas chamadas; reiniciar controller entre chamadas em um segundo teste.

**Matriz de crash:** antes de prepared; após prepared; após preenchimento; após fields_verified; após intenção; após consumo antes do clique; após clique antes da resposta; após resposta antes do ACK local; após confirmação antes do relatório; após relatório antes de avançar.

**Aceite:** nenhuma variante da matriz causa reenvio automático; nenhuma simples navegação é classificada como sucesso. Envio real permanece desabilitado até fase 9. Commit: `feat: add auditable submission and uncertain-result recovery`.

## 13. Fase 8 — redesign completo da extensão, progresso e operação

**Alterar:** `E/sidepanel/panel.html`, `panel.js`, `panel.css`, `E/tests/panel.test.mjs`; integrar relatório no serviço sem reimplementar a mesa web inteira.

- [ ] RED para controles indisponíveis sem pareamento, serviço incompatível, execução já ativa e contexto faltante.
- [ ] Seção “Modo automático” mostra setor, total descoberto/elegível/pendente, estado, ato atual e último confirmado.
- [ ] “Iniciar” cria execução explícita; descoberta gera relatório antes do primeiro envio. Mostrar claramente que o lote complementará os atos elegíveis.
- [ ] “Pausar” impede novo comando; “Retomar” concilia o anterior; “Encerrar” preserva relatório e fila remanescente. Não usar rótulo “concluído” para encerramento parcial.
- [ ] Exibir motivo legível de pendência e fundamento original/selecionado; escolhas por semelhança têm rótulo próprio, sem exigir confirmação individual.
- [ ] Permitir abrir/baixar HTML/CSV a qualquer momento. Mostrar revisão do relatório se estiver atrasada em relação ao banco.
- [ ] Ao reabrir painel, reconstruir da API, não de variável em memória. Refresh de status a cada 2 s apenas enquanto painel aberto; worker recebe eventos e usa alarme de 30 s para detectar estagnação, sem depender de manter painel aberto.
- [ ] Adicionar permissão `alarms` no manifest; alarme nunca dispara envio por si só após reinício. Ele pausa/atualiza estado e reconcilia, sem reemitir comando consumido.
- [ ] Botões manuais de preenchimento ficam indisponíveis na aba enquanto o lote está ativo; pausa permite revisão sem reativação automática.
- [ ] Não mostrar stack traces ou tokens ao usuário; apresentar código de erro e ação possível.

Comando em E: `node --test tests/panel.test.mjs tests/service-worker.test.mjs tests/automation-controller.test.mjs`.

**Aceite:** painel fecha/reabre sem perder histórico; contagens reconciliam com itens; stop/pause são testados antes e depois do clique. Commit: `feat: add automatic mode controls and live reporting`.

### 13.1 Diagnóstico e direção visual

**Público e tarefa:** operador que confere a resolução ao lado do portal e precisa identificar rapidamente qual ato está aberto, quais dados serão usados e se houve gravação. Priorizar legibilidade de textos legais e rastreabilidade, sem transformar o painel em uma apresentação comercial.

Problemas comprovados no código atual:

- `panel.html` apresenta sete seções empilhadas. Importação, estado da tela, pareamento e pesquisa ocupam espaço antes da prévia.
- `panel.css` impõe `table {min-width:42rem}` com seis colunas. Em uma largura de 360 px, a comparação exige rolagem horizontal.
- Botões têm o mesmo peso visual, inclusive ações de configuração e ações operacionais.
- `render()` reescreve incondicionalmente “A extensão não conclui o ato”; essa frase será falsa no novo modo automático.
- `renderRows()` produz linhas/células; o redesign requer trocar a estrutura sem perder fontes, estados, divergências e ação manual de substituição.
- O painel depende de `ELEMENT_IDS` e dos fixtures em `panel.test.mjs`. Trocar HTML sem adaptar contrato/renderização/testes quebrará a inicialização.

Alternativas consideradas: (1) apenas recolorir a tabela preserva o problema de largura; (2) dashboard com muitos cartões dificulta leitura das referências; (3) painel documental com três áreas de trabalho separa tarefas e mantém identidade sempre visível. Adotar a alternativa 3.

**Identidade escolhida:** superfícies claras, cabeçalho azul-petróleo contido, texto grafite, divisores suaves e cores semânticas de estado. Elemento característico: trilha de evidência da fundamentação — **Resolução → Regra aplicada → Opção no portal** — que torna a escolha auditável sem exigir abrir configurações.

Proposta usa tema claro único nesta versão; sem seletor de temas, bibliotecas de UI, fontes remotas, gráficos decorativos ou imagens geradas. Não é redesenho do portal do TCE nem da mesa web completa. O relatório HTML compartilha tokens visuais e terminologia, mantendo formato próprio para impressão.

### 13.2 Sistema visual e comportamento responsivo

**Criar:** `E/sidepanel/panel-tokens.css`, `E/sidepanel/panel-view.js` e `E/tests/panel-view.test.mjs`. **Alterar:** `panel.html`, `panel.css`, `panel.js`, `panel.test.mjs`; os módulos de operações continuam fora da renderização.

Tokens propostos, a implementar em CSS custom properties:

```css
:root {
  --surface-canvas: #f2f5f7;
  --surface-panel: #ffffff;
  --text-primary: #182b36;
  --text-secondary: #526572;
  --accent-primary: #145b6b;
  --line-subtle: #ccd7de;
  --status-success: #176343;
  --status-attention: #875300;
  --status-error: #a52b35;
  --focus-ring: #075fc6;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --radius-control: 6px;
  --radius-panel: 10px;
}
```

- Tipografia local: títulos em `"Segoe UI Variable Display", "Segoe UI", sans-serif`; corpo em `"Segoe UI", system-ui, sans-serif`; números de processo e horários com `"Cascadia Mono", Consolas, monospace`. Usar fallbacks, sem baixar fontes.
- Escala: título 20/26 px, seção 16/22 px, corpo 14/21 px, legenda 12/18 px. Fundamentação permanece em corpo 14 px; não diminuir fonte para caber.
- Layout de uma coluna de 320 a 479 px; a partir de 480 px, comparação dentro de cada campo pode usar duas colunas. Nunca retomar seis colunas no side panel.
- Documento original e opção proposta ficam empilhados em larguras estreitas e lado a lado apenas quando houver espaço. Referências completas quebram linha; não truncar conteúdo indispensável em reticências.
- Controles com pelo menos 40 px de altura, ações primárias com 44 px, foco visível de 2 px + offset. Medir contraste texto/fundo >= 4,5:1 e controles/foco >= 3:1 antes de aprovar; os hex acima são proposta, não validação já realizada.
- Cabeçalho de identidade e barra de ação contextual no topo, no fluxo sticky. Na aba Ato atual, colocar “Preencher campos disponíveis” e a indicação do modo manual logo abaixo das abas, antes da fundamentação e dos dados, conforme ajuste solicitado pelo usuário. Não duplicar a ação no rodapé. Reservar espaço e `scroll-padding` para não cobrir controles focados; com viewport baixo ou zoom alto, permitir que o conjunto superior volte ao fluxo normal.
- Estado representado por texto e ícone SVG local/inline, com cor complementar. Ícones decorativos têm `aria-hidden`; botões de ícone precisam de nome acessível. Não usar emoji como único indicador.
- Transições discretas de até 120 ms; respeitar `prefers-reduced-motion`. Sem animação contínua, confete ou barra que simule avanço não medido.

### 13.3 Arquitetura de informação e wireframes

Cabeçalho compartilhado: nome “Complementar Ato”, estado da conexão, acesso “Configurações”. Abaixo, processo e nome completos do interessado. Esses dados correspondem à aba vinculada; busca manual nunca os substitui como se mudasse a seleção real.

Navegação por tabs acessíveis: **Ato atual | Execução | Histórico**. Guardar tab selecionada em `chrome.storage.local` com chave nova `panel:view:v1`; reabrir painel restaura a preferência, mas problemas críticos aparecem em banner comum. Sem troca automática de tab a cada processo.

```text
ATO ATUAL — exemplo sintético em 360 px
┌─────────────────────────────────────┐
│ Complementar Ato    Conectado   ⚙   │
│ 100001/2020                         │
│ Interessado de exemplo              │
├─────────────────────────────────────┤
│ Ato atual | Execução | Histórico    │
├─────────────────────────────────────┤
│ [Preencher campos disponíveis]     │
│ Modo manual: preenche para revisão │
├─────────────────────────────────────┤
│ Fundamentação             Por regra│
│ Resolução                          │
│ Art. 6º da EC 41/2003 ...           │
│ Documento · página 2   [Ver fonte] │
│ Regra aplicada                     │
│ EC41 — sem referência ao § 5º      │
│ Opção no portal                    │
│ Civil - Artigo 6º, incisos I a IV… │
│ [Expandir referências completas]   │
├─────────────────────────────────────┤
│ Dados do ato         6 de 7 prontos│
│ Cargo                   Divergente │
│ Documento: PROFESSOR               │
│ Portal: valor existente            │
│ [Ver fonte] [Revisar divergência]  │
│ Outros campos…                     │
└─────────────────────────────────────┘
```

O wireframe abrevia texto apenas para caber no desenho. Na implementação, referências ficam integralmente disponíveis e a opção selecionada nunca perde artigos por corte silencioso. “Ver fonte” abre a evidência existente no serviço/mesa; fonte indisponível mostra motivo e citação textual, sem inventar URL de PDF.

```text
EXECUÇÃO
┌─────────────────────────────────────┐
│ Lote em andamento                  │
│ 18 analisados de 40                │
│ 15 confirmados · 3 pendentes       │
│ ━━━━━━━━━━━━━░░░░░░░░░░░░░░░      │
│ Agora: 100019/2020                 │
│ Preenchido → Aguardando confirmação│
│ Último confirmado: 100018/2020     │
│ [Pausar]  [Encerrar execução]      │
│ [Ver relatório parcial]           │
│ Pendências do lote                │
│ 100004/2020 · Cargo divergente     │
└─────────────────────────────────────┘

HISTÓRICO
┌─────────────────────────────────────┐
│ Execuções                          │
│ 08/09 14:20 · Pausada              │
│ 15 confirmados · 3 pendentes       │
│ [Abrir detalhes] [HTML] [CSV]      │
│ 08/09 10:05 · Concluída            │
│ ...                               │
└─────────────────────────────────────┘
```

- **Ato atual:** fundamentação primeiro; sete campos preservados, apresentados em blocos sem tabela larga. Fonte, valor documental, valor atual do portal e proposta são rótulos distintos. Estado “Sem alteração” quando os valores conferem; “Divergente” quando diferem.
- **Execução:** antes de iniciar, informar setor, fonte dos dados e que os atos elegíveis serão complementados. Durante descoberta, progresso indeterminado com páginas lidas; depois da fila congelada, denominador fixo. “Analisados” inclui terminais confirmados/pendentes/falhados; “Confirmados” contabiliza apenas persistência comprovada. Pausa, encerramento e incerto aparecem por extenso.
- **Histórico:** lista por início decrescente, 20 execuções por carregamento, botão “Carregar mais”; detalhe mostra cronologia, valores e evidências persistidos. Abrir histórico não muda aba do portal nem retoma execução.
- **Configurações:** seção expansível dentro do painel, contendo conexão ao serviço, código de pareamento, importação JSON e versão. Endereço técnico fica em “Opções avançadas”. Quando desconectado, mostrar ação “Conectar serviço local”; modo manual por JSON permanece acessível.
- **Pesquisa:** seção recolhida “Localizar dados” em Ato atual, usando busca existente. Resultado explicitamente rotulado “Consulta local — não altera o interessado no portal”.
- “Revisado” mantém significado de revisão manual; não usar check verde de envio para essa marca. Ação manual de substituir campo permanece individual e com confirmação existente.
- Sinal manual legado permanece em ação secundária “Sinalizar no portal”, com descrição “Não envia o ato”; não transformá-lo em CTA principal nem fazê-lo enviar silenciosamente.

### 13.4 Estados, acessibilidade e separação de responsabilidades

| Estado | Conteúdo e ação principal |
|---|---|
| Sem dados | Explicar necessidade de dados locais; “Conectar serviço local” e alternativa “Importar JSON”. |
| Portal não detectado | “Abra Meus Processos Eletrônicos na Área Restrita”; nenhuma ação de preencher habilitada. |
| Interessado não selecionado | Orientação para seleção no portal; identificação do processo continua visível. |
| Prévia pronta | Documento e proposta por campo; botão de preencher no modo manual. |
| Fundamentação por semelhança | Badge textual “Por semelhança”; motivo e ranking em detalhe expansível; sem porcentagem de certeza. |
| Divergência | Valor atual e documental lado a lado/empilhados; automático marca pendência. |
| Envio em andamento | “Envio iniciado — aguardando confirmação”; bloquear cliques duplicados. |
| Resultado incerto | Banner persistente “Não foi possível confirmar o envio”; orientar conferir/reconciliar; nunca oferecer “Enviar novamente” como solução direta. |
| Falha do relatório | Mostrar último evento persistido e revisão disponível do relatório; lote pausado. |
| Concluído com pendências | Exibir contagens e acesso às pendências; não usar “Todos complementados”. |

**Interface de apresentação proposta:** `buildPanelViewModel({record,snapshot,matches,run,connection,selectedView}) -> PanelViewModel`; `renderPanelView(root,model,handlers) -> void` em `panel-view.js`. `PanelViewModel` contém `identity`, `selectedView`, `connection`, `legalDecision`, `fields`, `runSummary`, `history`, `actions` e `banner`. Cada `action` possui `id`, `label`, `enabled` e `disabledReason`. Não incluir tokens nesse modelo.

- `panel.js` permanece responsável por chamadas, estado e handlers; `panel-view.js` apenas produz/atualiza DOM com `textContent` e componentes pequenos. Não usar `innerHTML` com documentos, nomes ou erros.
- Preservar IDs de comandos existentes quando o comportamento não mudar (`fill-button`, `refresh-button`, importação, pareamento, pesquisa). Migrar `preview-body`/tbody para `fields-list` conscientemente, atualizando `ELEMENT_IDS`, `renderRows` e fixtures no mesmo commit.
- Substituir a mensagem permanente por `mode-status`: manual “Preenchimento para revisão”; automático “O lote complementa os atos elegíveis”; pausado “Nenhum novo envio será iniciado”. Testar as três mensagens; não deixar aviso contraditório antigo.
- Usar `role=tablist`, `tab`, `tabpanel`, `aria-selected`, relações `aria-controls` e navegação por setas/Home/End; configurações com `button`/`aria-expanded` ou `details` nativo. Resultados da pesquisa devem usar botões/lista comuns, salvo implementação completa do padrão listbox atual.
- Uma região `aria-live=polite` resume transições relevantes; erro crítico usa `role=alert` apenas ao surgir. Polling de 2 s não anuncia repetidamente toda a tela.
- Renderização não perde foco, seleção de texto nem posição de scroll a cada refresh. Restaurar foco ao controle que abriu detalhes; novo ato atualiza identidade sem mover foco automaticamente.
- Histórico requer endpoint adicional autenticado `GET /api/v1/automation/runs?limit=20&before=<cursor>` e `GET /api/v1/automation/runs/<id>/events?after=<seq>&limit=100`. Cursores são opacos, ordenação estável por início/ID e sequência; limites máximos 100/500. Retornar `{api_version:1,runs,next_cursor}` e `{api_version:1,events,next_after,has_more}` respectivamente.
- Acrescentar `list_runs(limit:int,before:str|None) -> dict` ao store, e `listAutomationRuns({limit,before})`/`getAutomationEvents(runId,{after,limit})` ao bridge client. Aplicar testes de auth, paginação e não vazamento de outras raízes. Incluir esses contratos na fase 4 antes de integrar Histórico.

### 13.5 Entregas 8A–8E, TDD e aceite visual

**8A — especificação e fixtures visuais:** criar fixtures sintéticas para todos os estados da tabela acima e congelar tokens/wireframes desta seção. Gerar screenshots do painel atual em 360 e 480 px como referência local, sem dados pessoais. Nenhum screenshot já foi produzido por esta revisão documental.

**8B — estrutura e componentes:** implementar `panel-tokens.css` e `panel-view.js` com tabs, identidade, campos e trilha de fundamentação. Primeiro testar que todos os campos e fontes continuam acessíveis; depois substituir tabela. Não manter simultaneamente duas cópias ocultas da prévia.

**8C — integração operacional:** conectar Execução, Histórico e Configurações aos contratos das fases 4–7; não duplicar estado de execução no DOM. Preservar funcionamento manual, sinal legado e confirmação individual de override.

**8D — validação visual e acessibilidade:** criar `P/test_panel_redesign_browser.py` usando o harness de navegador já adotado no projeto. Screenshots são evidência complementar a assertions de layout e comportamento; não exigir igualdade pixel a pixel entre máquinas.

**8E — acabamento e pacote:** rever linguagem, contraste, foco, espaçamentos e estados vazios, atualizar guide e allowlist; só encerrar após QA do ZIP carregado no Chrome.

Testes RED/GREEN proporcionais:

```javascript
test('view model não apresenta semelhança como confirmação de envio', () => {
  const model = buildPanelViewModel(similarityPendingFixture());
  assert.equal(model.legalDecision.method, 'similarity');
  assert.equal(model.runSummary.confirmed, 0);
});

test('resultado incerto não oferece reenvio direto', () => {
  const model = buildPanelViewModel(unconfirmedRunFixture());
  assert.equal(model.actions.some(action => action.id === 'resend'), false);
  assert.ok(model.banner);
});
```

Definir fixtures locais com contratos da seção 4: primeiro caso com ato `filled` e decisão por semelhança; segundo com execução `paused` e item `unconfirmed`. Evitar tests que apenas verificam classe CSS ou copiam toda a implementação.

- [x] Em 320, 360, 480 e 640 px, nenhuma rolagem horizontal de página ou corte de ações/fontes; comparar `scrollWidth` e `clientWidth` com tolerância de 1 px.
- [x] Em Ato atual, ação de preenchimento e indicação do modo manual aparecem antes da fundamentação na ordem visual e de leitura; nenhuma cópia da ação fica no rodapé.
- [x] Escala de texto sintética de 200%, textos legais longos, nome de interessado longo e aumento da fonte não ocultam valores ou controles.
- [x] Teclado percorre tabs com setas/Home/End; foco é restaurado após renderização e polling não anuncia repetidamente a tela.
- [x] Reabrir painel preserva a tab em `storage.session` e recupera a execução persistida quando disponível; navegar pelo Histórico nunca envia mensagem de retomada.
- [x] Fonte indisponível, contexto incompleto e serviço antigo têm mensagens acionáveis e não parecem estados de sucesso.
- [x] Campos “Por regra”, “Por semelhança”, “Revisado” e “Confirmado no portal” são visualmente e semanticamente distintos.
- [x] Conferir contraste com medição automática (tokens de texto, status, ação e foco), idioma, IDs/targets de labels, cópia de segurança e leitura por teclado; a inspeção visual do portal real continua fora do escopo sintético.
- [x] Screenshots sintéticos por estado/largura são gerados em diretório temporário de QA; nenhuma captura de produção entra no Git.

Comandos: em E, `node --test tests/panel-view.test.mjs tests/panel.test.mjs tests/bridge-client.test.mjs`; em P, `python -m unittest test_panel_redesign_browser -q`; ao integrar, `npm test` e testes de automação da fase 9.

**Aceite do redesign:** operador identifica processo/interessado e estado sem procurar nas configurações; fundamentação e fonte podem ser comparadas em 360 px sem rolagem horizontal; ações manuais/automáticas não se confundem; histórico e relatório permanecem acessíveis durante falha; nenhuma regressão de identidade, preenchimento ou envio. Commits separados sugeridos: `feat: redesign act review panel`, `feat: integrate execution and history views`, `test: qualify responsive extension redesign`.

## 14. Fase 9 — qualificação ponta a ponta

**Criar:** `P/test_automation_browser.py`, `P/test_automation_integration.py`; ampliar fixtures do portal simulado e testes de recuperação.

### 14.1 Testes automatizados

- [x] Executar ciclo em portal local simulado com lista, seleção, frames separados, leitura do formulário e retorno em Chrome; serviço ausente bloqueia o submit sem clique. FakeElement não é a única evidência deste gate.
- [x] Executar também a matriz visual e de acessibilidade da fase 8; 320/360/480/640 px, escala sintética de 200%, tabs/teclado e smoke da extensão permaneceram verdes.
- [x] Cobrir 25 atos em duas páginas, 3 pendências documentais e um timeout de envio: após reabrir, o ordinal 11 ficou `unconfirmed`, três itens ficaram `pending` e a execução pausou para retomada explícita.
- [x] Reiniciar o journal/serviço e navegador separadamente; a suíte cobre recuperação, watchdog, isolamento de outra aba, troca de dataset e reabertura do perfil descartável.
- [x] Confirmar que bridge/serviço ausente impede envio e que os relatórios/HTML anteriores continuam legíveis; SQLite indisponível permanece gate de ambiente a repetir no runtime portátil final.
- [x] Fechar o guard de segurança da API: uma execução comum não consome comando quando `real_send_enabled=false`; o endpoint devolve `REAL_SEND_DISABLED` antes de autorizar `dispatch_allowed`.
- [x] Rodar suíte JS completa, Python focal e suíte Python ampla; a primeira ampla revelou e corrigiu a fixture que omitia `legal_context.py`, sem converter a falha em PASS.

### 14.2 Gate real, sem presumir sucesso

- [ ] Capturar em leitura DOM sanitizado das telas reais atuais e comparar com fixtures. Não versionar CPF, nomes reais ou parâmetros de sessão.
- [ ] Rodar descoberta e preflight reais sem clicar envio para três atos representativos disponíveis; comparar propostas à resolução manualmente.
- [ ] Preparar um ato concreto e relatório prévio. Realizar o primeiro envio supervisionado no escopo autorizado; identificar mensagem real de aceitação/erro e reabrir o ato para ler os dados gravados.
- [ ] Para o piloto, iniciar serviço com opção nova `--automation-pilot`, que permite no máximo um comando consumido no processo atual do serviço e mantém `real_send_enabled=false` para lotes. Exigir clique explícito no painel “Executar piloto de um ato”; reinício não repete o piloto. Essa opção só é usada durante qualificação, após os testes locais.
- [ ] Converter a observação real em fixture sanitizada e teste de `classifyPortalOutcome`. Se o portal usar diálogos nativos, verificar mecanismo observado antes de automatizar aceitação; não criar substituição genérica de `window.confirm`.
- [ ] Somente após o teste e a conferência do primeiro ato, habilitar `real_send_enabled`. Se não houver evidência suficiente, manter recurso real bloqueado e registrar o motivo exato; não simular PASS.
- [ ] Registrar qualificação em `<workflow_root>/automacao/qualificacao.json`, com versões de extensão/serviço/regras, hash das fixtures sanitizadas e ID do evento real confirmado. O serviço habilita lote somente para versões iguais às qualificadas. Atualização que altera envio ou classificação exige renovar o gate; o arquivo não transporta autorização automática para outro computador.
- [ ] Validar lote supervisionado de até cinco atos elegíveis, incluindo retorno e relatório após cada um. Ausência de determinada família no lote não é cobertura real dessa família.
- [ ] Concluir conferência do relatório: dados usados, decisões por semelhança, fontes, resultado, timestamps e ausência de segredos.

**Critério final:** zero seleção errada nos casos rotulados de regressão; 100% dos envios tentados têm intenção persistida anterior; confirmados têm evidência posterior; quedas não repetem envio; pendências documentais permitem avanço. Não prometer acurácia universal para escolhas por semelhança.

## 15. Fase 10 — pacote, transferência, documentação e Git

**Alterar:** `P/empacotar-extensao-complementar-ato.ps1`, `P/test_extension_zip_packager.py`, `P/empacotar-coletor-portatil.ps1`, `P/package_complete_archive.py`, `A/prepare_transfer.py`, `A/package_audit.py` e testes correspondentes; README raiz/portátil e guia rápido conforme necessário.

- [x] Acrescentar à allowlist os módulos novos da extensão: `lib/legal-foundation.js`, `lib/automation-schema.js`, `lib/automation-preflight.js`, `content/portal-navigation.js`, `content/portal-submit.js`, `background/automation-controller.js`. O teste compara exatamente a lista final.
- [x] Incluir também `sidepanel/panel-tokens.css` e `sidepanel/panel-view.js`; packager e auditoria validam o conjunto extraído. SVGs continuam inline estáticos.
- [x] Incluir módulos Python novos no pacote completo; os testes de pacote carregam o `legal_context.py` e verificam a pipeline autocontida. A prova com `sqlite3` ainda deve ser repetida contra o runtime portátil distribuível.
- [x] Publicar localmente a versão de extensão `1.1.0`, com capacidade automática schema 1 e regras `legal-foundation-v1`; o serviço informa capacidades e mantém `real_send_enabled=false`.
- [x] Preservar o fluxo existente de quiesce/fechamento do banco antes da transferência; testes de `prepare_transfer` e pacote permanecem verdes.
- [x] Auditar CRC, hashes, allowlist, imports e conteúdo do ZIP em fixtures novas; smoke Chrome do pacote final e validação do runtime portátil real permanecem pendentes de uma release autorizada.
- [x] Entregar a composição compatível de extensão + serviço no pacote completo local; a documentação não trata o ZIP isolado como persistência completa.
- [x] Atualizar guia com iniciar/pausar/retomar, interpretação de incerto, relatórios e serviço ausente.
- [x] Manter handoffs por fase; o handoff da Fase 9/10 registra contagens, limites, commit e retomada.
- [x] Commit apenas código, testes sanitizados e documentação. O staging foi explícito; não usar `git add .` para evitar incluir dados privados.
- [x] Verificar remoto antes de push. Na inspeção atual não existe remoto; nenhum push foi afirmado ou tentado.

**Rollback:** pausar/encerrar lote, preservar banco e relatórios, reinstalar pacote anterior em pasta separada. Não apagar histórico, não desfazer atos remotos e não editar banco manualmente para “zerar” pendências. Formato de banco incompatível deve abrir somente para exportação/consulta pela versão compatível.

## 16. Comandos de validação e registro de resultados

Executar a partir da raiz do repositório. Os comandos abaixo são para implementação futura; presença no plano não significa execução.

```powershell
git status --short --branch
git log -1 --oneline
git remote -v
node --version
python --version

Push-Location 'work/tce-extractor/portable/extensao-complementar-ato'
npm test
Pop-Location

Push-Location 'work/tce-extractor'
python -m unittest test_tce_extractor test_extension_exporter test_analysis_pipeline test_local_service test_workflow_state -q
python -m unittest test_legal_context test_automation_store test_automation_report test_automation_api test_automation_recovery test_automation_integration -q
python -m unittest test_automation_browser test_extension_browser -q
python -m unittest discover -s . -p 'test_*.py' -q
python -m unittest test_extension_zip_packager test_package_complete_archive test_package_audit test_prepare_transfer -q
Pop-Location
```

Se `python` não existir no PATH, resolver o runtime do projeto e usar caminho absoluto; não instalar nem trocar runtime silenciosamente. Alguns testes de navegador/empacotamento exigem dependências locais: registrar bloqueio específico e evidência que falta.

Modelo de registro por gate:

```text
Fase / commit:
Comando:
Executados / aprovados / falhados / ignorados:
RED observado e motivo:
GREEN observado:
Validação manual e ambiente:
Artefatos privados de evidência:
Limitação / próxima ação:
```

## 17. Matriz de rastreabilidade e revisão

| Requisito / risco | Fases | Prova necessária |
|---|---|---|
| Redações diferentes nas três famílias | 1, 2 | Fixtures abreviadas e multipágina com opção esperada |
| Art. 7º isolado | 2 | Teste explícito de regra operacional |
| §5 só na resolução | 1, 2 | Cargo professor sem §5; §5 em outra norma; trecho histórico |
| Outras opções por semelhança | 2 | Ranking persistido, empate/zero sem escolha |
| Todos os disponíveis | 5 | Múltiplas páginas, deduplicação, lista que muda |
| Preservar valores divergentes | 6 | Zero escritas antes da decisão de pular |
| Clicar no botão final real | 7, 9 | Frame correto e gravação real observada |
| Relatório incremental | 3, 7, 8 | Evento durável e arquivo legível após cada etapa |
| Queda no meio do envio | 7, 9 | Matriz de crash e nenhuma reemissão cega |
| Histórico legado | 3, 4 | `completed` manual não vira comprovante |
| Compatibilidade do pacote | 4, 10 | Cliente antigo/novo, allowlist, sqlite portátil |
| Redesign adaptado ao side panel | 8, 9 | 320–640 px, zoom 200%, comparação completa sem rolagem horizontal |
| Navegação e acessibilidade | 8, 9 | Tabs/teclado, foco preservado, contraste medido, anúncios sem repetição |
| Histórico sem efeitos colaterais | 4, 8 | Paginação, acesso autenticado e nenhum comando de retomada ao consultar |
| Dados privados | 3, 4, 10 | Escapes de relatório, auth e diff/ZIP sem segredos |

### Checklist de encerramento por fase

- [x] Testes comportamentais escritos antes da implementação; RED/GREEN dos blocos locais estão registrados nos handoffs e nos testes focalizados.
- [x] Critérios locais de aceite cumpridos; a qualificação real está explicitamente incompleta na seção 14.2.
- [x] Contratos compartilhados preservados; os módulos novos foram incluídos e auditados no empacotamento local.
- [x] Handoff atualizado com arquivos, problemas, tentativas, testes, validações manuais e retomada.
- [x] Commit específico criado; não houve push porque nenhum remoto está configurado.
- [x] Nenhum teste sintético foi descrito como validação real do portal.

## 18. Primeiro passo de execução

Começar pela fase 0, reproduzindo o matcher contra catálogo sintético baseado no observado. Em seguida construir contexto completo da resolução antes de alterar a seleção. A sequência evita corrigir apenas pontuação enquanto a fonte continua truncada. O modo de envio deve permanecer inativo até completar persistência, preflight, recuperação e qualificação real.
