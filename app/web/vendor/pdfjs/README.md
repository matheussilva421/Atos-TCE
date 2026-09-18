# PDF.js vendor slot

The review desk uses the locally pinned PDF.js 5.7.284 build when served by the
portable package. Its license and exact SHA-256 values are recorded in
`manifest.json`; no CDN or floating `latest` URL is permitted. The browser PDF
viewer remains the manual fallback if a restricted browser blocks module work.
