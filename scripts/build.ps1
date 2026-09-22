$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $projectRoot 'src'
$buildDir = Join-Path $projectRoot 'build'
$sourceFile = Join-Path $sourceDir 'main.tex'

if (-not (Test-Path -LiteralPath $sourceFile)) {
    throw "Source file not found: $sourceFile"
}

$xelatex = Get-Command xelatex -ErrorAction SilentlyContinue
if ($null -eq $xelatex) {
    throw 'xelatex was not found in PATH. Install a TeX distribution and add its binary directory to PATH.'
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null

Push-Location $sourceDir
try {
    for ($pass = 1; $pass -le 2; $pass++) {
        & $xelatex.Source '-interaction=nonstopmode' '-halt-on-error' "-output-directory=$buildDir" 'main.tex'
        if ($LASTEXITCODE -ne 0) {
            throw "XeLaTeX failed on pass $pass with exit code $LASTEXITCODE. See build/main.log."
        }
    }
}
finally {
    Pop-Location
}

Write-Output "Built: $(Join-Path $buildDir 'main.pdf')"


