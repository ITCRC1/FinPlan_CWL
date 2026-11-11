# Columnas «Mes» y «Acumulado» del mes elegido en Config!C7 (pMes), al final de una tabla.
#
# Owner, 2026-11-11: «que sea mensual, que yo pueda escoger el mes que quiero
# revisar y extraer». Son columnas CALCULADAS de la tabla, no de la consulta:
# cambiar el mes recalcula al instante, sin volver a bajar nada de FinPlan, y
# Excel las conserva y las rellena en cada «Actualizar todo».
function Add-ColumnasMes($lo, [string]$prefijo, [string]$nomMes, [string]$nomAcum) {
  $t = $lo.Name
  $nombres = @($lo.ListColumns | ForEach-Object { $_.Name })
  if (-not ($nombres -contains "$($prefijo)01") -or -not ($nombres -contains "$($prefijo)12")) {
    # La consulta bajó con error (la fila ERROR de una versión no rompe esto, pero
    # una consulta que no corrió deja otras columnas): se avisa y no se inventa nada.
    Write-Warning "$t no tiene columnas $($prefijo)01..$($prefijo)12 (tiene: $($nombres -join ', '))"
    return
  }
  $rango = "$t[@[$($prefijo)01]:[$($prefijo)12]]"
  foreach ($par in @(@($nomMes, "=INDEX($rango,1,pMes)"),
                     @($nomAcum, "=SUM(INDEX($rango,1,1):INDEX($rango,1,pMes))"))) {
    if (-not $par[0]) { continue }
    $existe = $false
    foreach ($c in $lo.ListColumns) { if ($c.Name -eq $par[0]) { $existe = $true } }
    if ($existe) { continue }
    $col = $lo.ListColumns.Add()
    $col.Name = $par[0]
    if ($col.DataBodyRange -ne $null) {
      $col.DataBodyRange.Formula = $par[1]
      $col.DataBodyRange.Interior.Color = 0xCCFFFF
    }
    $col.Range.Cells.Item(1, 1).Interior.Color = 0x7F3F1F
    $col.Range.Cells.Item(1, 1).Font.Color = 0xFFFFFF
  }
}

# «Mes anterior» (pMes − 1; en enero da 0). Para la columna «Pre-Cierre del mes
# anterior» de la hoja P&L Mes (owner, 2026-11-11: «side to side mismo mes ...
# precierre mes anterior, precierre mes de análisis»).
function Add-ColumnaMesAnterior($lo, [string]$prefijo, [string]$nombre) {
  $t = $lo.Name
  foreach ($c in $lo.ListColumns) { if ($c.Name -eq $nombre) { return } }
  $rango = "$t[@[$($prefijo)01]:[$($prefijo)12]]"
  $col = $lo.ListColumns.Add()
  $col.Name = $nombre
  if ($col.DataBodyRange -ne $null) {
    $col.DataBodyRange.Formula = "=IF(pMes=1,0,INDEX($rango,1,pMes-1))"
    $col.DataBodyRange.Interior.Color = 0xCCFFFF
    $col.DataBodyRange.NumberFormat = '#,##0.00;[Red](#,##0.00);"-"'
  }
  $col.Range.Cells.Item(1, 1).Interior.Color = 0x7F3F1F
  $col.Range.Cells.Item(1, 1).Font.Color = 0xFFFFFF
}
