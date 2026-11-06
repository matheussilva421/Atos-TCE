# Relatório de homologação — Complementador e-Contas 2.0.0

Data: 06/11/2026
Ambiente: Chrome QA isolado com build de salvamento habilitado
Autorização: um lote de 25 processos examinados e até 10 salvamentos
Veredito: `RELEASE_2.0_READY` / `G7_PENDING_HUMAN_ACCEPTANCE`

## Configuração

- Filtros: **Mutirão - Educação**; **ATO COMPLEMENTADO = Não**; **ProcessosNoSetor=true**; **semDistribuicao=true**.
- Captura: 25 pendentes, 0 concluídos, 0 sem status.
- Build de homologação: `work/qa-save-build-2026-11-05`, background SHA-256 `C69E92C062FE810F3C98F63CF8FDCCAC6F21FC2BE60C5F5EB23537B2A832CBDB`.
- Flags: execução true, salvamento true, fill-only false.
- Build 2.0.0 de entrega: background SHA-256 `50E2CE856CD2C49E4FD605B94AD7E4C3F2D6865478C014DC10502C8E404B2D03`. O delta em relação ao build homologado é apenas o fechamento das abas após `CONFIRMED`, testado em unitários e navegador.

## Resultado operacional

| Métrica | Valor |
| --- | ---: |
| Processos distintos examinados | 25 |
| Eventos `BEGIN_PROCESS` | 26 (uma recaptura do primeiro item) |
| Atos preenchidos | 10 |
| Atos salvos | 10 |
| Atos confirmados pelo motor | 10 |
| Atos confirmados por verificação independente | 10 de 10 |
| Revisão | 15 |
| Salvamentos incertos | 0 |
| Tentativas de salvamento | 10 |
| Duração total | 243 s |
| Tempo por processo | p50 10,4 s; p95 23,5 s; máximo 31,9 s |

A execução diagnóstica inicial de 1/1 examinou um processo com múltiplos interessados e não salvou. O lote 25/10 seguinte recapturou a página e concluiu os 25 examinados e 10 salvos.

## Motivos de revisão

| Motivo | Quantidade |
| --- | ---: |
| `MULTIPLE_INTERESTED` | 9 |
| `DOCUMENT_NOT_FOUND` | 3 |
| `GUIA_NOT_MATCHED` | 2 |
| `FIELD_NOT_PRESENT` | 1 |

Os documentos ausentes registraram campos como `matricula`, `dataNascimento`, `cargo` e `modalidade`, sem invenção de valores. Nenhum processo de revisão foi salvo.

## Verificação independente

Para cada um dos 10 processos `CONFIRMED`, foi aberta uma aba nova na rota `#/dashboard/complementar-ato/<id>`, sem clicar em salvar. Em **10/10**:

- a rota e o processo conferiram;
- o formulário estava renderizado;
- o botão “Complementar ato” não estava presente.

Nenhum **mark_uncertain**, nenhum segundo clique e nenhuma tentativa além das 10 confirmadas. Os quatro atos antigos não foram tocados.

## Testes e build

| Verificação | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **326 PASS**, 0 FAIL |
| `npm run test:browser` | **24 PASS**, 0 FAIL |
| `npm run build` / `build:test` | PASS |
| Extração do ZIP 2.0.0 | PASS, hashes conferidos |
| Build seguro 0.1.1 | preservado como rollback |

## ZIP 2.0.0

- Arquivo: `release/Complementador-eContas-2.0.0.zip`
- Bytes: 645.261
- SHA-256: `5606E669696FBF734BBFC01D197731D60EBA95393F3FC7519088C9E652E7A13A`
- Versão do manifesto: 2.0.0
- Conteúdo: manifest, bundles e `vendor/pdf.worker.mjs`; sem PDFs, dados pessoais ou documentação.

## Abas

- Processos `CONFIRMED` agora fecham as duas abas de trabalho automaticamente após o ACK.
- Processos em revisão, falha ou incerteza mantêm as abas para conferência; nenhuma aba com estado pendente é fechada.
- Nesta sessão, as abas remanescentes dos atos salvos foram fechadas; permaneceram apenas a listagem e abas de revisão.

## Gates

| Gate | Estado |
| --- | --- |
| F0 baseline/backup | PASS |
| F1 salvamento/checkpoint | PASS |
| F2 experiência/estabilidade | PASS |
| F3 classificação de campos | PASS; revisões reais classificadas |
| F4 MV3 | PARTIAL — kill físico do worker não executado |
| F5 cache/segurança | PASS sintético; autosave `UNKNOWN` |
| F6 suítes | PASS — 326 unitários, 24 navegador |
| F7 H2 adaptador | PASS — 10 salvamentos reais, 10/10 verificados |
| F8 H3 lote | PASS — 25 examinados, 10 salvos, 0 incertos |
| F9 Chrome profissional | NOT_RUN — não instalado por decisão de escopo |
| G7 aceite | PENDENTE — revisão/aceite do operador |

## Limitações e riscos

- O kill físico do service worker/reinício do navegador continua `MV3_WORKER_KILL_TEST_NOT_RUN`; a lógica está coberta por testes puros/estáticos.
- Autosave do portal permanece `UNKNOWN`.
- O Chrome profissional não foi tocado.
- A homologação real ocorreu no build QA 0.1.1 com o mesmo caminho de preenchimento/salvamento; o build 2.0.0 acrescenta apenas a limpeza pós-save das abas, coberta por testes.
- Rollback de código não desfaz ato já gravado no e-Contas; reversão institucional segue o procedimento oficial.

## Instalação e rollback

1. Extrair `Complementador-eContas-2.0.0.zip` em pasta local.
2. Abrir `chrome://extensions`, ativar modo desenvolvedor e carregar a pasta extraída.
3. O lote só começa após clique explícito em “⚡ Rodar automação”; não há início automático.
4. Rollback: remover/desativar a 2.0.0 e carregar o backup `work/batch-final-baseline-2026-11-05` (ou o candidato seguro 0.1.1). Nenhum ato já salvo é revertido pelo rollback.
