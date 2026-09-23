# Handoff — Best-Effort + Legal v4

**Data:** 2026-09-23
**Branch:** `codex/atos-tce-best-effort-v4`
**Base:** `b1d41e848c39cb61947b011501925c40f86793fb` (`origin/main` local tracking ref)

## Concluído

- Best-effort Task 1: adicionado `selectable_legal_options()` como filtro canônico de opções DOM reais. A função ignora placeholder, valor vazio, opção disabled/não selecionável, não usa label como fallback para value e preserva o `value` não vazio exatamente como recebido.
- Quatro testes novos em `tests/test_legal_rules.py` cobrem placeholder, ausência de value, valor literal do DOM e opções indisponíveis.
- Best-effort Task 2: `legal-foundation-v4` agora escolhe deterministicamente a melhor opção selecionável sempre que há texto documental e catálogo real. Baixa confiança/margem, empate, conflito, classe desconhecida e referência incompleta/contraditória ficam como warning. Valor de opção preserva a forma bruta do DOM.
- O seletor desempata primeiro por ausência de hard conflict, score, correspondência estrutural, crosswalk, discriminadores, lexical e por último `option_index`. A SPEC manda desempatar por componentes antes do índice, mesmo que o plano não enumere essa sequência.
- Oracles de decisão v3 seguem como histórico; os primitivos preservados continuam cobertos por paridade.
- Snapshot da extensão passa a reportar `disabled` por opção, inclusive quando o `<optgroup>` pai está desabilitado. Isso fecha a informação DOM necessária para o catálogo selecionável; a alteração está testada e será agrupada no commit de leitura de formulário do plano.
- Best-effort Task 3: `build_fill_plan()` agora bloqueia somente processo/identidade/generation, produz warnings de conteúdo por campo, preserva valores existentes divergentes e deixa campos independentes seguirem. `fundamento_legal` é resolvido antes de qualquer matching literal e validado contra as opções atuais selecionáveis.
- Best-effort Task 4: o leitor reconhece um formulário com âncoras de processo e pessoa interessada válidas mesmo se um controle de conteúdo estiver ausente; a propriedade daquele campo fica ausente no snapshot, sem fabricar estado vazio.

## Testes

- RED: `python -m unittest tests.test_legal_rules.SelectableLegalOptionsTests -v` — 4 erros esperados porque o helper ainda não existia.
- GREEN: `python -m unittest tests.test_legal_rules -v` — 28 testes, 28 aprovados, 0 falhas.
- RED: `python -m unittest tests.test_legal_rules.V4BestAvailableTests.test_equal_scores_use_semantic_components_before_catalog_index -v` — falhou como esperado, pois a primeira opção DOM ganhava o score empatado.
- GREEN: o mesmo teste direcionado passou; `python -m unittest tests.test_legal_rules -v` — 33 testes, 33 aprovados, 0 falhas.
- Snapshot DOM RED: `node --test extension/tests/detect-form.test.mjs` — 10/11 passaram; o novo teste falhou porque `disabled` não era reportado.
- Snapshot DOM GREEN: `node --test extension/tests/detect-form.test.mjs` — 11 testes, 11 aprovados, 0 falhas.
- RED: `python -m unittest tests.test_fill_service.PreflightTests -v` — 9 erros esperados nos contratos best-effort do preflight.
- RED adicional: um teste provou que controle legal disabled ainda entrava no plano; após incluir a guarda, passou.
- GREEN: `python -m unittest tests.test_fill_service.PreflightTests -v` — 21 testes, 21 aprovados, 0 falhas.
- GREEN da tarefa: `python -m unittest tests.test_fill_service -v` — 56 testes, 56 aprovados, 0 falhas.
- RED: `node --test extension/tests/detect-form.test.mjs` — o teste de formulário com `matricula` ausente falhou porque o leitor exigia todos os controles mapeados.
- GREEN: `node --test extension/tests/detect-form.test.mjs` — 11 testes, 11 aprovados, 0 falhas.

## Arquivos

- `app/analysis/legal.py`
- `tests/test_legal_rules.py`
- `tests/fixtures/legal-cases.json`
- `tests/legal_parity_harness.mjs`
- `tests/oracles/legal/README.md`
- `extension/content/detect-form.js`
- `extension/tests/detect-form.test.mjs`
- `extension/tests/fake-dom.mjs`
- `app/area_restrita/preflight.py`
- `tests/test_fill_service.py`
- Este handoff.

## Git e ambiente

- A ref local `origin/main` coincide com `origin/codex/mesa-local-refactor`; o branch de implementação parte desse SHA. `git fetch --prune origin` falhou por indisponibilidade de conexão com GitHub, então não foi possível refrescar refs remotas nesta sessão.
- O checkout original `codex/mesa-local-refactor` permanece intacto, com suas alterações preexistentes.
- O código de navegação ainda não foi alterado: Phase 0 exige concluir a observação real do formulário e do retorno antes de qualquer implementação dessa função.

## Discovery real em andamento

- Chrome perfil Matheus autenticado; lista do setor aberta no marcador normal, página 1/40, contagem visível 1.197.
- A leitura somente observacional dos frames detectou lista em frame interno e quadro de botões irmão; o scanner read-only existente confirmou 30 linhas na página 1.
- Comparação composta processo+interessado com o scan local de 21/09: 29/30 identidades correspondem; há drift de contagem/ordem. A página 1 contém apenas itens já concluídos. Primeiro `PRONTO` no scan salvo: posição 227 (página 8). Nenhum nome ou identificador individual foi registrado.
- A leitura atual confirmou novamente página 1/40, 30 linhas e total 1.197. A consulta por avaliação de DOM do tab de topo não atravessa os documentos de frame usados pela árvore de acessibilidade; requer diagnóstico pelo frame/CDP já permitido no plano. A divergência histórica segue sem resolução; não abrir processo por posição.
- Nenhuma ação de conclusão/envio foi executada.

## Próxima retomada

1. Iniciar Task 5 com RED para escrita por campo, ausência/readOnly/disabled/opção indisponível e falha isolada de escrita/releitura.
2. Prosseguir Tasks 6–9 com TDD: request x status, API, Mesa e integração; depois rodar gates amplos.
3. Prosseguir Phase 0 em portal real: estabelecer Mesa/extensão atuais, comparar sequência/página de limite e observar fluxo de interessado/formulário/retorno/estabilidade. Não clicar no botão final `Complementar Ato`.
4. A promoção e criação do branch de descoberta continuam limitadas pela impossibilidade de atualizar refs do GitHub; usar apenas os SHAs locais comprovados e registrar essa restrição.
