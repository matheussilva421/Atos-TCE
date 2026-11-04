# Benchmark sintético — Complementador e-Contas

> Nota: este benchmark é histórico da build anterior, com fixture de uma página e sem descoberta de documentos. As medições reais da build final estão em `qa-real-2026-11-04.md`.

- Data: 04/11/2026
- Navegador: Microsoft Edge 156.0.4314.58 (motor Chromium), perfil temporário de teste
- Node.js: 24.15.0
- Extensão: build de teste, dist-test, permissões limitadas ao servidor local
- Fixture: uma página HTML com formulário sintético, iframe de autos e PDF sintético de 1 página (877 bytes)
- Medição: performance.now() do clique em "⚡ Preencher" até a resposta final e readback
- Amostras: 7

| Amostra | Tempo (ms) |
|---|---:|
| 1 | 232 |
| 2 | 192 |
| 3 | 156 |
| 4 | 138 |
| 5 | 133 |
| 6 | 111 |
| 7 | 116 |

- p50: **138 ms**
- p95: **232 ms**

## Limitações

- Medição sintética, não é SLA nem prova de desempenho no e-Contas real.
- O PDF sintético é nato-digital, curto e de uma página; documentos maiores, digitalizações e o visualizador real podem ser mais lentos.
- A meta experimental de ~1 segundo para PDF nato-digital curto não é garantida.
- O acesso real aos bytes do PDF no portal foi verificado no Chrome QA; o Chrome profissional continua pendente de recarga autorizada.
