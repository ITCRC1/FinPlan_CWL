param([string]$In, [string]$Out, [string]$SpecPath)
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -Raw -Encoding UTF8 $SpecPath | ConvertFrom-Json; $filas = @($cfg.filas); $last = [int]$filas[$filas.Count-1].r; $netaRow = [int]$cfg.neta; $gopRow = [int]$cfg.gop
Copy-Item $In $Out -Force
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
try {
  $wb = $xl.Workbooks.Open($Out)
  $xl.Calculation = -4135   # manual mientras se escribe
  foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq 'P&L USALI') { $s.Delete() } }
  $ws = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count))
  $ws.Name = 'P&L USALI'
  $ws.Range("A:A").NumberFormat = "@"
  $ws.Range("D:D").NumberFormat = "@"
  foreach ($f in $filas) {
    $r = [int]$f.r
    $arr = New-Object 'object[,]' 1,18
    for ($j = 0; $j -lt 18; $j++) { $arr[0,$j] = [string]$f.celdas[$j] }
    $ws.Range("A$($r):R$($r)").Formula = $arr
    $row = $ws.Range("A$($r):R$($r)")
    switch ($f.estilo) {
      'titulo'    { $ws.Range("B$r").Font.Size = 14; $ws.Range("B$r").Font.Bold = $true }
      'nota'      { $ws.Range("B$r").Font.Italic = $true; $ws.Range("B$r").Font.Color = 0x6E6E6E }
      'selector'  { $ws.Range("A$r").Font.Bold = $true; $ws.Range("B$r").Interior.Color = 0xCCFFFF; $ws.Range("B$r").Font.Bold = $true
                    $v = $ws.Range("B$r").Validation; $v.Delete(); $v.Add(3, 1, 1, '=INDIRECT("tVersiones[Etiqueta]")') }
      'encabezado'{ $row.Font.Bold = $true; $row.Interior.Color = 0x3A2A1F; $row.Font.Color = 0xFFFFFF }
      'seccion'   { $row.Font.Bold = $true; $row.Font.Size = 12; $row.Interior.Color = 0xE6D8C9 }
      'grupo'     { $ws.Range("B$r").Font.Bold = $true; $ws.Range("B$r").Font.Color = 0x7F3F1F }
      'subtotal'  { $row.Font.Bold = $true; $ws.Range("E$($r):Q$($r)").Borders.Item(8).LineStyle = 1 }
      'total'     { $row.Font.Bold = $true; $row.Interior.Color = 0xF2EBE3; $ws.Range("E$($r):Q$($r)").Borders.Item(8).LineStyle = 1; $ws.Range("E$($r):Q$($r)").Borders.Item(9).LineStyle = -4119 }
      'control'   { $row.Font.Italic = $true; $row.Font.Color = 0x808080 }
      'resto'     { $row.Font.Italic = $true; $row.Font.Color = 0x808080 }
    }
  }
  $h = 6
  $meses = 'Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'
  for ($j = 0; $j -lt 12; $j++) { $ws.Cells.Item($h, 5 + $j).Value2 = $meses[$j] }
  $ws.Cells.Item($h, 17).Value2 = 'Anual'; $ws.Cells.Item($h, 18).Value2 = '% ingresos'
  $ws.Range("E7:Q$last").NumberFormat = '#,##0;[Red](#,##0);"-"'
  $ws.Range("R7:R$last").NumberFormat = '0.0%;[Red]-0.0%;""'
  $ws.Range("E$($h):R$($h)").HorizontalAlignment = -4152
  $ws.Columns.Item(1).ColumnWidth = 22; $ws.Columns.Item(2).ColumnWidth = 58
  $ws.Range("E:Q").ColumnWidth = 12; $ws.Columns.Item(18).ColumnWidth = 10
  $ws.Range("B2").WrapText = $false
  $ws.Range("C:D").EntireColumn.Hidden = $true
  $ws.Activate(); $xl.ActiveWindow.DisplayGridlines = $false
  try { $ws.Range("E7").Select(); $xl.ActiveWindow.FreezePanes = $true } catch { }  # cosmetico: Excel oculto a veces no lo deja
  $xl.Calculation = -4105
  $xl.CalculateFull()
  # VerificaciÃ³n: correr cada versiÃ³n y leer utilidad neta y controles
  $neta = $netaRow
  $ctrl = @()
  for ($i = 1; $i -le $last; $i++) { if ($filas[$i-1].estilo -eq 'control') { $ctrl += [int]$filas[$i-1].r } }
  $lo = $wb.Worksheets.Item('Config').ListObjects.Item('tVersiones')
  foreach ($c in $lo.ListColumns.Item('Etiqueta').DataBodyRange.Cells) {
    $et = [string]$c.Value2
    $ws.Range("B3").Value2 = $et; $xl.Calculate()
    $cv = ($ctrl | ForEach-Object { $ws.Cells.Item($_, 17).Value2 }) -join ' / '
    "{0,-22} utilidad neta anual = {1,14:N2}   GOP = {2,14:N2}   controles = {3}" -f $et, $ws.Cells.Item($neta, 17).Value2, $ws.Cells.Item($gopRow, 17).Value2, $cv
  }
  $ws.Range("B3").Value2 = 'Pre-Cierre 2026'; $xl.Calculate()
  $wb.Save(); $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }

