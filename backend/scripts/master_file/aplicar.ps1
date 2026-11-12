param([string]$Libro, [string]$Spec, [switch]$DejarVisibles)
# Escribe el Master File (hojas AM + Reporte) en un libro en vivo que YA tiene las
# tablas (tGL, tMotor, tHabitaciones, tEstadisticas). Via COM de Excel: las
# formulas con referencias estructuradas solo se pueden escribir cuando la tabla
# existe; escritas antes, se rompen al abrir.
$ErrorActionPreference = 'Stop'
# Los formatos se escriben en el idioma de ESTE Excel (NumberFormatLocal): con
# NumberFormat, un Excel en espanol llamado desde PowerShell leia '#,##0' con la
# coma como decimal y el reporte salia «5041101,712» y 44.7% como «4.5%».
# Se le pregunta a Excel sus separadores y se traduce el formato escrito en ingles.
function Formato-Local($xl, [string]$fmt) {
  $dec = $xl.International(3); $mil = $xl.International(4)
  return ($fmt -replace ',', [char]1 -replace '\.', [char]2) -replace [char]1, $mil -replace [char]2, $dec
}
$plano = Get-Content -Raw -Encoding UTF8 $Spec | ConvertFrom-Json
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  $xl.Calculation = -4135   # manual mientras se escribe

  # 1) Hojas vacias, en el orden del reporte y al principio del libro.
  $hojas = @($plano.hojas)
  foreach ($h in $hojas) { foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq $h.nombre) { $s.Delete() } } }
  # Y las de una corrida anterior aunque se llamaran distinto (p. ej. en otro idioma): todo
  # lo que sea reporte se rehace; las tablas de datos y Config no se tocan.
  foreach ($s in @($wb.Worksheets)) { if ($s.Name -match '^(AM\d\d |00 |Report)') { $s.Delete() } }
  $ant = $null
  foreach ($h in $hojas) {
    if ($ant -eq $null) { $ws = $wb.Worksheets.Add($wb.Worksheets.Item(1)) }
    else { $ws = $wb.Worksheets.Add([Type]::Missing, $ant) }
    $ws.Name = $h.nombre
    $ws.Cells.Font.Name = 'Calibri'; $ws.Cells.Font.Size = 10
    $xl.ActiveWindow.DisplayGridlines = $false
    $ant = $ws
  }

  # 2) Nombres (vA25, vF26... y los rangos de los graficos) ANTES de las formulas.
  foreach ($p in $plano.nombres.PSObject.Properties) {
    foreach ($n in @($wb.Names)) { if ($n.Name -eq $p.Name) { $n.Delete() } }
    $wb.Names.Add($p.Name, $p.Value) | Out-Null
  }

  # 3) Filas.
  $letra = { param($i) $s = ''; while ($i -gt 0) { $m = ($i - 1) % 26; $s = [char](65 + $m) + $s; $i = [int](($i - $m - 1) / 26) }; $s }
  foreach ($h in $hojas) {
    $ws = $wb.Worksheets.Item($h.nombre)
    $j = 1; foreach ($a in @($h.anchos)) { $ws.Columns.Item($j).ColumnWidth = $a; $j++ }
    $ultCol = @($h.anchos).Count
    foreach ($f in @($h.filas)) {
      $r = [int]$f.r; $c = @($f.celdas)
      if ($c.Count -gt 0) {
        $arr = New-Object 'object[,]' 1, $c.Count
        for ($k = 0; $k -lt $c.Count; $k++) { $arr[0, $k] = [string]$c[$k] }
        $fin = & $letra $c.Count
        $ws.Range("A$($r):$fin$($r)").Formula = $arr
      }
      $fila = $ws.Range("A$($r):" + (& $letra $ultCol) + "$r")
      switch ($f.estilo) {
        'titulo'     { $ws.Range("B$r").Font.Size = 15; $ws.Range("B$r").Font.Bold = $true; $ws.Range("B$r").Font.Color = 0x3A2A1F }
        'portada'    { $ws.Range("B$r").Font.Size = 20; $ws.Range("B$r").Font.Bold = $true; $ws.Range("B$r").Font.Color = 0x3A2A1F }
        'subportada' { $ws.Range("B$r").Font.Size = 13; $ws.Range("B$r").Font.Color = 0x7F3F1F }
        'nota'       { $ws.Range("B$r").Font.Italic = $true; $ws.Range("B$r").Font.Color = 0x6E6E6E; $ws.Range("B$r").WrapText = $false }
        'texto'      { $rg = $ws.Range("B$($r):" + (& $letra $ultCol) + "$r"); $rg.Merge(); $rg.WrapText = $true; $rg.VerticalAlignment = -4160 }
        'encabezado' { $fila.Font.Bold = $true; $fila.Interior.Color = 0x3A2A1F; $fila.Font.Color = 0xFFFFFF; $fila.HorizontalAlignment = -4152; $ws.Range("B$r").HorizontalAlignment = -4131 }
        'seccion'    { $fila.Font.Bold = $true; $fila.Interior.Color = 0xE6D8C9 }
        'subtotal'   { $fila.Font.Bold = $true; $fila.Borders.Item(8).LineStyle = 1 }
        'total'      { $fila.Font.Bold = $true; $fila.Interior.Color = 0xF2EBE3; $fila.Borders.Item(8).LineStyle = 1 }
        'resto'      { $fila.Font.Italic = $true; $fila.Font.Color = 0x808080 }
        'control'    { $fila.Font.Italic = $true; $fila.Font.Color = 0x808080 }
        'aux'        { $ws.Rows.Item($r).Hidden = $true }
        'pct'        { $ws.Range("C$($r):" + (& $letra $ultCol) + "$r").NumberFormatLocal = (Formato-Local $xl '0.0%;-0.0%;""') }
        'usd2'       { $ws.Range("C$($r):" + (& $letra $ultCol) + "$r").NumberFormatLocal = (Formato-Local $xl '#,##0.00;(#,##0.00);"-"') }
      }
      if ($f.alto) { $ws.Rows.Item($r).RowHeight = [double]$f.alto }
    }
    foreach ($fm in @($h.formatos)) {
      # El formato general no pisa las filas de % y de ADR, que ya tienen el suyo.
      foreach ($cel in $ws.Range($fm.rango).Rows) {
        $nf = [string]$cel.Cells.Item(1, 2).NumberFormat
        if ($nf -notmatch '%|0\.00') { $cel.NumberFormatLocal = (Formato-Local $xl $fm.fmt) }
      }
    }
    if ($h.ocultar_a) { $ws.Columns.Item(1).Hidden = $true }
    $ws.Activate(); $xl.ActiveWindow.DisplayGridlines = $false
  }

  # 4) Graficos (leen rangos con nombre: siguen al dato aunque cambie la version).
  $xl.Calculation = -4105
  $xl.Calculate()
  foreach ($h in $hojas) {
    $ws = $wb.Worksheets.Item($h.nombre)
    foreach ($g in @($h.graficos)) {
      if (-not $g) { continue }
      $cel = $ws.Range($g.celda)
      $co = $ws.ChartObjects().Add($cel.Left, $cel.Top, [double]$g.ancho, [double]$g.alto)
      $ch = $co.Chart
      $ch.ChartType = $(if ($g.tipo -eq 'lineas') { 4 } else { 51 })   # xlLine / xlColumnClustered
      while ($ch.SeriesCollection().Count -gt 0) { $ch.SeriesCollection(1).Delete() }
      foreach ($s in @($g.series)) {
        $se = $ch.SeriesCollection().NewSeries()
        $se.Name = "=" + $wb.Name.Replace("'", "''").Insert(0, "'") + "'!" + $s.nombre
        $se.Values = "='" + $wb.Name.Replace("'", "''") + "'!" + $s.ref
        $se.XValues = "='" + $wb.Name.Replace("'", "''") + "'!PL_MESES"
      }
      $ch.HasTitle = $true; $ch.ChartTitle.Text = $g.titulo; $ch.ChartTitle.Font.Size = 11
      $ch.HasLegend = $true; $ch.Legend.Position = -4107
      $ch.Axes(2).TickLabels.NumberFormatLocal = (Formato-Local $xl '#,##0')
    }
  }

  # 5) Reporte listo para PDF: vertical, una pagina de ancho.
  $rep = $wb.Worksheets.Item('Report')
  $ps = $rep.PageSetup
  $ps.Orientation = 1; $ps.Zoom = $false; $ps.FitToPagesWide = 1; $ps.FitToPagesTall = $false
  $ps.CenterHorizontally = $true; $ps.PrintArea = 'A1:G' + $rep.UsedRange.Rows.Count
  $ps.CenterFooter = 'CWL · Owners report · page &P of &N'

  # 6) Las tablas de datos quedan ocultas; Config y Escenarios a la vista (la llave va ahi).
  #    -DejarVisibles: el libro de trabajo completo (owner, 2026-11-12: validar los
  #    checkbooks junto a la presentacion), no se oculta nada.
  if (-not $DejarVisibles) {
  foreach ($n in @('GL','P&L Motor','Habitaciones por tipo','Estadisticas Rooms','Posiciones','Checkbook Ingresos','Checkbook Costos','Checkbook Gastos','Checkbook Planilla','Control Planilla','Checkbook Propietario')) {
    foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq $n) { $s.Visible = 0 } }
  }
  }
  $wb.Worksheets.Item('00 Index').Activate()
  $wb.Save(); $wb.Close($false)
  Write-Host "master file escrito: $Libro"
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
