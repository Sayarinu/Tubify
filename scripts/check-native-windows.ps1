$ErrorActionPreference = "Stop"
$installer = Get-ChildItem (Join-Path $PSScriptRoot "..\dist\native\Tubify-*-windows-x64-setup.exe") | Select-Object -First 1
if (-not $installer) { throw "The Tubify Windows installer was not produced." }
$installDir = Join-Path $env:LOCALAPPDATA "Programs\Tubify"
$executable = Join-Path $installDir "Tubify.exe"

function Install-Tubify {
    $process = Start-Process -FilePath $installer.FullName -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "The Tubify installer failed with exit code $($process.ExitCode)." }
    if (-not (Test-Path $executable)) { throw "The installer did not place Tubify.exe in the expected per-user directory." }
    $versionInfo = [Diagnostics.FileVersionInfo]::GetVersionInfo($executable)
    if ($versionInfo.ProductName -ne "Tubify" -or $versionInfo.FileDescription -ne "Tubify") {
        throw "The installed executable is missing Tubify product metadata."
    }
    $env:QT_QPA_PLATFORM = "offscreen"
    # Tubify.exe is a GUI-subsystem program, so PowerShell would not wait for it or report its exit code.
    $smoke = Start-Process -FilePath $executable -ArgumentList @("--smoke-test") -PassThru -Wait -NoNewWindow
    if ($smoke.ExitCode -ne 0) { throw "The installed Tubify app failed its Qt smoke launch (exit code $($smoke.ExitCode))." }

    $tone = Join-Path $env:TEMP "tubify-windows-audio-smoke.wav"
    $bundledFfmpeg = Get-ChildItem -Path $installDir -Recurse -Filter ffmpeg.exe | Where-Object { $_.Directory.Name -eq "helpers" } | Select-Object -First 1
    if (-not $bundledFfmpeg) { throw "The installer did not include the bundled FFmpeg helper." }
    & $bundledFfmpeg.FullName -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:duration=3" -y $tone
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tone)) { throw "The installed FFmpeg helper could not create the local audio fixture." }
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $executable
    $start.Arguments = "--player-worker"
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.CreateNoWindow = $true
    $player = [Diagnostics.Process]::new()
    $player.StartInfo = $start
    if (-not $player.Start()) { throw "The installed Tubify player worker did not start." }
    $player.StandardInput.WriteLine((ConvertTo-Json -Compress @{ source = $tone; headers = @() }))
    $player.StandardInput.Close()
    if (-not $player.WaitForExit(15000)) {
        $player.Kill()
        throw "The installed Tubify player worker timed out decoding local audio."
    }
    if ($player.ExitCode -ne 0) { throw "The installed Tubify player worker could not decode local audio: $($player.StandardError.ReadToEnd())" }
    Remove-Item $tone -Force -ErrorAction SilentlyContinue
}

Install-Tubify
Install-Tubify
$uninstaller = Join-Path $installDir "unins000.exe"
if (-not (Test-Path $uninstaller)) { throw "Inno Setup did not create the uninstaller." }
$process = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -PassThru -Wait
if ($process.ExitCode -ne 0 -or (Test-Path $executable)) { throw "Tubify did not uninstall cleanly." }
Write-Output "Native Tubify Windows clean-install, upgrade, launch, and uninstall passed."
