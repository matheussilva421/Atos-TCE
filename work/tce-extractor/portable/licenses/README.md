# Licenças e proveniência do runtime portátil

O runtime é montado somente durante a construção. Esta pasta acompanha o
pacote final e deve permanecer junto dos binários redistribuídos.

Componentes fixados:

- Python embutido 3.14.4, da fonte oficial Python.org. O construtor copia o
  `LICENSE.txt` presente no arquivo oficial para `licenses/Python/`.
- PyMuPDF 1.28.2, wheel Windows amd64 obtido do PyPI. O construtor copia os
  arquivos de licença presentes no `.dist-info` para `licenses/PyMuPDF/`.
- Tesseract 5.4.0.20240606, instalador NSIS Windows amd64 da UB Mannheim. O
  instalador verificado é extraído com o `7z.exe` temporário; binários, idiomas
  e avisos são copiados somente da árvore extraída para `licenses/Tesseract/`.
  O modelo português `por.traineddata` é baixado separadamente do repositório
  oficial `tessdata_fast`, verificado por SHA-256 e materializado nessa mesma
  árvore temporária antes da cópia.

`runtime-manifest.json` registra as URLs HTTPS, versões, hashes SHA-256 dos
artefatos de origem e hashes/tamanhos dos arquivos efetivamente incluídos.
O SHA-256 do instalador Tesseract é um valor observado porque o upstream não
publica checksum; o builder exige o valor fixado e falha em qualquer mudança.

O builder nunca executa o instalador Tesseract, não instala Python, PyMuPDF ou
Tesseract no computador de destino e não aceita `TesseractSource` nem uma
instalação local como fonte. Durante os gates, o `PATH` do processo é
temporariamente restrito ao sistema; os executáveis testados são sempre os
caminhos absolutos do build temporário. A árvore extraída precisa conter
`tesseract.exe`, DLLs, os idiomas `por`, `eng` e `osd`, documentação de licença
e a versão exata fixada.

As licenças não concedem uma licença comercial do PyMuPDF/Artifex. Verifique
se o uso do pacote sob AGPL ou uma licença comercial é adequado ao projeto.
