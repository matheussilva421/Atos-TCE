# Estado atual canônico — 2026-09-24

## Git

Branch de retomada:

```text
codex/atos-tce-unified
HEAD dcb9086fe5fdffe89022bfc14c07a85e728232df
```

No momento da revisão, a branch está **44 commits à frente de `main` e 0 atrás**.

Não recriar as antigas branches de implementação como fonte de verdade. A reconciliação de 24/09 consolidou o trabalho relevante na branch unificada.

## Best-Effort / Legal v4

### Implementado e coberto por testes

- catálogo canônico de opções legais selecionáveis;
- `legal-foundation-v4` com melhor opção disponível determinística;
- preflight best-effort por campo;
- valores divergentes existentes preservados;
- formulário legível mesmo com controle de conteúdo individual ausente;
- filler por campo;
- `field_results`;
- stale generation com uma releitura/replanejamento;
- resultado parcial sem corromper status documental;
- processo permanecendo `PRONTO` quando ainda existem pendências;
- UI da Mesa com alterados/preservados/revisar;
- integração backend/extensão.

**Não executar novamente Tasks 1–9 como trabalho novo.**

### Pendente

Task 10: **validação supervisionada no portal real**.

Faltam os cinco casos legais reais e o caso operacional no qual um campo falha mas campos independentes continuam sendo preenchidos.

Nenhum clique final deve ser automatizado.

## Próximo Processo

Nenhuma Task 1–8 de produção foi implementada.

A Phase 0 de discovery está parcialmente concluída.

### Evidência já obtida

```yaml
navigation_strategy: native_control
marker_restore: not_needed
```

Foi observado que o controle nativo `Proc./ Doc. Eletrônicos` retorna do formulário à lista nas amostras e preserva o marcador observado.

Também foram observados:

- lista e quadro de botões em frames distintos;
- abertura por identidade;
- transição lista -> ato -> interessado -> formulário;
- travessia de fronteira de página;
- interessado único em casos amostrados;
- retorno nativo aproximado em ~1,2 s;
- navegação manual para formulário em amostras de ~3,0 a 4,9 s.

### Gates ainda abertos

1. obter `SCAN_PAGE` vivo da Mesa/extensão atual;
2. confirmar valor bruto vivo do marcador;
3. explicar/reconciliar `1198` itens do scan salvo versus `1197` observados;
4. observar retorno após clique final realizado manualmente pelo operador;
5. medir baseline estrita após ato concluído/revisado;
6. observar caso multi-interessado se houver caso controlado disponível;
7. fechar e commitar a nota de discovery.

**Não iniciar `navigation_service.py`, `OPEN_NEXT_ACT` ou Tasks 1–8 antes disso.**

## Baseline registrado na reconciliação

No handoff de reconciliação de 24/09 foram registrados:

- Python: 616 executados, 615 aprovados, 0 falhas, 1 skip;
- extensão: 145 aprovados;
- web: 28 aprovados;
- `verify-project.ps1`: todos os sete estágios verdes;
- `git diff --check`: verde.

Reexecutar esses gates no HEAD atual antes de qualquer nova implementação.

## Segurança preservada

- não existe novo submit/finalize automático;
- identidade e generation continuam guardas globais;
- alvo ambíguo não pode ser escolhido por ordem de frame;
- valores de select devem pertencer ao catálogo atual;
- o clique final de **Complementar Ato** continua manual.