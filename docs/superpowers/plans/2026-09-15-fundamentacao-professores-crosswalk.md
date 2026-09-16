# Fundamentação Legal de Professores — Crosswalk v2

> Plano de execução derivado de `docs/PLANO_CODEX_FUNDAMENTACAO_LEGAL_PROFESSORES_TCE.md`, fornecido pelo usuário para esta implementação.

## Objetivo

Implementar um classificador jurídico especializado para aposentadorias de professores, separando fundamento documental da classificação cadastral do catálogo fechado da Área Restrita do TCE-RN. O fluxo deve reconhecer crosswalks entre normas estaduais/modernas e classes históricas do portal, sem transformar a resolução nem habilitar envio em casos ambíguos.

## Gates obrigatórios

- Parser estruturado de diplomas, artigos, parágrafos, incisos e alíneas.
- Perfil funcional separado para modalidade, proporcionalidade, base de cálculo, paridade e contexto docente.
- Crosswalk semântico auditável; Dice lexical residual com peso máximo de 5%.
- Opções militares rejeitadas no escopo civil.
- `confidence >= 0.90`, `margin >= 0.12` e ausência de conflito para AUTO; demais casos ficam em REVIEW/PENDING.
- Compatibilidade com os consumidores atuais e com `legal-foundation-v2` no JS/Python.
- Nenhum envio real; a qualificação final depende das suítes JS/Python e do smoke do pacote QA.

## Ordem de execução

1. Fixture e regressão RED.
2. Parser jurídico v2.
3. Perfil previdenciário funcional.
4. Catálogo/crosswalk e ranking.
5. Integração com `legal-foundation.js` e `matcher.js`.
6. Gates de automação e propagação do diagnóstico.
7. Diagnóstico do painel.
8. Versionamento e empacotamento.
9. Matriz de pelo menos 12 casos.
10. Verificação final e handoff.

O documento-fonte contém as assinaturas, casos, comandos e critérios completos; este arquivo mantém a execução localizada no repositório versionado.
