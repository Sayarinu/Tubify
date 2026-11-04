param([switch]$AllowDirty)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

if (-not $AllowDirty -and (git status --porcelain)) {
    throw "Refusing to package a dirty checkout. Commit or stash changes first (or pass -AllowDirty for a local test build)."
}
if ($env:OS -ne "Windows_NT" -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne "X64") {
    throw "The Tubify Windows package targets x64; run this build on 64-bit Windows."
}

$msysRoot = $env:MSYS2_ROOT
if (-not $msysRoot) { $msysRoot = $env:MSYS2_LOCATION }
if (-not $msysRoot) { throw "MSYS2_ROOT is required. Install MSYS2 UCRT64 mpv and FFmpeg packages first." }
$ucrtBin = Join-Path $msysRoot "ucrt64\bin"
$bash = Join-Path $msysRoot "usr\bin\bash.exe"
$cygpath = Join-Path $msysRoot "usr\bin\cygpath.exe"
foreach ($path in @($ucrtBin, $bash, $cygpath)) {
    if (-not (Test-Path $path)) { throw "MSYS2 UCRT64 is incomplete: $path" }
}

$mpvDll = @("mpv-2.dll", "libmpv-2.dll") | ForEach-Object { Join-Path $ucrtBin $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $mpvDll) { throw "MSYS2 UCRT64 did not provide mpv-2.dll or libmpv-2.dll." }
$ffmpeg = Join-Path $ucrtBin "ffmpeg.exe"
$ffprobe = Join-Path $ucrtBin "ffprobe.exe"
foreach ($path in @($ffmpeg, $ffprobe)) { if (-not (Test-Path $path)) { throw "FFmpeg helper is missing: $path" } }
$deno = $env:DENO_EXE
if (-not $deno) { $deno = (Get-Command deno.exe -ErrorAction SilentlyContinue).Source }
if (-not $deno -or -not (Test-Path $deno)) { throw "DENO_EXE or deno.exe is required to package the YouTube extractor runtime." }

# ldd follows the whole dependency tree, so one call covers libmpv and both FFmpeg helpers.
function Get-UcrtDependencies([string[]]$RootFiles) {
    $unixPaths = ($RootFiles | ForEach-Object { "'" + (& $cygpath -u $_).Trim() + "'" }) -join " "
    $lines = & $bash -lc "ldd $unixPaths" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect native dependencies: $($lines -join ' ')" }
    $found = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($line in $lines) {
        if ($line -match "(?:=>\s+)?(/ucrt64/bin/[^\s]+)\s+\(") {
            $dependency = Join-Path $ucrtBin (Split-Path $Matches[1] -Leaf)
            if (Test-Path $dependency) { [void]$found.Add((Resolve-Path $dependency).Path) }
        }
    }
    return @($found)
}

$version = & python -c "import pathlib,tomllib; print(tomllib.loads(pathlib.Path('native/pyproject.toml').read_text())['project']['version'])"
$buildRoot = Join-Path ([IO.Path]::GetTempPath()) ("tubify-windows-build-" + [guid]::NewGuid().ToString("N"))
$output = Join-Path $repo "dist\native"
$appOutput = Join-Path $buildRoot "dist\Tubify"
New-Item -ItemType Directory -Force -Path $buildRoot, $output | Out-Null
try {
    $venv = Join-Path $buildRoot "venv"
    uv venv --quiet --python 3.12 $venv
    if ($LASTEXITCODE -ne 0) { throw "uv could not create the Windows build environment." }
    $python = Join-Path $venv "Scripts\python.exe"
    uv pip install --quiet --python $python "./native[windows-build]"
    if ($LASTEXITCODE -ne 0) { throw "uv could not install the native Windows build dependencies." }
    $env:TUBIFY_ICON = Join-Path $buildRoot "Tubify.ico"
    & $python scripts/build-native-windows-icon.py $env:TUBIFY_ICON
    if ($LASTEXITCODE -ne 0) { throw "Could not render the Tubify Windows icon." }
    & $python -m PyInstaller --noconfirm --clean --distpath (Join-Path $buildRoot "dist") --workpath (Join-Path $buildRoot "work") packaging/windows/Tubify.spec
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $appOutput "Tubify.exe"))) {
        throw "PyInstaller did not produce Tubify.exe."
    }

    # libmpv and the helpers share one folder, so the libraries they have in common ship once.
    $helpers = Join-Path $appOutput "_internal\helpers"
    New-Item -ItemType Directory -Force -Path $helpers | Out-Null
    $roots = @($mpvDll, $ffmpeg, $ffprobe)
    $bundled = @($roots) + @(Get-UcrtDependencies $roots) + @($deno)
    $bundled | Sort-Object -Unique | ForEach-Object { Copy-Item -LiteralPath $_ -Destination $helpers -Force }

    & $python packaging/bundle_contents.py $appOutput --max-files 700 --max-mb 480
    if ($LASTEXITCODE -ne 0) { throw "The Tubify bundle ships more than it needs." }

    $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $knownIscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        if (Test-Path $knownIscc) { $iscc = $knownIscc }
    }
    if (-not $iscc) { throw "Inno Setup 6 is required. Install it or add ISCC.exe to PATH." }
    & $iscc "/DAppVersion=$version" "/DSourceDir=$appOutput" "/DIconFile=$env:TUBIFY_ICON" "/O$output" packaging/windows/Tubify.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to build the Tubify installer." }
    Write-Output "Built $(Join-Path $output "Tubify-$version-windows-x64-setup.exe")"
}
finally {
    Remove-Item -Recurse -Force $buildRoot -ErrorAction SilentlyContinue
    Remove-Item Env:\TUBIFY_ICON -ErrorAction SilentlyContinue
}
