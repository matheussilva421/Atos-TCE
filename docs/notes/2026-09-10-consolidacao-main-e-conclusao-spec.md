# Especificação — consolidação na main e conclusão do fluxo automático

**Data:** 10/09/2026  
**Status:** aprovada para planejamento e execução faseada  
**Escopo:** organização local, consolidação Git, limpeza segura, estabilização,
qualificação portal-real, rollout supervisionado e release final.

## 1. Objetivo

Levar o projeto do estado atual — branch de trabalho com alterações locais,
documentação parcialmente divergente e automação ainda não qualificada no
portal — a um estado final em que:

1. apenas a branch `main` exista localmente;
2. todo código e documento necessário esteja rastreado e revisado;
3. lixo e duplicatas locais tenham sido removidos por manifesto auditável;
4. dados privados, evidências e entregas autorizadas estejam preservados;
5. testes locais e de pacote tenham baseline reproduzível;
6. o fluxo automático tenha sido qualificado com evidência real;
7. a liberação progressiva possa ocorrer sem reenvio cego nem escrita parcial;
8. README, plano, handoff e artefato final descrevam o mesmo estado.

## 2. Estado de partida confirmado

- Branch ativa `codex/fundamentacao-automatico`, 94 commits à frente de `main`.
- 32 arquivos rastreados modificados e 10 novos não rastreados após a auditoria.
- Nenhum arquivo em stage e nenhum remoto Git configurado.
- `codex/transfer-quiescence` replica um patch já presente na branch ativa.
- O plano híbrido em `docs/superpowers/plans/` está ignorado pelo `.gitignore`.
- Gates atuais: extensão 287/287; Python portátil 34/34; menu 83/83.
- A suíte Python ampla não terminou dentro da janela observada.
- Lote real 1/50: 50 processos, 1.037 PDFs completos no transporte.
- ZIP mais novo: `fase11k`, SHA-256
  `85BAD2192F6F3C7289F574D4EF126F4700565843AFB5793E61E49CD47DE05FBB`.
- `real_send_enabled=false` e `pilot_enabled=false`.

## 3. Autoridades e limites

- A Área Restrita decide escopo, marcador, interessado, ação pendente e
  resultado remoto.
- O e-Contas fornece documentos e eventos; não promove elegibilidade.
- A resolução/documentos fundamentam os seis campos obrigatórios.
- `genero` pode permanecer vazio; modalidade, fundamento, DOE, cargo,
  matrícula e nascimento são obrigatórios.
- Nenhum dado ausente autoriza escrita parcial.
- Teste sintético, fixture, health check ou ZIP não prova efeito remoto.
- Resultado incerto vira `unconfirmed`; nunca há reenvio automático.
- O primeiro envio e qualquer ampliação de lote exigem checkpoint humano.

## 4. Modelo de limpeza

Todo item local será classificado antes de qualquer remoção:

| Classe | Tratamento |
|---|---|
| fonte versionada | preservar e revisar |
| documentação versionada | preservar, reconciliar e rastrear |
| entrega autorizada | preservar com tamanho/hash/índice |
| dado privado operacional | preservar fora do Git |
| evidência necessária | preservar com referência no handoff |
| cache ou staging reproduzível | candidato a quarentena |
| duplicata byte a byte | reter cópia canônica e quarentenar as demais |
| artefato desconhecido | não remover; investigar ou quarentenar |
| perfil/sessão ativa | nunca mover enquanto houver processo ou dependência |

A limpeza terá analisador somente leitura, manifesto e limpador separado. O
limpador operará em `WhatIf` por padrão, moverá primeiro para quarentena e só
apagará definitivamente após validação e aprovação específica.

## 5. Estado Git desejado

- Todos os commits necessários chegam a `main` por fast-forward quando a
  ancestralidade permitir.
- Alterações locais são revisadas e commitadas em unidades coerentes antes da
  troca de branch.
- `codex/transfer-quiescence` só é removida após comprovar equivalência do
  patch e presença do conteúdo em `main`.
- `codex/fundamentacao-automatico` só é removida após `main` apontar para o
  mesmo commit e os gates pós-consolidação passarem.
- Resultado final de `git branch --format` contém apenas `main`.
- Remoto privado é opcional e depende de decisão explícita; não será inventado.

## 6. Estado funcional desejado

O fluxo final deve provar, em ordem:

1. análise somente leitura e lotes determinísticos;
2. aquisição e preparação idempotentes;
3. OCR fallback em documento portal-real sem texto nativo;
4. três preflights reais sem envio;
5. primeiro envio supervisionado e resultado observado;
6. reabertura e conferência do estado persistido;
7. fixture sanitizada e qualificação versionada;
8. lote piloto de até cinco atos;
9. rollout progressivo com pausa por conflito, ausência ou incerteza;
10. relatório final e pacote reprodutível.

## 7. Critérios globais de conclusão

- `main` é a única branch local e o worktree está limpo.
- Não há plano necessário oculto por `.gitignore`.
- Manifesto de limpeza registra decisão, hash, origem e destino de cada item.
- Nenhum PDF, token, cookie, CPF bruto, perfil ou dado privado entra no Git.
- Todas as suítes definidas no plano terminam com contagem e status conhecidos.
- A suíte ampla não fica “verde por ausência de resultado”.
- O primeiro envio e o lote piloto possuem evidência portal-real auditável.
- O pacote final é extraído em pasta limpa e passa auditoria/smokes.
- README, plano mestre, handoff e release apontam para o mesmo ZIP/hash.
- Qualquer pendência remanescente tem causa, impacto e retomada documentados.

