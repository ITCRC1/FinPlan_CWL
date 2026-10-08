# -*- coding: utf-8 -*-
"""Narrativa del informe operativo de OCTUBRE 2026.  ← PLANTILLA SIN LLENAR

Pasos antes de escribir:

  1. Subir el Pre-Cierre de octubre y el mayor de octubre en «Auditoria del
     mayor». Sin el mayor el informe no puede nombrar proveedores ni asientos.
  2. python informes/generador/extraer.py --anio 2026 --mes 10
  3. python informes/generador/armar.py --anio 2026 --mes 10
     → sale con los cuadros completos y marcas [PENDIENTE] donde falta texto,
       y lista las claves que faltan.
  4. Mirar los cuadros, y recien entonces escribir aca.

⚠️ El orden importa: **los cuadros primero, el analisis despues**. Escribir el
analisis antes de ver los numeros es como se arma un informe que confirma lo que
uno ya creia.

Reglas de escritura en `informes/INFORME_OPERATIVO.md` §5. Modelo completo en
`n2026_09.py`.

Y una advertencia propia de octubre: en el Budget 2026 de CWL octubre tiene
ocupacion 0% y FTE 0 por decision del presupuesto. Si el real tuvo operacion, la
variacion de ingreso va a salir FAVORABLE y la de gasto tambien, y eso no
significa que el mes fue bueno: significa que se comparo contra un mes cerrado.
Hay que decirlo en `contexto` antes de cualquier otra cosa.
"""

NARRATIVA = {
    "propiedad": "CORCOVADO WILDERNESS LODGE",

    # ── 2 · resumen ejecutivo ─────────────────────────────────────────────
    # Dos o tres parrafos. El primero con las cifras de ingreso, gasto y GOP
    # contra presupuesto. El segundo con la lectura: que paso y por que.
    "resumen": [],

    # Entre cinco y siete, ORDENADOS POR IMPACTO EN DOLARES sobre el resultado
    # —no por tamano de la cuenta—. Formato: (titulo, monto, texto).
    "hallazgos": [],

    # ── 3 · contexto operativo ────────────────────────────────────────────
    "contexto": [],            # que clase de mes fue; en octubre, la advertencia
    "contexto_kpi": [],        # tarifa vs volumen: cual de los dos fallo
    "contexto_tipos": [],      # que categorias de villa no vendieron
    "contexto_secuencial": [],  # octubre contra setiembre: reacciono el costo?
    "contexto_nota": None,     # (titulo, texto) del recuadro de cierre

    # ── 4 y 5 · departamentos ─────────────────────────────────────────────
    "dept_resumen": [],
    "overhead_resumen": [],

    # Las claves son los nombres de `OPERATIVOS` y `OVERHEAD` en datos.py.
    # Cada uno: comentario (parrafos), cuentas (para la tabla del mayor) y
    # preguntas al gerente.
    "dept": {
        "Rooms": {"comentario": [], "cuentas": [], "preguntas": []},
        "Alimentos y Bebidas": {"comentario": [], "cuentas": [], "preguntas": []},
        "Spa": {"comentario": [], "cuentas": [], "preguntas": []},
        "Tours / Actividades": {"comentario": [], "cuentas": [], "preguntas": []},
        "Gift Shop": {"comentario": [], "cuentas": [], "preguntas": []},
        "Transportacion": {"comentario": [], "cuentas": [], "preguntas": []},
        "Lavanderia": {"comentario": [], "cuentas": [], "preguntas": []},
        "Innoceana": {"comentario": [], "cuentas": [], "preguntas": []},
        "Sostenibilidad y otros": {"comentario": [], "cuentas": [], "preguntas": []},
        "Cafeteria de empleados": {"comentario": [], "cuentas": [], "preguntas": []},
        "Administracion": {"comentario": [], "cuentas": [], "preguntas": []},
        "Ventas y Mercadeo": {"comentario": [], "cuentas": [], "preguntas": []},
        "Mantenimiento": {"comentario": [], "cuentas": [], "preguntas": []},
        "Sistemas (IT)": {"comentario": [], "cuentas": [], "preguntas": []},
        "Utilities / Energia": {"comentario": [], "cuentas": [], "preguntas": []},
    },

    # ── 6 · planilla ──────────────────────────────────────────────────────
    # Donde esta el desvio: salario base, o horas extra / vacaciones /
    # provisiones. Casi siempre es lo segundo.
    "payroll_conceptos": [],
    "payroll_nota": None,

    # ── 7 · margenes ──────────────────────────────────────────────────────
    "margenes": [],
    # Opcional: el cuadro de apertura del margen mas grave del mes.
    # {titulo, intro, cabeceras, filas, nota, cierre}
    "margen_detalle": None,

    # ── 8 · opex ──────────────────────────────────────────────────────────
    # Cada favorabilidad clasificada en AHORRO / DIFERIMIENTO / RECLASIFICACION.
    # La pista: si el Forecast del mes siguiente sube la cuenta, era diferimiento.
    "opex_favorables": None,   # {cabeceras, filas, nota, cierre}
    "opex_impactos": None,     # {cabeceras, filas}

    # ── 9 · clase 8 ───────────────────────────────────────────────────────
    "propiedad_notas": [],

    # ── 10 · hallazgos de clasificacion ───────────────────────────────────
    # Revisar si los casos de setiembre se corrigieron — ver §9 del .md:
    #   cafeteria 5700/5420 · tours 0152/0150 · internet 5700/5400 ·
    #   gift shop 0151/0165 · spa 0130/0140
    "clasificacion": None,     # {intro, cabeceras, filas, nota}
    "sin_presupuesto": None,   # {intro, cabeceras, filas, nota}
    "brechas": [],

    # ── 11 · agenda ───────────────────────────────────────────────────────
    # Las preguntas de las secciones 4 y 5, reagrupadas por responsable.
    # Formato: (responsable, foco, [preguntas]).
    "agenda": [],
}
