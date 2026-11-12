let
    // Centros de costo: Cafeteria (0220) y Lavanderia interna (0161), como
    // departamentos que ACUMULAN su costo, lo REPARTEN y quedan en 0.
    // Owner, 2026-11-12: «quiero ver cafeteria como un verdadero departamento de
    // costos que acumula y despues reparte y que al final queda en 0» · «igual
    // que lavanderia».
    //
    // Sale de dos consultas del libro, sin otra lectura:
    //   - GL: lo que el centro acumula (costo de ventas, planilla, opex) y su
    //     credito de reparto (categoria ALLOCATIONS, la 4999).
    //   - Repartos: a que departamento fue cada dolar, con su cuenta.
    // Controles: Neto = acumulado + credito (debe dar 0) y cargos + credito = 0.
    Meses = {"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12"},
    Todos = Meses & {"Annual"},
    Num = (v) => if v = null then 0 else v,
    Centros = {[Depto = "0220", Nombre = "Cafeteria (0220)", Tipo = "CAFETERIA"],
               [Depto = "0161", Nombre = "Lavanderia interna (0161)", Tipo = "LAUNDRY"]},
    Gl = Table.SelectRows(GL, each [Version] <> "ERROR"),
    Rep = Table.SelectRows(Repartos, each [Version] <> "ERROR"),
    Etiquetas = List.Distinct(Gl[Etiqueta]),

    // Sin filas, List.Sum da null: se fuerza 0 para que el control nunca quede vacio.
    Sumar = (t as table) as list => List.Transform(Todos, (m) => Num(List.Sum(List.Transform(Table.Column(t, m), Num)))),
    Fila = (etq, centro, bloque, concepto, depto, valores as list) =>
        Record.FromList({etq, centro, bloque, concepto, depto} & valores,
                        {"Etiqueta", "Centro", "Bloque", "Concepto", "Depto"} & Todos),
    Mas = (a as list, b as list) => List.Transform(List.Positions(a), (i) => a{i} + b{i}),

    UnCentro = (etq as text, c as record) as list =>
        let
            delCentro = Table.SelectRows(Gl, each [Etiqueta] = etq and [Dept code] = c[Depto]),
            cat = (k) => Sumar(Table.SelectRows(delCentro, each [Category] = k)),
            costo = cat("COST_OF_SALES"), planilla = cat("PAYROLL"), opex = cat("OPERATING_EXPENSES"),
            acumulado = Mas(Mas(costo, planilla), opex),
            credito = cat("ALLOCATIONS"),
            neto = Mas(acumulado, credito),
            cargosT = Table.SelectRows(Rep, each [Etiqueta] = etq and [Tipo] = c[Tipo] and [Rol] = "cargo"),
            porDepto = Table.Group(cargosT, {"Depto GL"}, List.Transform(Todos, (m) =>
                           {m, (t) => List.Sum(List.Transform(Table.Column(t, m), Num)), type number})),
            cargos = Table.TransformRows(Table.Sort(porDepto, {{"Annual", Order.Descending}}), (r) =>
                         Fila(etq, c[Nombre], "3 · A donde fue", "Cargo a departamento", r[Depto GL],
                              List.Transform(Todos, (m) => Num(Record.Field(r, m))))),
            totalCargos = Sumar(cargosT),
            control = Mas(totalCargos, credito)
        in
            {Fila(etq, c[Nombre], "1 · Acumula", "Costo de ventas", c[Depto], costo),
             Fila(etq, c[Nombre], "1 · Acumula", "Planilla", c[Depto], planilla),
             Fila(etq, c[Nombre], "1 · Acumula", "OPEX", c[Depto], opex),
             Fila(etq, c[Nombre], "1 · Acumula", "Total acumulado", c[Depto], acumulado),
             Fila(etq, c[Nombre], "2 · Reparte", "Reparto (credito 4999)", c[Depto], credito),
             Fila(etq, c[Nombre], "2 · Reparte", "NETO DEL CENTRO (debe dar 0)", c[Depto], neto)}
            & cargos
            // El Actual y el Forecast no guardan el reparto: viene hecho en el mayor.
            // Sin cargos guardados el control no prueba nada -- se dice, no se
            // muestra el credito entero como si fuera un descuadre.
            & (if Table.RowCount(cargosT) = 0
               then {Fila(etq, c[Nombre], "3 · A donde fue", "Sin detalle por departamento: el reparto viene hecho en el mayor", "", List.Repeat({0}, List.Count(Todos)))}
               else {Fila(etq, c[Nombre], "3 · A donde fue", "Total cargado a departamentos", "", totalCargos),
                     Fila(etq, c[Nombre], "4 · Control", "Cargos + credito (debe dar 0)", "", control)}),

    Filas = List.Combine(List.Transform(Etiquetas, (e) => List.Combine(List.Transform(Centros, (c) => UnCentro(e, c))))),
    Tabla = Table.FromRecords(Filas),
    Tipado = Table.TransformColumnTypes(Tabla, List.Transform(Todos, each {_, type number}))
in
    Tipado
