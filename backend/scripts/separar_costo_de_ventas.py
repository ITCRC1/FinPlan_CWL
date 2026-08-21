# -*- coding: utf-8 -*-
"""Saca las cuentas clase 5 de la línea de gasto y les da línea propia de COSTO.

**Por qué (owner, 2026-08-14).** En la Consulta GL la cuenta 5101 se llama "Food
Cost" y su línea de P&L decía `OPEX_FB`. "Todas las líneas de cuentas 5 son
Cost". Tiene razón: en USALI el costo de ventas es su propio renglón, no un
gasto operativo más.

**La regla que puso el owner: el resultado NO se mueve.** Es cómo se presenta el
costo, no un cambio de números. Por eso las fórmulas de los totales y de la
utilidad por departamento se ajustan en el mismo movimiento.

⚠️ **La trampa.** El motor arma `TOTAL_OPERATING_EXPENSES` como
`SUM(OPEX_*)` —por PREFIJO— y cada `PROFIT_X` como `REV_X − OPEX_X`. Si las
clase 5 se van a líneas `COS_*` y nadie toca esas fórmulas, **dejan de sumar en
los dos lados y el GOP sube por el monto completo del costo de ventas**, sin que
nada avise. Solo en A&B son $664,928 de enero a abril.

Por eso este script hace las tres cosas juntas, y por eso existe
`scripts/foto_pl_totales.py`: se toma la foto antes, se aplica, se compara, y
tiene que dar idéntico.

Se toca el JSON del seed y NO la base: el seed corre en cada arranque y
re-afirma el mapeo desde el archivo, así que una migración que tocara las tablas
sin cambiar el JSON se revertiría sola (`alembic/097_el_seed_manda_sobre_el_mapeo`).

    python -m scripts.separar_costo_de_ventas          # muestra qué haría
    python -m scripts.separar_costo_de_ventas --aplicar
"""
import json
import pathlib
import sys

ARCHIVO = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "seed_data" / "mapping_pl.json")

# Departamentos operativos: su costo entra en TOTAL_OPERATING_EXPENSES y baja la
# utilidad de su propio departamento.
COSTO_OPERATIVO = {
    "OPEX_SPA": [("COS_SPA", "Spa Cost", None)],
    "OPEX_TOURS": [("COS_TOURS", "Tours Cost", None)],
    "OPEX_TRANSPORTATION": [("COS_TRANSPORTATION", "Transportation Cost", None)],
    "OPEX_TIENDA": [("COS_TIENDA", "Tienda Cost", None)],
    "OPEX_RETAIL": [("COS_RETAIL", "Gift Shop Cost", None)],
    "OPEX_PRIVATE_BAR": [("COS_PRIVATE_BAR", "Private Bar Cost", None)],
    "OPEX_LAUNDRY": [("COS_LAUNDRY", "Laundry Cost", None)],
    "OPEX_INNOCEANA": [("COS_INNOCEANA", "Innoceana Cost", None)],
    "OPEX_CROWTHER_LAB": [("COS_CROWTHER_LAB", "Crowther Lab Cost", None)],
    "OPEX_CLUB": [("COS_CLUB", "Club Madresal Cost", None)],
    # A&B va partido en tres, que es como el owner lo lee.
    "OPEX_FB": [
        ("COS_FB_FOOD", "F&B Food Cost", {"5101", "5102", "5103"}),
        ("COS_FB_BEV", "F&B Beverage Cost",
         {"5150", "5151", "5152", "5153", "5154", "5155"}),
        ("COS_FB_MISC", "F&B Misc Cost",
         {"5161", "5162", "5163", "5164", "5165"}),
    ],
}

# Departamentos de overhead: su costo entra en TOTAL_OVERHEAD_EXPENSES. Prefijo
# distinto (`COH_`) justamente para que `SUM(COS_*)` no se los lleve al lado
# operativo.
COSTO_OVERHEAD = {
    "OH_CAFETERIA": [("COH_CAFETERIA", "Cafetería Cost", None)],
    "OH_EMPLOYEE_BENEFITS": [("COH_EMPLOYEE_BENEFITS", "Employee Benefits Cost", None)],
    "OH_INFORMATION_SYSTEM": [("COH_INFORMATION_SYSTEM", "Information Systems Cost", None)],
    "OH_CLARO_HUERTA": [("COH_CLARO_HUERTA", "Claro del Bosque Cost", None)],
    "OH_LAUNDRY": [("COH_LAUNDRY", "Laundry Cost", None)],
    "OH_AREC": [("COH_AREC", "Área Recreativa Cost", None)],
}

# El mismo corte, del lado del INGRESO (owner, 2026-08-14, con el mapeo marcado
# en amarillo sobre su propia pantalla de Account Mapping).
#
# Esto es lo que faltaba para que el Revenue Detail salga idéntico a su cuadro:
# "Other Rooms Revenue", "F&B Beverage" y "F&B Miscellaneous" no tenían línea y
# quedaban en gris.
#
# El prefijo sigue siendo `REV_`, así que `SUM(REV_*)` los sigue tomando y el
# ingreso total NO se mueve. Lo que sí hay que ajustar es la utilidad de Rooms y
# de A&B, que hoy resta contra UNA sola línea de ingreso.
INGRESO = {
    "REV_ROOMS": [
        ("REV_ROOMS", "Rooms Revenue", {"4000"}),
        ("REV_ROOMS_OTHER", "Other Rooms Revenue", {"4001", "4002"}),
    ],
    "REV_FB": [
        ("REV_FB", "F&B Food", {"4110"}),
        ("REV_FB_BEV", "F&B Beverage", {"4120", "4125", "4130", "4131"}),
        ("REV_FB_MISC", "F&B Miscellaneous", {"4132"}),
    ],
}

ORDEN_COS = 47      # entre la última OPEX_ (46) y TOTAL_OPERATING_EXPENSES (48)
ORDEN_COH = 82      # después de OH_AREC (81)
# Cada linea nueva de ingreso hereda el `display_order` de su padre, para que
# salgan pegadas a el en el reporte. Los empates ya existen en el archivo y el
# sistema los tolera; lo que NO se puede es empatar con otra linea ajena. La
# primera version le puso 21 a REV_FB_BEV y choco con el Private Bar — lo cazo
# `test_private_bar_aparte`.
ORDEN_REV = None   # se toma del padre

# Las fórmulas que hay que ajustar para que nada se mueva.
FORMULAS = {
    "TOTAL_OPERATING_EXPENSES": ("SUM(OPEX_*)", "SUM(OPEX_*) + SUM(COS_*)"),
    "TOTAL_OVERHEAD_EXPENSES": ("SUM(OH_*)", "SUM(OH_*) + SUM(COH_*)"),
}


def _separar_ingreso(d: dict, notas: list[str]):
    """Parte Rooms y A&B en sus líneas de ingreso, según el mapeo del owner."""
    movidas = 0
    for fila in d["account_mapping"]:
        origen = fila["report_line_code"]
        if origen not in INGRESO:
            continue
        cta = str(fila["account_code"])
        for code, nombre, cuentas in INGRESO[origen]:
            if cta in cuentas:
                if code != origen:
                    fila["report_line_code"] = code
                    movidas += 1
                fila["report_line_name"] = nombre
                break
        else:
            notas.append(f"  !! ingreso {cta} de {origen} no está en el mapeo "
                         "del owner — se queda donde está")
    notas.append(f"  {movidas} cuentas de ingreso movidas a su línea nueva")

    existentes = {r["line_code"] for r in d["report_line_config"]}
    usadas = {f["report_line_code"] for f in d["account_mapping"]}
    for origen, hijas in INGRESO.items():
        base = next(r for r in d["report_line_config"] if r["line_code"] == origen)
        for code, nombre, _ in hijas:
            if code == origen:
                base["line_name"] = nombre       # el nombre estandar del owner
                continue
            if code in existentes or code not in usadas:
                continue
            d["report_line_config"].append({**base, "line_code": code,
                                            "line_name": nombre})
            notas.append(f'  + {code} {nombre}')


def transformar(d: dict) -> tuple[dict, list[str]]:
    notas = []
    destino = {**COSTO_OPERATIVO, **COSTO_OVERHEAD}
    _separar_ingreso(d, notas)

    # 1. Mover las cuentas clase 5 a su línea nueva.
    movidas = 0
    for fila in d["account_mapping"]:
        origen = fila["report_line_code"]
        if origen not in destino or not str(fila["account_code"]).startswith("5"):
            continue
        cta = str(fila["account_code"])
        elegida = None
        for code, nombre, cuentas in destino[origen]:
            if cuentas is None or cta in cuentas:
                elegida = (code, nombre)
                break
        if elegida is None:
            notas.append(f"  !! {cta} de {origen} no cayó en ningún grupo — se queda")
            continue
        fila["report_line_code"] = elegida[0]
        fila["report_line_name"] = elegida[1]
        fila["report_section"] = ("COST OF SALES" if origen in COSTO_OPERATIVO
                                  else "OVERHEAD COST OF SALES")
        movidas += 1
    notas.append(f"  {movidas} cuentas clase 5 movidas a su línea de costo")

    # 2. Crear las líneas nuevas.
    existentes = {r["line_code"] for r in d["report_line_config"]}
    usadas = {f["report_line_code"] for f in d["account_mapping"]}
    nuevas = 0
    for mapa, orden, seccion in ((COSTO_OPERATIVO, ORDEN_COS, "COST OF SALES"),
                                 (COSTO_OVERHEAD, ORDEN_COH, "OVERHEAD COST OF SALES")):
        for origen, hijas in mapa.items():
            for code, nombre, _ in hijas:
                if code in existentes:
                    continue
                # Una línea sin una sola cuenta detrás es ruido en el reporte.
                if code not in usadas:
                    notas.append(f"  -  {code} no recibió ninguna cuenta — no se crea")
                    continue
                d["report_line_config"].append({
                    "report_id": "P&L_DETAIL_OWNERS",
                    "display_order": orden,
                    "line_code": code,
                    "section": seccion,
                    "line_name": nombre,
                    "line_type": "MAPPED",
                    "parent_line_code": ("SEC_OPERATING_EXPENSES"
                                         if seccion == "COST OF SALES"
                                         else "SEC_OVERHEAD_EXPENSES"),
                    "calculation_logic": "SUM mapped accounts",
                    "format_hint": "currency/number",
                    "active": True,
                })
                nuevas += 1
    notas.append(f"  {nuevas} líneas de costo creadas")

    # 3. Ajustar las fórmulas. SIN esto el GOP se mueve.
    creadas = {r["line_code"] for r in d["report_line_config"]}
    for r in d["report_line_config"]:
        lc = r["line_code"]
        if lc in FORMULAS:
            viejo, nuevo = FORMULAS[lc]
            if r.get("calculation_logic") == viejo:
                r["calculation_logic"] = nuevo
                notas.append(f'  {lc}: {viejo} -> {nuevo}')
            elif r.get("calculation_logic") != nuevo:
                actual = r.get("calculation_logic")
                notas.append(f"  !! {lc} tiene [{actual}] y no [{viejo}]. NO se toca.")
            continue
        # La utilidad de cada departamento tiene que SUMAR sus líneas de ingreso
        # nuevas y RESTAR su costo. Sin lo primero, Rooms y A&B se quedan sin la
        # parte del ingreso que se acaba de separar; sin lo segundo, no restan
        # el costo de ventas. Cualquiera de los dos olvidos mueve el GOP.
        if lc.startswith("PROFIT_"):
            expr = (r.get("calculation_logic") or "").strip()
            if not expr:
                continue
            cambio = False
            for origen, hijas in INGRESO.items():
                if origen not in expr:
                    continue
                for code, _, _ in hijas:
                    if code != origen and code in creadas and code not in expr:
                        # Va pegado al ingreso, ANTES de las restas.
                        expr = expr.replace(origen, f"{origen} + {code}", 1)
                        cambio = True
            for origen, hijas in COSTO_OPERATIVO.items():
                if origen not in expr:
                    continue
                for code, _, _ in hijas:
                    if code in creadas and code not in expr:
                        expr += f" - {code}"
                        cambio = True
            if cambio:
                r["calculation_logic"] = expr
                notas.append(f'  {lc}: -> {expr}')
    return d, notas


def main(aplicar: bool):
    d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    antes_lineas = len(d["report_line_config"])
    d, notas = transformar(d)
    print("\n".join(notas))
    print(f"\nlineas del reporte: {antes_lineas} -> {len(d['report_line_config'])}")
    if not aplicar:
        print("\n(prueba en seco - corre con --aplicar)")
        return
    ARCHIVO.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"\nescrito: {ARCHIVO}")


if __name__ == "__main__":
    main("--aplicar" in sys.argv)
