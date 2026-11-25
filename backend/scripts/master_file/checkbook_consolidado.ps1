param([string]$Libro, [string]$Salida, [switch]$Refrescar)
# Deja la pestaña «Checkbook Consolidado» del Master File viva POR SÍ SOLA.
#
# Owner, 2026-11-24: armó esa pestaña copiando las hojas del «Checkbook OPEX en
# vivo v4» (un bloque por depto) y le quedaron 112.881 fórmulas apuntando a ESE
# otro archivo ([1]Datos). Pidió «que se actualice automáticamente, sin depender
# del GL, así mismo como está, sin sufrir ningún cambio».
#
# Lo que hace, sin tocar una sola celda de la pestaña:
#   1) Hoja «Config Checkbook»: los lugares del libro (Meses, Fila 1, Fila 2, V,
#      W, X) con tipo · año · versión · hasta · período, y sus nombres pM_*, pF1_*…
#      La URL y la llave son las de Config (pURL / pLlave): una sola llave.
#   2) Hoja oculta «Datos» con la consulta CheckbookConsolidado (tabla tDatos), la misma
#      del checkbook en vivo: /api/consolidado/checkbook-opex/. No lee el GL.
#   3) Cambia el vínculo externo por este mismo libro: [1]Datos!G:G -> Datos!G:G.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$m = Get-Content -Raw -Encoding UTF8 (Join-Path $here 'checkbook_opex.m')

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.AskToUpdateLinks = $false
try {
  $wb = $xl.Workbooks.Open($Libro, 0)
  $wb.SaveAs($Salida, 51)            # el vínculo a sí mismo necesita su ruta final
  $xl.Calculation = -4135

  # Nombres viejos que apuntaban al Config del otro libro
  $lugares = 'pM','pF1','pF2','pV','pW','pX'
  $campos = 'tipo','anio','ver','hasta','modo','lbl'
  foreach ($n in @($wb.Names)) {
    $nom = $n.Name
    foreach ($l in $lugares) { foreach ($c in $campos) { if ($nom -eq "$($l)_$c") { $n.Delete() } } }
  }

  # 1) Config Checkbook
  foreach ($s in @($wb.Worksheets)) { if ($s.Name -ceq 'Config Checkbook') { $s.Delete() } }
  $cb = $wb.Worksheets.Item('Checkbook Consolidado')
  $cfg = $wb.Worksheets.Add($cb)
  $cfg.Name = 'Config Checkbook'
  $cfg.Cells.Font.Name = 'Calibri'; $cfg.Cells.Font.Size = 10
  $cfg.Range('B1').Value2 = 'Checkbook Consolidado — qué versión va en cada lugar'
  $cfg.Range('B1').Font.Size = 13; $cfg.Range('B1').Font.Bold = $true
  $cfg.Range('B2').Value2 = 'La URL y la llave son las de la hoja Config. Cambiar Tipo / Año / Versión y hacer Datos → Actualizar todo. No depende del GL.'
  $enc = 'Lugar del libro','Tipo','Año','Versión','Hasta mes','Período (V/W/X)','Rótulo (automático)'
  for ($i = 0; $i -lt $enc.Count; $i++) { $cfg.Cells.Item(4, 2 + $i).Value2 = $enc[$i] }
  $cfg.Range('B4:H4').Font.Bold = $true
  $cfg.Range('B4:H4').Interior.Color = 0x5F3A1E; $cfg.Range('B4:H4').Font.Color = 0xFFFFFF
  # Lo mismo que tenía el v4 del que salió la pestaña.
  $filas = @(
    @('Meses (detalle 800–820)', 'pM',  'BUDGET',   2027, 'Working', '',  ''),
    @('Fila de año 1',           'pF1', 'ACTUAL',   2025, '',        '',  ''),
    @('Fila de año 2',           'pF2', 'FORECAST', 2026, '',        '',  ''),
    @('Columna V',               'pV',  'ACTUAL',   2026, '',        12,  'ACUMULADO'),
    @('Columna W',               'pW',  'FORECAST', 2026, '',        12,  'ACUMULADO'),
    @('Columna X (no se usa en esta pestaña)', 'pX', '', '', '', '', '')
  )
  $q = [char]34
  $r = 5
  foreach ($f in $filas) {
    $cfg.Cells.Item($r, 2).Formula = "$($f[0])"
    $cfg.Cells.Item($r, 3).Formula = "$($f[2])"
    $cfg.Cells.Item($r, 4).Formula = "$($f[3])"   # Formula: el año queda número
    $cfg.Cells.Item($r, 5).NumberFormat = '@'
    $cfg.Cells.Item($r, 5).Formula = "$($f[4])"
    $cfg.Cells.Item($r, 6).Formula = "$($f[5])"
    $cfg.Cells.Item($r, 7).Formula = "$($f[6])"
    $rot = '=IF(C{0}="","",IF(C{0}="BUDGET","Budget",IF(C{0}="FORECAST","Forecast","Actual"))&" "&D{0}&IF(E{0}="",""," "&E{0})&IF(OR(F{0}="",F{0}>=12),""," a "&CHOOSE(F{0},"ene","feb","mar","abr","may","jun","jul","ago","set","oct","nov"))&IF(G{0}="MES"," (mes)",""))' -f $r
    $cfg.Cells.Item($r, 8).Formula = $rot
    $p = $f[1]
    $col = @{ tipo = 'C'; anio = 'D'; ver = 'E'; hasta = 'F'; modo = 'G'; lbl = 'H' }
    foreach ($k in $campos) {
      $wb.Names.Add("$($p)_$k", ("='Config Checkbook'!`${0}`${1}" -f $col[$k], $r)) | Out-Null
    }
    $r++
  }
  $v = $cfg.Range('C5:C10').Validation; $v.Delete(); $v.Add(3, 1, 1, 'BUDGET,FORECAST,ACTUAL') | Out-Null
  $v = $cfg.Range('G8:G10').Validation; $v.Delete(); $v.Add(3, 1, 1, 'ACUMULADO,MES') | Out-Null
  $notas = @(
    'Versión vacía = la vigente (el ★ de Escenarios). El Pre-Cierre se pide por su nombre y siempre trae solo el mes.',
    'Hoy: Meses = Budget 2027 Working · Fila 1 = Actual 2025 · Fila 2 = Forecast 2026 · V = Actual 2026 YTD · W = Forecast 2026 año.',
    'En 2027: Meses = Forecast 2027 · Fila 1 = Actual 2026 · Fila 2 = Budget 2027 Working · V = Budget 2027 hasta el mes cerrado · W = Budget 2027 año.',
    'Meses reales salen del mayor (detalle de Integrity desde ago-2026; lo que no trae detalle va al 800). Meses proyectados salen del checkbook de FinPlan.',
    'Las líneas y detalles de la pestaña son los que tenía al armarla: si en FinPlan se agrega una cuenta nueva, hay que agregarle su bloque.'
  )
  $r = 13; foreach ($t in $notas) { $cfg.Cells.Item($r, 2).Value2 = $t; $r++ }
  $cfg.Range('B13:B17').Font.Italic = $true
  $cfg.Columns.Item(2).ColumnWidth = 38
  foreach ($c in 3..7) { $cfg.Columns.Item($c).ColumnWidth = 13 }
  $cfg.Columns.Item(8).ColumnWidth = 34
  $cfg.Range('C5:G10').Interior.Color = 0xE1F5FF

  # 2) Datos + consulta
  # ⚠️ El Master File YA tiene una consulta «CheckbookOpex» (la de Checkbook Gastos)
  # y Power Query no distingue mayúsculas: llamar a esta «CheckbookOPEX» (y borrar con
  # -eq, que en PowerShell tampoco distingue) le borró la suya al owner el 2026-11-24 y
  # su tabla quedó en «The query 'CheckbookOpex' was not found». Nombre propio y -ceq.
  foreach ($s in @($wb.Worksheets)) { if ($s.Name -ceq 'Datos') { $s.Delete() } }
  foreach ($qq in @($wb.Queries)) { if ($qq.Name -ceq 'CheckbookConsolidado') { $qq.Delete() } }
  $wb.Queries.Add('CheckbookConsolidado', $m, 'Checkbook de OPEX y costo por depto, cuenta y detalle (para Checkbook Consolidado)') | Out-Null
  $ws = $wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count))
  $ws.Name = 'Datos'
  $conn = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=CheckbookConsolidado;Extended Properties=$q$q"
  $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range('A1'))
  $lo.Name = 'tDatos'
  $qt = $lo.QueryTable
  $qt.CommandType = 2
  $qt.CommandText = 'SELECT * FROM [CheckbookConsolidado]'
  $qt.BackgroundQuery = $false
  $qt.RefreshStyle = 0            # xlOverwriteCells: no corre las referencias
  $qt.PreserveColumnInfo = $true
  if ($Refrescar) { $qt.Refresh($false) | Out-Null }
  $ws.Visible = 0                 # oculta (xlSheetHidden)

  # 3) El vínculo externo pasa a ser este mismo libro
  $links = $wb.LinkSources(1)
  # Un arreglo COM empieza en 1: `if ($links)` revienta; se pregunta por $null.
  if ($null -ne $links) { foreach ($l in $links) { Write-Host "vinculo: $l"; $wb.ChangeLink($l, $wb.FullName, 1) } }
  $quedan = $wb.LinkSources(1)
  $n = 0; if ($null -ne $quedan) { foreach ($x in $quedan) { $n++ } }
  Write-Host "vinculos que quedan: $n"

  $xl.Calculation = -4105
  $xl.CalculateFull()
  $wb.Worksheets.Item('Config Checkbook').Activate()
  $wb.Save()
  Write-Host "listo: $Salida"
} finally {
  if ($wb) { $wb.Close($false) }
  $xl.Quit()
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
