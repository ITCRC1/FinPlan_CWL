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
    def __init__(self, anio: int, mes: int):
        ruta = AQUI / "datos" / f"{anio}_{mes:02d}.json"
        if not ruta.exists():
            raise SystemExit(
                f"Falta {ruta}. Corra primero:\n"
                f"  python informes/generador/extraer.py --anio {anio} --mes {mes}")
        self.d = json.loads(ruta.read_text(encoding="utf-8"))
        self.anio = anio
        self.mes = mes
        self.idx = mes - 1
        self.mes_nombre = MESES_ES[self.idx]
        self.deptos = self.d["deptos"]
        self.escs = [k for k in ("ACT", "BUD", "FCT") if k in self.d["meses"]]
        self.avisos = self.d.get("avisos", [])
        self.archivo_mayor = (self.d["mayor"][0]["archivo"] if self.d["mayor"] else None)

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
