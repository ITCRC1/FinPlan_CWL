# -*- coding: utf-8 -*-
"""Auditoria del detalle del mayor: la descripcion contra la cuenta y el depto.

Owner, 2026-10-05: *«necesito una herramienta de revision para asegurarme que
la descripcion de los gastos sea correctamente con la cuenta contable, el
departamento, y que genere un reporte de discrepancias para yo poder empezar a
revisar»*.

Que hace y que NO hace
---------------------
Esto **no decide** si un asiento esta bien: senala los que NO se parecen al
resto y dice por que, para que el owner los revise. Su revision sigue siendo
cuenta por cuenta y linea por linea — lo que cambia es por donde empieza.

**Las reglas salen del archivo, no de un diccionario.** No hay una lista que
diga «el jabon es gasto y no comida»: lo que hay es que un articulo con nombre
identico cayo en dos cuentas y una de las dos es minoria. Un diccionario
envejece y hay que mantenerlo; la comparacion contra el propio mayor se
actualiza sola cada mes.

Por que se compara el articulo y no la descripcion
--------------------------------------------------
En las compras (origen CXP) la columna `Referencia` trae el ARTICULO —«Aguacate
Hass unidad»— mientras `Descripcion` trae el proveedor. El articulo es lo
comparable: el mismo jabon comprado dos veces tiene el mismo texto, mientras
que un proveedor vende cosas distintas.

Lo que se aprendio afinando esto contra setiembre 2026
------------------------------------------------------
La primera version saco **1.047 hallazgos** y era inservible: nueve filas
identicas para el mismo jabon, y 837 avisos que eran el reparto legitimo de
comida entre el restaurante (5101) y el comedor de empleados (5420). Un reporte
asi no se revisa, se cierra. Dos correcciones:

1. **Se agrupa por articulo, no por linea.** El hallazgo es «este articulo cayo
   en esta cuenta»; las lineas son la evidencia y viajan adentro. Asi el owner
   lee un renglon por caso y abajo tiene los asientos para ir a buscarlos.

2. **Un reparto parejo no es un error, es una decision.** Huevos 24 veces en
   5101 y 21 en 5420 es a proposito. Lo sospechoso es lo DESPAREJO: 15 contra
   3. Por eso dentro de la misma clase solo se avisa cuando la minoria no llega
   a `UMBRAL_MINORIA` de la mayoria.

⚠️ El cruce de CLASE se avisa SIEMPRE, por parejo que sea: un articulo no puede
ser costo de lo que se vende y gasto de operacion al mismo tiempo. Ahi el
reparto parejo no es una decision, es la mitad mal en algun lado.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Iterable

#: Departamentos que por USALI NO pueden tener costo de ventas (clase 5): no
#: venden un producto directo. CLAUDE.md §21.10 regla 13.
SIN_COSTO_DE_VENTAS = {
    "0110",                                          # Rooms
    "0180", "0181", "0182", "0183", "0184", "0186",  # Admin
    "0190",                                          # Sales & Marketing
    "0200", "0205",                                  # Maintenance / Utilities
}

#: Cuentas de cajon: existen, son validas, y por eso mismo se usan cuando no se
#: sabe donde poner algo. No son un error — son donde se esconde uno.
VERTEDERO = {"7380": "MISCELLANEOUS"}

#: El costo de la comida del comedor de empleados (CLAUDE.md §3.2).
COMIDA_DE_EMPLEADOS = {"5420", "5421"}
#: Donde deberia estar la comida del restaurante.
COSTO_DE_RESTAURANTE = "5101"

#: Palabras de producto PREMIUM. Owner, 2026-10-05: *«errores que metan
#: productos premium en employees food y que deberian ser food cost de
#: restaurantes»*.
#:
#: ⚠️ Esta es la UNICA regla con lista de palabras, y es a proposito. Las demas
#: comparan el archivo contra si mismo porque la pregunta es «¿esto se parece al
#: resto?». Aca la pregunta es otra —«¿esto es un producto de carta?»— y eso no
#: esta en ningun numero del mayor: el archivo no trae cantidad, asi que por
#: monto no se puede separar un filete de pargo de un saco de arroz a granel.
#: Probado contra setiembre: por monto salian cafe, arroz y muslo de pollo
#: mezclados con los filetes; por palabra salen los seis articulos que son.
#:
#: Es una lista para CRECER. Si aparece un producto de carta que no esta aca,
#: se agrega la palabra y queda cubierto para siempre.
PREMIUM = (
    "filete", "filet", "lomito", "solomillo", "churrasco", "rib eye", "ribeye",
    "bistec", "cordero", "pargo", "congrio", "corvina", "dorado", "atun", "atún",
    "salmon", "salmón", "camaron", "camarón", "langosta", "pulpo", "calamar",
    "mariscos", "vino",
)

#: Que tan desparejo tiene que ser un reparto para que sea sospechoso. Con 1/3:
#: 15 contra 3 avisa, 24 contra 21 no. Subirlo trae mas ruido del bueno y mas
#: del malo; bajarlo esconde casos reales. Se ajusta mirando un mes completo.
UMBRAL_MINORIA = 1 / 3

#: Como el owner lee el estado de resultados. Owner, 2026-10-05: *«a mi me
#: gustaria tener las discrepancias por tipo de cuenta. Costos empieza con 5,
#: payroll 6, Opex 7 y property expenses 8»*.
#:
#: La clase 4 va aparte y no estaba en esa lista: el ingreso tambien se revisa
#: —ahi vive la 4999, que tiene que netear a cero— y mandarlo a un grupo de
#: gasto lo escondería. Si un mes no trae hallazgos de ingreso, el grupo
#: simplemente no aparece.
GRUPOS: dict[str, str] = {
    "4": "Ingresos",
    "5": "Costos",
    "6": "Planilla",
    "7": "Opex",
    "8": "Gastos de propiedad",
}
ORDEN_GRUPOS = ("Costos", "Planilla", "Opex", "Gastos de propiedad", "Ingresos")


def grupo_de(cuenta: str) -> str:
    """El tipo de cuenta al que pertenece un hallazgo, por su primer digito."""
    return GRUPOS.get(cuenta[:1], "Otros")


#: Como el owner lee el MAYOR COMPLETO, del 1 al 9. Owner, 2026-10-07, viendo el
#: reporte de cambios: *«debe ir por cuenta del 1 al 8 y debe ir por categoria,
#: Balance 01-03, Revenue 4, costos 5, payrol 6, Opex 7-8, Stats 9»*.
#:
#: ⚠️ **No es lo mismo que `GRUPOS` y las dos conviven a proposito.** `GRUPOS`
#: es como se leen los HALLAZGOS —solo clases 4 a 8, con la 7 y la 8
#: separadas («Opex» y «Gastos de propiedad»), como el owner lo pidio el
#: 2026-10-05— y esto es como se lee el MAYOR entero, que incluye el balance y
#: las estadisticas y junta 7 con 8. Unificarlas a mano habria cambiado en
#: silencio un cuadro que el owner ya revisa.
CATEGORIAS: dict[str, str] = {
    "1": "Balance", "2": "Balance", "3": "Balance",
    "4": "Revenue",
    "5": "Costos",
    "6": "Planilla",
    "7": "Opex", "8": "Opex",
    "9": "Stats",
}
#: El orden en que salen: el del numero de cuenta, 1 -> 9.
ORDEN_CATEGORIAS = ("Balance", "Revenue", "Costos", "Planilla", "Opex", "Stats",
                    "Otras")


def categoria_de(cuenta: str) -> str:
    """La categoria del mayor a la que pertenece una cuenta, por su clase."""
    return CATEGORIAS.get(str(cuenta or "")[:1], "Otras")


ALTA, MEDIA, BAJA = "alta", "media", "baja"
_ORDEN = {ALTA: 0, MEDIA: 1, BAJA: 2}


@dataclass
class Hallazgo:
    """Un caso a revisar. `lineas` son los asientos concretos donde esta."""
    #: Costos · Planilla · Opex · Gastos de propiedad · Ingresos. Sale de la
    #: cuenta SENALADA, no de la sugerida: el caso se revisa donde el asiento
    #: esta hoy, no donde deberia terminar.
    grupo: str
    regla: str
    severidad: str
    cuenta: str
    dept: str
    concepto: str          # el articulo, el puesto o el rotulo en discusion
    n_lineas: int
    monto_crc: float
    monto_usd: float
    porque: str
    sugerencia: str = ""
    lineas: list[dict] = field(default_factory=list)

    def dict(self) -> dict:
        return asdict(self)


@dataclass
class Resumen:
    periodo: str = ""
    lineas_del_archivo: int = 0
    lineas_revisadas: int = 0
    hallazgos: list[Hallazgo] = field(default_factory=list)
    por_regla: dict[str, int] = field(default_factory=dict)
    por_severidad: dict[str, int] = field(default_factory=dict)
    por_grupo: dict[str, dict] = field(default_factory=dict)
    lineas_senaladas: int = 0
    monto_en_revision_crc: float = 0.0

    def cerrar(self) -> "Resumen":
        orden_g = {g: i for i, g in enumerate(ORDEN_GRUPOS)}
        self.hallazgos.sort(key=lambda h: (orden_g.get(h.grupo, 9),
                                           _ORDEN[h.severidad], -abs(h.monto_crc)))
        for h in self.hallazgos:
            self.por_regla[h.regla] = self.por_regla.get(h.regla, 0) + 1
            self.por_severidad[h.severidad] = self.por_severidad.get(h.severidad, 0) + 1
        for g in ORDEN_GRUPOS:
            hs = [h for h in self.hallazgos if h.grupo == g]
            if hs:
                self.por_grupo[g] = {
                    "casos": len(hs),
                    "lineas": sum(h.n_lineas for h in hs),
                    "monto_crc": round(sum(abs(h.monto_crc) for h in hs), 2),
                    "alta": sum(1 for h in hs if h.severidad == ALTA),
                }
        self.lineas_senaladas = sum(h.n_lineas for h in self.hallazgos)
        self.monto_en_revision_crc = round(
            sum(abs(h.monto_crc) for h in self.hallazgos), 2)
        return self


def _clave(texto: str) -> str:
    return " ".join(texto.lower().split())


def _crc(v: float) -> str:
    return "CRC {:,.0f}".format(v)


def _evidencia(ls: list) -> list[dict]:
    return [{"asiento": l.asiento, "linea": l.linea, "fecha": l.fecha,
             "cuenta": l.cuenta, "descripcion": l.descripcion,
             "referencia": l.referencia, "origen": l.origen,
             "monto_crc": round(l.monto_crc, 2),
             "monto_usd": round(l.monto_usd, 2)} for l in ls]


def _hallazgo(ls: list, regla: str, sev: str, concepto: str, porque: str,
              sugerencia: str = "") -> Hallazgo:
    return Hallazgo(
        grupo=grupo_de(ls[0].cuenta),
        regla=regla, severidad=sev, cuenta=ls[0].cuenta, dept=ls[0].seg2,
        concepto=concepto, n_lineas=len(ls),
        monto_crc=round(sum(l.monto_crc for l in ls), 2),
        monto_usd=round(sum(l.monto_usd for l in ls), 2),
        porque=porque, sugerencia=sugerencia, lineas=_evidencia(ls))


# ─────────────────────────────── reglas ───────────────────────────────
def _dominante(por_llave: dict[str, list]) -> str | None:
    """La llave con mas lineas; a igual cantidad, la de mas plata. None si empatan.

    Devolver None en el empate NO es rendirse: es la diferencia entre decir
    «esto va alla» y «esto esta partido al medio y alguien tiene que decidir».
    Inventar un ganador en un 9 contra 9 seria mandar al owner a mover la mitad
    correcta.
    """
    if not por_llave:
        return None
    monto = {k: abs(sum(x.monto_crc for x in v)) for k, v in por_llave.items()}
    orden = sorted(por_llave, key=lambda k: (len(por_llave[k]), monto[k]), reverse=True)
    if len(orden) > 1:
        a, b = orden[0], orden[1]
        if len(por_llave[a]) == len(por_llave[b]) and abs(monto[a] - monto[b]) < 1:
            return None
    return orden[0]


def _articulo_en_varias_cuentas(lineas: list) -> list[Hallazgo]:
    """El mismo articulo en cuentas distintas. La minoria es la sospechosa.

    ⚠️ **La dominancia se mide primero por CLASE y despues por cuenta.** Medirla
    solo por cuenta se equivoca justo cuando mas importa: «White C Comercial»
    —un producto de limpieza— tenia 6 lineas en 5420 (costo de comida) y 21
    repartidas en siete cuentas 7xxx de suministros. Por cuenta ganaba 5420 con
    sus 6 contra 3, y la herramienta recomendaba mandar la limpieza al costo de
    comida: siete avisos, todos al reves. Por clase gana el gasto operativo 21 a
    6, que es lo correcto, y sale UN aviso sobre las 6 lineas equivocadas.
    """
    grupos: dict[str, list] = defaultdict(list)
    for l in lineas:
        if l.clase in "57" and len(l.referencia) >= 4:
            grupos[_clave(l.referencia)].append(l)

    out: list[Hallazgo] = []
    for ls_art in grupos.values():
        por_clase: dict[str, list] = defaultdict(list)
        for l in ls_art:
            por_clase[l.clase].append(l)

        # 1) El cruce de clase manda: un articulo no puede ser costo de lo que se
        #    vende y gasto de operacion a la vez, por parejo que este repartido.
        if len(por_clase) > 1:
            dom_clase = _dominante(por_clase)
            if dom_clase is None:
                detalle = " vs ".join(
                    "clase {} x{} ({})".format(c, len(v), _crc(sum(x.monto_crc for x in v)))
                    for c, v in sorted(por_clase.items()))
                for c, ls in sorted(por_clase.items()):
                    out.append(_hallazgo(
                        ls, "ARTICULO_CRUZA_CLASE", ALTA, ls[0].referencia,
                        "«{}» quedo partido entre costo de ventas y gasto de operacion "
                        "sin un lado dominante: {}. Un articulo no puede ser los dos; "
                        "hay que decidir cual es."
                        .format(ls[0].referencia, detalle)))
                continue
            buenos = por_clase[dom_clase]
            por_cuenta_dom: dict[str, list] = defaultdict(list)
            for l in buenos:
                por_cuenta_dom[l.seg1 + "-" + l.seg2].append(l)
            sug = _dominante(por_cuenta_dom) or ""
            for c, ls in por_clase.items():
                if c == dom_clase:
                    continue
                out.append(_hallazgo(
                    ls, "ARTICULO_CRUZA_CLASE", ALTA, ls[0].referencia,
                    "«{}» se registro {} veces en la clase {} ({}) y {} {} aca, en la "
                    "clase {} ({}). Cruza de clase: no puede ser costo de lo que se "
                    "vende y gasto de operacion a la vez."
                    .format(ls[0].referencia, len(buenos), dom_clase,
                            _crc(sum(x.monto_crc for x in buenos)), len(ls),
                            "vez" if len(ls) == 1 else "veces", c,
                            _crc(sum(x.monto_crc for x in ls))), sug))
            ls_art = buenos      # dentro de la clase buena, seguir afinando

        # 2) Dentro de una misma clase, solo lo DESPAREJO: un reparto parejo es
        #    una decision (huevos al restaurante y al comedor), no un error.
        por_cuenta: dict[str, list] = defaultdict(list)
        for l in ls_art:
            por_cuenta[l.seg1 + "-" + l.seg2].append(l)
        if len(por_cuenta) < 2:
            continue
        dom = _dominante(por_cuenta)
        if dom is None:
            continue
        n_dom = len(por_cuenta[dom])
        monto = {k: sum(x.monto_crc for x in v) for k, v in por_cuenta.items()}
        for cuenta, ls in por_cuenta.items():
            if cuenta == dom or len(ls) / n_dom > UMBRAL_MINORIA:
                continue
            out.append(_hallazgo(
                ls, "ARTICULO_EN_VARIAS_CUENTAS", MEDIA, ls[0].referencia,
                "«{}» se registro {} {} en {} ({}) y solo {} {} en esta cuenta ({})."
                .format(ls[0].referencia, n_dom, "vez" if n_dom == 1 else "veces",
                        dom, _crc(monto[dom]), len(ls),
                        "vez" if len(ls) == 1 else "veces", _crc(monto[cuenta])), dom))
    return out


def _costo_en_depto_sin_costo(lineas: list) -> list[Hallazgo]:
    """Clase 5 en un departamento que no vende nada."""
    por_cuenta: dict[str, list] = defaultdict(list)
    for l in lineas:
        if l.clase == "5" and l.seg2 in SIN_COSTO_DE_VENTAS:
            por_cuenta[l.cuenta].append(l)
    return [_hallazgo(ls, "COSTO_EN_DEPTO_SIN_COSTO", ALTA, ls[0].cuenta,
                      "La clase 5 es el costo de lo vendido y el departamento {} no "
                      "vende un producto directo: no deberia tener cuentas 5xxx."
                      .format(ls[0].seg2))
            for ls in por_cuenta.values()]


def _planilla_depto(lineas: list) -> list[Hallazgo]:
    """El departamento que dice el texto contra el que dice la cuenta.

    Es el error que el owner cazo a mano en agosto: cuentas de planilla del
    comedor de empleados (0220) rotuladas «FRONT DESK». La cuenta manda sobre el
    rotulo, asi que el rotulo minoritario de cada departamento es el sospechoso.
    """
    etiquetas: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for l in lineas:
        if l.clase == "6" and l.num_doc:
            etiquetas[l.seg2][_clave(l.num_doc)].append(l)
    out: list[Hallazgo] = []
    for dept, por_rotulo in etiquetas.items():
        if len(por_rotulo) < 2:
            continue
        dom = max(por_rotulo, key=lambda k: len(por_rotulo[k]))
        bueno = por_rotulo[dom][0].num_doc
        for rotulo, ls in por_rotulo.items():
            if rotulo == dom:
                continue
            out.append(_hallazgo(
                ls, "PLANILLA_DEPTO_NO_COINCIDE", ALTA, ls[0].num_doc,
                "La cuenta es del departamento {}, que en el resto del mes se rotula "
                "«{}» ({} lineas). Esta dice «{}»."
                .format(dept, bueno, len(por_rotulo[dom]), ls[0].num_doc), bueno))
    return out


def _planilla_puesto(lineas: list) -> list[Hallazgo]:
    """Un codigo de puesto (seg3) con mas de un nombre."""
    puestos: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for l in lineas:
        if l.clase == "6" and l.referencia:
            puestos[(l.seg2, l.seg3)][_clave(l.referencia)].append(l)
    out: list[Hallazgo] = []
    for (dept, seg3), por_nombre in puestos.items():
        if len(por_nombre) < 2:
            continue
        dom = max(por_nombre, key=lambda k: len(por_nombre[k]))
        bueno = por_nombre[dom][0].referencia
        for nombre, ls in por_nombre.items():
            if nombre == dom:
                continue
            out.append(_hallazgo(
                ls, "PLANILLA_PUESTO_NO_COINCIDE", MEDIA, ls[0].referencia,
                "El puesto {} del departamento {} aparece como «{}» en {} lineas y "
                "como «{}» en esta."
                .format(seg3, dept, bueno, len(por_nombre[dom]), ls[0].referencia),
                bueno))
    return out


def _cuenta_vertedero(lineas: list) -> list[Hallazgo]:
    """Lo que cayo en una cuenta generica. No es un error: es donde se esconde."""
    por_dept: dict[tuple, list] = defaultdict(list)
    for l in lineas:
        if l.seg1 in VERTEDERO:
            por_dept[(l.seg1, l.seg2)].append(l)
    return [_hallazgo(ls, "CUENTA_GENERICA", BAJA,
                      "{} {}".format(s1, VERTEDERO[s1]),
                      "{} ({}) es una cuenta de cajon y el departamento {} le cargo "
                      "{} en {} lineas. Vale revisar cuales tienen cuenta propia."
                      .format(s1, VERTEDERO[s1], s2,
                              _crc(sum(l.monto_crc for l in ls)), len(ls)))
            for (s1, s2), ls in por_dept.items()]


def _allocation_no_netea(lineas: list) -> list[Hallazgo]:
    """La 4999 tiene que sumar cero a nivel de hotel (CLAUDE.md regla 15)."""
    ls = [l for l in lineas if l.seg1 == "4999"]
    total = sum(l.monto_crc for l in ls)
    if not ls or abs(total) < 1:
        return []
    return [_hallazgo(ls, "ALLOCATION_NO_NETEA", ALTA, "4999 DISTRIBUCION",
                      "La cuenta 4999 reparte gasto: tiene que sumar cero a nivel de "
                      "hotel y suma {} en {} lineas."
                      .format(_crc(total), len(ls)))]



def _premium_en_comida_de_empleados(lineas: list) -> list[Hallazgo]:
    """Producto de carta cargado al costo de la comida del personal.

    Owner, 2026-10-05: *«errores que metan productos premium en employees food y
    que deberian ser food cost de restaurantes»*.

    Mueve plata entre dos lineas del P&L que se leen al reves: infla el costo
    del comedor —que despues se reparte a TODOS los departamentos via la 4999—
    y abarata el costo del restaurante, que es donde se mide el margen de F&B.
    Los dos indicadores quedan mal y ninguno da error.
    """
    por_art: dict[str, list] = defaultdict(list)
    for l in lineas:
        if l.seg1 in COMIDA_DE_EMPLEADOS and l.referencia:
            t = _clave(l.referencia)
            if any(p in t for p in PREMIUM):
                por_art[t].append(l)
    return [_hallazgo(
        ls, "PREMIUM_EN_COMIDA_DE_EMPLEADOS", ALTA, ls[0].referencia,
        "«{}» es un producto de carta y esta en {}, el costo de la comida del "
        "personal ({} {} por {}). Si se compro para el restaurante va en {}: "
        "cargarlo aca infla el comedor —que se reparte a todos los departamentos— "
        "y abarata el margen de F&B."
        .format(ls[0].referencia, ls[0].seg1, len(ls),
                "linea" if len(ls) == 1 else "lineas",
                _crc(sum(l.monto_crc for l in ls)), COSTO_DE_RESTAURANTE),
        COSTO_DE_RESTAURANTE + "-0120") for ls in por_art.values()]


def _puesto_en_varios_departamentos(lineas: list) -> list[Hallazgo]:
    """Un puesto cargado a un departamento que no es el suyo.

    Owner, 2026-10-05: *«en las cuentas de payroll 6, posiciones que no
    corresponden al departamento»*.

    No es lo mismo que `_planilla_puesto`, que mira un codigo con dos nombres.
    Aca es al reves: el mismo NOMBRE de puesto repartido entre departamentos
    distintos. Puede ser legitimo —un cocinero del comedor de empleados es un
    cocinero— pero es exactamente lo que hay que mirar: en setiembre «COCINERO
    B» tenia 42 lineas en Kitchen y 42 en Employee Dining.

    Se senala el departamento con MENOS plata, que es el candidato a estar de
    mas; si los dos estan parejos se senalan ambos.
    """
    por_puesto: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for l in lineas:
        if l.clase == "6" and l.referencia:
            por_puesto[_clave(l.referencia)][l.seg2].append(l)
    out: list[Hallazgo] = []
    for por_dept in por_puesto.values():
        if len(por_dept) < 2:
            continue
        dom = _dominante(por_dept)
        reparto = " · ".join(
            "{} x{} ({})".format(d, len(v), _crc(sum(x.monto_crc for x in v)))
            for d, v in sorted(por_dept.items(),
                               key=lambda kv: -abs(sum(x.monto_crc for x in kv[1]))))
        for dept, ls in por_dept.items():
            if dom is not None and dept == dom:
                continue
            out.append(_hallazgo(
                ls, "PUESTO_EN_VARIOS_DEPARTAMENTOS", MEDIA, ls[0].referencia,
                "El puesto «{}» esta cargado a mas de un departamento: {}. Revisar "
                "si la plaza de {} corresponde a ese departamento."
                .format(ls[0].referencia, reparto, dept),
                "" if dom is None else dom))
    return out

REGLAS = (_articulo_en_varias_cuentas, _costo_en_depto_sin_costo, _planilla_depto,
          _planilla_puesto, _cuenta_vertedero, _allocation_no_netea,
          _premium_en_comida_de_empleados, _puesto_en_varios_departamentos)


def revisar(lineas: Iterable, desde_clase: int = 4, periodo: str = "") -> Resumen:
    """Las discrepancias del mes, ordenadas por severidad y por monto.

    `desde_clase=4` deja fuera el balance (clases 1, 2 y 3): el owner revisa
    «las cuentas que empiezan con 4 en adelante», las del estado de resultados.
    """
    todas = list(lineas)
    ls = [l for l in todas if l.seg1[:1].isdigit() and int(l.seg1[0]) >= desde_clase]
    r = Resumen(periodo=periodo, lineas_del_archivo=len(todas), lineas_revisadas=len(ls))
    for regla in REGLAS:
        r.hallazgos.extend(regla(ls))
    return r.cerrar()
