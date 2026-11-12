let
    // Checkbook del propietario (owner, 2026-11-12: «meter los checkbooks de ...
    // management fees y gastos dueños»): todo lo que va DEBAJO del GOP --
    // management fees (3% y royalties), renta, seguros, otros, reserva de capital,
    // capex, intereses, depreciación e impuestos -- por línea del P&L, cuenta y mes.
    //
    // Sale de la MISMA consulta GL, como el checkbook de ingresos: en el Budget el
    // management fee se calcula (ingreso × %) y no vive en ninguna tabla de
    // checkbook; en el GL viene con la cifra del P&L en su cuenta de asiento, así
    // que las seis versiones cuadran con el P&L por construcción.
    Fuente = GL,
    Meses = {"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12"},
    Debajo = Table.SelectRows(Fuente, each [Category] = "BELOW_GOP" or [Version] = "ERROR"),
    Columnas = Table.SelectColumns(Debajo,
        {"Etiqueta","Version","Section","P&L line","Report line","Dept code","GL department",
         "Account","Account name","Status"} & Meses & {"Annual"}),
    // Gasto en positivo, como el resto de los checkbooks (el GL ya lo trae así).
    Ceros = Table.TransformColumns(Columnas,
        List.Transform(Meses & {"Annual"}, each {_, (v) => if v = null then 0 else v, type number})),
    // Solo lo que tiene alguna cifra en el año; el universo completo está en la hoja GL.
    ConCifra = Table.SelectRows(Ceros, each [Version] = "ERROR" or
        List.AnyTrue(List.Transform(Meses, (m) => Number.Abs(Record.Field(_, m)) > 0.004))),
    Orden = Table.Sort(ConCifra, {{"Etiqueta", Order.Ascending}, {"Section", Order.Ascending},
                                  {"P&L line", Order.Ascending}, {"Account", Order.Ascending}})
in
    Orden
