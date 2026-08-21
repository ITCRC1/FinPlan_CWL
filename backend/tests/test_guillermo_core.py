# -*- coding: utf-8 -*-
"""El núcleo de Guillermo — Fase 1 (`docs/GUILLERMO.md`).

Lo que estas pruebas vigilan no es que el código corra, sino **que un control
no pueda volverse decorativo**: que «no sé» no se lea como «está bien», que un
verde sobre una lista vacía no exista, y que el silencio no signifique salud
por accidente.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.guillermo.core import (
    ArchivoVisto, Esperado, TERMINALES, TRANSICIONES, TransicionInvalida,
    estado_visible, latido_vencido, nivel_1_presencia, nivel_2_periodo,
    normalizar, puede_pasar, transicionar, variacion_sospechosa,
)

AHORA = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)


# ── Normalización (§7.4) ────────────────────────────────────────────────────

def test_los_cinco_pasos_de_la_normalizacion():
    """El ejemplo literal del spec."""
    assert normalizar("MANT. PISCINA QUÍMICOS") == "MANT PISCINA QUIMICOS"
    assert normalizar("Mant  piscina quimicos") == "MANT PISCINA QUIMICOS"
    assert normalizar("  mant.piscina , quimicos  ") == "MANT PISCINA QUIMICOS"


def test_normalizar_nada_no_revienta():
    assert normalizar(None) == ""
    assert normalizar("") == ""
    assert normalizar("   ") == ""


def test_la_normalizacion_NO_junta_conceptos_distintos():
    """⚠️ El riesgo del otro lado: si normalizara de más, dos gastos distintos
    caerían en la misma regla y el mapeo mandaría plata a la cuenta
    equivocada."""
    assert normalizar("PISCINA QUIMICOS") != normalizar("PISCINA REPUESTOS")
    assert normalizar("Cuenta 7065") != normalizar("Cuenta 7080")


# ── Máquina de estados (§7.5) ───────────────────────────────────────────────

def test_las_transiciones_del_spec():
    assert puede_pasar("queued", "running")
    assert puede_pasar("running", "pending_review")
    assert puede_pasar("pending_review", "validated")
    assert puede_pasar("validated", "imported")
    assert puede_pasar("imported", "reverted")


def test_de_un_estado_terminal_no_se_sale():
    assert TERMINALES == {"failed", "shadowed", "reverted"}
    for t in TERMINALES:
        assert TRANSICIONES[t] == set()
        with pytest.raises(TransicionInvalida):
            transicionar(t, "running")


def test_un_batch_importado_no_puede_volver_a_correr():
    """Reimportar sobre lo ya importado tiene que pasar por `reverted`, que
    deja rastro. Si `imported → running` fuera válido, la reimportación
    borraría la traza de la primera."""
    assert not puede_pasar("imported", "running")
    assert puede_pasar("imported", "reverted")


def test_una_transicion_invalida_REVIENTA_y_dice_cuales_valen():
    """⚠️ Revienta a propósito en vez de devolver False: un batch en un estado
    imposible es peor que uno que falló, porque el que falló se ve."""
    with pytest.raises(TransicionInvalida) as e:
        transicionar("queued", "imported")
    assert "queued" in str(e.value) and "running" in str(e.value)


def test_el_modo_sombra_no_puede_terminar_en_importado():
    """Sombra procesa y NO escribe. Su terminal es `shadowed`."""
    assert puede_pasar("validated", "shadowed")
    assert "shadowed" in TERMINALES


# ── Nivel 1 · presencia (§6.2) ──────────────────────────────────────────────

def test_SIN_MANIFIESTO_no_dice_que_todo_esta_bien():
    """⚠️ **La prueba que evita el peor falso positivo.** Hoy el manifiesto
    está vacío porque su contenido es la decisión D-1. Un verde sobre una lista
    vacía de esperados diría «llegó todo» sin saber qué tenía que llegar."""
    r = nivel_1_presencia([ArchivoVisto("cualquiera.csv", 100)], [])
    assert len(r) == 1
    assert r[0].pasa is False
    assert "D-1" in r[0].detalle


def test_un_reporte_obligatorio_que_falta_es_una_falla():
    r = nivel_1_presencia(
        [ArchivoVisto("otro.csv", 100)],
        [Esperado("trial_balance", "TrialBalance_*.csv", obligatorio=True)])
    assert any(not h.pasa for h in r)


def test_un_reporte_opcional_que_falta_NO_es_una_falla():
    r = nivel_1_presencia(
        [], [Esperado("extra", "Extra_*.csv", obligatorio=False)])
    assert all(h.pasa for h in r)


def test_el_archivo_VACIO_no_pasa():
    r = nivel_1_presencia([ArchivoVisto("TrialBalance_18.csv", 0)],
                          [Esperado("tb", "TrialBalance_*.csv")])
    assert any(not h.pasa and "vacío" in h.detalle for h in r)


def test_el_archivo_TRUNCADO_no_pasa():
    """⚠️ El caso peligroso: entra, parsea y da totales más chicos sin que nada
    falle. Un archivo a medio escribir se ve igual que uno completo."""
    r = nivel_1_presencia([ArchivoVisto("TrialBalance_18.csv", 120)],
                          [Esperado("tb", "TrialBalance_*.csv", tamano_min=5000)])
    assert any(not h.pasa and "truncado" in h.detalle for h in r)


# ── Nivel 2 · identidad del período (§6.2) ──────────────────────────────────

def test_detecta_EL_REDESCARGADO_DE_AYER():
    """⚠️ La razón de ser del nivel 2: el archivo llega, tiene el nombre de
    hoy, pesa lo de siempre y trae los datos de otro día."""
    r = nivel_2_periodo([ArchivoVisto("hoy.csv", 900, date(2026, 8, 17))],
                        date(2026, 8, 18), date(2026, 8, 18))
    assert not r[0].pasa
    assert "2026-08-17" in r[0].detalle


def test_una_fecha_QUE_NO_SE_PUDO_LEER_no_pasa_como_buena():
    """⚠️ «No sé» y «coincide» no son lo mismo. Tratarlos igual es cómo un
    control se vuelve decorativo."""
    r = nivel_2_periodo([ArchivoVisto("x.pdf", 900, None)],
                        date(2026, 8, 18), date(2026, 8, 18))
    assert not r[0].pasa
    assert "no se pudo leer" in r[0].detalle


def test_la_fecha_correcta_pasa():
    r = nivel_2_periodo([ArchivoVisto("x.csv", 900, date(2026, 8, 18))],
                        date(2026, 8, 18), date(2026, 8, 18))
    assert r[0].pasa


# ── Detector de falso positivo (§6.3) ───────────────────────────────────────

def test_el_comparable_es_EL_MISMO_MES_DEL_ANO_ANTERIOR():
    """⚠️ Corrección al spec, que decía «el período anterior comparable» sin
    definirlo. Medido en Corcovado: setiembre corre al 9,1% de ocupación y
    febrero al 81,4%. Mes contra mes, la alerta salta SIEMPRE.

    Con el mismo mes del año anterior, la caída estacional no dispara nada; con
    el mes previo, sí. Esta prueba fija cuál es el comparable correcto.
    """
    feb, sep = Decimal("400000"), Decimal("40000")
    salta_mes_previo, _ = variacion_sospechosa(sep, feb, Decimal("10"))
    assert salta_mes_previo, "mes contra mes la estacionalidad dispara la alerta"

    sep_anterior = Decimal("38000")
    salta_ano, var = variacion_sospechosa(sep, sep_anterior, Decimal("10"))
    assert not salta_ano, f"contra el mismo mes del año anterior no debería saltar (var {var})"


def test_sin_comparable_NO_dice_que_esta_bien():
    salta, var = variacion_sospechosa(Decimal("100"), Decimal("0"), Decimal("10"))
    assert salta is False and var == 0


def test_la_caida_grande_tambien_dispara_no_solo_la_subida():
    """Un total que se DERRUMBA es tan sospechoso como uno que se dispara —
    suele ser el archivo truncado."""
    salta, _ = variacion_sospechosa(Decimal("10"), Decimal("100"), Decimal("10"))
    assert salta


# ── Heartbeat · dead-man switch (§12.1) ─────────────────────────────────────

def test_NUNCA_HABER_LATIDO_cuenta_como_vencido():
    """⚠️ Si «no hay registro» diera «todo bien», el estado inicial —y el de un
    worker que jamás arrancó— sería verde."""
    vencido, motivo = latido_vencido(None, 26, AHORA)
    assert vencido and "nunca" in motivo


def test_el_latido_reciente_esta_sano():
    vencido, _ = latido_vencido(AHORA - timedelta(hours=2), 26, AHORA)
    assert not vencido


def test_el_latido_viejo_esta_vencido():
    vencido, motivo = latido_vencido(AHORA - timedelta(hours=30), 26, AHORA)
    assert vencido and "30" in motivo


def test_un_latido_sin_zona_horaria_no_revienta():
    """Postgres puede devolver naive según la conexión. Reventar acá dejaría el
    dead-man switch muerto — justo el control que no puede fallar callado."""
    vencido, _ = latido_vencido(datetime(2026, 8, 20, 4, 0), 26, AHORA)
    assert vencido is False


# ── El semáforo (§10.1) ─────────────────────────────────────────────────────

def test_EL_LATIDO_VENCIDO_GANA_SOBRE_LOS_PENDIENTES():
    """⚠️ Un Guillermo trabado con cero pendientes se vería verde si los
    pendientes mandaran — y «cero pendientes» sería justamente la consecuencia
    de estar trabado, no una buena noticia."""
    e = estado_visible(latido_vencido_=True, motivo_latido="sin latido",
                       pendientes=0, corriendo=False)
    assert e.state == "stuck" and e.color == "rojo"


def test_los_pendientes_ponen_ambar():
    e = estado_visible(latido_vencido_=False, motivo_latido="",
                       pendientes=4, corriendo=False)
    assert e.state == "pending" and e.color == "ambar" and e.pendientes == 4


def test_al_dia_es_verde():
    e = estado_visible(latido_vencido_=False, motivo_latido="",
                       pendientes=0, corriendo=False)
    assert e.state == "idle" and e.color == "verde"


# ── El núcleo es PURO (§2) ──────────────────────────────────────────────────

def test_el_nucleo_no_toca_ni_la_red_ni_el_disco_ni_la_base():
    """⚠️ Requisito de diseño: el mismo código corre en el cron de Railway y en
    un agente local. Si el núcleo supiera de dónde vienen los archivos, cambiar
    de fuente sería reescribirlo."""
    import ast
    import inspect

    from app.guillermo import core

    # ⚠️ Se mira el CÓDIGO, no el texto. Buscar la cadena «open(» encontraba el
    # propio docstring que explica que no se usa `open()` — una prueba que
    # falla por su propia documentación enseña a borrar la documentación.
    arbol = ast.parse(inspect.getsource(core))

    modulos = set()
    llamadas = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            modulos.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module.split(".")[0])
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                llamadas.add(f.id)
            elif isinstance(f, ast.Attribute):
                llamadas.add(f.attr)

    prohibidos = {"os", "io", "pathlib", "requests", "httpx", "aiohttp",
                  "sqlalchemy", "app", "socket", "shutil", "subprocess"}
    assert not (modulos & prohibidos), (
        f"el núcleo importa {sorted(modulos & prohibidos)}: deja de ser puro y "
        f"no puede correr igual en Railway y en un agente local")
    assert "open" not in llamadas, "el núcleo abre archivos"
    assert "execute" not in llamadas, "el núcleo toca la base"


def test_la_config_nace_en_SOMBRA():
    """Guillermo nace sin permiso de escribir. Pasar a asistido es una decisión
    humana — y hoy ni siquiera hay con qué medir el acierto (D-9)."""
    from app.seed_guillermo import PARAMETROS

    d = {k: v for k, v, _ in PARAMETROS}
    assert d["autonomy_level"] == "shadow"
    # ⚠️ Antes acá había `len(PARAMETROS) == 10`, que sólo fijaba un número y
    # había que subirlo cada vez que se agregaba un parámetro. Lo que de verdad
    # importa es que ninguno nazca dando permisos ni mandando correo solo.
    assert len(d) == len(PARAMETROS), "hay dos parámetros con la misma clave"
    assert d["notify_emails"] == "", (
        "los destinatarios son la decisión D-5 de cada propiedad: nacen vacíos")
    assert d["ultimo_aviso_latido"] == "" and d["ultimo_resumen_semanal"] == ""


# ── La ronda y las fuentes (Fase 4) ─────────────────────────────────────────

def test_la_ronda_LATE_AUNQUE_FALLE():
    """⚠️ El latido no dice «salió bien», dice «Guillermo corrió».

    Si sólo latiera al terminar bien, un fallo repetido se vería igual que un
    worker muerto — y el dead-man switch, que existe justamente para
    distinguirlos, no distinguiría nada.
    """
    import inspect

    from app.guillermo import runner

    fuente = inspect.getsource(runner.correr_ronda)
    # El heartbeat se agrega DESPUÉS del try/except, no adentro del camino feliz.
    assert "except Exception" in fuente
    assert fuente.index("except Exception") < fuente.index("GuillermoHeartbeat(")


def test_un_fallo_no_deja_el_batch_colgado_en_running():
    """Quedaría contando como «corriendo» para siempre y el semáforo diría que
    está trabajando."""
    import inspect

    from app.guillermo import runner

    fuente = inspect.getsource(runner.correr_ronda)
    assert '"failed"' in fuente


def test_el_modo_sombra_termina_en_shadowed_y_NO_en_imported():
    import inspect

    from app.guillermo import runner

    fuente = inspect.getsource(runner.correr_ronda)
    assert '"shadowed" if modo == "shadow" else "imported"' in fuente


def test_una_fuente_sin_conectar_REVIENTA_en_vez_de_devolver_vacio():
    """⚠️ Si `MailSource` devolviera lista vacía, la ronda diría «no llegó
    nada» — indistinguible de que Opera no mandó los reportes. Un
    `NotImplementedError` dice la verdad: no está conectada."""
    import pytest as _p

    from app.guillermo.sources import MailSource, OhipSource, Periodo

    p = Periodo(date(2026, 8, 20), date(2026, 8, 20))
    for fuente in (MailSource(), OhipSource()):
        with _p.raises(NotImplementedError):
            fuente.fetch(p)


def test_la_carpeta_espera_a_que_el_archivo_deje_de_crecer():
    """⚠️ Con OneDrive o SFTP el archivo puede estar a medio escribir cuando se
    detecta: entra truncado, parsea igual y da totales más chicos sin que nada
    falle."""
    from app.guillermo.sources import FolderSource

    from app.guillermo.sources import Periodo

    f = FolderSource("/no/existe", estabilidad_seg=30)
    assert f.estabilidad_seg == 30
    # Una carpeta que no existe devuelve vacío, no revienta: el nivel 1 lo
    # reporta como reportes ausentes, que es la verdad del batch.
    assert f.fetch(Periodo(date(2026, 8, 20), date(2026, 8, 20))) == []


def test_las_fuentes_hacen_el_IO_y_el_nucleo_no():
    """El contrato del §5: cambiar de fuente no toca `core.py`."""
    import ast
    import inspect

    from app.guillermo import sources

    arbol = ast.parse(inspect.getsource(sources))
    llamadas = {n.func.id for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "open" in llamadas, "las fuentes son las que tocan el disco"


# ── «Nunca arrancó» no es «trabado» ─────────────────────────────────────────

def test_RECIEN_INSTALADO_NO_SE_PINTA_DE_ROJO():
    """⚠️ **El defecto que esto atrapa**, encontrado al preguntar «¿y se va a
    ver?».

    Guillermo nunca corrió una ronda, así que el dead-man switch lo daba por
    vencido → `stuck` → **el gato salía en rojo, sentado, en todas las
    pantallas, y no se iba.** Y era mentira: no está trabado, nunca arrancó, y
    arrancarlo depende de una decisión del owner (D-1).

    Una alarma que suena desde el día cero se aprende a ignorar — y entonces no
    suena el día que importa.
    """
    e = estado_visible(latido_vencido_=True, motivo_latido="nunca latió",
                       pendientes=0, corriendo=False,
                       nunca_arranco=True, configurado=False)
    assert e.state == "off" and e.color == "gris"
    assert "D-1" in e.mensaje


def test_pero_TAMPOCO_se_pinta_de_verde():
    """El otro lado del error: un worker que jamás corrió no está sano."""
    e = estado_visible(latido_vencido_=True, motivo_latido="nunca latió",
                       pendientes=0, corriendo=False,
                       nunca_arranco=True, configurado=False)
    assert e.color != "verde"
    assert e.state != "idle"


def test_CON_MANIFIESTO_no_haber_corrido_SI_es_una_falla():
    """⚠️ En cuanto alguien configura qué esperar, no haber corrido deja de ser
    «todavía no lo encendieron» y pasa a ser una falla de verdad."""
    e = estado_visible(latido_vencido_=True, motivo_latido="nunca latió",
                       pendientes=0, corriendo=False,
                       nunca_arranco=True, configurado=True)
    assert e.state == "stuck" and e.color == "rojo"


def test_un_guillermo_que_CORRIA_y_se_traba_sigue_en_rojo():
    """La distinción no puede debilitar el dead-man switch: si alguna vez
    latió, dejar de latir es rojo, haya manifiesto o no."""
    e = estado_visible(latido_vencido_=True, motivo_latido="hace 30 h",
                       pendientes=0, corriendo=False,
                       nunca_arranco=False, configurado=False)
    assert e.state == "stuck" and e.color == "rojo"


# ── ¿Qué falta subir? (D-1 del owner, 2026-08-20) ───────────────────────────

def test_el_mes_EN_CURSO_no_se_reclama():
    """⚠️ Todavía no cerró. Reclamarlo sería pedir algo que no existe, y una
    alerta que pide imposibles se aprende a ignorar."""
    from app.guillermo.faltantes import _meses_a_reclamar

    faltan = _meses_a_reclamar(ultimo_mes=7, hoy=date(2026, 8, 20),
                               gracia_dias=0)
    assert 8 not in faltan
    assert faltan == []


def test_un_mensual_no_esta_atrasado_EL_DIA_2():
    """⚠️ El GL se cierra alrededor del día 10. Con diez días de gracia, el 2 de
    agosto todavía no se reclama julio; el 20, sí."""
    from app.guillermo.faltantes import _meses_a_reclamar

    temprano = _meses_a_reclamar(6, date(2026, 8, 2), gracia_dias=10)
    tarde = _meses_a_reclamar(6, date(2026, 8, 20), gracia_dias=10)
    assert 7 not in temprano
    assert 7 in tarde


def test_reclama_TODOS_los_meses_que_faltan_no_solo_el_ultimo():
    """Medido en producción: los actuales y el Balance Sheet tienen dato hasta
    MAYO. Faltan junio **y** julio — decir sólo «falta julio» escondería un mes
    entero."""
    from app.guillermo.faltantes import _meses_a_reclamar

    faltan = _meses_a_reclamar(5, date(2026, 8, 20), gracia_dias=10)
    assert faltan == [6, 7]


def test_sin_ningun_dato_reclama_desde_enero():
    from app.guillermo.faltantes import _meses_a_reclamar

    assert _meses_a_reclamar(None, date(2026, 3, 20), gracia_dias=0) == [1, 2]


def test_en_enero_no_se_reclama_nada_del_ano_nuevo():
    """El año arranca sin meses cerrados propios. Reclamar «diciembre» acá
    sería mirar el año anterior con la regla del actual."""
    from app.guillermo.faltantes import _meses_a_reclamar

    assert _meses_a_reclamar(None, date(2026, 1, 15), gracia_dias=0) == []


def test_NO_SE_SUBIO_y_NO_PUEDO_SABERLO_no_son_lo_mismo():
    """⚠️ **La distinción que sostiene el aviso.** El registro de archivos
    arrancó el 2026-08-20: para los diarios que sólo se pueden medir por ahí,
    la respuesta correcta antes de esa fecha es «no se sabe», no «falta».

    Tratar la ausencia de registro como un atraso inventaría atrasos el primer
    día — y un aviso que nace equivocado no se vuelve a mirar.
    """
    import inspect

    from app.guillermo import faltantes

    fuente = inspect.getsource(faltantes._por_ultima_subida)
    assert "sin registro de subidas" in fuente
    assert "de antes no se sabe" in fuente


def test_una_fecha_de_actualizacion_VACIA_cae_a_cobertura():
    """⚠️ `channel_mix_entries` tiene la columna `actualizado_en` pero **vacía**
    (medido en producción). Un NULL dice «no se registró», no «no se subió»:
    tratarlo como «nunca» inventaría un atraso donde hay datos hasta mayo."""
    import inspect

    from app.guillermo import faltantes

    fuente = inspect.getsource(faltantes._por_actualizacion)
    assert "_por_cobertura" in fuente
    assert "sin fecha de actualización" in fuente


def test_cada_reporte_dice_COMO_se_lo_midio():
    """Las tres formas no valen lo mismo hacia atrás. Mezclarlas sin decir cuál
    se usó convierte el aviso en ruido."""
    from app.guillermo.faltantes import Faltante

    campos = {f for f in Faltante.__dataclass_fields__}
    assert "como_se_mide" in campos


def test_el_manifiesto_es_EL_QUE_DIJO_EL_OWNER():
    """D-1, textual (2026-08-20): «unos XML en Operations y Marketing todos los
    días · el upload de los actuales 1 vez al mes · el balance sheet».

    ⚠️ Nada más. Si alguien agrega un reporte acá, que sea porque el owner lo
    pidió — un manifiesto inventado hace que Guillermo reclame archivos que
    nadie prometió.
    """
    from app.seed_guillermo import MANIFIESTO

    ids = {m[0] for m in MANIFIESTO}
    assert ids == {"actuales_gl", "balance_sheet", "otb_xml", "country_xml",
                   "channel_xml"}
    frec = {m[0]: m[2] for m in MANIFIESTO}
    assert frec["actuales_gl"] == "monthly"
    assert frec["balance_sheet"] == "monthly"
    for diario in ("otb_xml", "country_xml", "channel_xml"):
        assert frec[diario] == "daily"
