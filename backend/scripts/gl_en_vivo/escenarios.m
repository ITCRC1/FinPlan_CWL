let
    P = (n as text) => Excel.CurrentWorkbook(){[Name = n]}[Content]{0}[Column1],
    // Celda vacía -> "" (nunca null): una fila a medio llenar no tumba la consulta.
    T = (v) => if v = null then "" else Text.Trim(Text.From(v)),
    Url = T(P("pURL")),
    LlaveCruda = P("pLlave"),
    Llave = T(LlaveCruda),
    Cols = {"Anio", "Tipo", "Version", "Estado"},
    Fallo = (msg as text) => #table(Cols, {{null, "ERROR", msg, null}}),
    Resp = Web.Contents(Url, [
        RelativePath = "api/consolidado/escenarios/",
        Headers = [#"x-api-key" = Llave, Accept = "application/json"],
        ManualStatusHandling = {400, 404, 422, 500, 502, 503, 504},
                // Con «Actualizar todo» llegan ~70 pedidos juntos y el servidor los
                // atiende de a uno: el GL completo tardaba mas de los 100 s que Power
                // Query espera por defecto y la consulta entera caia (owner, 2026-11-12).
                Timeout = #duration(0, 0, 10, 0)
    ]),
    Estado = Value.Metadata(Resp)[Response.Status],
    Salida =
        if Llave = "" then Fallo("Falta la llave de solo lectura en Config")
                else if Estado <> 200 then Fallo("El servidor respondio HTTP " & Text.From(Estado))
        else #table(Cols, List.Transform(Json.Document(Resp)[escenarios], each
                {[year], [tipo], (let v = [version] in if v = null then "" else v), [status]}))
in
    Salida
