# One explicit local opt-in; no retained environment or source constants edited.
[CmdletBinding()]
param(
    [switch]$VerifyApi,
    [ValidateRange(1, 10)][double]$Interval = 4,
    [int]$BackendPort = 8002,
    [int]$FrontendPort = 5177,
    [string[]]$Asset = @(),
    [string]$StopFile
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$demoPython = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    throw 'Repository Python environment is missing; follow the documented dependency setup.'
}
$previousTestDatabase = $env:TEST_DATABASE_URL
try {
    if (-not $env:TEST_DATABASE_URL) {
        $databasePort = Read-Host 'Local PostgreSQL port [55433]'
        if (-not $databasePort) { $databasePort = '55433' }
        if ($databasePort -notmatch '^\d+$' -or [int]$databasePort -notin 1..65535) {
            throw 'Invalid local PostgreSQL port.'
        }
        $databaseUser = Read-Host 'Local PostgreSQL admin user [transformer]'
        if (-not $databaseUser) { $databaseUser = 'transformer' }
        $databaseSecret = Read-Host 'Local PostgreSQL password' -AsSecureString
        $credential = [System.Management.Automation.PSCredential]::new($databaseUser, $databaseSecret)
        $encodedUser = [Uri]::EscapeDataString($databaseUser)
        $encodedSecret = [Uri]::EscapeDataString($credential.GetNetworkCredential().Password)
        $env:TEST_DATABASE_URL = "postgresql+psycopg://${encodedUser}:${encodedSecret}@127.0.0.1:${databasePort}/postgres"
        $encodedSecret = $null
        $credential = $null
    }
    $demoArguments = @(
        (Join-Path $PSScriptRoot 'live_physics_demo.py'), '--interval', $Interval,
        '--backend-port', $BackendPort, '--frontend-port', $FrontendPort
    )
    if ($VerifyApi) { $demoArguments += '--verify-api' }
    foreach ($assetId in $Asset) { $demoArguments += @('--asset', $assetId) }
    if ($StopFile) { $demoArguments += @('--stop-file', $StopFile) }
    & $demoPython @demoArguments
    if ($LASTEXITCODE -ne 0) { throw "Owned demo launcher failed (exit $LASTEXITCODE)." }
} finally {
    $env:TEST_DATABASE_URL = $previousTestDatabase
}
