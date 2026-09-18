# Smoke supervisionado do R3 — passo a passo (2026-09-17)

Preenchimento supervisionado do pacote validado. **Não** inclui envio/finalização.
`autoSubmit=false` e `real_send_enabled=false` continuam a fronteira.

Pacote usado: `C:\Users\slvma\Downloads\Github\Atos-TCE\outputs\qa-extract-2026-09-17`
(extração do ZIP `Atos-TCE-Professor-IPERN-completo-2026-09-17.zip`,
SHA-256 `cf64e3f8f5e5703fd6a2be11dea729458e816517a00e1958f56ad5088c8276bf`), aprovada
7/7 no `TESTAR-PACOTE.ps1`.

## 0. Checagens antes de abrir o portal

Rodar na raiz do repositório (`C:\Users\slvma\Downloads\Github\Atos-TCE`).

**0.1 Dataset íntegro**

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\outputs\check-dataset-status.ps1 -Root .\outputs\qa-extract-2026-09-17
```

Esperado: `IsPresent=True`, `IsValid=True`,
`LogicalSha256=81cf7eab4fd14db43c492db0a5f6e2944ac890cb251b16bc3fb14049defeba30`,
`ProcessCount=724`, `RecordCount=739`.

**0.2 Nenhuma execução pendente para reconciliar**

```powershell
& '.\outputs\qa-extract-2026-09-17\runtime\python\python.exe' -B .\outputs\smoke-pending-check.py '.\outputs\qa-extract-2026-09-17\acervo-tce\automacao\execucoes.sqlite3'
```

Esperado: todas as tabelas com `= 0`.

**0.3 Revisão do contexto jurídico vigente**

```powershell
$pkg = 'C:\Users\slvma\Downloads\Github\Atos-TCE\outputs\qa-extract-2026-09-17'
$ptr = Join-Path $pkg 'acervo-tce\publicacao-atual.json'
if (Test-Path -LiteralPath $ptr) { (Get-Content -LiteralPath $ptr -Raw | ConvertFrom-Json).revision } else { 'sem publicacao-atual.json -> revisao 0 (dataset do sidecar)' }
```

**0.4 Fronteira de envio**

Não iniciar ponte nem piloto. Sem `acervo-tce\automacao\qualificacao.json` real, a ponte
informa `real_send_enabled=false` e o painel mantém o controle de envio automático
desabilitado. Conferir visualmente no painel antes de preencher.

## 1. Subir o pacote e carregar a extensão

```powershell
Set-Location 'C:\Users\slvma\Downloads\Github\Atos-TCE\outputs\qa-extract-2026-09-17'
.\INICIAR.cmd            # menu + serviço local; opção 5 abre o HTML de conferência
.\INICIAR.cmd abrir-mesa # alternativa direta para abrir o HTML
```

Extensão: Chrome → `chrome://extensions` → Modo do desenvolvedor → **Carregar sem
compactação** → `<pacote>\extensao-complementar-ato`. Usar perfil dedicado, nunca o pessoal.

## 1.1 Escolha dos atos (atalho)

O contexto jurídico do pacote tem 739 identidades: 679 `complete`, 49 `conflict`,
7 `incomplete` e 4 `missing`. Para localizar candidatos rapidamente:

```powershell
& '.\outputs\qa-extract-2026-09-17\runtime\python\python.exe' -B .\outputs\smoke-candidates.py '.\outputs\qa-extract-2026-09-17'
```

Use um processo `complete` para tentar o **caso A** (contexto utilizável; AUTO ainda depende
do catálogo do portal e dos limiares) e um `conflict`/`incomplete`/`missing` para o **caso B**
sem depender de sorte.

## 2. Portal (login manual)

1. Fazer login manualmente na Área Restrita (nenhuma credencial por automação).
2. Em **Processos no Setor**, selecionar manualmente o marcador vigente e clicar em
   **Consultar**.
3. No painel da extensão, deixar **Marcador do lote (opcional)** vazio: a automação lê o
   marcador já selecionado e pausa para revisão se ele mudar.

## 3. Painel: importar dados e atualizar prévia

1. **Importar/Atualizar dados** → `<pacote>\acervo-tce\dados-complementar-ato.json`.
2. Abrir o ato do interessado no portal e clicar em **Atualizar prévia**.
3. Abrir a aba **Detalhes** → seção **Fundamentação jurídica**.

Evidência do painel (DevTools no painel: clique com o botão direito → Inspecionar):

```js
(() => {
  const d = document.querySelector('#panel-details-view');
  const c = document.querySelector('[data-field="fundamento_legal"]');
  return { detalhes: d ? d.innerText : 'sem detalhes', campo: c ? c.innerText : 'sem card' };
})()
```

## Caso A — decisão AUTO

Esperado no painel: `Regras: legal-foundation-v3`; `Contexto jurídico: disponível` ou
`reconstruído`; `Estado: seleção automática`; `Fundamento legal: será preenchido`; candidato
principal preenchido.

1. Anotar **Candidato principal** e a linha `Proposta:` do card do fundamento.
2. Clicar em **Preencher campos disponíveis**.
3. Ler o `<select>` no portal (DevTools na página do portal):

```js
(() => {
  const s = document.querySelector('[name="txtFundamentoLegal"]');
  return s ? { value: s.value, label: s.selectedOptions[0]?.textContent?.trim() ?? null } : 'select ausente';
})()
```

4. Exigir igualdade: `label` do portal === `Proposta:` do painel; o `value` é o
   `legalDecision.option_value` autorizado (o content script só escreve quando
   `decision.option_value === proposedValue`, coberto por teste).
5. Qualquer divergência: **parar** a sessão e registrar.

## Caso B — decisão não-AUTO

1. Abrir um ato com `Estado` diferente de seleção automática (revisão necessária, empate
   real, contexto bloqueado ou conflito documental) — ou `Proposta segura: nenhuma`.
2. Ler o `value` atual do `<select>` antes de preencher (mesmo snippet do caso A).
3. Clicar em **Preencher campos disponíveis**.
4. Conferir: o `<select>` do fundamento **não mudou**; o resumo da execução lista o
   fundamento em *Preservados*; os demais campos elegíveis foram preenchidos normalmente.

## Caso C — refresh e revisão

1. Clicar em **Atualizar prévia** novamente e comparar `Contexto jurídico`, `Origem`
   (`cache` / `sidecar` / `evidências locais`) e `Estado` com a revisão do passo 0.3.
2. Se o dataset for reimportado (nova revisão), a decisão do painel deve refletir a nova
   evidência — nunca reaproveitar contexto antigo silenciosamente.
3. Se `Origem` mostrar `evidências locais` (reconstruído), confirmar que o resultado
   apresentado corresponde à reconstrução, não ao cache anterior.

## Encerramento

1. Não clicar em enviar/finalizar; não habilitar envio automático; não alterar
   `real_send_enabled`.
2. Gravar a evidência localmente, fora do Git:
   `<pacote>\dados-locais\smoke-r3-AAAAMMDD-HHMM.md` com processo/interessado, estados,
   proposta, `value`/`label` lidos do portal e horários. Sem CPF, matrícula, token, cookie,
   HTML privado ou URL autenticada.
3. Encerrar: ` .\INICIAR.cmd parar` (se o serviço foi iniciado) e fechar o Chrome.

## O que reprova o smoke

- valor selecionado no portal diferente da proposta autorizada;
- fundamento escrito em estado não-AUTO;
- decisão antiga reapresentada como atual depois de mudança de evidência;
- qualquer tentativa de envio/finalização ou de habilitar envio automático.
