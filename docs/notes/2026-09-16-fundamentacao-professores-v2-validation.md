# Validação da matriz de fundamentação legal de professores v2

## Escopo

Matriz sintética table-driven para o crosswalk entre fundamentos documentais e o catálogo civil do portal. O fixture é `work/tce-extractor/tests/fixtures/legal-foundations-professores-v2.json` e o teste executável é `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-legal-crosswalk.test.mjs`.

## Cobertura

| Grupo | Casos | Resultado |
|---|---:|---|
| Aposentadoria voluntária integral | 4 | 3 selected/AUTO, 1 review/manual |
| Aposentadoria voluntária proporcional | 3 | 3 selected/AUTO |
| Incapacidade | 3 | 3 selected/AUTO |
| Ambíguo | 1 | 1 review/manual |
| Negativo civil × catálogo militar | 1 | 1 pending, sem AUTO |
| **Total** | **12** | **9 selected, 2 review, 1 pending** |

Todos os 12 casos possuem `scope` esperado, classe/opções de catálogo controladas e resultado esperado de `automatic`. O teste também verifica que cada perfil produz evidência funcional.

## Resultado executado

Comando:

```text
node --test portable/extensao-complementar-ato/tests/portal-legal-crosswalk.test.mjs
```

Resultado:

- 5 testes executados;
- 5 aprovados;
- 0 falhados;
- matriz de 12 casos exercitada dentro do teste table-driven;
- 0 falso AUTO na matriz: o caso docente com margem `0.1085` e o caso sem artigo ficam em `review`; o caso civil contra catálogo militar fica `pending`.

## Classificação da evidência

- `PASS_FIXTURE`: matriz sintética verde, incluindo regras de rejeição, margem e ausência de classe compatível.
- `NOT_TESTED`: dados reais anonimizados de processos não foram adicionados neste worktree.
- `BLOCKED`: não há evidência de login/portal real nem autorização para preencher ou enviar atos; a matriz não substitui o preflight manual com usuário autenticado.

## Próxima validação necessária

Antes de qualquer promoção para uso real, adicionar pelo menos seis documentos anonimizados representativos, preservar o fundamento original, revisar manualmente cada mapeamento e executar o preflight isolado sem envio. Casos não cobertos ou com conflito devem permanecer em `review`/`pending`.
