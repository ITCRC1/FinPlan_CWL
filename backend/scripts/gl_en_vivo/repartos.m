let
    // Celdas con nombre de la hoja Config.
    P = (n as text) => Excel.CurrentWorkbook(){[Name = n]}[Content]{0}[Column1],
    // Celda vacía -> "" (nunca null): una fila a medio llenar no tumba la consulta.
    T = (v) => if v = null then "" else Text.Trim(Text.From(v)),
    Url = T(P("pURL")),
    LlaveCruda = P("pLlave"),
    Llave = T(LlaveCruda),

    // La LISTA de versiones vive en una tabla del libro, no en el codigo: agregar
    // un Draft es escribir un renglon, no editar la consulta.
    TodasLasFilas = Excel.CurrentWorkbook(){[Name = "tVersiones"]}[Content],
    // Solo las prendidas. Apagar una fila es escribir NO, no borrarla.
    Versiones = Table.SelectRows(TodasLasFilas, each
        Text.Upper(T(Record.FieldOrDefault(_, "Usar", "SI"))) <> "NO"
        and T(Record.FieldOrDefault(_, "Anio", null)) <> ""
        and T(Record.FieldOrDefault(_, "Tipo", null)) <> ""),

    Meses = {"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12"},
    // Columnas de la pestana, con la version adelante: sin eso no se sabe
    // de que escenario es la fila.
    Cols = {"Etiqueta","Version","Tipo","Centro","Nombre centro","Destino","Nombre destino","Depto GL","Cuenta","Rol"} & Meses & {"Annual","Leido"},
    Num = (v) => if v = null then 0 else v,

    // Un error NO tumba el libro entero: esa version baja con una fila que lo dice
    // y las demas siguen. Un refresh que falla del todo se lee como "no hay datos".
    // ERROR = algo fallo (llave, servidor). «SIN DATOS» = la version no tiene
    // repartos guardados, que es lo normal en el Actual y el Forecast: no es un error.
    Fallo = (etiqueta as text, msg as text) =>
        #table(Cols, {{etiqueta, "ERROR", msg} & List.Repeat({null}, List.Count(Cols) - 3)}),

    Traer = (etiqueta as text, anio as text, tipoArg as text, versionArg as text) =>
        let
            // ⚠️ Los parametros NO pueden llamarse igual que los campos del
            // registro. Con `[tipo = tipo]` Power Query no distingue el campo
            // del parametro y falla con «We found one or more unbound names
            // when recompiling a function internally ... tipo, version».
            Filtro = [year = anio, tipo = tipoArg]
                     & (if versionArg = "" then [] else [version = versionArg]),
            Resp = Web.Contents(Url, [
                RelativePath = "api/consolidado/repartos/",
                Query = Filtro,
                Headers = [#"x-api-key" = Llave, Accept = "application/json"],
                // 401/403 no se pueden atrapar: Power Query los trata como error
                // de credenciales y los muestra como tal.
                ManualStatusHandling = {400, 404, 422, 500, 502, 503}
            ]),
            Estado = Value.Metadata(Resp)[Response.Status],
            Salida =
                if Llave = "" then Fallo(etiqueta, "Falta la llave de solo lectura en Config")
                else if Estado = 404 then
                    Fallo(etiqueta, "No existe " & tipoArg & " " & anio
                          & (if versionArg = "" then "" else " version '" & versionArg & "'"))
                else if Estado <> 200 then Fallo(etiqueta, "El servidor respondio HTTP " & Text.From(Estado))
                else
                    let
                        j = Json.Document(Resp),
                        ver = j[escenario][version],
                        leido = DateTime.ToText(DateTime.LocalNow(), "dd/MM/yyyy HH:mm"),
                        filas = List.Transform(j[lineas], each
                            {etiqueta, ver, [tipo], [origen], [origen_nombre], [destino], [destino_nombre], [destino_gl], [cuenta], [rol]}
                            & List.Transform([meses], Num) & {Num([anual]), leido})
                    in
                        if List.Count(filas) = 0
                        then #table(Cols, {{etiqueta, "SIN DATOS", "Sin repartos guardados: el Actual y el Forecast traen el reparto hecho en el mayor; el detalle por destino solo existe en los Budget y el Pre-Cierre"} & List.Repeat({null}, List.Count(Cols) - 3)})
                        else #table(Cols, filas)
        in
            Salida,

    // ── Las versiones las dice FinPlan, no el libro ─────────────────────
    //
    // Owner, 2026-11-10: *«puede el archivo de excel actualizar las versiones
    // directamente desde finplan una vez que se conecta»*.
    //
    // Si en la columna Version se escribe `*`, esa fila se abre en TODAS las
    // versiones que el sistema tenga de ese anio y ese tipo. Un Draft4 que se
    // cree manana aparece solo en el proximo refresh, sin tocar el libro -- y
    // un nombre mal escrito deja de ser posible.
    //
    // ⚠️ Se deja ELEGIR en vez de traer todo siempre a proposito: cada version
    // es un P&L completo de doce meses del lado del servidor. Pedir de una el
    // universo entero de escenarios -- budgets 2028 a 2035 incluidos -- hace
    // del refresh una espera larga para datos que nadie estaba mirando.
    ListaEscenarios =
        let
            R = Web.Contents(Url, [
                RelativePath = "api/consolidado/escenarios/",
                Headers = [#"x-api-key" = Llave, Accept = "application/json"],
                ManualStatusHandling = {400, 404, 422, 500, 502, 503}
            ])
        in
            if Llave = "" or Value.Metadata(R)[Response.Status] <> 200
            then {}
            else Json.Document(R)[escenarios],

    // Una fila de Config -> una o varias filas {Etiqueta, Anio, Tipo, Version}.
    Abrir = (fila as record) as list =>
        let
            anio = T(fila[Anio]),
            tipo = Text.Upper(T(fila[Tipo])),
            etq = let e = T(fila[Etiqueta]) in if e = "" then T(fila[Tipo]) & " " & T(fila[Anio]) else e,
            crudo = T(fila[Version])
        in
            if crudo <> "*" then {[E = etq, A = anio, T = tipo, V = crudo]}
            else
                let
                    hay = List.Select(ListaEscenarios, each
                        Text.From([year]) = anio and Text.Upper(Text.From([tipo])) = tipo),
                    nombres = List.Distinct(List.Transform(hay, each
                        let v = [version] in if v = null then "" else Text.From(v)))
                in
                    if List.Count(nombres) = 0
                    then {[E = etq, A = anio, T = tipo, V = ""]}
                    else List.Transform(nombres, (v) =>
                        [E = etq & " · " & (if v = "" then "(sin version)" else v),
                         A = anio, T = tipo, V = v]),

    Expandidas = Table.FromRecords(List.Combine(
        Table.TransformRows(Versiones, each Abrir(_)))),

    ConDatos = Table.AddColumn(Expandidas, "Datos", each Traer([E], [A], [T], [V])),
    Solo = Table.SelectColumns(ConDatos, {"Datos"}),
    Unido = Table.ExpandTableColumn(Solo, "Datos", Cols),
    Tipado = Table.TransformColumnTypes(Unido,
        List.Transform(Meses & {"Annual"}, each {_, type number}))
in
    Tipado
