[CmdletBinding()]
param([Parameter(Mandatory)][string]$SessionFile)
$ErrorActionPreference = 'Stop'
$resolvedSession = (Resolve-Path -LiteralPath $SessionFile).Path
$session = Get-Content -LiteralPath $resolvedSession -Raw | ConvertFrom-Json
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$expectedCompose = Join-Path $repo 'docker-compose.physics-demo.yml'
$expectedEnv = Join-Path $env:TEMP "$($session.project).env"
$expectedSession = Join-Path $env:TEMP "$($session.project).session.json"
if ($session.project -notmatch '^physicsdemo-[0-9a-f]{32}$' -or
    $session.database -ne "live_physics_demo_$($session.project.Substring(12))" -or
    $session.compose_file -ne $expectedCompose -or $session.env_file -ne $expectedEnv -or
    $resolvedSession -ne $expectedSession) {
    throw 'Session identity/path does not belong to this isolated launcher.'
}
& docker compose --project-name $session.project --env-file $session.env_file `
    -f $expectedCompose --profile physics-demo down --timeout 30
if ($LASTEXITCODE -ne 0) { throw 'Stop failed; session files retained for retry.' }
# No Docker volume removal: this profile stores disposable state in tmpfs.
Remove-Item -LiteralPath $expectedEnv
Remove-Item -LiteralPath $resolvedSession
Write-Host 'Owned demo stopped. Retained projects and volumes untouched.'
