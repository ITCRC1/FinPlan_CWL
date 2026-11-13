param([string]$In, [string]$Out, [string]$TestUrl = "", [string]$TestKey = "")
# Mete las consultas GL y Escenarios en el libro del Cierre Mensual, via COM de Excel.
#
# Una SOLA consulta GL, no una por versión: lee la tabla `tVersiones` de Config
# y las apila con una columna `Etiqueta`. Al final de tGL van «Mes» y
# «Acumulado» del mes de Config!C7 (mes_columnas.ps1).
#
# -TestUrl/-TestKey: para probar el libro sin la llave real (respuestas
# capturadas servidas en 127.0.0.1). Al final se repone pURL y se vacía pLlave.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "mes_columnas.ps1")
$m = Get-Content -Raw -Encoding UTF8 (Join-Path $here "query.m")

$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false
$xl.Visible = $false
try {
    $wb = $xl.Workbooks.Open($In)
    # Ignorar niveles de privacidad SOLO en este libro: la consulta combina
    # celdas del propio libro (llave, año, versión) con la web.
    $wb.Queries.FastCombine = $true
    $urlReal = [string]$wb.Worksheets.Item("Config").Range("pURL").Value2
    if ($TestUrl) { $wb.Worksheets.Item("Config").Range("pURL").Value2 = $TestUrl }
    if ($TestKey) { $wb.Worksheets.Item("Config").Range("pLlave").Value2 = $TestKey }

    $qn = "GL"
    $wb.Queries.Add($qn, $m, "Cuentas del mayor por mes, las seis versiones del cierre, desde FinPlan CWL") | Out-Null
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
    if ($TestKey) {
        $qt.Refresh($false) | Out-Null
        Add-ColumnasMes $lo "M" "Mes" "Acumulado"
        Add-ColumnaMesAnterior $lo "M" "Mes anterior"
        foreach ($c in $lo.ListColumns) {
            if ($c.Name -match '^(M\d\d|Annual|Mes|Acumulado)$') { $c.DataBodyRange.NumberFormat = '#,##0.00;[Red](#,##0.00);"-"' }
        }
        "GL                   filas = {0}" -f $lo.ListRows.Count
    }
    try { $ws.Activate(); $xl.ActiveWindow.SplitRow = 1; $xl.ActiveWindow.FreezePanes = $true } catch { }  # cosmetico: Excel oculto a veces no lo deja

    $me = Get-Content -Raw -Encoding UTF8 (Join-Path $here "escenarios.m")
    $wb.Queries.Add("Escenarios", $me, "Escenarios y versiones disponibles en FinPlan CWL") | Out-Null
    $ws2 = $wb.Worksheets.Item("Escenarios")
    $ws2.Cells.Clear() | Out-Null
    $conn2 = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=Escenarios;Extended Properties=`"`""
    $lo2 = $ws2.ListObjects.Add(0, $conn2, $null, 1, $ws2.Range("A1"))
    $lo2.Name = "tEscenarios"
    $qt2 = $lo2.QueryTable
    $qt2.CommandType = 2
    $qt2.CommandText = "SELECT * FROM [Escenarios]"
    $qt2.BackgroundQuery = $false
    $qt2.RefreshStyle = 0
    $qt2.AdjustColumnWidth = $true
    if ($TestKey) { $qt2.Refresh($false) | Out-Null }

    $wb.Worksheets.Item("Config").Activate()
    # La llave NO se guarda en el archivo que se comparte; la URL vuelve a la del backend.
    $wb.Worksheets.Item("Config").Range("pLlave").Value2 = ""
    if ($TestUrl) { $wb.Worksheets.Item("Config").Range("pURL").Value2 = $urlReal }
    $wb.SaveAs($Out, 51)
    Write-Host "libro con consulta: $Out"
} finally {
    $wb = $null
    $xl.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
