param([string]$Libro, [switch]$Refrescar, [string]$TestUrl = "", [string]$TestKey = "", [string]$UrlFinal = "")
# Reemplaza el TEXTO de todas las consultas de un libro en vivo por el de los .m del repo,
# sin tocar hojas, tablas ni formulas. La consulta vive DENTRO del archivo: un arreglo en
# un .m no llega a un libro ya entregado hasta que se le reescribe la consulta.
# Con -Refrescar actualiza todo de a una consulta (como lo hace Excel sin apuro).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$mapa = [ordered]@{
  "GL" = "query.m"; "Escenarios" = "escenarios.m";
  "CheckbookIngresos" = "ingresos.m"; "CheckbookCostos" = "costos.m"; "CheckbookOpex" = "opex.m";
  "CheckbookPlanilla" = "planilla.m"; "ControlPlanilla" = "control_planilla.m"; "Repartos" = "repartos.m";
  "CentrosCosto" = "centros_costo.m"; "RepartoSalarios" = "reparto_salarios.m"; "Posiciones" = "posiciones.m";
  "CheckbookPropietario" = "propietario.m"; "Motor" = "motor.m"; "Habitaciones" = "habitaciones.m";
  "Estadisticas" = "estadisticas.m"
}
$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false; $xl.Visible = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  $wb.Queries.FastCombine = $true
  $cfg = $wb.Worksheets.Item("Config")
  if ($TestUrl) { $cfg.Range("pURL").Value2 = $TestUrl }
  if ($TestKey) { $cfg.Range("pLlave").Value2 = $TestKey }
  foreach ($q in $mapa.Keys) {
    $m = Get-Content -Raw -Encoding UTF8 (Join-Path $here $mapa[$q])
    $hay = $false
    foreach ($x in @($wb.Queries)) { if ($x.Name -eq $q) { $x.Formula = $m; $hay = $true } }
    Write-Host ("{0,-22} {1}" -f $q, $(if ($hay) { "actualizada" } else { "NO EXISTE en el libro" }))
  }
  if ($Refrescar) {
    # Primero las de datos, despues las que leen de otras (Ingresos, Propietario, Control).
    foreach ($ws in @($wb.Worksheets)) {
      foreach ($lo in @($ws.ListObjects)) {
        try { $qt = $lo.QueryTable } catch { continue }
        if ($qt -eq $null) { continue }
        $qt.BackgroundQuery = $false
        $qt.Refresh($false) | Out-Null
        Write-Host ("{0,-22} filas = {1}" -f $ws.Name, $lo.ListRows.Count)
      }
    }
    $xl.CalculateFull()
  }
  if ($UrlFinal) { $cfg.Range("pURL").Value2 = $UrlFinal }
  if ($TestKey) { $cfg.Range("pLlave").Value2 = "" }
  $wb.Save(); $wb.Close($false)
  Write-Host "FIN 0"
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
