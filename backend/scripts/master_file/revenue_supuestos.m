let
    // Celdas con nombre: pURL y pLlave de Config, y el escenario de RV3 Inputs.
    P = (n as text) => Excel.CurrentWorkbook(){[Name = n]}[Content]{0}[Column1],
    // Celda vacia -> "" (nunca null).
    T = (v) => if v = null then "" else Text.Trim(Text.From(v)),
    Url = T(P("pURL")),
    Llave = T(P("pLlave")),
    Anio = T(P("pRV_anio")),
    Tipo = Text.Upper(T(P("pRV_tipo"))),
    Version = T(P("pRV_ver")),

    Cols = {"Clave", "Valor", "Texto"},
    // Un error NO deja el libro en blanco sin explicacion: baja una fila que lo
    // dice y RV3 Inputs la muestra en rojo («Message from the refresh»).
    Fallo = (msg as text) => #table(Cols, {{"INFO|error|0", null, msg}}),

    Traer = () =>
        let
            Filtro = [year = Anio, tipo = Tipo] & (if Version = "" then [] else [version = Version]),
            Resp = Web.Contents(Url, [
                RelativePath = "api/consolidado/revenue-supuestos/",
                Query = Filtro,
                Headers = [#"x-api-key" = Llave, Accept = "application/json"],
                // 401/403 no se pueden atrapar: Power Query los trata como error de credenciales.
                ManualStatusHandling = {400, 404, 422, 500, 502, 503, 504},
                // «Actualizar todo» manda ~70 pedidos juntos y el servidor los atiende de a
                // uno: con los 100 s por defecto una consulta puede caer (owner, 2026-11-12).
                Timeout = #duration(0, 0, 10, 0)
            ]),
            Estado = Value.Metadata(Resp)[Response.Status],
            Salida =
                if Llave = "" then Fallo("Missing the read-only key in Config!C5")
                else if Anio = "" or Tipo = "" then Fallo("Choose Year and Type in RV3 Inputs")
                else if Estado = 404 then
                    Fallo("FinPlan has no " & Tipo & " " & Anio
                          & (if Version = "" then "" else " version '" & Version & "'")
                          & " — see the sheet Escenarios for the exact names")
                else if Estado <> 200 then Fallo("FinPlan answered HTTP " & Text.From(Estado))
                else
                    let
                        j = Json.Document(Resp),
                        filas = List.Transform(j[filas], each {[clave], [valor], [texto]})
                    in
                        if List.Count(filas) = 0 then Fallo("The scenario came back empty")
                        else #table(Cols, filas)
        in
            Salida,

    // Table.Buffer obliga a leer la respuesta ADENTRO del try: sin el, el error
    // escapa al expandir y la consulta entera cae.
    Datos = try Table.Buffer(Traer()) otherwise Fallo("FinPlan did not answer in time: Data > Refresh this query again"),
    Tipado = Table.TransformColumnTypes(Datos, {{"Clave", type text}, {"Valor", type number}, {"Texto", type text}})
in
    Tipado
