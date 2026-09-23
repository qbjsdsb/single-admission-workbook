$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $projectRoot 'src'
$validateScript = Join-Path $PSScriptRoot 'validate_content.py'
$contentScript = Join-Path $PSScriptRoot 'build_content.py'
$qaScript = Join-Path $PSScriptRoot 'qa_pdf.py'
$buildDir = Join-Path $projectRoot 'build'
$fixturesDir = Join-Path $projectRoot 'fixtures'

function Resolve-XeLaTeX {
    $candidates = [System.Collections.Generic.List[string]]::new()

    if ($env:XELATEX) {
        $candidates.Add($env:XELATEX)
    }

    $command = Get-Command xelatex -ErrorAction SilentlyContinue
    if ($command) {
        $candidates.Add($command.Source)
    }

    $uninstallKeys = @(
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($key in $uninstallKeys) {
        Get-ItemProperty -Path $key -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -match 'MiKTeX|TeX Live|TeX' -and $_.InstallLocation } |
            ForEach-Object {
                $install = [Environment]::ExpandEnvironmentVariables([string]$_.InstallLocation)
                $candidates.Add((Join-Path $install 'miktex\bin\x64\xelatex.exe'))
                $candidates.Add((Join-Path $install 'bin\x64\xelatex.exe'))
                $parent = Split-Path -Parent $install
                if ($parent) {
                    $candidates.Add((Join-Path $parent 'MiKTeX\miktex\bin\x64\xelatex.exe'))
                }
            }
    }

    foreach ($root in @('C:\texlive', 'D:\texlive', 'C:\Program Files\MiKTeX', 'D:\Apps')) {
        if (Test-Path -LiteralPath $root) {
            Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'xelatex.exe' -ErrorAction SilentlyContinue |
                ForEach-Object { $candidates.Add($_.FullName) }
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw 'XeLaTeX was not found. Put it on PATH, set XELATEX to xelatex.exe, or install a TeX distribution.'
}

function Resolve-Python {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $command = Get-Command python3 -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $command = Get-Command py -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw 'Python was not found. Install Python 3.10+ or make python available in PATH.'
}

if (-not (Test-Path -LiteralPath $fixturesDir)) {
    throw "Fixtures directory not found: $fixturesDir"
}

$xelatex = Resolve-XeLaTeX
$python = Resolve-Python
$pdfinfo = Get-Command pdfinfo -ErrorAction SilentlyContinue
$pdftotext = Get-Command pdftotext -ErrorAction SilentlyContinue
$pdftoppm = Get-Command pdftoppm -ErrorAction SilentlyContinue
if (-not $pdfinfo -or -not $pdftotext -or -not $pdftoppm) {
    throw 'Poppler tools pdfinfo, pdftotext, and pdftoppm are required for PDF and visual QA.'
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null

& $python $validateScript --fixtures $fixturesDir
if ($LASTEXITCODE -ne 0) { throw 'Content validation failed.' }

& $python $contentScript --fixtures $fixturesDir --output-dir $buildDir
if ($LASTEXITCODE -ne 0) { throw 'Content generation failed.' }

$subjects = @('chinese', 'math', 'politics', 'english')
foreach ($subject in $subjects) {
    & $python $contentScript --fixtures $fixturesDir --output-dir $buildDir --subject $subject --single-question
    if ($LASTEXITCODE -ne 0) { throw "Sample generation failed for $subject." }
}

function Invoke-WorkbookCompile {
    param(
        [Parameter(Mandatory = $true)][string]$JobName,
        [Parameter(Mandatory = $true)][string]$InputName,
        [int]$Passes = 2
    )

    Push-Location $buildDir
    try {
        for ($pass = 1; $pass -le $Passes; $pass++) {
            & $xelatex '-interaction=nonstopmode' '-halt-on-error' '-file-line-error' "-jobname=$JobName" $InputName *> $null
            if ($LASTEXITCODE -ne 0) {
                throw "XeLaTeX failed for $JobName on pass $pass with exit code $LASTEXITCODE. See build/$JobName.log."
            }
        }
    }
    finally {
        Pop-Location
    }
}

Invoke-WorkbookCompile -JobName 'student' -InputName 'generated_student.tex'
Invoke-WorkbookCompile -JobName 'teacher' -InputName 'generated_teacher.tex'
$dotRegressionInput = [System.IO.Path]::GetRelativePath($buildDir, (Join-Path $sourceDir 'dot-mark-regression.tex'))
Invoke-WorkbookCompile -JobName 'dot-mark-regression' -InputName $dotRegressionInput

foreach ($subject in $subjects) {
    foreach ($edition in @('student', 'teacher')) {
        $inputName = "generated_${subject}_${edition}.tex"
        $jobName = "$subject-sample-$edition"
        Invoke-WorkbookCompile -JobName $jobName -InputName $inputName -Passes 1
    }
}

$renderRoot = Join-Path $buildDir 'render'
$renderKinds = @('student', 'teacher', 'dot-mark-regression')
foreach ($subject in $subjects) {
    $renderKinds += "$subject-sample-student"
    $renderKinds += "$subject-sample-teacher"
}
foreach ($kind in $renderKinds) {
    $renderDir = Join-Path $renderRoot $kind
    foreach ($mode in @('color', 'grayscale')) {
        $modeDir = Join-Path $renderDir $mode
        New-Item -ItemType Directory -Path $modeDir -Force | Out-Null
        $prefix = Join-Path $modeDir 'page'
        $dpi = if ($kind -eq 'dot-mark-regression') { '300' } else { '200' }
        $rasterArgs = @('-png', '-r', $dpi)
        if ($mode -eq 'grayscale') { $rasterArgs += '-gray' }
        $rasterArgs += @((Join-Path $buildDir "$kind.pdf"), $prefix)
        & $pdftoppm.Source @rasterArgs
        if ($LASTEXITCODE -ne 0) { throw "pdftoppm $mode rendering failed for $kind." }
    }
}

& $python $qaScript --build-dir $buildDir --fixtures $fixturesDir
if ($LASTEXITCODE -ne 0) { throw 'PDF QA failed. See build/qa-report.json.' }

Write-Output "Built and checked: $(Join-Path $buildDir 'student.pdf')"
Write-Output "Built and checked: $(Join-Path $buildDir 'teacher.pdf')"
foreach ($subject in $subjects) {
    Write-Output "Built one-page subject samples: $(Join-Path $buildDir "${subject}-sample-student.pdf") and $(Join-Path $buildDir "${subject}-sample-teacher.pdf")"
}


