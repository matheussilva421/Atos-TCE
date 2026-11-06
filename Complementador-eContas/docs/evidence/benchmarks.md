# Benchmark sintético — Complementador e-Contas

- Data: 05/11/2026
- Navegador: Microsoft Edge 156.0.4314.58 (motor Chromium), perfil temporário de teste
- Node.js: 24.15.0
- Extensão: build de teste, dist-test, permissões limitadas ao servidor local
- Fixture: uma página HTML com formulário sintético, iframe de autos e PDF sintético de 1 página (877 bytes)
- Medição: performance.now() do clique em "⚡ Preencher" até a resposta final e readback
- Amostras: 7

| Amostra | Tempo (ms) |
|---|---:|
| 1 | 704 |
| 2 | 476 |
| 3 | 414 |
| 4 | 428 |
| 5 | 424 |
| 6 | 421 |
| 7 | 437 |

- p50: **428 ms**
- p95: **704 ms**

## Limitações

- Medição sintética, não é SLA nem prova de desempenho no e-Contas real.
- O PDF sintético é nato-digital, curto e de uma página; documentos maiores, digitalizações e o visualizador real podem ser mais lentos.
- A meta experimental de ~1 segundo para PDF nato-digital curto não é garantida.
- O acesso real aos bytes do PDF foi verificado no Chrome QA; o Chrome profissional segue pendente. Esta medição é da build de teste atual, não do portal real.
