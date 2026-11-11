param([string]$Libro, [string]$TestUrl = "", [string]$TestKey = "", [switch]$Refrescar)
# Último paso del libro del Cierre Mensual: (opcional) un «Actualizar todo» completo
# para comprobar que las columnas del mes sobreviven al refresh, ordena las hojas,
# repone la URL del backend y deja la llave VACÍA.
$ErrorActionPreference = 'Stop'
$orden = @('Config', 'P&L Mes', 'P&L YTD', 'Controles', 'P&L USALI', 'GL', 'Checkbook Ingresos', 'Checkbook Costos',
           'Checkbook OPEX', 'Checkbook Planilla', 'Posiciones', 'Estadisticas Rooms', 'P&L Motor', 'Escenarios')
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  $cfg = $wb.Worksheets.Item('Config')
  $urlReal = [string]$cfg.Range('pURL').Value2
  if ($Refrescar) {
    if ($TestUrl) { $cfg.Range('pURL').Value2 = $TestUrl }
    if ($TestKey) { $cfg.Range('pLlave').Value2 = $TestKey }
    foreach ($c in @($wb.Connections)) { try { $c.OLEDBConnection.BackgroundQuery = $false } catch {} }
    $wb.RefreshAll(); $xl.CalculateUntilAsyncQueriesDone(); $xl.CalculateFull()
    foreach ($s in @($wb.Worksheets)) {
      foreach ($lo in @($s.ListObjects)) {
        $n = @($lo.ListColumns | ForEach-Object { $_.Name })
        $mes = if ($n -contains 'Mes') { 'Mes' } elseif ($n -contains 'Costo mes') { 'Costo mes' } else { '' }
        $vacias = 0
        if ($mes -and $lo.ListRows.Count -gt 0) {
          foreach ($v in @($lo.ListColumns.Item($mes).DataBodyRange.Value2)) { if ($v -eq $null) { $vacias++ } }
        }
        "{0,-20} {1,-14} filas={2,5}  columna del mes: {3,-10} celdas vacias={4}" -f $s.Name, $lo.Name, $lo.ListRows.Count, $mes, $vacias
      }
    }
  }
  for ($i = $orden.Count - 1; $i -ge 0; $i--) {
    $h = $null; foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq $orden[$i]) { $h = $s } }
    if ($h) { $h.Move($wb.Worksheets.Item(1)) }
  }
  $cfg.Range('pLlave').Value2 = ''
  if ($TestUrl) { $cfg.Range('pURL').Value2 = $urlReal }
  $cfg.Activate()
  "hojas: " + ((@($wb.Worksheets) | ForEach-Object { $_.Name }) -join ' | ')
  "pURL = " + $cfg.Range('pURL').Value2 + "   pLlave vacia = " + ([string]$cfg.Range('pLlave').Value2 -eq '')
  $wb.Save(); $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
