param([string]$Libro, [string]$Hojas, [string]$Salida,
      [string]$TestUrl = "", [string]$TestKey = "", [switch]$Refrescar)
# Mete las pestañas RV (ingreso reconstruido, Standard vs Villas) en el Master File.
#
# Owner, 2026-11-28: «metelo en el master file». Un solo «Actualizar todo» tiene
# que mover también estas hojas: nada de un segundo libro.
#
#   1) Borra las RV de una corrida anterior (por nombre exacto, -ceq).
#   2) Copia las seis hojas de $Hojas (build_revenue.py) EN GRUPO, antes de
#      «AM97 Controls»: copiadas juntas, las referencias entre ellas quedan
#      internas. Si algún vínculo quedara apuntando al libro de origen, se
#      cambia por este mismo libro.
#   3) Nombres pRV_anio / pRV_tipo / pRV_ver -> RV3 Inputs!B5:B7.
#   4) Consulta «RevenueSupuestos» -> tabla tRevSup en la hoja oculta «RV Data».
#      URL y llave son las de Config (pURL / pLlave): una sola llave.
#   5) Agrega las RV al «00 Index».
#
# ⚠️ No toca Config. -TestUrl/-TestKey son SOLO para probar contra un backend
# local en una copia de trabajo: nunca se usan sobre el libro que se entrega.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$m = Get-Content -Raw -Encoding UTF8 (Join-Path $here 'revenue_supuestos.m')
$nombres = @('RV1 Revenue Build', 'RV2 Per guest-night', 'RV3 Inputs', 'RV4 Rooms', 'RV5 Revenue lines', 'RV Data')

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.AskToUpdateLinks = $false
try {
  $wb = $xl.Workbooks.Open($Libro, 0)
  $wb.SaveAs($Salida, 51)
  $xl.Calculation = -4135      # manual mientras se arma

  # 1) Lo de una corrida anterior
  foreach ($s in @($wb.Worksheets)) { if ($nombres -ccontains $s.Name) { $s.Visible = -1; $s.Delete() } }
  foreach ($qq in @($wb.Queries)) { if ($qq.Name -ceq 'RevenueSupuestos') { $qq.Delete() } }
  foreach ($n in @($wb.Names)) { if (@('pRV_anio', 'pRV_tipo', 'pRV_ver') -ccontains $n.Name) { $n.Delete() } }

  # 2) Copiar en grupo
  $src = $xl.Workbooks.Open($Hojas, 0)
  $destino = $null
  foreach ($s in @($wb.Worksheets)) { if ($s.Name -ceq 'AM97 Controls') { $destino = $s } }
  $grupo = $src.Worksheets.Item([object[]]$nombres)
  if ($destino) { $grupo.Copy($destino) } else { $grupo.Copy([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count)) }
  $rutaHojas = $src.FullName
  $src.Close($false)
  $links = $wb.LinkSources(1)
  if ($null -ne $links) {
    foreach ($l in $links) { if ($l -eq $rutaHojas) { Write-Host "vinculo a si mismo: $l"; $wb.ChangeLink($l, $wb.FullName, 1) } }
  }

  # 3) Nombres del escenario
  $wb.Names.Add('pRV_anio', "='RV3 Inputs'!`$B`$5") | Out-Null
  $wb.Names.Add('pRV_tipo', "='RV3 Inputs'!`$B`$6") | Out-Null
  $wb.Names.Add('pRV_ver', "='RV3 Inputs'!`$B`$7") | Out-Null
  $v = $wb.Worksheets.Item('RV3 Inputs').Range('B6').Validation
  $v.Delete(); $v.Add(3, 1, 1, 'BUDGET,FORECAST') | Out-Null

  # 4) Consulta y tabla
  $wb.Queries.FastCombine = $true
  $wb.Queries.Add('RevenueSupuestos', $m, 'Revenue inputs of one scenario (RV sheets), from FinPlan CWL') | Out-Null
  $ws = $wb.Worksheets.Item('RV Data')
  $ws.Cells.Clear() | Out-Null
  $q = [char]34
  $conn = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=RevenueSupuestos;Extended Properties=$q$q"
  $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range('A1'))
  $lo.Name = 'tRevSup'
  $qt = $lo.QueryTable
  $qt.CommandType = 2
  $qt.CommandText = 'SELECT * FROM [RevenueSupuestos]'
  $qt.BackgroundQuery = $false
  $qt.RefreshStyle = 0          # xlOverwriteCells: no corre referencias
  $qt.PreserveColumnInfo = $true
  if ($TestUrl) { $wb.Worksheets.Item('Config').Range('pURL').Value2 = $TestUrl }
  if ($TestKey) { $wb.Worksheets.Item('Config').Range('pLlave').Value2 = $TestKey }
  if ($Refrescar) { $qt.Refresh($false) | Out-Null }
  $ws.Visible = 0               # oculta

  # 5) Indice
  $ix = $null
  foreach ($s in @($wb.Worksheets)) { if ($s.Name -ceq '00 Index') { $ix = $s } }
  if ($ix) {
    $ult = $ix.Cells.Item($ix.Rows.Count, 2).End(-4162).Row
    $filas = @(
      @('RV1 Revenue Build', 'Every revenue line rebuilt from its inputs, Standard vs Villas, against the Revenue Checkbook; statistics and controls'),
      @('RV2 Per guest-night', 'From rack rate to net, per guest-night, for each package line (Food, Beverage, Tours, Transport, Sustainability)'),
      @('RV3 Inputs', 'Scenario to read + every revenue input: FinPlan | Mine (your own assumption) | Used'),
      @('RV4 Rooms', 'Available, occupied, guests, net rate and Room Revenue by category and month, with Standard / Villas subtotals'),
      @('RV5 Revenue lines', 'Every revenue line by set and month, with the FinPlan checkbook row and the difference')
    )
    $k = 0
    foreach ($s in @($ix.Range("B5:B$ult").Value2)) { if ($s -like 'RV*') { $k++ } }
    if ($k -eq 0) {
      $n0 = $ix.Cells.Item($ult, 1).Value2
      $r = $ult + 1
      foreach ($f in $filas) {
        # .Formula y no .Value2: un numero sacado de un arreglo COM no se deja asignar.
        if ($n0 -is [double]) { $n0 = [int]$n0 + 1; $ix.Cells.Item($r, 1).Formula = "$n0" }
        $ix.Cells.Item($r, 2).Formula = "$($f[0])"; $ix.Cells.Item($r, 3).Formula = "$($f[1])"; $r++
      }
    }
  }

  $xl.Calculation = -4105      # automatico
  $xl.CalculateFull()
  $wb.Worksheets.Item('RV1 Revenue Build').Activate()
  $wb.Save()
  $quedan = $wb.LinkSources(1); $n = 0; if ($null -ne $quedan) { foreach ($x in $quedan) { $n++; Write-Host "vinculo externo: $x" } }
  Write-Host "listo: $Salida  (vinculos externos: $n)"
  $wb.Close($true)
} finally {
  $xl.Quit()
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
