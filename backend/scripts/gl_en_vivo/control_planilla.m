let
    // Control de planilla: el checkbook contra el GL (owner, 2026-11-12: «los
    // checkbooks de planilla con el gl para poder auditar los datos calculados»).
    //
    // Una fila por version x depto (como lo muestra el GL) x cuenta 6xxx: lo que
    // suma el checkbook posicion por posicion -- salario x FTE / TC, CCSS y
    // aguinaldo calculados -- y lo que llega al mayor del P&L. La diferencia de
    // cada mes es lo que hay que explicar; cero es que lo calculado llego entero.
    //
    // «Origen» dice de donde salio el lado del checkbook: «checkbook» (posiciones
    // digitadas) o «del mayor» (versiones sin checkbook, que por construccion
    // dan diferencia cero: no hay calculo que auditar).
    Meses = {"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12"},
    Todos = Meses & {"Annual"},
    Num = (v) => if v = null then 0 else v,
    Sumas = (prefijo as text) => List.Transform(Todos, (m) =>
        {prefijo & m, (t) => List.Sum(List.Transform(Table.Column(t, m), Num)), type number}),

    Cb0 = Table.SelectRows(CheckbookPlanilla, each [Version] <> "ERROR"),
    Cb = Table.Group(Cb0, {"Etiqueta", "Dept GL", "Cuenta"},
        Sumas("CB ") & {{"Origen", (t) => if List.Contains(Table.Column(t, "Puesto"), "(del mayor)")
                                         then "del mayor" else "checkbook", type text},
                       {"Concepto", (t) => List.First(Table.Column(t, "Concepto")), type text}}),

    Gl0 = Table.SelectRows(GL, each [Category] = "PAYROLL" and [Version] <> "ERROR"),
    Gl1 = Table.RenameColumns(Gl0, {{"Etiqueta", "GL Etiqueta"}, {"Dept code", "GL Dept"},
                                    {"Account", "GL Cuenta"}}),
    Gl = Table.Group(Gl1, {"GL Etiqueta", "GL Dept", "GL Cuenta"},
        Sumas("GL ") & {{"Nombre GL", (t) => List.First(Table.Column(t, "Account name")), type text},
                       {"Departamento", (t) => List.First(Table.Column(t, "GL department")), type text}}),

    Unido = Table.Join(Cb, {"Etiqueta", "Dept GL", "Cuenta"}, Gl, {"GL Etiqueta", "GL Dept", "GL Cuenta"},
                       JoinKind.FullOuter),
    Uno = (a, b) => if a = null then b else a,
    Filas = Table.TransformRows(Unido, (r) =>
        let
            cb = (m) => Num(Record.Field(r, "CB " & m)),
            gl = (m) => Num(Record.Field(r, "GL " & m)),
            soloCb = r[GL Etiqueta] = null,
            soloGl = r[Etiqueta] = null
        in
            [Etiqueta = Uno(r[Etiqueta], r[GL Etiqueta]),
             #"Dept GL" = Uno(r[Dept GL], r[GL Dept]),
             Departamento = r[Departamento],
             Cuenta = Uno(r[Cuenta], r[GL Cuenta]),
             Nombre = Uno(r[Nombre GL], r[Concepto]),
             Origen = if soloGl then "solo en el GL" else if soloCb then "solo en el checkbook" else r[Origen],
             #"Checkbook anual" = cb("Annual"),
             #"GL anual" = gl("Annual"),
             #"Diferencia anual" = cb("Annual") - gl("Annual")]
            & Record.FromList(List.Transform(Meses, (m) => cb(m) - gl(m)),
                              List.Transform(Meses, (m) => "Dif " & m))),
    Tabla = Table.FromRecords(Filas),
    // Sin las cuentas que en los dos lados dan cero todo el ano (el GL baja el
    // universo del mapeo con ceros).
    ConCifra = Table.SelectRows(Tabla, each Number.Abs([Checkbook anual]) > 0.004
                                         or Number.Abs([GL anual]) > 0.004),
    Orden = Table.Sort(ConCifra, {{"Etiqueta", Order.Ascending}, {"Dept GL", Order.Ascending},
                                  {"Cuenta", Order.Ascending}}),
    Tipado = Table.TransformColumnTypes(Orden,
        List.Transform({"Checkbook anual", "GL anual", "Diferencia anual"}
                       & List.Transform(Meses, (m) => "Dif " & m), each {_, type number}))
in
    Tipado
