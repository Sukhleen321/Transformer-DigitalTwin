# Explicit, disposable full-stack profile; retained projects are never targeted.
[CmdletBinding()]
param(
    [int]$BackendPort = 8002,
    [int]$FrontendPort = 5177,
    [int]$DatabasePort = 55434,
    [int]$MqttPort = 51886,
    [int]$ModbusPort = 1503,
    [switch]$CheckOnly,
    [switch]$BuildOnly
)
$ErrorActionPreference = 'Stop'
if ($CheckOnly -and $BuildOnly) { throw 'Choose CheckOnly or BuildOnly.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$composeFile = Join-Path $repo 'docker-compose.physics-demo.yml'
$identity = [guid]::NewGuid().ToString('N')
$project = "physicsdemo-$identity"
$envFile = Join-Path $env:TEMP "$project.env"
$sessionFile = Join-Path $env:TEMP "$project.session.json"
$database = "live_physics_demo_$identity"
$reservedPorts = [System.Collections.Generic.HashSet[int]]::new()
function Find-DemoPort([int]$preferred) {
    if ($preferred -lt 1024 -or $preferred -gt 65435) { throw 'Port must be 1024–65435.' }
    for ($port = $preferred; $port -lt $preferred + 100; $port++) {
        if ($reservedPorts.Contains($port)) { continue }
        $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
        try { $probe.Start(); [void]$reservedPorts.Add($port); return $port }
        catch [System.Net.Sockets.SocketException] { continue }
        finally { $probe.Stop() }
    }
    throw "No free local port near $preferred."
}
$BackendPort = Find-DemoPort $BackendPort
$FrontendPort = Find-DemoPort $FrontendPort
$DatabasePort = Find-DemoPort $DatabasePort
$MqttPort = Find-DemoPort $MqttPort
$ModbusPort = Find-DemoPort $ModbusPort
$password = [guid]::NewGuid().ToString('N')
# Write credentials only to this user's temporary file, never source or stdout.
$demoValues = @{
    PHYSICS_DEMO_TAG = $identity
    PHYSICS_DEMO_DB_NAME = $database
    PHYSICS_DEMO_DB_PASSWORD = $password
    PHYSICS_DEMO_HTTP_PORT = $BackendPort
    PHYSICS_DEMO_FRONTEND_PORT = $FrontendPort
    PHYSICS_DEMO_DB_PORT = $DatabasePort
    PHYSICS_DEMO_MQTT_PORT = $MqttPort
    PHYSICS_DEMO_MODBUS_PORT = $ModbusPort
}
$priorValues = @{}
foreach ($key in $demoValues.Keys) {
    $priorValues[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, [string]$demoValues[$key], 'Process')
}
$demoValues.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" } |
    Set-Content -LiteralPath $envFile -Encoding ascii
$password = $null
$arguments = @('compose', '--project-name', $project, '--env-file', $envFile,
               '-f', $composeFile, '--profile', 'physics-demo')
$started = $false
try {
    & docker @arguments config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration validation failed.' }
    if ($CheckOnly) {
        Write-Host 'Isolated ten-transformer Compose configuration: valid (not started).'
        return
    }
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine unavailable. Start Docker Desktop, then rerun.' }
    if ($BuildOnly) {
        & docker @arguments build
        if ($LASTEXITCODE -ne 0) { throw 'Current-source demo image build failed.' }
        Write-Host "Built current-source demo images with local tag $identity; no services started."
        return
    }
    & docker @arguments up --build --detach --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) {
        # Only this new unique project can have been created by this command.
        & docker @arguments down --timeout 30
        throw 'Owned demo build/startup failed. See Docker output; retained projects untouched.'
    }
    @{
        project = $project; env_file = $envFile; compose_file = $composeFile
        database = $database; image_tag = $identity
        frontend = "http://127.0.0.1:$FrontendPort"
        backend = "http://127.0.0.1:$BackendPort"
        mqtt_port = $MqttPort; modbus_port = $ModbusPort; database_port = $DatabasePort
    } | ConvertTo-Json | Set-Content -LiteralPath $sessionFile -Encoding ascii
    $started = $true
    Write-Host "LIVE SIMULATION: ten fictional assets. Frontend http://127.0.0.1:$FrontendPort"
    Write-Host "Backend http://127.0.0.1:$BackendPort; MQTT $MqttPort; Modbus $ModbusPort"
    Write-Host "Session file: $sessionFile"
    Write-Host "Stop: ./backend/scripts/Stop-TenTransformerDemo.ps1 -SessionFile '$sessionFile'"
} finally {
    foreach ($key in $priorValues.Keys) {
        [Environment]::SetEnvironmentVariable($key, $priorValues[$key], 'Process')
    }
    $demoValues.PHYSICS_DEMO_DB_PASSWORD = $null
    if (-not $started) { Remove-Item -LiteralPath $envFile -ErrorAction SilentlyContinue }
}
