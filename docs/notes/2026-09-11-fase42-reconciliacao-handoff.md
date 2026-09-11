# Fase 4.2 — reconciliação dos bloqueios (2026-09-11)

Status: **NÃO PASSA / bloqueado**. Esta atualização registra a reconciliação
sanitizada; não houve preenchimento, envio, finalização ou persistência no
portal.

## Evidência portal-real

Em Chromium 151 isolado, já autenticado manualmente pelo usuário, foram
repetidos os três fluxos de leitura:

1. consulta exata do processo/ano;
2. identificação de uma única ação `Complementar Ato`;
3. confirmação da identidade e seleção reversível do único rádio;
4. releitura dos sete controles e do catálogo;
5. reload da sidepanel e comparação por hashes/flags, sem publicar valores.

O catálogo observado continha 13 opções de modalidade, 35 de fundamento legal
e 3 de gênero. As abas abertas foram fechadas e a inspeção final não deixou
frame `ComplementarAto` ativo.

## Proveniência do dataset

Auditoria independente em modo somente leitura:

- 50 processos e 51 registros;
- os três candidatos presentes uma única vez;
- seis campos obrigatórios presentes em `source_value`/`form_value`, com
  `status=found`, `confidence=high` e citações com chaves de processo,
  evento, página e documento;
- `genero` ausente na fonte nos três candidatos;
- hash lógico do dataset válido.

As citações não fornecem hash de PDF nem âncora textual suficiente para
reextrair uma data automaticamente. `source_value=form_value` nos campos
textuais/selects locais não prova que o `option.value` atual do portal seja o
mesmo.

## Matriz de reconciliação

| Processo/ano | Evidência comparável | Classificação | Decisão |
| --- | --- | --- | --- |
| `100120/2026` | DOE: `date_canonical_equal=true`; cargo/matrícula/nascimento: igualdade direta; modalidade/fundamento: sem igualdade com valor/rótulo selecionado, matcher `tie` | DOE somente representação; selects indeterminados | Bloqueado |
| `100273/2025` | modalidade `tie`; fundamento sem valor selecionado seguro; DOE `date_canonical_equal=false`; matrícula `identifier_compact_equal=false`; cargo/nascimento iguais | selects insuficientes; DOE/matrícula não são formato comprovado | Bloqueado |
| `100065/2026` | DOE: `date_canonical_equal=true`; cargo/matrícula/nascimento: igualdade direta; modalidade `tie`, fundamento `probable`, sem proposta determinística | DOE somente representação; selects indeterminados | Bloqueado |

O estado `Divergente` de DOE na sidepanel permanece esperado no contrato
atual, pois a UI compara a representação textual bruta. A igualdade civil foi
registrada apenas como evidência de reconciliação; não foi usada para escrever
ou marcar o preflight como aprovado. Também não foi aplicado normalizador de
matrícula, pois uma comparação somente por dígitos poderia colidir registros.

## Hardening identificado

O preflight automático agora aceita somente `method=exact` ou `method=rule`
quando a decisão está selecionada; `similarity` é bloqueado com
`LEGAL_DECISION_METHOD_UNSAFE`. A mudança TDD ficou restrita aos arquivos do
preflight e passou: 20/20 testes focais e 291/291 na suíte da extensão.

## Retomada

- manter `real_send_enabled=false` e `pilot_enabled=false`;
- não usar `APPLY_FIELDS` enquanto houver qualquer divergência, empate,
  decisão provável ou evidência incompleta;
- obter âncora/hash documental suficiente para as datas e `option.value` único
  para os selects obrigatórios;
- repetir a sessão controlada e só então reavaliar a Tarefa 4.2;
- mesmo com três preflights verdes, qualquer envio exige autorização humana
  imediata ato a ato.
