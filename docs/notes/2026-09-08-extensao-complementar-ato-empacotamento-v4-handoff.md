# Handoff — empacotamento v4 da extensão Complementar Ato — 08/09/2026

## Resumo

Foi criado um empacotador oficial, reproduzível e independente de `Get-FileHash`
para gerar um ZIP somente da extensão. A allowlist é explícita; arquivos de
teste, documentação, runtime, acervo e credenciais ficam fora do artefato.

## Artefato

- Caminho: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\extensao-complementar-ato-2026-09-08-v4.zip`
- Tamanho: `33440` bytes
- SHA-256: `8B0BBBA8131EA1D9B8156AAC60D374A85ED1D16D2AF1B55C77D1809ADCF61E46`
- Raiz interna: `extensao-complementar-ato/`
- Entradas: `11`

## Conteúdo

```text
manifest.json
background/service-worker.js
content/form-detector.js
lib/bridge-client.js
lib/matcher.js
lib/messages.js
lib/normalizer.js
lib/schema.js
sidepanel/panel.css
sidepanel/panel.html
sidepanel/panel.js
```

## Reprodução e verificação

Comando:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\empacotar-extensao-complementar-ato.ps1 -OutputPath <destino>\extensao-complementar-ato.zip
```

O script exige `-Force` para sobrescrever destino existente, copia somente a
allowlist, rejeita reparse points, valida as entradas internas e calcula SHA-256
com .NET para funcionar no Windows PowerShell disponível.

- `python -m unittest test_extension_zip_packager -q`: 1 pass, 0 falhas.
- `python -m unittest discover -s . -p 'test_*.py' -q`: 250 pass, 3 skips, 0 falhas.
- ZIP extraído em pasta temporária e smoke Chrome: pass; Chrome 145; 7 linhas,
  persistência após restart, troca de processo, empate recalculado e controles
  protegidos intactos.
- CRC e allowlist: 11 entradas, 0 fora do escopo.
- `test_review_live_browser.py`: 1 pass; seleção publicada chega à mesa em menos de
  2 s e pausa/retomada manual foram verificadas em navegador local autenticado.

## Retomada

1. Conferir o SHA-256 acima antes da distribuição.
2. Extrair o ZIP em pasta nova.
3. Em `chrome://extensions`, ativar Modo do desenvolvedor e usar “Carregar sem
   compactação” apontando para `extensao-complementar-ato`.
4. Fazer o pareamento local novamente, pois tokens não são transportados.

QA autenticada no portal real, benchmark dos mesmos 20 processos e teste em
segundo PC continuam gates externos não executados.
