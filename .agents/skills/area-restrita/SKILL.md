---
name: area-restrita
description: Use when investigating or changing Atos-TCE Área Restrita navigation, state detection, pagination, interested-person selection, form filling, or return flow. Requires Portal Lab evidence before runtime changes and blocks guessed selectors and finalization.
---

# Área Restrita: investigação antes de alterar runtime

Use este procedimento para qualquer mudança na navegação, detecção de tela,
paginação, seleção de interessado, preenchimento ou retorno da Área Restrita.
Chrome DevTools MCP e Playwright CLI são ferramentas de desenvolvimento; o
runtime distribuído continua sendo Mesa + extensão MV3.

## Limites que não podem ser relaxados

- Autenticação no portal é feita manualmente pela pessoa operadora. Não leia,
  digite, copie ou versione credenciais, cookies, tokens ou estado de sessão.
- O MCP deve estar comprovadamente conectado ao Chrome dedicado do Portal Lab
  em `127.0.0.1:9222`. A presença das ferramentas MCP não prova o alvo.
- A ação final **Complementar Ato**, submit, assinatura e tramitação são L3 e
  permanecem exclusivamente manuais. O agente pode observar o estado depois
  que a pessoa operadora executá-la.
- Capturas brutas, snapshots, traces e dados do portal ficam fora do Git em
  `tmp/portal-lab/<sessao>/raw/`. Só fixtures revistas e sanitizadas podem ser
  versionadas.
- `portal-contract.json` é um oráculo documental/de teste baseado no código e
  fixtures existentes. Até a observação real correspondente, não o descreva
  como comportamento atual confirmado do portal.
- Para **Próximo processo**, não implemente runtime antes de Best-Effort Task 10
  e Next Process Phase 0 estarem fechadas conforme os documentos de estado e o
  plano consolidado vigentes.

## Sequência obrigatória

Execute estes passos na ordem. Se faltar evidência ou um gate, pare na etapa
afetada e registre o bloqueio; não substitua evidência por suposição.

```text
A. Ler portal-contract + código atual.
B. Classificar ação L0/L1/L2/L3.
C. L3 -> recusar.
D. Capturar BEFORE.
E. Executar no máximo uma transição.
F. Capturar AFTER.
G. Sanitizar.
H. Comparar.
I. Criar fixture.
J. Escrever teste RED.
K. Só então alterar runtime.
L. Rodar GREEN + suíte.
M. Verificar packaging boundary.
```

Antes de D, confirme que o alvo MCP é o Chrome dedicado e que a ação é
permitida no nível classificado. Em L0, capturas devem ser somente estruturais
e de leitura. L1/L2 exigem os gates em `references/safety.md`; faça uma única
transição e confira o resultado antes de qualquer outra ação. Nunca inclua
valores de campos, corpos de requisição/resposta, headers, cookies ou storage
nas capturas.

Depois de H, examine o diff sanitizado. Se a observação não separar com clareza
dois estados, frames ou identidades, classifique como `ambiguous` e não avance.
Uma captura não pode virar fixture até ser revisada e aprovada pelo sanitizador.
O teste RED deve reproduzir a divergência observada e falhar pela razão
esperada antes da menor correção de runtime.

## Timeout e retries

Não corrija uma divergência real apenas aumentando RETRY/DELAY/TIMEOUT.
Primeiro identifique qual evidência estrutural distingue o estado observado.
Um ajuste de tempo só é permitido como limite superior depois de existir
um predicado estrutural testado.

## Dono de seletores e estados

Qualquer seletor promovido para runtime deve morar em area-snapshot.js
ou no módulo já designado como dono do controle. Não criar um segundo
mapa de seletores no router, Skill, script Python ou portal-contract.

`extension/lib/area-snapshot.js` é o dono atual dos seletores e assinaturas
estruturais compartilhados de leitura. Mantenha o `portal-contract` como
documentação e oráculo dos testes; ele não é configuração operacional.
Consulte `references/portal-states.md` para interpretar estados sem inventar
seletores nem assumir ordem de frames.

## Validação e registro

- Comece pelos testes focados que cobrem o contrato RED/GREEN.
- Rode as suítes Python, extensão e web e
  `work/tce-extractor/verify-project.ps1` quando exigido pelo gate da tarefa.
- Verifique a fronteira do pacote: MCP, Playwright CLI, `.agents/`, `devtools/`
  e `tmp/portal-lab/` não podem entrar no runtime/ZIP.
- Atualize o handoff com evidência observada, sanitização, testes, GitHub,
  limitações e passos de retomada. Diferencie estados sintéticos dos reais.
