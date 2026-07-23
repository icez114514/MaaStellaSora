[CmdletBinding()]
param(
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$installRoot = Join-Path $repoRoot 'install'
$embeddedPython = Join-Path $installRoot 'python\python.exe'
$resourceChecker = Join-Path $repoRoot 'check_resource.py'
$resourceSource = Join-Path $repoRoot 'assets\resource\base'
$installer = Join-Path $repoRoot 'tools\ci\install.py'
$interfaceSource = Join-Path $repoRoot 'assets\interface.json'
$runtimeInterface = Join-Path $installRoot 'interface.json'
$localDevMarker = Join-Path $installRoot 'local-dev.json'
$mfaExecutable = Join-Path $installRoot 'MFAAvalonia.exe'
$gitExecutable = (Get-Command git -ErrorAction Stop).Source

foreach ($requiredPath in @(
    $embeddedPython,
    $resourceChecker,
    $resourceSource,
    $installer,
    $interfaceSource,
    $mfaExecutable
)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path not found: $requiredPath"
    }
}

function Remove-GeneratedDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    if ($Name -notin @('agent', 'resource')) {
        throw "Refusing to remove unexpected generated directory: $Name"
    }

    $target = Join-Path $installRoot $Name
    if (-not (Test-Path -LiteralPath $target)) {
        return
    }

    $resolvedInstall = (Resolve-Path -LiteralPath $installRoot).Path.TrimEnd('\')
    $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
    $expectedTarget = [System.IO.Path]::GetFullPath($target)
    $installPrefix = $resolvedInstall + '\'

    if ($resolvedTarget -ne $expectedTarget) {
        throw "Refusing to remove redirected path: $resolvedTarget"
    }
    if (-not $resolvedTarget.StartsWith(
        $installPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Generated directory is outside install: $resolvedTarget"
    }

    $item = Get-Item -LiteralPath $resolvedTarget -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to remove a reparse point: $resolvedTarget"
    }

    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}

function Stop-DevelopmentMfa {
    $expectedPath = [System.IO.Path]::GetFullPath($mfaExecutable)
    $runningProcesses = @(Get-Process `
        -Name 'MFAAvalonia' `
        -ErrorAction SilentlyContinue)

    foreach ($process in $runningProcesses) {
        $processPath = $null
        try {
            $processPath = $process.Path
        }
        catch {
            $processPath = $null
        }

        if ([string]::IsNullOrWhiteSpace($processPath)) {
            throw (
                'Unable to verify the running MFAAvalonia path. ' +
                'Run dev-run.bat so the check has administrator privileges.'
            )
        }

        $actualPath = [System.IO.Path]::GetFullPath($processPath)
        if (-not $actualPath.Equals(
            $expectedPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Write-Warning "Skipping MFAAvalonia from another directory: $actualPath"
            continue
        }

        Write-Host "Closing development MFAAvalonia process $($process.Id)..."
        if ($process.CloseMainWindow()) {
            $null = $process.WaitForExit(5000)
        }

        $process.Refresh()
        if (-not $process.HasExited) {
            Write-Host "Forcing development MFAAvalonia process $($process.Id) to stop..."
            try {
                Stop-Process -Id $process.Id -Force -ErrorAction Stop
                $null = $process.WaitForExit(5000)
            }
            catch {
                throw (
                    "Unable to stop MFAAvalonia process $($process.Id). " +
                    'Run dev-run.bat and approve administrator privileges.'
                )
            }
        }

        if (-not $process.HasExited) {
            throw "MFAAvalonia process $($process.Id) did not exit."
        }
    }
}

function Get-LocalDevMetadata {
    $baseTag = (& $gitExecutable tag `
        --points-at HEAD `
        --sort=-version:refname `
        'v[0-9]*' 2>$null | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($baseTag)) {
        $baseTag = (& $gitExecutable tag `
            --merged HEAD `
            --sort=-version:refname `
            'v[0-9]*' 2>$null | Select-Object -First 1)
    }
    if ([string]::IsNullOrWhiteSpace($baseTag)) {
        $sourceInterface = Get-Content `
            -LiteralPath $interfaceSource `
            -Encoding UTF8 `
            -Raw | ConvertFrom-Json
        $baseTag = [string]$sourceInterface.version
        if (-not $baseTag.StartsWith('v')) {
            $baseTag = 'v' + $baseTag
        }
    }
    else {
        $baseTag = $baseTag.Trim()
    }

    $originUrl = (& $gitExecutable remote get-url origin).Trim()
    $owner = 'local'
    if ($originUrl -match 'github\.com[:/]([^/]+)/') {
        $owner = $Matches[1]
    }
    $owner = ($owner -replace '[^0-9A-Za-z-]', '-').Trim('-').ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($owner)) {
        $owner = 'local'
    }

    $commit = (& $gitExecutable rev-parse --short=8 HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($commit)) {
        throw 'Unable to determine the current Git commit.'
    }

    $dirtyOutput = & $gitExecutable status --porcelain --untracked-files=normal
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to determine the Git working tree status.'
    }
    $isDirty = @($dirtyOutput).Count -gt 0

    $personalVersion = "$baseTag+$owner.dev.$commit"
    if ($isDirty) {
        $personalVersion += '.dirty'
    }

    [pscustomobject]@{
        Version = $personalVersion
        BaseTag = $baseTag
        Owner = $owner
        Commit = $commit
        Dirty = $isDirty
    }
}

Stop-DevelopmentMfa

Push-Location $repoRoot
try {
    Write-Host 'Checking source resources...'
    $checkOutput = & $embeddedPython $resourceChecker $resourceSource 2>&1
    $checkExitCode = $LASTEXITCODE
    if ($checkExitCode -ne 0) {
        $checkOutput | Select-Object -Last 80
        throw "Resource check failed with exit code $checkExitCode."
    }
    Write-Host 'Resource check passed.'

    Write-Host 'Refreshing generated agent and resource directories...'
    Remove-GeneratedDirectory -Name 'agent'
    Remove-GeneratedDirectory -Name 'resource'

    $devMetadata = Get-LocalDevMetadata

    $installOutput = & $embeddedPython $installer $devMetadata.Version 'win-x64' 2>&1
    $installExitCode = $LASTEXITCODE
    if ($installExitCode -ne 0) {
        $installOutput | Select-Object -Last 80
        throw "Development install failed with exit code $installExitCode."
    }

    if (-not (Test-Path -LiteralPath $mfaExecutable)) {
        throw "MFAAvalonia executable disappeared after synchronization: $mfaExecutable"
    }

    $runtimeInterfaceData = Get-Content `
        -LiteralPath $runtimeInterface `
        -Encoding UTF8 `
        -Raw | ConvertFrom-Json
    $runtimeInterfaceData.version = $devMetadata.Version
    $runtimeInterfaceData.custom_title =
        "$($runtimeInterfaceData.custom_title) [LOCAL DEV]"

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $runtimeInterfaceJson = $runtimeInterfaceData |
        ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText(
        $runtimeInterface,
        $runtimeInterfaceJson + [Environment]::NewLine,
        $utf8NoBom
    )

    $marker = [ordered]@{
        kind = 'local-dev'
        version = $devMetadata.Version
        base_tag = $devMetadata.BaseTag
        fork_owner = $devMetadata.Owner
        commit = $devMetadata.Commit
        dirty = $devMetadata.Dirty
        generated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    }
    $markerJson = $marker | ConvertTo-Json
    [System.IO.File]::WriteAllText(
        $localDevMarker,
        $markerJson + [Environment]::NewLine,
        $utf8NoBom
    )

    Write-Host "Development runtime refreshed: $($devMetadata.Version)"
    if (-not $NoLaunch) {
        Write-Host 'Requesting administrator privileges for MFAAvalonia...'
        Start-Process `
            -FilePath $mfaExecutable `
            -WorkingDirectory $installRoot `
            -Verb RunAs
    }
}
finally {
    Pop-Location
}
