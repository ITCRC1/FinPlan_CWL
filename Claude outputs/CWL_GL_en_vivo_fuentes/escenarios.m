let
    P = (n as text) => Excel.CurrentWorkbook(){[Name = n]}[Content]{0}[Column1],
    Url = Text.Trim(Text.From(P("pURL"))),
    LlaveCruda = P("pLlave"),
    Llave = if LlaveCruda = null then "" else Text.Trim(Text.From(LlaveCruda)),
    Cols = {"Anio", "Tipo", "Version", "Estado"},
    Fallo = (msg as text) => #table(Cols, {{null, "ERROR", msg, null}}),
    Resp = Web.Contents(Url, [
        RelativePath = "api/consolidado/escenarios/",
        Headers = [#"x-api-key" = Llave, Accept = "application/json"],
        ManualStatusHandling = {307, 308, 400, 404, 422, 500, 502, 503}
    ]),
    Estado = Value.Metadata(Resp)[Response.Status],
    Salida =
        if Llave = "" then Fallo("Falta la llave de solo lectura en Config")
        else if Estado = 307 or Estado = 308
                then Fallo("La direccion redirige: en Config poner la del BACKEND "
                           & "(https://finplancwl-backend.up.railway.app), no la del frontend")
                else if Estado <> 200 then Fallo("El servidor respondio HTTP " & Text.From(Estado))
        else #table(Cols, List.Transform(Json.Document(Resp)[escenarios], each
                {[year], [tipo], (let v = [version] in if v = null then "" else v), [status]}))
in
    Salida
