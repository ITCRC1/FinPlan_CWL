param([string]$Libro, [switch]$Refrescar, [string[]]$Solo = @(), [string]$TestUrl = "", [string]$TestKey = "")
# Pestañas de detalle del Cierre Mensual de CWL (owner, 2026-11-11): «máximo detalle
# checkbook de gastos y checkbook de opex, ingresos y costos, posición por posición».
# Misma mecánica que add_queries.ps1: una consulta por pestaña que lee tVersiones,
# y al final de cada tabla las columnas del mes elegido (mes_columnas.ps1).
#
# -Refrescar necesita la llave en Config!C5 (o -TestUrl/-TestKey) y el backend desplegado.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "mes_columnas.ps1")
$defs = @(
  @{ q = "CheckbookIngresos"; hoja = "Checkbook Ingresos"; tabla = "tIngresos";   m = "ingresos.m";   d = "Checkbook de ingresos: depto x cuenta x mes (USD, positivo), de la consulta GL";
     mes = @(,@("M", "Mes", "Acumulado")) },
  @{ q = "CheckbookCostos";   hoja = "Checkbook Costos";   tabla = "tCostos";     m = "costos.m";     d = "Checkbook de costo de ventas (clase 5): depto x cuenta x mes (USD)";
     mes = @(,@("M", "Mes", "Acumulado")) },
  @{ q = "CheckbookOpex";     hoja = "Checkbook OPEX";     tabla = "tOpex";       m = "opex.m";       d = "Checkbook de OPEX: depto x cuenta x detalle x mes (USD)";
     mes = @(,@("M", "Mes", "Acumulado")) },
  @{ q = "CheckbookPlanilla"; hoja = "Checkbook Planilla"; tabla = "tPlanilla";   m = "planilla.m";   d = "Checkbook de planilla: posicion x concepto x mes";
     mes = @(,@("M", "Mes", "Acumulado")) },
  @{ q = "Posiciones";        hoja = "Posiciones";        tabla = "tPosiciones"; m = "posiciones.m"; d = "Posiciones por mes: FTE y costo, con nombre y salario";
     mes = @(@("FTE ", "FTE mes", ""), @("Costo M", "Costo mes", "Costo acum")) },
  @{ q = "Estadisticas";      hoja = "Estadisticas Rooms"; tabla = "tEstadisticas"; m = "estadisticas.m"; d = "Estadisticas de habitaciones por mes: disponibles, ocupadas, ocupacion, ADR, RevPAR";
     mes = @(,@("M", "Mes", "")) },
  @{ q = "Motor";             hoja = "P&L Motor";          tabla = "tMotor";      m = "motor.m";      d = "Lineas del P&L que calcula FinPlan, para el control motor - GL";
     mes = @(,@("M", "Mes", "Acumulado")) }
)
if ($Solo.Count -gt 0) { $defs = @($defs | Where-Object { $Solo -contains $_.q }) }
$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false; $xl.Visible = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  $wb.Queries.FastCombine = $true
  $cfg = $wb.Worksheets.Item("Config")
  $urlReal = [string]$cfg.Range("pURL").Value2
  if ($TestUrl) { $cfg.Range("pURL").Value2 = $TestUrl }
  if ($TestKey) { $cfg.Range("pLlave").Value2 = $TestKey }
  foreach ($x in $defs) {
    $m = Get-Content -Raw -Encoding UTF8 (Join-Path $here $x.m)
    foreach ($q in @($wb.Queries)) { if ($q.Name -eq $x.q) { $q.Delete() } }
    foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq $x.hoja) { $s.Delete() } }
    $wb.Queries.Add($x.q, $m, $x.d) | Out-Null
    $ws = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count))
    $ws.Name = $x.hoja
    $conn = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=$($x.q);Extended Properties=`"`""
    $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range("A1"))
    $lo.Name = $x.tabla
    $qt = $lo.QueryTable
    $qt.CommandType = 2
    $qt.CommandText = "SELECT * FROM [$($x.q)]"
    $qt.BackgroundQuery = $false
    $qt.RefreshStyle = 0
    $qt.PreserveColumnInfo = $true
    $qt.AdjustColumnWidth = $true
    if ($Refrescar) {
      $qt.Refresh($false) | Out-Null
      foreach ($p in $x.mes) { Add-ColumnasMes $lo $p[0] $p[1] $p[2] }
      foreach ($c in $lo.ListColumns) {
        if ($c.Name -match '^(M\d\d|Annual|Anio|Costo|Salario|Devengado|Cargas|Beneficios|Mes|Acumulado|Tasa)') { $c.DataBodyRange.NumberFormat = '#,##0.00;[Red](#,##0.00);"-"' }
        elseif ($c.Name -match '^FTE') { $c.DataBodyRange.NumberFormat = '0.00' }
      }
      "{0,-20} filas = {1}" -f $x.hoja, $lo.ListRows.Count
    }
    try { $ws.Activate(); $xl.ActiveWindow.SplitRow = 1; $xl.ActiveWindow.FreezePanes = $true } catch { }  # cosmetico: Excel oculto a veces no lo deja
  }
  $cfg.Activate()
  $cfg.Range("pLlave").Value2 = ""          # la llave no viaja en el archivo
  if ($TestUrl) { $cfg.Range("pURL").Value2 = $urlReal }
  $wb.Save(); $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
