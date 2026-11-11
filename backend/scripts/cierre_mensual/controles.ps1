param([string]$Libro, [switch]$Verificar)
# Hoja «Controles» del Cierre Mensual: lo que tiene que dar 0, por versión, en el mes
# de Config!C7 y en el acumulado. Todo son fórmulas sobre las tablas del libro.
$ErrorActionPreference = 'Stop'
# (título, plantilla). En la plantilla: $V = celda con la etiqueta de la versión,
# #F# = Mes | Acumulado, #P# = la columna de costo de Posiciones (Costo mes | Costo acum).
# ⚠️ Plantillas LITERALES a propósito: en PowerShell la coma pesa más que el `+`,
# y `@("a", 'x' + $y)` arma un arreglo de tres elementos sin avisar.
$checks = @(
  @("Motor − GL (utilidad neta)",
    '=ROUND(SUMIFS(tMotor[#F#],tMotor[Etiqueta],$V,tMotor[Linea],"NET_PROFIT")+SUMIFS(tGL[#F#],tGL[Etiqueta],$V)-SUMIFS(tGL[#F#],tGL[Etiqueta],$V,tGL[Status],"SIN MAPEO"),2)'),
  @("SIN MAPEO en el GL (el P&L no lo ve)",
    '=ROUND(SUMIFS(tGL[#F#],tGL[Etiqueta],$V,tGL[Status],"SIN MAPEO"),2)'),
  @("Σ Posiciones − Σ Planilla",
    '=ROUND(SUMIFS(tPosiciones[#P#],tPosiciones[Etiqueta],$V)-SUMIFS(tPlanilla[#F#],tPlanilla[Etiqueta],$V),2)'),
  @("Σ Planilla − PAYROLL del GL",
    '=ROUND(SUMIFS(tPlanilla[#F#],tPlanilla[Etiqueta],$V)-SUMIFS(tGL[#F#],tGL[Etiqueta],$V,tGL[Category],"PAYROLL"),2)'),
  @("Checkbook OPEX − OPEX del GL",
    '=ROUND(SUMIFS(tOpex[#F#],tOpex[Etiqueta],$V)-SUMIFS(tGL[#F#],tGL[Etiqueta],$V,tGL[Category],"OPERATING_EXPENSES"),2)'),
  @("Reparto del GL (ALLOCATIONS)",
    '=ROUND(SUMIFS(tGL[#F#],tGL[Etiqueta],$V,tGL[Category],"ALLOCATIONS"),2)'),
  @("Checkbook Costos − costo de ventas del GL",
    '=ROUND(SUMIFS(tCostos[#F#],tCostos[Etiqueta],$V)-SUMIFS(tGL[#F#],tGL[Etiqueta],$V,tGL[Category],"COST_OF_SALES"),2)'),
  @("Checkbook Ingresos − ingreso del GL",
    '=ROUND(SUMIFS(tIngresos[#F#],tIngresos[Etiqueta],$V)+SUMIFS(tGL[#F#],tGL[Etiqueta],$V,tGL[Category],"REVENUE"),2)')
)
function Plantilla([string]$t, [string]$celda, [bool]$acum) {
  $f = if ($acum) { 'Acumulado' } else { 'Mes' }
  $p = if ($acum) { 'Costo acum' } else { 'Costo mes' }
  $t.Replace('$V', $celda).Replace('#F#', $f).Replace('#P#', $p)
}
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  foreach ($s in @($wb.Worksheets)) { if ($s.Name -eq 'Controles') { $s.Delete() } }
  $ws = $wb.Worksheets.Add($wb.Worksheets.Item(3))
  $ws.Name = 'Controles'
  $ws.Range("A1").Value2 = 'Controles del Cierre Mensual — deben dar 0'
  $ws.Range("A1").Font.Bold = $true; $ws.Range("A1").Font.Size = 14
  $ws.Range("A2").Formula = '="Mes: "&pMesNombre&" ("&pMes&") y acumulado enero → "&pMesNombre&".   Cambialo en Config!C7."'
  $ws.Range("A2").Font.Bold = $true; $ws.Range("A2").Font.Color = 0x1F1F7F
  $ws.Range("A4").Value2 = 'Versión'
  $col = 2
  foreach ($c in $checks) {
    $ws.Cells.Item(4, $col).Value2 = $c[0]
    $ws.Range($ws.Cells.Item(4, $col), $ws.Cells.Item(4, $col + 1)).HorizontalAlignment = 7
    $ws.Cells.Item(5, $col).Value2 = 'Mes'; $ws.Cells.Item(5, $col + 1).Value2 = 'Acumulado'
    for ($k = 1; $k -le 6; $k++) {
      $r = 5 + $k
      $ws.Cells.Item($r, $col).Formula = Plantilla $c[1] "`$A$r" $false
      $ws.Cells.Item($r, $col + 1).Formula = Plantilla $c[1] "`$A$r" $true
    }
    $col += 2
  }
  for ($k = 1; $k -le 6; $k++) { $ws.Cells.Item(5 + $k, 1).Formula = "=INDEX(tVersiones[Etiqueta],$k)" }
  $ult = $col - 1
  $enc = $ws.Range($ws.Cells.Item(4, 1), $ws.Cells.Item(5, $ult))
  $enc.Font.Bold = $true; $enc.Interior.Color = 0x3A2A1F; $enc.Font.Color = 0xFFFFFF; $enc.WrapText = $true
  $ws.Rows.Item(4).RowHeight = 32
  $datos = $ws.Range($ws.Cells.Item(6, 2), $ws.Cells.Item(11, $ult))
  $datos.NumberFormat = '#,##0.00;[Red]-#,##0.00;"0"'
  # Verde si da 0; ámbar si no (las columnas informativas —SIN MAPEO y reparto— no son error).
  $fc = $datos.FormatConditions
  $fc.Delete() | Out-Null
  $f1 = $fc.Add(1, 3, "=0"); $f1.Interior.Color = 0xCEEFC6
  $f2 = $fc.Add(1, 4, "=0"); $f2.Interior.Color = 0x9CEBFF
  $ws.Columns.Item(1).ColumnWidth = 18
  $ws.Range($ws.Cells.Item(1, 2), $ws.Cells.Item(1, $ult)).EntireColumn.ColumnWidth = 13
  $notas = @(
    'Cómo leerlo:',
    '• Motor − GL: la utilidad que calcula FinPlan contra la que suma el mayor (sin las cuentas SIN MAPEO). En el Forecast los meses cerrados vienen del Actual en el motor y del archivo importado en el GL: esa mezcla aparece acá y es conocida.',
    '• SIN MAPEO: plata del mayor sin renglón del P&L (p. ej. 0250-8050 en el Pre-Cierre de septiembre). No es error del libro: hay que mapear la cuenta en Admin · Account Mapping.',
    '• Posiciones = Planilla = PAYROLL del GL: la planilla posición por posición cuadra con el mayor.',
    '• OPEX: si «Checkbook OPEX − OPEX del GL» es igual al reparto con signo contrario, es el reparto de Cafetería (0220) y Lavandería (0161), que vive en el GL y no en el checkbook.',
    '• Costos e Ingresos: el checkbook contra el mayor. Ingresos sale de la misma consulta GL, así que da 0 por construcción.'
  )
  for ($i = 0; $i -lt $notas.Count; $i++) {
    $c = $ws.Cells.Item(13 + $i, 1); $c.Value2 = $notas[$i]; $c.Font.Size = 9; $c.Font.Color = 0x555555
  }
  $ws.Cells.Item(13, 1).Font.Bold = $true
  $ws.Activate(); $xl.ActiveWindow.DisplayGridlines = $false
  $ws.Range("B6").Select() | Out-Null; $xl.ActiveWindow.FreezePanes = $true
  $xl.CalculateFull()
  if ($Verificar) {
    $mesCel = $wb.Worksheets.Item('Config').Range('pMes'); $orig = [int]$mesCel.Value2
    for ($mes = 1; $mes -le 12; $mes++) {
      $mesCel.Value2 = [double]$mes; $xl.Calculate()
      for ($k = 1; $k -le 6; $k++) {
        $vals = @(); for ($j = 2; $j -le $ult; $j++) { $vals += ('{0:N0}' -f [double]$ws.Cells.Item(5 + $k, $j).Value2) }
        "mes {0,2} {1,-16} {2}" -f $mes, $ws.Cells.Item(5 + $k, 1).Text, ($vals -join ' ')
      }
    }
    $mesCel.Value2 = [double]$orig; $xl.Calculate()
  }
  $wb.Save(); $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
