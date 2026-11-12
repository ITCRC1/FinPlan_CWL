param([string]$Libro, [switch]$Refrescar, [string[]]$Solo = @(), [string]$TestUrl = "", [string]$TestKey = "", [string]$UrlFinal = "")
# Agrega los checkbooks al libro en vivo: Ingresos, Costos, Gastos (OPEX), Planilla, Posiciones,
# Propietario (management fees y gastos de duenos) y Estadisticas (owner, 2026-11-11 y 2026-11-12).
# Misma mecanica que add_queries.ps1: una consulta por pestana que lee tVersiones.
$ErrorActionPreference = "Stop"
# Los formatos se escriben en el idioma de ESTE Excel (NumberFormatLocal): con
# NumberFormat, un Excel en espanol llamado desde PowerShell leia '#,##0' con la
# coma como decimal y el reporte salia «5041101,712» y 44.7% como «4.5%».
# Se le pregunta a Excel sus separadores y se traduce el formato escrito en ingles.
function Formato-Local($xl, [string]$fmt) {
  $dec = $xl.International(3); $mil = $xl.International(4)
  return ($fmt -replace ',', [char]1 -replace '\.', [char]2) -replace [char]1, $mil -replace [char]2, $dec
}
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$defs = @(
  @{ q = "CheckbookIngresos";   hoja = "Checkbook Ingresos";   tabla = "tIngresos";   m = "ingresos.m";    d = "Checkbook de ingresos: depto x cuenta x mes (USD, positivo), desde el GL" },
  @{ q = "CheckbookCostos";     hoja = "Checkbook Costos";     tabla = "tCostos";     m = "costos.m";      d = "Checkbook de costo de ventas (clase 5): depto x cuenta x mes (USD)" },
  @{ q = "CheckbookOpex";       hoja = "Checkbook Gastos";     tabla = "tOpex";       m = "opex.m";        d = "Checkbook de gastos (OPEX): depto x cuenta x detalle x mes (USD)" },
  @{ q = "CheckbookPlanilla";   hoja = "Checkbook Planilla";   tabla = "tPlanilla";   m = "planilla.m";    d = "Checkbook de planilla: posicion x concepto x mes" },
  @{ q = "ControlPlanilla";     hoja = "Control Planilla";     tabla = "tControlPlanilla"; m = "control_planilla.m"; d = "Checkbook de planilla contra el GL: version x depto x cuenta, con la diferencia de cada mes" },
  @{ q = "Repartos";            hoja = "Repartos";             tabla = "tRepartos";   m = "repartos.m";    d = "Repartos de Cafeteria, Lavanderia y salarios: centro -> depto x cuenta x mes" },
  @{ q = "CentrosCosto";        hoja = "Centros de costo";     tabla = "tCentrosCosto"; m = "centros_costo.m"; d = "Cafeteria y Lavanderia como centros de costo: acumula, reparte, neto en 0 y a donde fue" },
  @{ q = "RepartoSalarios";     hoja = "Reparto de salarios";  tabla = "tRepartoSalarios"; m = "reparto_salarios.m"; d = "Reparto de salarios regla por regla: sale del origen, entra al destino, control contra lo guardado" },
  @{ q = "Posiciones";          hoja = "Posiciones";           tabla = "tPosiciones"; m = "posiciones.m";  d = "Posiciones por mes: FTE y costo, con nombre y salario" },
  @{ q = "CheckbookPropietario";hoja = "Checkbook Propietario";tabla = "tPropietario";m = "propietario.m"; d = "Debajo del GOP: management fees, renta, seguros, capital, intereses, depreciacion e impuestos" },
  @{ q = "Motor";               hoja = "P&L Motor";            tabla = "tMotor";      m = "motor.m";       d = "Lineas del P&L que calcula FinPlan, para el control motor - GL" },
  @{ q = "Habitaciones";        hoja = "Habitaciones por tipo"; tabla = "tHabitaciones"; m = "habitaciones.m"; d = "Estadisticas por tipo de habitacion y por set (estandar, Villas): disponibles, ocupadas, pax, ocupacion, ingreso, ADR, RevPAR" },
  @{ q = "Estadisticas";        hoja = "Estadisticas Rooms";   tabla = "tEstadisticas"; m = "estadisticas.m"; d = "Estadisticas de habitaciones por mes: disponibles, ocupadas, ocupacion, ADR, RevPAR" }
)
# Con -File, PowerShell pasa "A,B,C" como UN solo texto: se parte aca.
$Solo = @($Solo | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($Solo.Count -gt 0) { $defs = @($defs | Where-Object { $Solo -contains $_.q }) }
$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false; $xl.Visible = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  $wb.Queries.FastCombine = $true
  $cfg = $wb.Worksheets.Item("Config")
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
      foreach ($c in $lo.ListColumns) {
        if ($c.Name -match '^(M\d\d|Annual|Anio|Costo|Salario|Devengado|Cargas|Beneficios|Dif |Checkbook anual|GL anual|Diferencia|Disponibles|Ocupadas|Pax|Ingreso|ADR|RevPAR)') { $c.DataBodyRange.NumberFormatLocal = (Formato-Local $xl '#,##0.00;(#,##0.00);"-"') }
        elseif ($c.Name -match '%') { $c.DataBodyRange.NumberFormatLocal = (Formato-Local $xl '0.0') }
        elseif ($c.Name -match '^FTE') { $c.DataBodyRange.NumberFormatLocal = (Formato-Local $xl '0.00') }
      }
      "{0,-20} filas = {1}" -f $x.hoja, $lo.ListRows.Count
    }
    $ws.Activate(); $xl.ActiveWindow.SplitRow = 1; $xl.ActiveWindow.FreezePanes = $true
  }
  # La llave NO viaja en el archivo, y la direccion queda la de produccion.
  if ($UrlFinal) { $cfg.Range("pURL").Value2 = $UrlFinal }
  $cfg.Range("pLlave").Value2 = ""
  $wb.Worksheets.Item("Config").Activate()
  $wb.Save(); $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
