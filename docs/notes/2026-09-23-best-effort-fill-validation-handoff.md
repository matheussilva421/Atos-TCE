# Handoff — validação Best-Effort / legal-foundation-v4

**Estado:** implementação e gates locais verdes; validação supervisionada na Área Restrita pendente de sessão autenticada do operador.

## Commit testado

- Branch: `codex/best-effort-form-filling`
- SHA: `c13677815dcb0d164f3182ce06681d00ea0e8c19`
- Os dois commits finais de correção neste bloco são `576904d` e `c136778`.

## Gates automatizados

| Comando | Resultado |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py' -q` | 603 executados; 602 passaram; 0 falhas; 1 skip |
| `npm test --prefix extension` | 143 passaram; 0 falhas |
| `node --test app/web/tests/*.test.mjs` | 24 passaram; 0 falhas; warning não bloqueante `MODULE_TYPELESS_PACKAGE_JSON` |
| `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1` | 1.258 executados; 1.256 passaram; 0 falhas; 2 skips; todas as 7 etapas passaram |
| `git diff --check` | passou |

O verificador oficial cobriu extensão, web, Python portátil, PowerShell, pacote/auditoria, automação da raiz e diff. O caminho efetivo no checkout é `work/tce-extractor/verify-project.ps1`; a invocação sugerida pelo plano na raiz (`.\verify-project.ps1`) não existe neste layout.

## Correções de revisão com TDD

- Catálogo legal: RED reproduziu seleção de `EC41` quando a opção estava desabilitada, apesar de haver outra opção selecionável. A leitura agora transporta `disabled` (incluindo grupo desabilitado), legal v4 e preflight ranqueiam apenas opções selecionáveis, e o writer mantém a última guarda. GREEN focal: regras legais 34/34, preflight/serviço 69/69, leitor+writer 31/31.
- Resultado sem campos: RED reproduziu HTTP 400 para `field_results: {}` e request presa em `FILLING`. A API aceita um mapa vazio explícito; o serviço sintetiza campos obrigatórios pendentes, finaliza somente a tentativa, e mantém o processo `PRONTO`. GREEN: API 87/87; teste integrado confirma resumo pendente e retry pelo processo.
- RED adicional reproduziu seleção através de `optgroup` desabilitado; GREEN confirma `option_unavailable`, sem escrita.
- Revisão de código: os dois defeitos acima foram corrigidos. Foram anotados como possíveis smells (duplicação pequena da filtragem de opções e derivação de estado a partir de texto localizado); não alterados neste escopo. Não foi encontrada operação nova de submit/finalização.

## Validação real supervisionada — pendente

Nenhum caso real foi executado ainda. Não havia aba da Área Restrita aberta na sessão Chrome observada. Não substituir evidência real por fixtures ou pelos gates locais.

| Caso obrigatório | Identidade / texto documental / opções DOM / candidatos / escolha / confiança e margem / conflito / campos alterados-preservados-pendentes / releitura / status |
|---|---|
| ECE 20/2020 não literal | PENDENTE — sessão real necessária |
| EC 41/2003 | PENDENTE — sessão real necessária |
| EC 47/2005 | PENDENTE — sessão real necessária |
| CF art. 40 | PENDENTE — sessão real necessária |
| Correspondência deliberadamente fraca/não literal | PENDENTE — sessão real necessária |

Também falta o caso operacional supervisionado: uma falha isolada de campo não crítico, campos independentes preenchidos e relidos, pendência identificada e processo ainda `PRONTO`/retryable.

## Continuação exata

1. No Chrome do perfil `Matheus`, abrir e autenticar manualmente em `https://novaarearestrita.tce.rn.gov.br` (não compartilhar credenciais com a automação), abrir a lista normal da Área Restrita, selecionar o marcador dinâmico normalmente usado e deixar a lista visível.
2. Avisar quando estiver pronto. Continuar os cinco casos Best-Effort sem clicar em **Complementar Ato**.
3. Em seguida, na branch de discovery baseada no `main` promovido, executar integralmente a PHASE 0 do plano de navegação, registrar frames, retorno, marcador, lista/paginação, interessado, ordem do scan e latências. Nenhum código de navegação antes de a nota ser completa e commitada.
4. A PHASE 0 solicita observar o resultado de **Complementar Ato** manual. Não automatizar esse clique; se esse passo for necessário para fechar a evidência, parar no formulário revisado para o operador executar manualmente e depois continuar a observação.

## Segurança

- Não foi adicionado submit/send/auto-submit/complement/finalize automático; o clique final permanece manual.
- Nenhum PDF, ZIP, perfil, token, HAR ou trace foi incluído no Git.
- Os anexos do goal continuam sendo as entradas canônicas; não foi criada cópia deles no repositório.
