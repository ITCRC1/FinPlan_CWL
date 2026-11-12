let
    // Checkbook de ingresos del Cierre Mensual (owner, 2026-11-11): «máximo
    // detalle ... ingresos y costos». Sale de la MISMA consulta GL (no de otra
    // lectura): departamento × cuenta de ingreso × mes, en POSITIVO.
    //
    // ⚠️ No usa /consolidado/revenue-checkbook/: ese lee revenue_entries, que
    // solo tiene el Budget (los ACTUAL y el Forecast no traen checkbook de
    // ingresos, su ingreso vive en el mayor). Saliendo del GL las seis
    // versiones cuadran con el P&L por construcción.
    Fuente = GL,
    Meses = {"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12"},
    SoloIngreso = Table.SelectRows(Fuente, each [Category] = "REVENUE" or [Version] = "ERROR"),
    Columnas = Table.SelectColumns(SoloIngreso,
        {"Etiqueta","Version","Dept code","GL department","Account","Account name",
         "P&L line","Report line","Status"} & Meses & {"Annual"}),
    // El GL trae el ingreso NEGATIVO (es crédito); el checkbook lo muestra en positivo.
    Positivo = Table.TransformColumns(Columnas,
        List.Transform(Meses & {"Annual"}, each {_, (v) => if v = null then 0 else -v, type number})),
    // Solo las cuentas con alguna cifra en el año: el universo completo está en la hoja GL.
    ConCifra = Table.SelectRows(Positivo, each [Version] = "ERROR" or
        List.AnyTrue(List.Transform(Meses, (m) => Number.Abs(Record.Field(_, m)) > 0.004)))
in
    ConCifra
