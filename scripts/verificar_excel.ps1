param(
    [Parameter(Mandatory = $true)][string]$Arquivo,
    [switch]$Salvar
)
# Abre a planilha no Excel (COM), recalcula tudo e devolve um JSON com:
# erros de fórmula, total de conferências, quantas estão OK e onde há DIVERGE.
# Com -Salvar, grava a planilha recalculada (assim os valores ficam guardados no arquivo).
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$x = $null
$wb = $null
try {
    $caminho = (Resolve-Path $Arquivo).Path
    $x = New-Object -ComObject Excel.Application
    $x.Visible = $false
    $x.DisplayAlerts = $false
    $saida = [ordered]@{ excel = $x.Version; erros = @(); total = $null; ok = $null; fora_do_ok = @(); salvo = $false }
    $wb = $x.Workbooks.Open($caminho)
    $x.CalculateFull()
    foreach ($ws in $wb.Worksheets) {
        $rng = $null
        try { $rng = $ws.UsedRange.SpecialCells(-4123, 16) } catch { $rng = $null }
        if ($rng) { foreach ($c in $rng.Cells) { $saida.erros += ("{0}!{1}" -f $ws.Name, $c.Address($false, $false)) } }
    }
    $saida.total = [int]$wb.Names.Item("Conf_total").RefersToRange.Value2
    $saida.ok = [int]$wb.Names.Item("Conf_ok").RefersToRange.Value2
    foreach ($nome in @("Conf_status_resumo", "Conf_status_class", "Conf_status_art", "Conf_status_fin", "Conf_status_fin_jogo", "Conf_status_elenco", "Conf_status_elenco_tj")) {
        $r = $wb.Names.Item($nome).RefersToRange
        foreach ($c in $r.Cells) {
            if ($c.Value2 -ne "OK") { $saida.fora_do_ok += ("{0}!{1}={2}" -f $r.Worksheet.Name, $c.Address($false, $false), $c.Value2) }
        }
    }
    if ($Salvar) { $wb.Save(); $saida.salvo = $true }
    $saida | ConvertTo-Json -Depth 4 -Compress
}
catch {
    (@{ falha = $_.Exception.Message } | ConvertTo-Json -Compress)
    exit 2
}
finally {
    if ($wb) { try { $wb.Close($false) } catch {} }
    if ($x) { try { $x.Quit() } catch {}; [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($x) }
}
