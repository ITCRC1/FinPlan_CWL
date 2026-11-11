param([string]$Libro, [string]$Specs)
# -Specs: rutas separadas por «;» (con -File, PowerShell no arma arreglos).
$SpecPaths = @($Specs -split ';' | Where-Object { $_ })
# Escribe las hojas «P&L Mes» y «P&L YTD» desde pl_vistas_spec.py y las verifica en
# los doce meses de Config!C7 (utilidad de cada columna y el peor control).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "mes_columnas.ps1")
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  # La columna «Pre-Cierre del mes anterior» lee tGL[Mes anterior]: se asegura acá
  # para que un libro armado antes la tenga sin volver a correr add_queries.
  Add-ColumnaMesAnterior $wb.Worksheets.Item('GL').ListObjects.Item('tGL') "M" "Mes anterior"
  $xl.Calculation = -4135
  $pos = 2
  foreach ($sp in $SpecPaths) {
    $cfg = Get-Content -Raw -Encoding UTF8 $sp | ConvertFrom-Json
    $filas = @($cfg.filas); $last = [int]$filas[$filas.Count - 1].r; $netaRow = [int]$cfg.neta; $ncel = [int]$cfg.ncel
    $dl = @($cfg.datos); $var = @($cfg.var); $d0 = $dl[0]; $d1 = $dl[$dl.Count - 1]; $v0 = $var[0]; $v3 = $var[3]
    $ultCol = $var[3]
    foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq $cfg.hoja) { $s.Delete() } }
    $ws = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($pos - 1)); $pos++
    $ws.Name = $cfg.hoja
    $ws.Range("A:A").NumberFormat = "@"; $ws.Range("D:D").NumberFormat = "@"
    foreach ($f in $filas) {
      $r = [int]$f.r
      $arr = New-Object 'object[,]' 1, $ncel
      for ($j = 0; $j -lt $ncel; $j++) { $arr[0, $j] = [string]$f.celdas[$j] }
      try { $ws.Range("A$($r):$($ultCol)$($r)").Formula = $arr }
      catch {
        # Una celda mala no se pierde en silencio: se escribe de a una y se dice cuál.
        for ($j = 0; $j -lt $ncel; $j++) {
          try { $ws.Cells.Item($r, $j + 1).Formula = $arr[0, $j] }
          catch { Write-Warning "fila $r col $($j + 1): $($arr[0, $j])"; $ws.Cells.Item($r, $j + 1).Value2 = "'" + $arr[0, $j] }
        }
      }
      $row = $ws.Range("A$($r):$($ultCol)$($r)")
      switch ($f.estilo) {
        'titulo'    { $ws.Range("B$r").Font.Size = 14; $ws.Range("B$r").Font.Bold = $true }
        'nota'      { $ws.Range("B$r").Font.Italic = $true; $ws.Range("B$r").Font.Color = 0x6E6E6E }
        'encabezado'{ $row.Font.Bold = $true; $row.Interior.Color = 0x3A2A1F; $row.Font.Color = 0xFFFFFF }
        'seccion'   { $row.Font.Bold = $true; $row.Font.Size = 12; $row.Interior.Color = 0xE6D8C9 }
        'grupo'     { $ws.Range("B$r").Font.Bold = $true; $ws.Range("B$r").Font.Color = 0x7F3F1F }
        'subtotal'  { $row.Font.Bold = $true; $ws.Range("$d0$($r):$d1$($r)").Borders.Item(8).LineStyle = 1 }
        'total'     { $row.Font.Bold = $true; $row.Interior.Color = 0xF2EBE3; $ws.Range("$d0$($r):$d1$($r)").Borders.Item(8).LineStyle = 1; $ws.Range("$d0$($r):$d1$($r)").Borders.Item(9).LineStyle = -4119 }
        'control'   { $row.Font.Italic = $true; $row.Font.Color = 0x808080 }
        'resto'     { $row.Font.Italic = $true; $row.Font.Color = 0x808080 }
      }
    }
    # Fila 3: el mes y la base de la varianza (elegible). Fila 5: encabezado con el mes. Fila 6: clave fija.
    $ws.Range("B3").Formula = '="Mes: "&pMesNombre&"  ("&pMes&")  · cambialo en Config!C7      Base de la varianza →"'
    $ws.Range("B3").Font.Bold = $true; $ws.Range("B3").Font.Color = 0x1F1F7F; $ws.Range("B3").HorizontalAlignment = -4152
    $ws.Range("E3").Value2 = [string]$cfg.base_defecto
    if ([string]$cfg.bandera) {
      # Bandera (¿el Pre-Cierre trae algo en el mes?) en la columna separadora, fila 4, en blanco sobre blanco.
      $ws.Range("$($cfg.sep)4").Formula = [string]$cfg.bandera
      $ws.Range("$($cfg.sep)4").Font.Color = 0xFFFFFF
    }
    $ws.Range("E3").Interior.Color = 0xCCFFFF; $ws.Range("E3").Font.Bold = $true
    $lista = (@($cfg.fijos) | Where-Object { $_ -notmatch '^(Budget|Forecast)' }) -join ','
    $val = $ws.Range("E3").Validation; $val.Delete(); $val.Add(3, 1, 1, $lista) | Out-Null
    for ($k = 0; $k -lt $dl.Count; $k++) {
      $ws.Range("$($dl[$k])5").Formula = [string]$cfg.visibles[$k]
      $ws.Range("$($dl[$k])6").Value2 = [string]$cfg.fijos[$k]
    }
    for ($k = 0; $k -lt 4; $k++) { $ws.Range("$($var[$k])6").Value2 = [string]$cfg.var_titulos[$k] }
    $ws.Range("$($v0)5").Formula = '="Varianza: "&$E$3&" − Budget y − Forecast"'
    $ws.Range("$($d0)5:$($d1)5").Font.Bold = $true; $ws.Range("$($d0)5:$($d1)5").Interior.Color = 0xE6D8C9
    $ws.Range("$($d0)5:$($v3)6").WrapText = $true; $ws.Rows.Item(5).RowHeight = 30
    $ws.Range("$($v0)5").Font.Bold = $true; $ws.Range("$($v0)5").WrapText = $false
    $ws.Range("$($d0)7:$($d1)$last").NumberFormat = '#,##0;[Red](#,##0);"-"'
    $ws.Range("$($var[0])7:$($var[0])$last").NumberFormat = '#,##0;[Red](#,##0);"-"'
    $ws.Range("$($var[2])7:$($var[2])$last").NumberFormat = '#,##0;[Red](#,##0);"-"'
    $ws.Range("$($var[1])7:$($var[1])$last").NumberFormat = '0.0%;[Red]-0.0%;""'
    $ws.Range("$($var[3])7:$($var[3])$last").NumberFormat = '0.0%;[Red]-0.0%;""'
    $ws.Range("$($d0)5:$($v3)6").HorizontalAlignment = -4152
    $ws.Columns.Item(1).ColumnWidth = 20; $ws.Columns.Item(2).ColumnWidth = 52
    $ws.Range("$($d0):$($d1)").ColumnWidth = 13; $ws.Range("$($cfg.sep):$($cfg.sep)").ColumnWidth = 3
    $ws.Range("$($v0):$($v3)").ColumnWidth = 12
    $ws.Range("C:D").EntireColumn.Hidden = $true
    $ws.Activate(); $xl.ActiveWindow.DisplayGridlines = $false
    $ws.Range("E7").Select() | Out-Null; $xl.ActiveWindow.FreezePanes = $true
  }
  $xl.Calculation = -4105; $xl.CalculateFull()

  # Verificación: doce meses, utilidad neta de cada columna y el peor control.
  $mesCel = $wb.Worksheets.Item('Config').Range('pMes'); $orig = [double]$mesCel.Value2
  foreach ($sp in $SpecPaths) {
    $cfg = Get-Content -Raw -Encoding UTF8 $sp | ConvertFrom-Json
    $ws = $wb.Worksheets.Item($cfg.hoja); $dl = @($cfg.datos); $netaRow = [int]$cfg.neta
    $ctrl = @(); foreach ($f in $cfg.filas) { if ($f.estilo -eq 'control') { $ctrl += [int]$f.r } }
    "== $($cfg.hoja): " + (@($cfg.fijos) -join ' | ')
    for ($mes = 1; $mes -le 12; $mes++) {
      $mesCel.Value2 = [double]$mes; $xl.Calculate()
      $peor = 0.0
      foreach ($r in $ctrl) { foreach ($c in $dl) { $v = [double]$ws.Range("$c$r").Value2; if ([math]::Abs($v) -gt [math]::Abs($peor)) { $peor = $v } } }
      $netas = @($dl | ForEach-Object { '{0,11:N0}' -f [double]$ws.Range("$_$netaRow").Value2 })
      $vb = $ws.Range("$($cfg.var[0])$netaRow").Text; $vf = $ws.Range("$($cfg.var[2])$netaRow").Text
      "mes {0,2} {1}  var B {2,10} var F {3,10}  peor control {4:N2}" -f $mes, ($netas -join ''), $vb, $vf, $peor
    }
  }
  $mesCel.Value2 = $orig; $xl.Calculate()
  $wb.Worksheets.Item('Config').Activate()
  $wb.Save(); $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
