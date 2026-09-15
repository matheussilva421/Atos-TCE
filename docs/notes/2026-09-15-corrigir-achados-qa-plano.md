# Plano de correção dos achados QA — Atos-TCE

**Data:** 15/09/2026
**Base:** `c84bced`
**Escopo:** corrigir os achados confirmados na revisão do pacote, sem alterar o pacote de referência de 14/09 e sem executar envio no portal.

## Restrições globais

- Trabalhar na `main`, conforme autorização explícita do usuário.
- Cada alteração de comportamento terá teste RED antes do código, GREEN focado e regressão ampla.
- O empacotador deve produzir ZIP autocontido; nenhum dado local, perfil, cookie, token ou credencial pode entrar em distribuição pública.
- Identidade, escopo, documento e OCR devem falhar de forma segura quando a evidência for insuficiente.
- Ações externas de envio permanecem desabilitadas.

## Tarefas

### Task 1 — Empacotamento e privacidade

Incluir no empacotador todos os módulos exigidos pela opção de lista autoritativa e endurecer a auditoria pública para que `.xlsx` e `.sqlite3` só sejam aceitos dentro do acervo privado permitido. Criar testes que falhem com o empacotador/auditor atuais e validar ZIP limpo.

### Task 2 — Identidade exata do processo

Remover fallback para o primeiro resultado em `TcePortal.Driver.js`. A resolução deve exigir número/ano exatos e bloquear divergência. Criar regressão no teste Node do driver e executar a suíte da extensão.

**Status em 15/09/2026:** concluída.

- Correção mínima aplicada em `work/tce-extractor/portable/TcePortal.Driver.js`: removido o fallback para `result[0]`; divergência, lista vazia e item exato sem `idProcesso` falham antes dos eventos.
- Criado `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-driver.test.mjs`, com execução isolada do driver e cobertura de divergência sem chamada de eventos, item exato sem ID e correspondência exata.
- TDD: RED final `1 falhou / 2 passaram`; GREEN focado `3/3`; suíte Node `379/379`.
- Relatório completo: `.superpowers/sdd/2026-09-15-corrigir-achados-qa-plano/task-2-report.md`.
- Pacote de referência preservado; não houve rede, login, envio ou QA portal real.

### Task 3 — Escopo e cardinalidade da análise

Permitir `sector_finalistic` e `my_processes` na análise autoritativa, propagando a origem confirmada pela tela real. Preservar um item por interessado; divergência ou identidade ambígua deve bloquear o item sem colapsar interessados distintos em um único item elegível. Atualizar schemas, controlador, materializador e testes.

### Task 4 — Evidência de aquisição/OCR e gates

Não promover citação nominal a documento/OCR pronto sem artefato, hash e evidência compatíveis. Manter itens sem documentos em `acquisition_pending`/aquisição elegível, mas fora de `eligible`. Registrar confirmação da prévia, tamanho e estados por item/lote no serviço e no painel. Criar testes RED/GREEN.

### Task 5 — Documentação, pacote e regressão final

Atualizar handoff, relatório de causa raiz e matriz comparativa. Executar testes Python, Node, PowerShell, auditoria, empacotamento e inspeção de conteúdo. Confirmar que a referência original permanece byte a byte inalterada e registrar commit/push.
