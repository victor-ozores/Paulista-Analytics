# Recarrega os CSV de data/processed em TODAS as tabelas do modelo aberto no Power BI Desktop.
# Use depois de rodar 04_tratar.py e 05_validar.py, no lugar do botao Atualizar, quando o modelo
# for conferido pelo MCP. O Refresh da ferramenta de tabelas do MCP responde "sucesso" mas nao
# recarrega nada; o que funciona e mandar este comando de atualizacao completa ao motor local.
#
# Uso:  powershell -File scripts\atualizar_modelo_aberto.ps1 [-Porta 63032]
# Sem -Porta, descobre a porta do motor (msmdsrv.exe) filho do PBIDesktop.exe.
param([int]$Porta = 0)

$dll = "C:\Program Files (x86)\Microsoft.NET\ADOMD.NET\170\Microsoft.AnalysisServices.AdomdClient.dll"
if (-not (Test-Path $dll)) { Write-Output "ERRO: biblioteca ADOMD.NET nao encontrada em $dll"; exit 1 }

if ($Porta -eq 0) {
    $desktop = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id
    if (-not $desktop) { Write-Output "ERRO: o Power BI Desktop nao esta aberto."; exit 1 }
    $motor = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe'" | Where-Object { $desktop -contains $_.ParentProcessId } | Select-Object -First 1
    if (-not $motor) { Write-Output "ERRO: motor do modelo nao encontrado (abra o projeto no Desktop)."; exit 1 }
    $Porta = Get-NetTCPConnection -OwningProcess $motor.ProcessId -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty LocalPort
    if (-not $Porta) { Write-Output "ERRO: porta do motor nao encontrada."; exit 1 }
}

try {
    Add-Type -Path $dll
    $c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Porta")
    $c.Open()
    $db = $c.Database
    $cmd = $c.CreateCommand()
    $cmd.CommandText = '{"refresh":{"type":"full","objects":[{"database":"' + $db + '"}]}}'
    $cmd.CommandTimeout = 600
    $relogio = [Diagnostics.Stopwatch]::StartNew()
    $null = $cmd.ExecuteNonQuery()
    Write-Output ("modelo atualizado (porta " + $Porta + ") em " + [math]::Round($relogio.Elapsed.TotalSeconds, 1) + " s")
    $c.Close()
} catch {
    Write-Output ("ERRO: " + $_.Exception.Message)
    exit 1
}
