# -*- coding: utf-8 -*-
"""La capa de datos del informe. Lee el JSON de `extraer.py` y nada mas.

⚠️ Ninguna funcion de aqui vuelve a sumar los totales por clase: los devuelve
tal como los calculo `gasto_por_clase_api._por_mes`. Ver la cabecera de
`extraer.py`.
"""
from __future__ import annotations

import json
import pathlib
from collections import defaultdict

AQUI = pathlib.Path(__file__).resolve().parent

MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "setiembre", "octubre", "noviembre", "diciembre"]

CONCEPTOS = [
    ("c6000_sw", "6000", "Salarios y jornales", "devengado"),
    ("c6001_overtime", "6001", "Horas extra", "devengado"),
    ("c6002_day_off", "6002", "Dia libre laborado", "devengado"),
    ("c6003_working_holiday", "6003", "Feriado trabajado", "devengado"),
    ("c6004_disabilities", "6004", "Incapacidades", "devengado"),
    ("c6010_commissions", "6010", "Comisiones", "devengado"),
    ("c6024_vacations_taken", "6024", "Vacaciones disfrutadas", "devengado"),
    ("c6027_incentive_bonus", "6027", "Bono de incentivo", "devengado"),
    ("c6020_ccss", "6020", "CCSS patronal 26,83%", "carga"),
    ("c6022_occ_hazard", "6022", "Riesgos del trabajo (INS)", "carga"),
    ("c6021_aguinaldo", "6021", "Aguinaldo (1/12)", "provision"),
    ("c6023_vacation_prov", "6023", "Provision de vacaciones", "provision"),
    ("c6026_severance", "6026", "Preaviso y cesantia", "provision"),
    ("c6025_cafeteria", "6025", "Cafeteria", "beneficio"),
    ("c6028_housing", "6028", "Vivienda", "beneficio"),
    ("c6029_transport", "6029", "Transporte", "beneficio"),
    ("c6030_other", "6030", "Otros beneficios", "beneficio"),
]

#: Los tres departamentos que el tab deja fuera del gasto salvo en el
#: Pre-Cierre. Es la regla permanente de allocation vista desde el reporte.
EXCL = {"0220", "0161", "0162"}

#: Los departamentos operativos del P&L, en su orden, y de que codigos de
#: FinPlan se compone cada uno. Algunos son la suma de varios: A&B junta 0120
#: con Private Bar (0121) y el Spa vive partido entre 0130 y 0140.
OPERATIVOS = [
    ("Rooms", {"0110"}),
    ("Alimentos y Bebidas", {"0120", "0121"}),
    ("Spa", {"0130", "0140"}),
    ("Tours / Actividades", {"0150"}),
    ("Gift Shop", {"0165"}),
    ("Transportacion", {"0152"}),
    ("Lavanderia", {"0161", "0162"}),
    ("Innoceana", {"0155"}),
    ("Sostenibilidad y otros", {"280"}),
    ("Cafeteria de empleados", {"0220"}),
]

OVERHEAD = [
    ("Administracion", {"0180"}),
    ("Ventas y Mercadeo", {"0190"}),
    ("Mantenimiento", {"0200"}),
    ("Sistemas (IT)", {"0230"}),
    ("Utilities / Energia", {"0210", "0205"}),
]


class Datos:
    """La lectura del corte del mes.

    Se construye de dos formas, y las dos tienen que existir: el ENDPOINT
    extrae en memoria y pasa el dict; el SCRIPT de linea de comandos trabaja
    sobre el archivo guardado, para poder rearmar el informe sin volver a tocar
    produccion.
    """

    def __init__(self, anio, mes, corte=None):
        if corte is None:
            ruta = AQUI / "datos" / f"{anio}_{mes:02d}.json"
            if not ruta.exists():
                raise SystemExit(
                    f"Falta {ruta}. Corra primero: "
                    f"  python informes/extraer.py --anio {anio} --mes {mes}")
            corte = json.loads(ruta.read_text(encoding="utf-8"))
        self.d = corte
        self.anio = anio
        self.mes = mes
        self.idx = mes - 1
        self.mes_nombre = MESES_ES[self.idx]
        self.deptos = self.d["deptos"]
        self.escs = [k for k in ("ACT", "BUD", "FCT") if k in self.d["meses"]]
        self.avisos = self.d.get("avisos", [])
        self.archivo_mayor = (self.d["mayor"][0]["archivo"] if self.d["mayor"] else None)
        #: De que subida de Pre-Cierre vienen los cuadros. Es lo que permite
        #: decir si el analisis escrito describe ESTE dato o uno anterior.
        self.subida = self.d.get("subida")

    # ── nombres ────────────────────────────────────────────────────────────
    def nom(self, dept: str) -> str:
        n = self.deptos.get(dept, "")
        return f"{dept} · {n}" if n and n != dept else dept

    def rotulo(self, esc: str) -> str:
        return self.d["escenarios"][esc]["rotulo"]

    # ── totales de la fuente oficial ───────────────────────────────────────
    def total(self, esc: str, clase: str, mes: int | None = None) -> float:
        """El total de la clase. `_por_mes` devuelve las cuatro de GASTO
        —payroll, cost, opex, property—; el INGRESO no viene en esa fila, asi
        que se suma su apertura, que la misma funcion dejo en `detalle`."""
        m = self.mes if mes is None else mes
        f = next(x for x in self.d["meses"][esc] if int(x["month"]) == m)
        if clase in f:
            return float(f[clase])
        return sum(self.det(esc, clase, m).values())

    def tot_gasto(self, esc: str, mes: int | None = None) -> float:
        return sum(self.total(esc, c, mes) for c in ("payroll", "cost", "opex"))

    def gop(self, esc: str, mes: int | None = None) -> float:
        return self.total(esc, "revenue", mes) - self.tot_gasto(esc, mes)

    def pl(self, esc: str, linea: str, periodo: str = "mes") -> float:
        return float(self.d["pl"][esc][periodo].get(linea, 0.0))

    # ── apertura por departamento ──────────────────────────────────────────
    def _serie(self, esc: str, clase: str, clave: str):
        s = self.d["detalle"][esc].get(clase, {}).get(clave)
        if s is None:
            return [0.0] * 12
        if isinstance(s, dict):
            return [float(s.get(str(m), s.get(m, 0)) or 0) for m in range(1, 13)]
        return [float(x or 0) for x in s]

    def det(self, esc: str, clase: str, mes: int | None = None) -> dict:
        i = (self.mes if mes is None else mes) - 1
        return {k: self._serie(esc, clase, k)[i]
                for k in self.d["detalle"][esc].get(clase, {})}

    def grupo(self, deptos: set, clase: str, esc: str, mes: int | None = None) -> float:
        return sum(v for k, v in self.det(esc, clase, mes).items() if k in deptos)

    def cuatro(self, deptos: set, esc: str, mes: int | None = None) -> dict:
        return {c: self.grupo(deptos, c, esc, mes)
                for c in ("revenue", "cost", "payroll", "opex")}

    def resultado(self, deptos: set, esc: str) -> float:
        c = self.cuatro(deptos, esc)
        return c["revenue"] - c["cost"] - c["payroll"] - c["opex"]

    # ── apertura por cuenta ────────────────────────────────────────────────
    def por_cuenta(self, clase: str, periodo: str = "mes") -> dict:
        """`{(depto, cuenta): {ACT, BUD, FCT, nombre}}`.

        ⚠️ La llave NUNCA incluye el nombre. El real escribe «UTILITIES - OIL»
        y el presupuesto «Oil (Boat and Equipment)» para la misma 7395; agrupar
        por nombre las parte en dos filas que no se ven como la misma cuenta, y
        el cuadro muestra dos variaciones donde hay una.
        """
        a = defaultdict(lambda: {"ACT": 0.0, "BUD": 0.0, "FCT": 0.0, "nombre": ""})
        for x in self.d["lineas"][clase]:
            if x["esc"] != "ACT" and clase != "revenue" and x["dept_code"] in EXCL:
                continue
            k = (x["dept_code"], x["account_code"])
            n = str(x["account_name"] or "")
            if not a[k]["nombre"] or n.isupper():
                a[k]["nombre"] = n
            a[k][x["esc"]] += x[periodo]
        return dict(a)

    # ── planilla ───────────────────────────────────────────────────────────
    def payroll_concepto(self, periodo: str = "mes") -> dict:
        out = {c[1]: {"nombre": c[2], "tipo": c[3],
                      **{e: 0.0 for e in self.escs}} for c in CONCEPTOS}
        for esc in self.escs:
            for f in self.d["payroll"].get(esc, {}).get(periodo, []):
                if esc != "ACT" and f["dept_code"] in EXCL:
                    continue
                for col, cod, _n, _t in CONCEPTOS:
                    out[cod][esc] += f.get(col, 0.0)
        return out

    def payroll_depto(self, periodo: str = "mes") -> dict:
        out = defaultdict(lambda: {e: 0.0 for e in self.escs})
        for esc in self.escs:
            for f in self.d["payroll"].get(esc, {}).get(periodo, []):
                if esc != "ACT" and f["dept_code"] in EXCL:
                    continue
                out[f["dept_code"]][esc] += sum(f.get(c[0], 0.0) for c in CONCEPTOS)
        return dict(out)

    def concepto_por_depto(self, codigo: str, esc: str = "ACT") -> dict:
        col = next(c[0] for c in CONCEPTOS if c[1] == codigo)
        return {f["dept_code"]: f.get(col, 0.0)
                for f in self.d["payroll"].get(esc, {}).get("mes", [])
                if abs(f.get(col, 0.0)) > 0.005}

    # ── estadistica de habitaciones ────────────────────────────────────────
    def stats(self) -> dict:
        rs = self.d["stats"].get("ACT") or []
        disp = sum(float(x["nights_available"] or 0) for x in rs)
        occ = sum(float(x["nights_occupied"] or 0) for x in rs)
        rev = sum(float(x["revenue"] or 0) for x in rs)
        pax = sum(float(x["pax"] or 0) for x in rs)
        out = {"ACT": {"disp": disp, "occ": occ, "rev": rev, "pax": pax,
                       "ocup": occ / disp if disp else 0,
                       "adr": rev / occ if occ else 0,
                       "revpar": rev / disp if disp else 0, "tipos": rs}}
        for k in ("BUD", "FCT"):
            s = self.d["stats"].get(k)
            if not s:
                out[k] = None
                continue
            disp = float(s["rooms_available"] or 0)
            occ = float(s["rooms_occupied"] or 0)
            adr = float(s["adr"] or 0)
            out[k] = {"disp": disp, "occ": occ, "rev": occ * adr,
                      "pax": float(s["guests"] or 0),
                      "ocup": float(s["occupancy_pct"] or 0), "adr": adr,
                      "revpar": occ * adr / disp if disp else 0, "tipos": []}
        return out

    # ── el mayor ───────────────────────────────────────────────────────────
    def mayor(self) -> dict:
        """`{(depto, cuenta): {usd, n, prov}}` — el mismo camino del Audit
        Integral: puente de Integrity a FinPlan y despues consolidacion."""
        out = defaultdict(lambda: {"usd": 0.0, "n": 0, "prov": defaultdict(float)})
        for m in self.d["mayor"]:
            if (m["seg1"] or "")[:1] not in "45678":
                continue
            k = (m["dept"], m["seg1"])
            out[k]["usd"] += m["usd"]
            out[k]["n"] += 1
            out[k]["prov"][(m["descripcion"] or "(sin descripcion)")[:42]] += m["usd"]
        return dict(out)

    @staticmethod
    def proveedores(agg: dict, dept: str, cuenta: str, top: int = 4):
        v = agg.get((dept, cuenta))
        if not v:
            return []
        return sorted(v["prov"].items(), key=lambda x: -abs(x[1]))[:top]

    def por_proveedor(self, nombres: list[str]) -> list[dict]:
        """Factura por factura de una lista de proveedores — **solo 5-6-7-8**.

        Owner, 2026-11-06: *«que venga el detalle de las facturas una a una por
        proveedor, el monto en colones y el monto en usd, de los cargos
        posteados en las cuentas 5-6-7-8 solamente»* y *«la cuenta y
        departamento donde esta quedando registrado»* y *«alguna nota que se
        haya puesto»*.

        Cuatro decisiones, cada una medida contra el mayor de ago–oct 2026:

        1. **La factura es el ASIENTO.** `num_doc` viene destrozado desde
           Integrity —`1.00003010000001e+17`, «CD», «MAINTENANCE»— y no
           identifica nada. El asiento agrupa limpio.
        2. **Se busca en `descripcion` Y en `referencia`.** Normalmente el
           tercero esta en `descripcion`, pero «Consultants Costa Rica» lo trae
           al reves: la marca en `descripcion` y la razon social
           `3-102-844425 SOCIEDAD...` en `referencia`. Mirar uno solo pierde
           facturas enteras.
        3. **Solo clases 5-6-7-8.** Lo que cae en 1-3 es balance y **no es
           gasto del periodo**: SDG RH suma ₡195,5M en el mayor pero ₡173,6M de
           eso es la cuenta 2000 —el pasivo de salarios que pasa por ellos— y
           al P&L solo llegan ₡21,9M. Sumar todo se equivoca por nueve veces.
        4. **El IVA queda fuera.** Vive en la 2000, asi que el filtro por clase
           ya lo saca; las lineas que lo traen en cuenta de gasto se descartan
           aparte, porque IVA en gasto es IVA que no se recupero.

        El USD **no se recalcula**: `extraccion` ya lo dejo en `usd`, dividido
        por el `tc` de cada linea. Dos caminos hacia el mismo numero terminan
        dando dos numeros.
        """
        patrones = [(n or "").strip().upper() for n in nombres if (n or "").strip()]
        fuera = []
        for patron in patrones:
            facturas, cargos = {}, {}
            for m in self.d["mayor"]:
                if (m["seg1"] or "")[:1] not in "5678":
                    continue
                ref = (m.get("referencia") or "")
                desc = (m.get("descripcion") or "")
                if patron not in desc.upper() and patron not in ref.upper():
                    continue
                if "IVA" in ref.upper():
                    continue
                crc = float(m["debito"] or 0) - float(m["credito"] or 0)
                usd_ = float(m.get("usd") or 0)
                k = (str(m.get("fecha") or ""), str(m.get("asiento") or ""))
                f = facturas.setdefault(k, {
                    "fecha": k[0], "asiento": k[1], "crc": 0.0, "usd": 0.0,
                    "tc": float(m.get("tc") or 0), "cuentas": set(),
                    "conceptos": set(), "notas": set()})
                f["crc"] += crc
                f["usd"] += usd_
                f["cuentas"].add(f'{m["seg1"]} · {m["seg2"]}')
                if ref:
                    f["conceptos"].add(ref[:34])
                if m.get("desc_asiento"):
                    f["notas"].add(str(m["desc_asiento"])[:90])
                c = cargos.setdefault((m["seg2"], m["seg1"]), {
                    "dept": m["seg2"], "cuenta": m["seg1"], "crc": 0.0,
                    "usd": 0.0, "n": 0})
                c["crc"] += crc
                c["usd"] += usd_
                c["n"] += 1
            if not facturas:
                fuera.append({"nombre": patron, "facturas": [], "cargos": [],
                              "crc": 0.0, "usd": 0.0})
                continue
            fuera.append({
                "nombre": patron,
                "facturas": sorted(facturas.values(), key=lambda x: (x["fecha"], x["asiento"])),
                "cargos": sorted(cargos.values(), key=lambda x: -abs(x["usd"])),
                "crc": sum(f["crc"] for f in facturas.values()),
                "usd": sum(f["usd"] for f in facturas.values()),
            })
        return sorted(fuera, key=lambda x: -abs(x["usd"]))

    #: El corte de la varianza: las lineas que explican el 80% del movimiento.
    CORTE_EXPLICA = 0.80

    def _mayor_de(self, previo: bool) -> list:
        return self.d.get("mayor_prev" if previo else "mayor") or []

    @staticmethod
    def _top_que_explica(filas: list[dict], corte: float) -> tuple[list[dict], float]:
        """Las filas que explican `corte` del movimiento total, y cuanto cubren.

        ⚠️ Se ordena por el VALOR ABSOLUTO de la variacion y el denominador es
        la suma de los absolutos, no la variacion neta. Si se usara el neto, un
        mes donde un departamento sube 50 y otro baja 50 tendria denominador
        cero y «explicaria» el infinito. Lo que el owner pidio —«el 80% de las
        cuentas que explican la varianza»— es el movimiento, no el saldo.
        """
        orden = sorted(filas, key=lambda x: -abs(x["var"]))
        total = sum(abs(f["var"]) for f in orden)
        if total <= 0:
            return [], 0.0
        acum, fuera = 0.0, []
        for f in orden:
            fuera.append(f)
            acum += abs(f["var"])
            if acum / total >= corte:
                break
        return fuera, acum / total

    def varianza_mes_anterior(self) -> dict:
        """Este mes contra el anterior, en el mismo escenario (Pre-Cierre).

        Owner, 2026-11-06: *«ANALISIS DE VARIANZAS VERSUS EL MES PASADO... las
        cuentas 6 que es salario, un analisis por posicion por departamento...
        y las cuentas de gastos por departamento por cuenta... el 80% de las
        cuentas que explican la varianza total versus el mes previo»*.

        **Sale del MAYOR, no de los checkbooks**, y por una razon dura: la
        posicion (`seg3`) solo existe ahi. Ni `actual_entries` ni los
        checkbooks la tienen — el presupuesto se armo al nivel de la cuenta
        (ver `el-presupuesto-no-tiene-tercer-nivel`). El mayor es tambien lo
        que alimenta el Pre-Cierre, asi que los dos miran el mismo dato.

        ⚠️ **Las reclasificaciones de allocation distorsionan la comparacion
        por departamento.** Mueven costo de un departamento a otro con neto
        cero: un mes con reclasificaciones y otro sin ellas se ven como un
        cambio de plantilla que no ocurrio. Se cuentan aparte y se avisan.
        Medido en CWL: agosto 2026 traia 160 lineas de reclasificacion por neto
        ₡0; setiembre y octubre, ninguna.
        """
        act, prev = self._mayor_de(False), self._mayor_de(True)
        if not act or not prev:
            return {"hay": False, "periodo_prev": self.d.get("mayor_prev_periodo", "")}

        def recl(m) -> bool:
            return ("RECLASIF" in (m.get("referencia") or "").upper()
                    or "RECLASIF" in (m.get("descripcion") or "").upper())

        def junta(filas, clave, clases):
            fuera = {}
            for m in filas:
                if (m["seg1"] or "")[:1] not in clases or recl(m):
                    continue
                fuera[clave(m)] = fuera.get(clave(m), 0.0) + float(m.get("usd") or 0)
            return fuera

        def arma(clave, clases, campos):
            a = junta(act, clave, clases)
            b = junta(prev, clave, clases)
            filas = []
            for k in set(a) | set(b):
                va, vb = a.get(k, 0.0), b.get(k, 0.0)
                if abs(va) < 0.005 and abs(vb) < 0.005:
                    continue
                f = dict(zip(campos, k if isinstance(k, tuple) else (k,)))
                f.update({"act": va, "prev": vb, "var": va - vb})
                filas.append(f)
            top, cubre = self._top_que_explica(filas, self.CORTE_EXPLICA)
            return {"todas": filas, "top": top, "cubre": cubre,
                    "act": sum(f["act"] for f in filas),
                    "prev": sum(f["prev"] for f in filas),
                    "var": sum(f["var"] for f in filas)}

        clases = {}
        for cl, etiqueta in (("5", "Costo de ventas"), ("6", "Planilla"),
                             ("7", "Opex"), ("8", "Propiedad")):
            a = sum(float(m.get("usd") or 0) for m in act
                    if (m["seg1"] or "")[:1] == cl and not recl(m))
            b = sum(float(m.get("usd") or 0) for m in prev
                    if (m["seg1"] or "")[:1] == cl and not recl(m))
            clases[cl] = {"etiqueta": etiqueta, "act": a, "prev": b, "var": a - b}

        return {
            "hay": True,
            "periodo_prev": self.d.get("mayor_prev_periodo", ""),
            "corte": self.CORTE_EXPLICA,
            "clases": clases,
            # Clase 6 por departamento y posicion — lo que pidio para salarios.
            "planilla": arma(lambda m: (m["seg2"] or "", m["seg3"] or ""),
                             "6", ("dept", "pos")),
            # Gastos por departamento y cuenta.
            "gastos": arma(lambda m: (m["seg2"] or "", m["seg1"] or ""),
                           "578", ("dept", "cuenta")),
            "reclasif": {
                "act": sum(1 for m in act if recl(m)),
                "prev": sum(1 for m in prev if recl(m)),
                "neto_act": sum(float(m.get("usd") or 0) for m in act if recl(m)),
                "neto_prev": sum(float(m.get("usd") or 0) for m in prev if recl(m)),
            },
        }

    def nombre_posicion(self, dept: str, pos: str) -> str:
        """`seg3` -> nombre, del catalogo de posiciones. 36 de 39 casan."""
        cat = self.d.get("posiciones") or {}
        return cat.get(f"{dept}|{pos}") or cat.get(pos) or ""

    def creditos_allocation(self) -> dict:
        """Los creditos 4999 que el reporte DESCARTA — ver la seccion 10.1.

        El tab incluye el gasto de Cafeteria y Lavanderia y descarta su credito
        de reparto, asi que el GOP del reporte sale peor que el del motor por
        exactamente esta cifra.
        """
        out = {}
        for x in self.d["lineas"]["opex"]:
            if x["esc"] == "ACT" and x["account_code"] == "4999":
                out[x["dept_code"]] = x["mes"]
        return out

    def meses_cargados(self) -> list:
        """Que meses trae el espejo del Pre-Cierre. Si no esta el anterior, no
        hay comparativo secuencial y el informe lo dice."""
        return [int(f["month"]) for f in self.d["meses"]["ACT"]
                if abs(f["payroll"]) + abs(f["cost"]) + abs(f["opex"]) > 0.005]
