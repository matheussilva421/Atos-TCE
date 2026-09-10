# Lote 1/50 — campos incompletos

Data da leitura: 10/09/2026.

Fonte: `work/tce-extractor/outputs/live-real-fase11h-sector-lot50/publicacoes/120/resultados.json`, revisão 120 da preparação progressiva do lote congelado pelo marcador `PROFESSOR - IPERN - 2 RUBRICAS (549)`.

## Resumo

- 50 processos analisados;
- 51 registros de interessado (um processo possui dois interessados);
- 50 processos aparecem como `partial` porque pelo menos um dos sete campos da allowlist não foi encontrado;
- `genero`: ausente nos 51 registros;
- `data_nascimento`: ausente em 9 registros;
- `modalidade`: ausente em 1 registro;
- `fundamento_legal`: ausente em 1 registro;
- `data_publicacao_doe`, `cargo` e `matricula`: encontrados nos 51 registros.

Regra operacional confirmada pelo usuário: `genero` pode permanecer ausente e não bloqueia a preparação automática. Todos os demais campos da allowlist — `modalidade`, `fundamento_legal`, `data_publicacao_doe`, `cargo`, `matricula` e `data_nascimento` — são obrigatórios; a ausência de qualquer um deles bloqueia o preflight e impede escrita parcial.

## Processos com data de nascimento ausente

- 100012/2026
- 101577/2026
- 102260/2026
- 102326/2026
- 102381/2026
- 103777/2025
- 104280/2025
- 104338/2025
- 104956/2025 (apenas um dos dois registros de interessado)

## Processo com modalidade e fundamento legal ausentes

- 104956/2025 — o segundo registro de interessado não teve `modalidade` nem `fundamento_legal` encontrados. O primeiro registro do mesmo processo teve esses campos.

## Processos com somente gênero ausente

100065/2026, 100120/2026, 100182/2026, 100271/2026, 100273/2025, 100278/2025, 100295/2026, 100394/2025, 100455/2025, 100463/2025, 100506/2025, 100577/2025, 101320/2026, 101356/2026, 101363/2026, 101456/2026, 101531/2026, 101731/2026, 101737/2026, 102256/2026, 102262/2026, 102291/2026, 102325/2026, 102380/2026, 102388/2026, 102390/2026, 103455/2025, 103477/2025, 103795/2025, 103830/2025, 104099/2025, 104292/2025, 104293/2025, 104592/2025, 104657/2025, 104975/2025, 105215/2025, 105223/2025, 105235/2025, 105240/2025.

## Correção da contagem anterior

A mensagem anterior informou “40 `partial`”. A leitura da revisão 120 mostra que a preparação progressiva tem 50 resultados `partial`; os 10 `complete` pertenciam ao status de sincronização do checkpoint de coleta, não ao status final dos resultados de análise. A contagem correta para a qualificação dos campos é, portanto, 50/50 processos `partial`, por causa principalmente de `genero` ausente.

Nenhum ato foi aberto, preenchido ou enviado para produzir este relatório.

## Regra implementada — 10/09/2026

- [x] Preflight automático permite `genero` ausente e simplesmente preserva o
  controle vazio do portal.
- [x] Preflight automático bloqueia ausência de modalidade, fundamento legal,
  data de publicação no DOE, cargo, matrícula ou data de nascimento com
  `FIELD_PROPOSAL_MISSING`.
- [x] Teste dedicado cobre o caso permitido e cada um dos seis campos
  obrigatórios; a suíte da extensão passou com 287/287 testes.
