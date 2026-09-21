# Handoff — paginação da Área Restrita no portal legado (2026-09-21)

## Situação observada

Com a Mesa e a extensão conectadas, a análise real da Área Restrita falhou
com: paginação incoerente: página 1 depois de 1. O portal visualmente
avançava na lista, mas o scanner continuava lendo a página atual como 1.

## Causa raiz confirmada

O portal legado não usa aria-current=page para indicar a página atual. Ele usa
o controle NumeroPagina, um input/select cujo value muda de 1 para 2, enquanto
os links de navegação continuam sendo encontrados pelo adaptador. pageInfo()
ignorava esse controle e aplicava o fallback 1 em todas as leituras.

## Correção

- extension/lib/area-snapshot.js agora lê a página atual de aria-current=page
  ou, no portal legado, de NumeroPagina/input[name=NumeroPagina]/
  select[name=pagina].
- extension/tests/area-snapshot.test.mjs adiciona uma regressão que altera
  NumeroPagina de 1 para 2 e exige que o snapshot acompanhe a página.
- Nenhuma ação de ato, seleção de processo ou envio foi adicionado.

## Validação

- RED: o teste do controle legado falhou com 1 !== 2.
- GREEN focado: area-snapshot — 16/16; router e navigate — 58/58.
- Suíte completa da extensão: npm test --prefix extension — 125/125.
- Gate oficial: verify-project.ps1 — 1.254 verificações, 1.252 aprovadas,
  0 falhas e 2 skips ambientais.

## Retomada manual

Depois de publicar a correção:

1. Pare o START atual com Ctrl+C.
2. Atualize a branch e reinicie a Mesa.
3. Em chrome://extensions, atualize a extensão carregada de
   C:\Users\slvma\Downloads\Github\Atos-TCE\extension.
4. Reabra o painel e o portal na lista de processos.
5. Clique em Analisar Área Restrita novamente.

O resultado esperado é a leitura sequencial das 40 páginas mostradas pelo
portal, sem a mensagem de paginação incoerente. A Mesa só deve persistir o
retrato depois da varredura coerente.

M3, M5 e M6 continuam bloqueados pela validação humana correspondente no
portal.

## GitHub

- Branch: codex/mesa-local-refactor.
- O arquivo local não rastreado work/tce-extractor/.codex-live-pilot.py foi
  preservado.
