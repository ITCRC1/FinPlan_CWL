# -*- coding: utf-8 -*-
"""La sesión se corta por INACTIVIDAD, y los dos lados dicen lo mismo.

**Por qué existe (2026-08-21).** Se bajó `TOKEN_TTL` de 7 días a 10 minutos. Un
TTL corto sin renovación saca a la gente a mitad de cargar un checkbook de 12
meses, así que se agregó `/auth/refresh` y un latido en el frontend que renueva
mientras haya actividad.

Eso deja **el mismo número escrito en dos archivos**: `TOKEN_TTL` en Python y
`TTL_MS` en TypeScript. Si se cambia uno solo, no falla nada visible — el front
renueva tarde y empieza a sacar a gente que está escribiendo, de a ratos y sin
error en pantalla. Estas pruebas son el único lugar donde ese desfase avisa.
"""
import io
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
AUTH_PY = RAIZ / "backend" / "app" / "auth.py"
AUTH_API = RAIZ / "backend" / "app" / "api" / "auth_api.py"
GATE_TSX = RAIZ / "frontend" / "components" / "AuthGate.tsx"
API_TS = RAIZ / "frontend" / "lib" / "api.ts"


def _leer(p: pathlib.Path) -> str:
    return io.open(p, encoding="utf-8").read()


def test_token_dura_diez_minutos():
    """El backend emite tokens de 10 minutos."""
    from app.auth import TOKEN_TTL
    assert TOKEN_TTL == 600, (
        f"TOKEN_TTL es {TOKEN_TTL}s y se esperaba 600 (10 min). Si el cambio "
        "es a propósito, actualizá también TTL_MS en AuthGate.tsx.")


def test_los_dos_lados_dicen_el_mismo_numero():
    """`TTL_MS` del front == `TOKEN_TTL` del backend, en milisegundos."""
    from app.auth import TOKEN_TTL

    m = re.search(r"const\s+TTL_MS\s*=\s*([^;]+);", _leer(GATE_TSX))
    assert m, "no se encontró `TTL_MS` en AuthGate.tsx"

    # `10 * 60 * 1000` → 600000, sin ejecutar nada.
    expr = m.group(1).strip()
    assert re.fullmatch(r"[\d\s*]+", expr), f"TTL_MS no es aritmética simple: {expr}"
    ttl_ms = 1
    for parte in expr.split("*"):
        ttl_ms *= int(parte.strip())

    assert ttl_ms == TOKEN_TTL * 1000, (
        f"El front cree que el token dura {ttl_ms/1000:.0f}s y el backend lo "
        f"emite por {TOKEN_TTL}s. Si el front cree que dura MÁS, renueva tarde "
        "y saca a gente que está trabajando.")


def test_renovar_antes_de_que_venza():
    """Se renueva bastante antes del vencimiento, no sobre la hora."""
    txt = _leer(GATE_TSX)
    m = re.search(r"const\s+ENTRE_RENOVACIONES_MS\s*=\s*([^;]+);", txt)
    assert m, "no se encontró `ENTRE_RENOVACIONES_MS`"
    entre = 1
    for parte in m.group(1).split("*"):
        entre *= int(parte.strip())

    from app.auth import TOKEN_TTL
    assert entre < TOKEN_TTL * 1000 / 2, (
        "Entre renovaciones tiene que pasar menos de MEDIA vida del token. Si "
        "no, una renovación puede llegar después de que ya venció.")


def test_existe_el_endpoint_de_refresh():
    """Sin `/auth/refresh` el latido del front no renueva nada."""
    txt = _leer(AUTH_API)
    assert '@router.post("/refresh")' in txt, "falta POST /auth/refresh"


def test_refresh_exige_token_valido():
    """Renovar prolonga una sesión viva; no resucita una vencida."""
    txt = _leer(AUTH_API)
    bloque = txt.split('@router.post("/refresh")', 1)[1].split("@router.", 1)[0]
    assert "get_current_user" in bloque, (
        "El refresh tiene que depender de `get_current_user`. Sin eso, un token "
        "vencido —o inventado— se cambiaría por uno nuevo y la sesión no "
        "caducaría nunca.")


def test_el_refresh_no_arrastra_a_login():
    """Un 401 al renovar es normal y no debe sacar a nadie de la pantalla."""
    txt = _leer(API_TS)
    assert "export async function refrescarSesion" in txt, (
        "falta `refrescarSesion` en lib/api.ts")
    bloque = txt.split("export async function refrescarSesion", 1)[1]
    bloque = bloque.split("\nasync function apiFetch", 1)[0]
    assert "apiFetch" not in bloque, (
        "`refrescarSesion` no puede pasar por `apiFetch`: ese redirige a /login "
        "ante cualquier 401, y al renovar un 401 es un caso esperado.")


def test_el_latido_no_corre_en_login():
    """En `/login` no hay sesión que renovar."""
    txt = _leer(GATE_TSX)
    assert 'pathname?.startsWith("/login")) return;' in txt, (
        "el efecto del latido tiene que salirse temprano en /login")
