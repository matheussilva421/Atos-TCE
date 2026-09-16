# Handoff — gravação da Área Restrita e pasta pronta (16/09/2026)

## Resultado

O runner de qualificação agora grava a sessão manual em dois níveis:

- `observacao-portal-real.json` contém a fotografia estrutural sanitizada;
- `recording.json` contém cliques, mudanças, tentativas de envio, navegações,
  console e falhas em formato estrutural, sem valores de campos;
- `trace.zip` e `network.har` ficam privados em `dados-locais`.

O runner nunca digita credenciais, preenche atos, conclui ou envia. O trace e o
HAR são brutos e privados; não devem ser compartilhados.

## Pasta pronta

A pasta de trabalho descompactada está em:

`outputs/TCE-fixed-2026-09-16`

Ela contém o acervo privado, 739 registros, 14.179 PDFs, JSONs, extensão
`1.1.0`, ponte, runtime e o código local do gravador. O launcher é:

`outputs/TCE-fixed-2026-09-16/INICIAR-CAPTURA-AREA-RESTRITA.cmd`

Locks e solicitações de transferência órfãos foram removidos. Não há
`service.json` antes da inicialização; a ponte o cria com um novo código de
pareamento.

## Validação

- `python -m unittest test_real_portal_session test_automation_qualification test_qa_workflow -q`: 56/56, 0 falhas.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1 -TimeoutSeconds 900`: 1.174 checks, 1.172 aprovados, 0 falhas, 2 skips.
- Runner copiado para a pasta pronta: hash igual ao fonte.
- `portal-submit.js` na pasta pronta contém o observador de resultado atualizado.
- Acervo conferido: 739 registros e 14.179 PDFs.

## Ação humana necessária

Execute o launcher na pasta pronta e faça o login manualmente no Chrome que
abrir. Navegue até `ProcessonoSetor.asp`, escopo finalístico e marcador `6189`.
O runner registrará as ações enquanto a janela permanecer aberta. Ao terminar,
pressione `Ctrl+C`; a ponte será encerrada pelo launcher.

Ainda não foram executados preflights reais nem qualquer envio. Depois da
captura, revisar a observação e executar os três preflights sem concluir o ato.
Qualquer envio exige autorização imediata e específica, um ato por vez.

## GitHub

Estado final: `main` e `origin/main` estão alinhadas em `bd949c5`
(`feat: record structural portal qualification sessions`). O commit e o push
foram confirmados. A pasta em `outputs/` é privada e ignorada pelo Git.
