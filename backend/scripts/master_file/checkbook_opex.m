let
    // Celdas con nombre de la hoja Config.
    P = (n as text) => Excel.CurrentWorkbook(){[Name = n]}[Content]{0}[Column1],
    Txt = (v) => if v = null then "" else Text.Trim(Text.From(v)),
    Url = Txt(P("pURL")),
    Llave = Txt(P("pLlave")),

    // Los cinco lugares del libro: tipo · año · versión (· hasta mes en V y W).
    // Una versión vacía no se manda: el servidor usa la vigente.
    Lugar = (cod as text, prefijo as text, conHasta as logical) =>
        let
            tipo = Txt(P("p" & cod & "_tipo")),
            anio = Txt(P("p" & cod & "_anio")),
            ver = Txt(P("p" & cod & "_ver")),
            hasta = if conHasta then Txt(P("p" & cod & "_hasta")) else "",
            modo = if conHasta then Txt(P("p" & cod & "_modo")) else "",
            r = (if tipo = "" then [] else Record.FromList({tipo}, {prefijo & "_tipo"}))
                & (if anio = "" then [] else Record.FromList({anio}, {prefijo & "_anio"}))
                & (if ver = "" then [] else Record.FromList({ver}, {prefijo & "_ver"}))
                & (if hasta = "" then [] else Record.FromList({hasta}, {prefijo & "_hasta"}))
                & (if modo = "" then [] else Record.FromList({modo}, {prefijo & "_modo"}))
        in
            r,
    Filtro = Lugar("M", "m", false) & Lugar("F1", "f1", false) & Lugar("F2", "f2", false)
             & Lugar("V", "v", true) & Lugar("W", "w", true) & Lugar("X", "x", true),

    Cols = {"Clave", "Serie", "Dept", "Cuenta", "Detalle", "Desc",
            "M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12", "Anual"},
    Fallo = (msg as text) => #table(Cols, {{"ERROR", "ERROR", null, null, null, msg}
                                           & List.Repeat({null}, 13)}),

    Traer = () =>
        let
            Resp = Web.Contents(Url, [
                RelativePath = "api/consolidado/checkbook-opex/",
                Query = Filtro,
                Headers = [#"x-api-key" = Llave, Accept = "application/json"],
                // 401/403 no se pueden atrapar: Power Query los muestra como error de credenciales.
                ManualStatusHandling = {400, 404, 422, 500, 502, 503},
                // Arma hasta cinco escenarios: puede pasar de los 100 s por defecto.
                Timeout = #duration(0, 0, 10, 0)
            ]),
            Estado = Value.Metadata(Resp)[Response.Status],
            Salida =
                if Llave = "" then Fallo("Falta la llave de solo lectura en Config")
                else if Estado = 404 then Fallo("No existe la version pedida en Meses (revisar Config y la hoja Escenarios)")
                else if Estado = 422 then Fallo("Tipo invalido en Config: BUDGET, FORECAST o ACTUAL")
                else if Estado <> 200 then Fallo("El servidor respondio HTTP " & Text.From(Estado))
                else
                    let
                        j = Json.Document(Resp),
                        filas = List.Transform(j[filas], each
                            {[clave], [serie], [dept], [cuenta], [detalle], [desc]} & [meses] & {[anual]})
                    in
                        #table(Cols, filas)
        in
            Salida,

    Resultado = try Table.Buffer(Traer()) otherwise Fallo("No se pudo leer FinPlan (revisar URL y conexion)"),
    Tipado = Table.TransformColumnTypes(Resultado,
        {{"Clave", type text}, {"Serie", type text}, {"Dept", type text}, {"Cuenta", type text},
         {"Detalle", type text}, {"Desc", type text}}
        & List.Transform({"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12","Anual"},
                         each {_, type number}))
in
    Tipado
