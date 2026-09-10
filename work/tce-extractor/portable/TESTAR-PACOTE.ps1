[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$PackageRoot = ''
)

Set-StrictMode -Version 2.0

if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $PackageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
}

function Add-TcePortableError {
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Errors,
        [Parameter(Mandatory)][string]$Message
    )
    if (-not $Errors.Contains($Message)) { [void]$Errors.Add($Message) }
}

function Get-TceJsonProperty {
    param([AllowNull()][object]$InputObject, [Parameter(Mandatory)][string]$Name)
    if ($null -eq $InputObject) { return $null }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return ,$property.Value
}

function Get-TcePortableRuntimeLayout {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $root = [IO.Path]::GetFullPath($PackageRoot)
    $python = Join-Path $root 'runtime\python\python.exe'
    $pythonPth = Join-Path $root 'runtime\python\python314._pth'
    $tesseract = Join-Path $root 'runtime\tesseract\tesseract.exe'
    $tessdata = Join-Path $root 'runtime\tesseract\tessdata'
    $languages = @('por', 'eng', 'osd')
    $required = @(
        $python,
        $pythonPth,
        $tesseract,
        (Join-Path $root 'runtime\tesseract\libtesseract-5.dll'),
        (Join-Path $root 'runtime\tesseract\libleptonica-6.dll')
    )
    foreach ($language in $languages) { $required += Join-Path $tessdata ($language + '.traineddata') }
    $missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
    [pscustomobject]@{
        PackageRoot = $root; Python = $python; PythonPth = $pythonPth; Tesseract = $tesseract
        Tessdata = $tessdata; Languages = $languages; Required = $required; Missing = $missing
        IsComplete = ($missing.Count -eq 0)
    }
}

function ConvertTo-TcePortableDiagnosticText {
    param([AllowNull()][object[]]$Output)
    $text = (@($Output) | ForEach-Object { [string]$_ }) -join ' '
    $text = $text -replace '\s+', ' '
    $text = $text -replace '(?i)\b(?:authorization|cookie|token|credential|session|password)\b\s*[:=]?\s*[^,; ]+', '[dado removido]'
    if ($text.Length -gt 240) { $text = $text.Substring(0, 240) + '...' }
    return $text.Trim()
}

function Invoke-TcePortableRuntimeProbe {
    param([Parameter(Mandatory)][pscustomobject]$Runtime)
    $errors = New-Object System.Collections.ArrayList
    if (-not $Runtime.IsComplete) {
        Add-TcePortableError $errors 'runtime portatil incompleto; executaveis nao foram chamados'
        return [pscustomobject]@{ IsValid = $false; Errors = $errors.ToArray(); PythonOutput = @(); TesseractOutput = @() }
    }
    $pythonOutput = @()
    try {
        $pythonOutput = @(& $Runtime.Python -B -s -c 'import pymupdf; print(pymupdf.__version__)' 2>&1)
        if ($LASTEXITCODE -ne 0) { Add-TcePortableError $errors ('Python falhou no teste PyMuPDF: ' + (ConvertTo-TcePortableDiagnosticText $pythonOutput)) }
    } catch { Add-TcePortableError $errors 'Python portatil nao pode ser executado' }
    $tesseractOutput = @()
    try {
        $tesseractOutput = @(& $Runtime.Tesseract --tessdata-dir $Runtime.Tessdata --list-langs 2>&1)
        if ($LASTEXITCODE -ne 0) { Add-TcePortableError $errors ('Tesseract falhou no teste de idiomas: ' + (ConvertTo-TcePortableDiagnosticText $tesseractOutput)) }
    } catch { Add-TcePortableError $errors 'Tesseract portatil nao pode ser executado' }
    $observedLanguages = @($tesseractOutput | ForEach-Object { ([string]$_).Trim() } | Where-Object { $Runtime.Languages -contains $_ } | Sort-Object -Unique)
    foreach ($language in $Runtime.Languages) { if ($observedLanguages -notcontains $language) { Add-TcePortableError $errors ('idioma Tesseract ausente em --list-langs: ' + $language) } }
    [pscustomobject]@{ IsValid = ($errors.Count -eq 0); Errors = $errors.ToArray(); PythonOutput = $pythonOutput; TesseractOutput = $tesseractOutput; ObservedLanguages = $observedLanguages }
}

function Add-TcePortableManifestReference {
    param(
        [Parameter(Mandatory)][string]$ExtensionRoot,
        [Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Declared,
        [Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Errors,
        [AllowNull()][object]$Value,
        [Parameter(Mandatory)][string]$Label
    )
    if ($Value -is [string]) {
        $rawPath = [string]$Value
        $normalized = $rawPath.Replace('/', '\')
        if ([string]::IsNullOrWhiteSpace($rawPath) -or [IO.Path]::IsPathRooted($normalized) -or $normalized -match '^[A-Za-z]:' -or $normalized -match '(^|\\)\.\.($|\\)') {
            Add-TcePortableError $Errors ($Label + ': caminho relativo invalido'); return
        }
        $candidate = Join-Path $ExtensionRoot $normalized
        [void]$Declared.Add($normalized.Replace('\', '/'))
        if ($rawPath -match '[*?]') {
            if (@(Get-ChildItem -Path $candidate -File -ErrorAction SilentlyContinue).Count -eq 0) { Add-TcePortableError $Errors ($Label + ': arquivo nao encontrado') }
        } elseif (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { Add-TcePortableError $Errors ($Label + ': arquivo nao encontrado') }
        return
    }
    Add-TcePortableError $Errors ($Label + ': referencia de arquivo ausente ou invalida')
}

function Add-TcePortableManifestListReferences {
    param(
        [Parameter(Mandatory)][string]$ExtensionRoot,
        [Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Declared,
        [Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Errors,
        [AllowNull()][object]$Value,
        [Parameter(Mandatory)][string]$Label
    )
    if ($null -eq $Value -or $Value -is [string]) { Add-TcePortableError $Errors ($Label + ': lista de arquivos ausente ou invalida'); return }
    $items = @($Value)
    if ($items.Count -eq 0) { Add-TcePortableError $Errors ($Label + ': lista de arquivos vazia'); return }
    for ($index = 0; $index -lt $items.Count; $index++) { Add-TcePortableManifestReference $ExtensionRoot $Declared $Errors $items[$index] ($Label + '[' + $index + ']') }
}

function Get-TcePortableExtensionManifestStatus {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $root = [IO.Path]::GetFullPath($PackageRoot)
    $extensionRoot = Join-Path $root 'extensao-complementar-ato'
    $manifestPath = Join-Path $extensionRoot 'manifest.json'
    $errors = New-Object System.Collections.ArrayList
    $declared = New-Object System.Collections.ArrayList
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Add-TcePortableError $errors 'manifest.json da extensao ausente'
        return [pscustomobject]@{ IsValid = $false; Errors = $errors.ToArray(); Permissions = @(); HostPermissions = @(); DeclaredFiles = @() }
    }
    try { $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
        Add-TcePortableError $errors 'manifest.json da extensao nao e JSON valido'
        return [pscustomobject]@{ IsValid = $false; Errors = $errors.ToArray(); Permissions = @(); HostPermissions = @(); DeclaredFiles = @() }
    }
    if ((Get-TceJsonProperty $manifest 'manifest_version') -ne 3) { Add-TcePortableError $errors 'manifest da extensao nao usa Manifest V3' }
    $permissions = @((Get-TceJsonProperty $manifest 'permissions') | ForEach-Object { [string]$_ })
    $hostPermissions = @((Get-TceJsonProperty $manifest 'host_permissions') | ForEach-Object { [string]$_ })
    if (($permissions -join '|') -ne 'storage|sidePanel|alarms') { Add-TcePortableError $errors 'permissoes devem ser exatamente storage, sidePanel e alarms' }
    if (($hostPermissions -join '|') -ne 'https://novaarearestrita.tce.rn.gov.br/*|http://127.0.0.1/*') { Add-TcePortableError $errors 'hosts permitidos devem ser o portal e o bridge loopback' }
    $background = Get-TceJsonProperty $manifest 'background'
    Add-TcePortableManifestReference $extensionRoot $declared $errors (Get-TceJsonProperty $background 'service_worker') 'background.service_worker'
    $sidePanel = Get-TceJsonProperty $manifest 'side_panel'
    Add-TcePortableManifestReference $extensionRoot $declared $errors (Get-TceJsonProperty $sidePanel 'default_path') 'side_panel.default_path'
    $contentScripts = Get-TceJsonProperty $manifest 'content_scripts'
    if ($null -eq $contentScripts -or $contentScripts -is [string] -or @($contentScripts).Count -eq 0) { Add-TcePortableError $errors 'content_scripts ausente ou vazio' } else {
        $scriptIndex = 0
        foreach ($script in @($contentScripts)) {
            $matches = @((Get-TceJsonProperty $script 'matches') | ForEach-Object { [string]$_ })
            if (($matches -join '|') -ne 'https://novaarearestrita.tce.rn.gov.br/*') { Add-TcePortableError $errors ('content_scripts[' + $scriptIndex + '] usa host diferente') }
            Add-TcePortableManifestListReferences $extensionRoot $declared $errors (Get-TceJsonProperty $script 'js') ('content_scripts[' + $scriptIndex + '].js')
            $css = Get-TceJsonProperty $script 'css'
            if ($null -ne $css) { Add-TcePortableManifestListReferences $extensionRoot $declared $errors $css ('content_scripts[' + $scriptIndex + '].css') }
            $scriptIndex++
        }
    }
    $action = Get-TceJsonProperty $manifest 'action'
    if ($null -ne $action) {
        $popup = Get-TceJsonProperty $action 'default_popup'
        if ($null -ne $popup) { Add-TcePortableManifestReference $extensionRoot $declared $errors $popup 'action.default_popup' }
        $icon = Get-TceJsonProperty $action 'default_icon'
        if ($null -ne $icon) {
            if ($icon -is [string]) { Add-TcePortableManifestReference $extensionRoot $declared $errors $icon 'action.default_icon' }
            else { foreach ($value in @($icon.PSObject.Properties | ForEach-Object Value)) { Add-TcePortableManifestReference $extensionRoot $declared $errors $value 'action.default_icon' } }
        }
    }
    $icons = Get-TceJsonProperty $manifest 'icons'
    if ($null -ne $icons) { foreach ($value in @($icons.PSObject.Properties | ForEach-Object Value)) { Add-TcePortableManifestReference $extensionRoot $declared $errors $value 'icons' } }
    $options = Get-TceJsonProperty $manifest 'options_ui'
    if ($null -ne $options) { Add-TcePortableManifestReference $extensionRoot $declared $errors (Get-TceJsonProperty $options 'page') 'options_ui.page' }
    $devtoolsPage = Get-TceJsonProperty $manifest 'devtools_page'
    if ($null -ne $devtoolsPage) { Add-TcePortableManifestReference $extensionRoot $declared $errors $devtoolsPage 'devtools_page' }
    $sandbox = Get-TceJsonProperty $manifest 'sandbox'
    if ($null -ne $sandbox) { Add-TcePortableManifestListReferences $extensionRoot $declared $errors (Get-TceJsonProperty $sandbox 'pages') 'sandbox.pages' }
    [pscustomobject]@{ IsValid = ($errors.Count -eq 0); Errors = $errors.ToArray(); Permissions = $permissions; HostPermissions = $hostPermissions; DeclaredFiles = @($declared | Sort-Object -Unique) }
}

function Get-TcePortableNodeStatus {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $root = [IO.Path]::GetFullPath($PackageRoot)
    $errors = New-Object System.Collections.ArrayList
    foreach ($relative in @('node_modules', 'package-lock.json', 'npm-shrinkwrap.json', 'pnpm-lock.yaml', 'yarn.lock')) { if (Test-Path -LiteralPath (Join-Path $root $relative)) { Add-TcePortableError $errors ('dependencia Node encontrada: ' + $relative) } }
    $extensionRoot = Join-Path $root 'extensao-complementar-ato'
    foreach ($relative in @('node_modules', 'package-lock.json', 'npm-shrinkwrap.json', 'pnpm-lock.yaml', 'yarn.lock')) { if (Test-Path -LiteralPath (Join-Path $extensionRoot $relative)) { Add-TcePortableError $errors ('dependencia Node encontrada: extensao-complementar-ato/' + $relative) } }
    foreach ($relative in @('extensao-complementar-ato\package.json', 'extensao-complementar-ato\content\package.json')) {
        $path = Join-Path $root $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        try { $package = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Add-TcePortableError $errors ('package.json invalido: ' + $relative); continue }
        foreach ($field in @('dependencies', 'optionalDependencies', 'peerDependencies', 'bundledDependencies')) { if ($null -ne (Get-TceJsonProperty $package $field)) { Add-TcePortableError $errors ('package.json declara ' + $field + ': ' + $relative) } }
    }
    foreach ($relative in @('INICIAR.bat', 'INICIAR.cmd', 'Coletar-Processos-TCE.ps1', 'app\menu.ps1', 'app\analysis_pipeline.py', 'app\evidence_geometry.py', 'app\bridge_auth.py', 'app\local_service.py', 'app\qualification.py', 'app\workflow_state.py', 'app\filter_new_batch.py', 'app\extension_exporter.py', 'app\package_complete_archive.py')) {
        $path = Join-Path $root $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        if ((Get-Content -LiteralPath $path -Raw -Encoding UTF8) -match '(?i)(^|[^A-Za-z0-9_-])node(?:\.exe)?([^A-Za-z0-9_-]|$)') { Add-TcePortableError $errors ('arquivo operacional chama Node: ' + $relative) }
    }
    [pscustomobject]@{ IsValid = ($errors.Count -eq 0); Errors = $errors.ToArray() }
}

function ConvertTo-TceCanonicalValue {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Collections.IDictionary]) {
        $ordered = [ordered]@{}
        foreach ($key in @($Value.Keys | Sort-Object)) { $ordered[[string]$key] = ConvertTo-TceCanonicalValue $Value[$key] }
        return ,$ordered
    }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $items = New-Object System.Collections.ArrayList
        foreach ($item in $Value) { [void]$items.Add((ConvertTo-TceCanonicalValue $item)) }
        return ,$items.ToArray()
    }
    $properties = @($Value.PSObject.Properties)
    if ($properties.Count -gt 0 -and $Value -isnot [string]) {
        $ordered = [ordered]@{}
        foreach ($property in @($properties | Sort-Object Name)) { $ordered[$property.Name] = ConvertTo-TceCanonicalValue $property.Value }
        return ,$ordered
    }
    return $Value
}

function Get-TceSha256Hex {
    param([Parameter(Mandatory)][string]$Text)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text))
        return (([BitConverter]::ToString($digest)).Replace('-', '')).ToLowerInvariant()
    } finally { $algorithm.Dispose() }
}

function Test-TceNonNegativeInteger {
    param([AllowNull()][object]$Value)
    return ($null -ne $Value -and $Value -isnot [bool] -and ($Value -is [int] -or $Value -is [long] -or $Value -is [decimal]) -and [decimal]$Value -ge 0 -and [decimal]$Value -eq [math]::Truncate([decimal]$Value))
}

function Get-TcePortableDatasetStatus {
    param([Parameter(Mandatory)][string]$ArchiveRoot)
    $root = [IO.Path]::GetFullPath($ArchiveRoot)
    $datasetPath = Join-Path $root 'acervo-tce\dados-complementar-ato.json'
    $archivePath = Join-Path $root 'acervo-tce'
    $errors = New-Object System.Collections.ArrayList
    if (-not (Test-Path -LiteralPath $archivePath)) { return [pscustomobject]@{ IsPresent = $false; IsValid = $true; Errors = @(); DatasetPath = $datasetPath; ProcessCount = $null; RecordCount = $null; LogicalSha256 = $null } }
    if (-not (Test-Path -LiteralPath $archivePath -PathType Container)) { Add-TcePortableError $errors 'acervo-tce existe, mas nao e um diretorio'; return [pscustomobject]@{ IsPresent = $true; IsValid = $false; Errors = $errors.ToArray(); DatasetPath = $datasetPath; ProcessCount = $null; RecordCount = $null; LogicalSha256 = $null } }
    if (-not (Test-Path -LiteralPath $datasetPath -PathType Leaf)) { Add-TcePortableError $errors 'dados-complementar-ato.json ausente sob acervo-tce'; return [pscustomobject]@{ IsPresent = $true; IsValid = $false; Errors = $errors.ToArray(); DatasetPath = $datasetPath; ProcessCount = $null; RecordCount = $null; LogicalSha256 = $null } }
    try { $dataset = Get-Content -LiteralPath $datasetPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Add-TcePortableError $errors 'dados-complementar-ato.json nao e JSON valido'; return [pscustomobject]@{ IsPresent = $true; IsValid = $false; Errors = $errors.ToArray(); DatasetPath = $datasetPath; ProcessCount = $null; RecordCount = $null; LogicalSha256 = $null } }
    $expectedRootKeys = @('schema_version', 'generated_at', 'batch', 'records')
    $rootKeys = @($dataset.PSObject.Properties.Name)
    foreach ($key in $expectedRootKeys) { if ($rootKeys -notcontains $key) { Add-TcePortableError $errors ('campo ausente no JSON: ' + $key) } }
    foreach ($key in $rootKeys) { if ($expectedRootKeys -notcontains $key) { Add-TcePortableError $errors ('campo inesperado no JSON: ' + $key) } }
    if ((Get-TceJsonProperty $dataset 'schema_version') -ne 1) { Add-TcePortableError $errors 'schema_version do JSON deve ser 1' }
    if ([string]::IsNullOrWhiteSpace([string](Get-TceJsonProperty $dataset 'generated_at'))) { Add-TcePortableError $errors 'generated_at do JSON esta vazio' }
    $batch = Get-TceJsonProperty $dataset 'batch'
    if ($null -eq $batch) { Add-TcePortableError $errors 'batch ausente no JSON' }
    else {
        $batchKeys = @($batch.PSObject.Properties.Name)
        foreach ($key in @('id', 'logical_sha256', 'process_count', 'record_count', 'process_keys')) { if ($batchKeys -notcontains $key) { Add-TcePortableError $errors ('campo ausente em batch: ' + $key) } }
        foreach ($key in $batchKeys) { if (@('id', 'logical_sha256', 'process_count', 'record_count', 'process_keys') -notcontains $key) { Add-TcePortableError $errors ('campo inesperado em batch: ' + $key) } }
    }
    $processKeysValue = Get-TceJsonProperty $batch 'process_keys'; $processKeys = @(); if ($null -ne $processKeysValue) { $processKeys = @($processKeysValue) }
    $recordsValue = Get-TceJsonProperty $dataset 'records'; $records = @(); if ($null -ne $recordsValue) { $records = @($recordsValue) }
    $processCount = Get-TceJsonProperty $batch 'process_count'; $recordCount = Get-TceJsonProperty $batch 'record_count'; $logicalSha = [string](Get-TceJsonProperty $batch 'logical_sha256')
    if (-not (Test-TceNonNegativeInteger $processCount)) { Add-TcePortableError $errors 'batch.process_count deve ser inteiro nao negativo' }
    if (-not (Test-TceNonNegativeInteger $recordCount)) { Add-TcePortableError $errors 'batch.record_count deve ser inteiro nao negativo' }
    if ($null -eq $processKeysValue -or $processKeysValue -is [string]) { Add-TcePortableError $errors 'batch.process_keys deve ser lista' }
    if ($null -eq $recordsValue -or $recordsValue -is [string]) { Add-TcePortableError $errors 'records deve ser lista' }
    if ((Test-TceNonNegativeInteger $processCount) -and [int]$processCount -ne $processKeys.Count) { Add-TcePortableError $errors 'process_count nao corresponde a process_keys' }
    if ((Test-TceNonNegativeInteger $recordCount) -and [int]$recordCount -ne $records.Count) { Add-TcePortableError $errors 'record_count nao corresponde a records' }
    $seenProcessKeys = New-Object System.Collections.Generic.HashSet[string]
    foreach ($processKey in $processKeys) { $keyText = [string]$processKey; if ($keyText -notmatch '^\d+/\d{4}$') { Add-TcePortableError $errors ('process key nao canonica: ' + $keyText) }; if (-not $seenProcessKeys.Add($keyText)) { Add-TcePortableError $errors ('process key duplicada: ' + $keyText) } }
    foreach ($record in $records) { $process = Get-TceJsonProperty $record 'process'; $recordKey = [string](Get-TceJsonProperty $process 'key'); if ([string]::IsNullOrWhiteSpace($recordKey)) { Add-TcePortableError $errors 'registro sem process.key' } elseif ($processKeys -notcontains $recordKey) { Add-TcePortableError $errors ('registro referencia processo ausente: ' + $recordKey) } }
    if ($logicalSha -notmatch '^[0-9a-f]{64}$') { Add-TcePortableError $errors 'batch.logical_sha256 deve conter 64 hexadecimais minusculos' }
    else {
        $logicalPayload = [ordered]@{ schema_version = Get-TceJsonProperty $dataset 'schema_version'; batch_id = Get-TceJsonProperty $batch 'id'; process_keys = $processKeys; records = $records }
        try { $canonicalJson = ConvertTo-Json -InputObject (ConvertTo-TceCanonicalValue $logicalPayload) -Compress -Depth 100; if ((Get-TceSha256Hex $canonicalJson) -cne $logicalSha) { Add-TcePortableError $errors 'batch.logical_sha256 nao corresponde ao conteudo do JSON' } } catch { Add-TcePortableError $errors 'nao foi possivel calcular o hash logico do JSON' }
    }
    [pscustomobject]@{ IsPresent = $true; IsValid = ($errors.Count -eq 0); Errors = $errors.ToArray(); DatasetPath = $datasetPath; ProcessCount = $processCount; RecordCount = $recordCount; LogicalSha256 = $logicalSha }
}

function Invoke-TcePortableDatasetSchemaProbe {
    param([Parameter(Mandatory)][string]$PackageRoot, [Parameter(Mandatory)][pscustomobject]$Runtime)
    $errors = New-Object System.Collections.ArrayList
    $oldLocation = Get-Location
    try { Set-Location -LiteralPath $PackageRoot; $output = @(& $Runtime.Python -B -s 'app\extension_exporter.py' --validate 'acervo-tce\dados-complementar-ato.json' 2>&1); if ($LASTEXITCODE -ne 0) { Add-TcePortableError $errors ('schema Python rejeitou o JSON: ' + (ConvertTo-TcePortableDiagnosticText $output)) } } catch { Add-TcePortableError $errors 'nao foi possivel executar a validacao Python do JSON' } finally { Set-Location -LiteralPath $oldLocation }
    [pscustomobject]@{ IsValid = ($errors.Count -eq 0); Errors = $errors.ToArray() }
}

function Get-TcePortableAuditDistribution {
    param([Parameter(Mandatory)][string]$PackageRoot)
    if (Test-Path -LiteralPath (Join-Path ([IO.Path]::GetFullPath($PackageRoot)) 'acervo-tce')) { return 'private' }
    return 'public'
}

function Invoke-TcePortablePackageAudit {
    param([Parameter(Mandatory)][string]$PackageRoot, [Parameter(Mandatory)][pscustomobject]$Runtime)
    $root = [IO.Path]::GetFullPath($PackageRoot); $distribution = Get-TcePortableAuditDistribution $root; $errors = New-Object System.Collections.ArrayList; $auditScript = Join-Path $root 'app\package_audit.py'
    if (-not (Test-Path -LiteralPath $auditScript -PathType Leaf)) { Add-TcePortableError $errors 'app/package_audit.py ausente; auditor nao executado'; return [pscustomobject]@{ IsValid = $false; Distribution = $distribution; Errors = $errors.ToArray(); FindingCount = $null } }
    if (-not $Runtime.IsComplete) { Add-TcePortableError $errors ('auditoria ' + $distribution + ' nao executada: runtime portatil incompleto'); return [pscustomobject]@{ IsValid = $false; Distribution = $distribution; Errors = $errors.ToArray(); FindingCount = $null } }
    $oldLocation = Get-Location; $output = @(); $exitCode = 1
    try { Set-Location -LiteralPath $root; $output = @(& $Runtime.Python -B -s 'app\package_audit.py' '.' '--distribution' $distribution 2>&1); $exitCode = $LASTEXITCODE } catch { Add-TcePortableError $errors ('auditor ' + $distribution + ' nao pode ser executado') } finally { Set-Location -LiteralPath $oldLocation }
    $auditReport = $null; try { $auditReport = ((@($output) | ForEach-Object { [string]$_ }) -join [Environment]::NewLine | ConvertFrom-Json) } catch { }
    if ($null -eq $auditReport) { Add-TcePortableError $errors ('auditor ' + $distribution + ' nao retornou JSON'); return [pscustomobject]@{ IsValid = $false; Distribution = $distribution; Errors = $errors.ToArray(); FindingCount = $null } }
    $findingCount = @((Get-TceJsonProperty $auditReport 'findings')).Count
    if ($exitCode -ne 0 -or (Get-TceJsonProperty $auditReport 'ok') -ne $true) { Add-TcePortableError $errors ('auditoria ' + $distribution + ' reprovada com ' + $findingCount + ' achado(s)') }
    [pscustomobject]@{ IsValid = ($errors.Count -eq 0); Distribution = $distribution; Errors = $errors.ToArray(); FindingCount = $findingCount }
}

function Add-TcePortableCheck {
    param([Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Checks, [Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][bool]$Passed, [Parameter(Mandatory)][AllowEmptyString()][string]$Message)
    if ([string]::IsNullOrWhiteSpace($Message)) { $Message = 'sem detalhes adicionais' }
    [void]$Checks.Add([pscustomobject]@{ Name = $Name; Passed = $Passed; Message = $Message })
}

function Invoke-TcePortablePackageCheck {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $root = [IO.Path]::GetFullPath($PackageRoot); $checks = New-Object System.Collections.ArrayList
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { Add-TcePortableCheck $checks 'raiz do pacote' $false 'diretorio ausente'; return [pscustomobject]@{ PackageRoot = $root; Distribution = 'public'; Passed = $false; Checks = $checks.ToArray() } }
    $runtime = Get-TcePortableRuntimeLayout $root
    if ($runtime.IsComplete) { Add-TcePortableCheck $checks 'layout do runtime' $true 'Python, Tesseract, DLLs e idiomas presentes' } else { Add-TcePortableCheck $checks 'layout do runtime' $false ('arquivos ausentes: ' + (($runtime.Missing | ForEach-Object { $_.Substring($root.Length + 1) }) -join ', ')) }
    if ($runtime.IsComplete) { $runtimeProbe = Invoke-TcePortableRuntimeProbe $runtime; Add-TcePortableCheck $checks 'execucao do runtime' $runtimeProbe.IsValid ($runtimeProbe.Errors -join '; ') }
    $extension = Get-TcePortableExtensionManifestStatus $root; Add-TcePortableCheck $checks 'manifest e arquivos declarados' $extension.IsValid ($extension.Errors -join '; ')
    $node = Get-TcePortableNodeStatus $root; Add-TcePortableCheck $checks 'dependencia Node' $node.IsValid ($(if ($node.IsValid) { 'Node nao e necessario no destino' } else { $node.Errors -join '; ' }))
    $dataset = Get-TcePortableDatasetStatus $root; if ($dataset.IsPresent) { Add-TcePortableCheck $checks 'dados da extensao' $dataset.IsValid ($dataset.Errors -join '; ') } else { Add-TcePortableCheck $checks 'dados da extensao' $true 'acervo-tce ausente; modo public' }
    $audit = Invoke-TcePortablePackageAudit $root $runtime; Add-TcePortableCheck $checks ('auditoria ' + $audit.Distribution) $audit.IsValid ($audit.Errors -join '; ')
    if ($dataset.IsPresent -and $dataset.IsValid -and $runtime.IsComplete) { $schema = Invoke-TcePortableDatasetSchemaProbe $root $runtime; Add-TcePortableCheck $checks 'schema da extensao' $schema.IsValid ($schema.Errors -join '; ') }
    [pscustomobject]@{ PackageRoot = $root; Distribution = $audit.Distribution; Passed = ($checks.Count -gt 0 -and @($checks | Where-Object { -not $_.Passed }).Count -eq 0); Checks = $checks.ToArray() }
}

if ($MyInvocation.InvocationName -ne '.') {
    $result = Invoke-TcePortablePackageCheck -PackageRoot $PackageRoot
    Write-Host ('Pacote: ' + $result.PackageRoot) -ForegroundColor Cyan
    Write-Host ('Auditoria selecionada: ' + $result.Distribution)
    foreach ($check in $result.Checks) { if ($check.Passed) { Write-Host ('PASSOU: ' + $check.Name + ' - ' + $check.Message) -ForegroundColor Green } else { Write-Host ('FALHOU: ' + $check.Name + ' - ' + $check.Message) -ForegroundColor Red } }
    if ($result.Passed) { Write-Host 'Pacote integro: verificacao offline aprovada.' -ForegroundColor Green; exit 0 }
    Write-Host 'Pacote reprovado: corrija os itens acima antes de transportar.' -ForegroundColor Red; exit 1
}
