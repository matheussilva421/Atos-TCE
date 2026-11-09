# Complementador e-Contas — painel móvel e recolhível

Branch: `codex/complementador-e-contas`.

- Os painéis de formulário e de listagem compartilham `Complementador-eContas/src/shared/floating-panel.mjs`.
- Arraste pelo título ou use Tab e as setas. A posição respeita a janela, inclusive após redimensionar ou receber novos resultados.
- Esconder recolhe o painel e mostra um botão para reabri-lo. O DOM e o estado operacional são preservados, sem pausar/iniciar/parar lotes.
- Estado visual apenas em memória, até recarregar. Sem novas permissões, storage ou mensagens ao background.
- Testes unitários cobrem esconder/reabrir, preservação do conteúdo, arraste, limites, cancelamento, controles e teclado. Teste de navegador cobre os dois painéis reais da extensão.

Validação: `npm test` (348/348), `npm run build`, `npm run build:test` e `npm run test:browser` (26/26), além de `git diff --check`. Testes de navegador realizados com Chrome for Testing 157.0.8103.38, via `TEST_BROWSER_EXECUTABLE`; o Chromium do sistema não carregou extensões por linha de comando e o Chromium 133 do Playwright falhou ao inicializar neste ambiente. Sem acesso ao portal autenticado nem operações reais sobre processos.
