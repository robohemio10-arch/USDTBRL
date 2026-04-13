$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $ProjectRoot "config\live_100usdt.yml"

function Resolve-PythonCommand {
    $candidates = @(
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
        "python",
        "py -3",
        "python3"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -like "* *") {
            try {
                $parts = $candidate.Split(" ", 2)
                & $parts[0] $parts[1] --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    return @{
                        Command = $parts[0]
                        ArgsPrefix = @($parts[1])
                    }
                }
            }
            catch {
            }
            continue
        }

        if (Test-Path $candidate) {
            return @{
                Command = $candidate
                ArgsPrefix = @()
            }
        }

        try {
            & $candidate --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{
                    Command = $candidate
                    ArgsPrefix = @()
                }
            }
        }
        catch {
        }
    }

    throw "Nenhum interpretador Python utilizável foi encontrado."
}

if (-not (Test-Path $ConfigPath)) {
    throw "Arquivo de configuração live não encontrado: $ConfigPath"
}

$python = Resolve-PythonCommand

Set-Location $ProjectRoot
$env:PYTHONUTF8 = "1"

Write-Host "STARTING_LIVE config=config/live_100usdt.yml"
& $python.Command @($python.ArgsPrefix + @("bot.py", "--config", "config/live_100usdt.yml"))
exit $LASTEXITCODE
