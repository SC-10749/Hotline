$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$envFile = if ($env:DODO_ENV_FILE) {
    [Environment]::ExpandEnvironmentVariables($env:DODO_ENV_FILE)
} else {
    [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".env"))
}

if (-not (Test-Path $envFile)) {
    Write-Error "Environment file not found: $envFile"
    exit 1
}

$configProfile = if ($env:DODO_ENV_PROFILE) { $env:DODO_ENV_PROFILE } else { 'remote' }
$remoteOverrides = @{}
Get-Content -LiteralPath $envFile -Encoding utf8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $parts = $line.Split('=', 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($key.StartsWith('REMOTE_')) {
            $remoteOverrides[$key.Substring(7)] = $value
        } else {
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}
if ($configProfile -eq 'remote') {
    foreach ($configKey in $remoteOverrides.Keys) {
        Set-Item -Path "Env:$configKey" -Value $remoteOverrides[$configKey]
    }
}

Write-Host "Using Python: $python"
Write-Host "Using environment: $envFile"
& $python -m python_backend.main
