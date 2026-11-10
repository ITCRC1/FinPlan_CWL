let
    // Celdas con nombre de la hoja Config.
    P = (n as text) => Excel.CurrentWorkbook(){[Name = n]}[Content]{0}[Column1],
    Url = Text.Trim(Text.From(P("pURL"))),
    LlaveCruda = P("pLlave"),
    Llave = if LlaveCruda = null then "" else Text.Trim(Text.From(LlaveCruda)),
    Catalogo = let v = P("pCatalogo") in if v = null then "false" else Text.Lower(Text.Trim(Text.From(v))),

    // La LISTA de versiones vive en una tabla del libro, no en el codigo: agregar
    // un Draft es escribir un renglon, no editar la consulta.
    Versiones = Excel.CurrentWorkbook(){[Name = "tVersiones"]}[Content],

    Meses = {"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12"},
    // Las mismas columnas del export de Admin · Account Mapping y en SU orden
    // (owner, 2026-11-10: «quiero todas las columnas que tiene el ultimo que
    // subi»), con la version adelante -- sin eso no se sabe de que escenario es
    // la fila -- y los extras del reporte al final.
    Cols = {"Etiqueta","Version",
            "Status","Section","P&L line","Report line",
            "Dept code","GL department","Account","Account name","Nature",
            "Category","Mapeo","Por linea","Sin movimiento"}
           & Meses & {"Annual","Leido"},
    Num = (v) => if v = null then 0 else v,

    // Un error NO tumba el libro entero: esa version baja con una fila que lo dice
    // y las demas siguen. Un refresh que falla del todo se lee como "no hay datos".
    Fallo = (etiqueta as text, msg as text) =>
        #table(Cols, {{etiqueta, "ERROR", msg} & List.Repeat({null}, List.Count(Cols) - 3)}),

    Traer = (etiqueta as text, anio as text, tipo as text, version as text) =>
        let
            Filtro = [year = anio, tipo = tipo, catalogo = Catalogo]
                     & (if version = "" then [] else [version = version]),
            Resp = Web.Contents(Url, [
                RelativePath = "api/consolidado/gl/",
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
                    Fallo(etiqueta, "No existe " & tipo & " " & anio
                          & (if version = "" then "" else " version '" & version & "'"))
                else if Estado <> 200 then Fallo(etiqueta, "El servidor respondio HTTP " & Text.From(Estado))
                else
                    let
                        j = Json.Document(Resp),
                        ver = j[escenario][version],
                        leido = DateTime.ToText(DateTime.LocalNow(), "dd/MM/yyyy HH:mm"),
                        filas = List.Transform(j[cuentas], each
                            {etiqueta, ver,
                             [estado], [seccion], [linea], [renglon],
                             [dept], [dept_name], [cuenta], [nombre], [naturaleza],
                             [categoria], [mapeo], [por_linea], [sin_movimiento]}
                            & List.Transform([meses], Num) & {Num([anual]), leido})
                    in
                        if List.Count(filas) = 0
                        then Fallo(etiqueta, "El escenario no devolvio ninguna cuenta")
                        else #table(Cols, filas)
        in
            Salida,

    ConDatos = Table.AddColumn(Versiones, "Datos", each
        Traer(Text.From([Etiqueta]), Text.From([Anio]), Text.Upper(Text.From([Tipo])),
              let v = [Version] in if v = null then "" else Text.Trim(Text.From(v)))),
    Solo = Table.SelectColumns(ConDatos, {"Datos"}),
    Unido = Table.ExpandTableColumn(Solo, "Datos", Cols),
    Tipado = Table.TransformColumnTypes(Unido,
        List.Transform(Meses & {"Annual"}, each {_, type number}))
in
    Tipado
