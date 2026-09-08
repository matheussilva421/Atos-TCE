# Relatório — Fase 0: baseline e casos de regressão

Data: 2026-09-08
Branch: `codex/fundamentacao-automatico`
Brief: `task-0-brief.md`

## Status

Fase 0 concluída dentro do escopo autorizado. Foram adicionados somente testes e
fixtures sanitizados. Nenhum resolvedor novo, API, persistência, automação,
redesign, clique ou envio foi implementado.

O estado esperado desta fase mantém uma regressão RED conhecida: o matcher
legado ainda escolhe a primeira opção quando todos os sinais pontuam zero. O
teste agora registra o contrato futuro (`optionValue === null`); a correção de
produção fica para a fase posterior, conforme o brief.

## Baseline registrada

Estado inicial observado antes das alterações desta tarefa:

- Branch: `codex/fundamentacao-automatico`.
- HEAD: `dc84402 docs: move manual fill action to top of planned panel`.
- Remoto Git: nenhum remoto configurado; não houve push.
- Node: `v24.15.0`.
- Python: `3.14.4`.
- Alteração pré-existente preservada: `docs/notes/2026-09-08-fundamentacao-automatico-handoff.md`.
- Dataset v1 e seus sete campos não foram alterados.

## RED/GREEN

### RED comportamental

Teste focal executado após escrever a regressão, antes de qualquer código
funcional:

```text
cd work/tce-extractor/portable/extensao-complementar-ato
node --test tests/matcher.test.mjs tests/normalizer.test.mjs
```

Resultado RED: 32 testes, 31 passaram, 1 falhou. A falha foi comportamental e
esperada: para `"texto sem referências"`, o matcher retornou
`synthetic-ec41-without-p5` em vez de `null`. Não houve erro de importação ou de
configuração.

Após incorporar o catálogo e as fixtures, o mesmo teste focal ficou em 34
testes, 33 passando e 1 falhando na mesma regressão. Os testes de catálogo e
superfícies simuladas passaram.

### GREEN preservado

Baseline JavaScript antes das alterações:

```text
cd work/tce-extractor/portable/extensao-complementar-ato
npm test
```

Resultado: 124 testes, 124 passaram, 0 falharam.

Suíte Python focal da extração/exportação/serviço:

```text
cd work/tce-extractor
python -m unittest test_tce_extractor test_analysis_pipeline test_extension_exporter test_local_service -q
```

Resultado: 85 testes executados, 85 passaram, 0 falharam e 1 foi omitido por
condição ambiental. Permaneceram apenas os warnings já observados de API
depreciada do `fitz` e limpeza de erros HTTP temporários.

Suíte JavaScript completa após os artefatos da fase:

```text
cd work/tce-extractor/portable/extensao-complementar-ato
npm test
```

Resultado: 126 testes, 125 passaram, 1 falhou e 0 foram omitidos. A única falha
é a regressão RED descrita acima; não surgiram falhas adicionais.

Não existe atualmente teste Python focal que consuma os novos arquivos
`tests/fixtures/automatic-portal/`; portanto não foi criado nem alegado um
PASS artificial para esse caso. Os testes Python existentes continuam cobertos
pelo comando focal acima.

## Arquivos alterados/criados

- Alterado `work/tce-extractor/portable/extensao-complementar-ato/tests/matcher.test.mjs`:
  - carrega o catálogo sanitizado;
  - verifica schema v1, sete campos, três opções canônicas e quatro opções
    auxiliares;
  - verifica valores sintéticos e placeholder não selecionável;
  - verifica as cinco superfícies distintas e a marcação simulada;
  - verifica que o frame mantém o modo manual de sinalização sem envio;
  - substitui o teste que documentava a seleção indevida por uma regressão que
    exige `optionValue === null`.
- Criado `work/tce-extractor/tests/fixtures/legal-foundations.json`:
  catálogo sintético com `EC41_SEM_P5`, `EC41_COM_P5`, `EC47_ART3`, art. 6º-A,
  CF art. 40 § 1º II, opção militar e placeholder.
- Criado `work/tce-extractor/tests/fixtures/automatic-portal/process-list-page-1.html`.
- Criado `work/tce-extractor/tests/fixtures/automatic-portal/process-list-page-2.html`.
- Criado `work/tce-extractor/tests/fixtures/automatic-portal/people.html`.
- Criado `work/tce-extractor/tests/fixtures/automatic-portal/form.html`.
- Criado `work/tce-extractor/tests/fixtures/automatic-portal/buttons-frame.html`.
- Criado `work/tce-extractor/tests/fixtures/automatic-portal/simulator-result.json`.
- `normalizer.test.mjs` não foi alterado: não houve comportamento de
  normalização novo nesta fase que exigisse contrato adicional.

## Sanitização e limites

- Todos os valores selecionáveis usam prefixo `synthetic-`; o placeholder tem
  valor vazio e `selectable: false`.
- Processos, pessoas, matrículas e textos de formulário são sintéticos; não há
  CPF, CNPJ, token, credencial, nome de produção ou sessão autenticada.
- Não foram lidos, alterados ou publicados PDFs reais.
- Toda superfície HTML contém `data-fixture-status="simulated"`; o resultado
  JSON usa `fixture_status: "simulated"`, `is_simulated: true`,
  `status: "simulated-success"` e `request.sent: false`.
- O frame preserva a mensagem de sinalização manual existente; “sucesso” do
  simulador não é evidência de gravação no portal.

## Riscos e retomada

1. Antes da fase que corrigir o matcher/resolvedor, a suíte completa continuará
   com uma falha intencional: qualquer fonte sem referência positiva não pode
   receber opção por ordem ou score zero.
2. O catálogo contém rótulos sintéticos baseados nas três opções canônicas
   documentadas, mas seus `value` não são IDs reais. A integração futura deve
   obter os valores reais do catálogo observado em cada formulário, sem fixar
   índices ou IDs.
3. Os fixtures de portal são contratos locais e não validam seletores contra o
   portal autenticado. Qualificação real permanece fora desta fase.

Próxima retomada: implementar o contrato de resolução específico da Fase 2
contra este catálogo e fechar a regressão com testes RED/GREEN próprios, sem
promover o resultado simulado a sucesso real.

## Fix report — revisão incremental da Fase 0

Data: 2026-09-08

Os três achados da revisão foram corrigidos sem alterar o handoff ou o ledger do
controlador:

1. `matcher.test.mjs` agora fixa por igualdade os três pares canônicos de
   `rule_id`, `value` e `label`, confirma que são selecionáveis, exige valores
   selecionáveis não vazios e únicos, e associa explicitamente
   `PLACEHOLDER` a `value: ""` e `selectable: false`.
2. O teste lê as duas páginas da lista, exige conteúdo diferente e verifica
   processos distintos (`SYN-0001/2099` e `SYN-0003/2099`). Também cobre os
   marcadores do resultado JSON: `fixture_status`, `is_simulated`, aviso de
   não comprovação real, `sent: false`, modo manual, `simulated-success` e
   ausência de identificador persistente.
3. `buttons-frame.html` reproduz a não exclusividade do ID `botao` com dois
   botões homônimos. O teste exige os dois elementos e duas ações
   `signal-only`; a mensagem manual permanece presente e nenhuma submissão é
   realizada.

### RED/GREEN deste fix

Após escrever as novas asserções, antes de alterar a fixture de botões:

```text
node --test tests/matcher.test.mjs tests/normalizer.test.mjs
```

Resultado RED: 34 testes, 32 passaram e 2 falharam. Uma falha foi a nova
asserção de dois `id="botao"` contra a fixture antiga (1 encontrado); a outra
foi a regressão conhecida do matcher, que retornou
`synthetic-ec41-without-p5` em vez de `null`.

Após a alteração mínima de `buttons-frame.html`, o teste focal ficou em 34
testes, 33 passando e 1 falhando. Todos os contratos novos passaram; resta
somente a regressão intencional do matcher, sem mudança de produção.

A suíte completa final:

```text
npm test
```

Resultado: 126 testes, 125 passaram, 1 falhou e 0 foram omitidos. A única falha
é a mesma regressão RED de score zero/ordem; não surgiram falhas adicionais.

Commit incremental: `test: harden phase 0 fixtures and catalog contracts` (SHA
informado na resposta final; o relatório integra o commit).

## Commit e GitHub

Commit: `test: reproduce legal foundation selection failures` (SHA informado
na resposta final; este relatório integra o próprio commit). Como não há
remoto configurado neste checkout, nenhum push foi realizado.
