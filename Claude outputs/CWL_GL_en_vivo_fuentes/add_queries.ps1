param([string]$In, [string]$Out, [string]$TestUrl = "", [string]$TestKey = "")
# Mete la consulta de Power Query en el libro, via COM de Excel.
#
# Una SOLA consulta, no una por version: lee la tabla `tVersiones` de Config y
# las apila con una columna `Etiqueta`. Asi agregar un Draft es escribir un
# renglon en el libro, no editar la consulta ni volver a correr esto.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$m = Get-Content -Raw -Encoding UTF8 (Join-Path $here "query.m")

$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false
$xl.Visible = $false
try {
    $wb = $xl.Workbooks.Open($In)
    # Ignorar niveles de privacidad SOLO en este libro: la consulta combina
    # celdas del propio libro (llave, anio, version) con la web.
    $wb.Queries.FastCombine = $true
    if ($TestUrl) { $wb.Worksheets.Item("Config").Range("pURL").Value2 = $TestUrl }
    if ($TestKey) { $wb.Worksheets.Item("Config").Range("pLlave").Value2 = $TestKey }

    $qn = "GL"
    $wb.Queries.Add($qn, $m, "Cuentas del mayor por mes, todas las versiones, desde FinPlan CWL") | Out-Null

    $ws = $wb.Worksheets.Item("GL")
    $ws.Cells.Clear() | Out-Null
    $conn = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=$qn;Extended Properties=`"`""
    $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range("A1"))
    $lo.Name = "tGL"
    $qt = $lo.QueryTable
    $qt.CommandType = 2
    $qt.CommandText = "SELECT * FROM [$qn]"
    $qt.BackgroundQuery = $false
    $qt.RefreshStyle = 0      # xlOverwriteCells: no corre referencias
    $qt.PreserveColumnInfo = $true
    $qt.AdjustColumnWidth = $true
    if ($TestKey) { $qt.Refresh($false) | Out-Null }

    $wb.Worksheets.Item("Config").Activate()
    # La llave NO se guarda en el archivo que se comparte.
    $wb.Worksheets.Item("Config").Range("pLlave").Value2 = ""
    $wb.SaveAs($Out, 51)
    Write-Host "libro con consulta: $Out"
} finally {
    $wb = $null
    $xl.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
