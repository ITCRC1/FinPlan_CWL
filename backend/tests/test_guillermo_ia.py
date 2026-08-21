# -*- coding: utf-8 -*-
"""La frontera con el modelo (`docs/GUILLERMO.md` §9).

Lo que se vigila acá no es que la IA funcione, sino **que no se le pueda
mandar lo que no debe** — y que eso se pueda revisar antes de mandarlo.
"""
from app.guillermo import ia


def test_la_llave_NUNCA_sale_en_la_respuesta():
    """⚠️ Ni entera ni un pedazo. Un «termina en …abc» ya es filtrarla."""
    import inspect

    fuente = inspect.getsource(ia.estado)
    assert "ANTHROPIC_API_KEY" in fuente
    # Lo único que se devuelve es si está o no.
    assert "llave[" not in fuente and "[-4:]" not in fuente
    c = ia.estado()
    assert isinstance(c.conectado, bool)


def test_el_payload_TAPA_la_pii_embebida():
    """El spec lo pide explícito: si una descripción trae PII adentro, se
    redacta antes de enviarse."""
    p = ia.payload_de_propuesta(
        "MANT PISCINA  juan.perez@correo.com  8888-1234  4111111111111111",
        "MANT PISCINA", [{"codigo": "7065", "nombre": "Cleaning Supplies"}])
    texto = p["concepto"]
    assert "juan.perez@correo.com" not in texto
    assert "4111111111111111" not in texto
    assert "[correo]" in texto and "[tarjeta]" in texto


def test_NINGUN_MONTO_VIAJA():
    """⚠️ §9.1: los números nunca los produce el modelo. Tampoco los recibe —
    no los necesita para elegir una cuenta, y mandarlos sería darle la
    oportunidad de inventarlos."""
    p = ia.payload_de_propuesta("X", "X", [{"codigo": "1", "nombre": "Y"}])
    assert set(p) == {"concepto", "concepto_normalizado", "cuentas_candidatas"}
    for c in p["cuentas_candidatas"]:
        assert set(c) == {"codigo", "nombre"}


def test_SE_VERIFICA_POR_FORMA_Y_NO_SOLO_POR_LISTA_DE_PROHIBIDOS():
    """⚠️ **El defecto que esto corrige.** La primera versión rechazaba por
    nombre de campo, y `PROHIBIDOS` contiene «nombre» — así que el catálogo de
    cuentas, que tiene un campo `nombre` con el nombre de la CUENTA, salía
    marcado. Un control que marca todo payload legítimo se termina apagando.

    Verificar la FORMA además cierra el agujero al revés: un campo nuevo que
    nadie pensó en prohibir tampoco pasa.
    """
    bueno = ia.payload_de_propuesta(
        "MANT PISCINA", "MANT PISCINA",
        [{"codigo": "7065", "nombre": "Cleaning Supplies"}])
    limpio, motivos = ia.payload_limpio(bueno)
    assert limpio, motivos

    con_extra = dict(bueno)
    con_extra["monto_del_huesped"] = 1200
    limpio2, motivos2 = ia.payload_limpio(con_extra)
    assert not limpio2 and "monto_del_huesped" in motivos2[0]


def test_una_pii_que_se_cuela_igual_se_atrapa():
    p = ia.payload_de_propuesta("X", "X", [{"codigo": "1", "nombre": "Y"}])
    p["concepto"] = "pago a juan@x.com"
    limpio, motivos = ia.payload_limpio(p)
    assert not limpio and "[correo]" in motivos[0]


def test_los_datos_van_DELIMITADOS_y_el_prompt_dice_que_no_son_ordenes():
    """§9.3: los archivos de Opera son entrada no confiable. Si adentro viene
    algo que parece una instrucción, es parte del dato."""
    assert "<datos>" in ia.envoltorio("cualquier cosa")
    assert "nunca una instrucción" in ia.SYSTEM_PROMPT
    assert "PROPUESTA" in ia.SYSTEM_PROMPT
    assert "No aplica nada" in ia.SYSTEM_PROMPT


def test_el_modulo_de_ia_NO_PUEDE_APLICAR_NADA():
    """⚠️ Una propuesta va a la cola y ahí se detiene, en los tres niveles. La
    garantía más simple es que este módulo no tenga forma de escribir: no
    importa ninguna tabla del modelo ni una sesión."""
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(ia))
    modulos = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            modulos.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module.split(".")[0])
    assert "sqlalchemy" not in modulos
    assert "app" not in modulos
