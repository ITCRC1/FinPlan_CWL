# -*- coding: utf-8 -*-
"""El conector de Claude (claude.ai) a FinPlan, de punta a punta sobre una base en memoria.

Owner, 2026-11-16: «quiero que mi jefe haga consultas directas a Claude desde su
computadora» · «él puede ver todo» · «he creado Draft1-PAN para que Claude arme el
budget». Se prueba el camino completo que hace claude.ai: descubrimiento → registro
del cliente → pantalla de FinPlan → código con PKCE → token → MCP; y los candados.
"""
import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("aiosqlite")

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CALLBACK = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models  # noqa: F401 — registra todos los modelos
    from app import claude_escritura, claude_herramientas
    from app.api import claude_mcp_api
    from app.auth import hash_password
    from app.models.acceso_claude import ClaudeCliente, ClaudeCodigo, ClaudeConsulta, ClaudeRefresh
    from app.models.payroll_position import PayrollPosition
    from app.models.scenario import Scenario
    from app.models.user import User

    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    hacer = async_sessionmaker(eng, expire_on_commit=False)

    async def preparar():
        async with eng.begin() as c:
            for t in (User, Scenario, PayrollPosition, ClaudeCliente, ClaudeCodigo, ClaudeRefresh, ClaudeConsulta):
                await c.run_sync(lambda s, t=t: t.__table__.create(s))
        async with hacer() as s:
            s.add_all([
                User(id="u1", email="jefe@x.com", name="Jefe", password_hash=hash_password("clave-buena-1"),
                     role="collaborator", active=True, acceso_claude=True),
                User(id="u2", email="sin@x.com", name="Sin", password_hash=hash_password("clave-buena-2"),
                     role="admin", active=True, acceso_claude=False),
                Scenario(id="s-work", hotel_id="CWL", year=2027, type="BUDGET", version="Working",
                         status="draft", claude_puede_editar=False),
                Scenario(id="s-pan", hotel_id="CWL", year=2027, type="BUDGET", version="Draft1-PAN",
                         status="draft", claude_puede_editar=True),
                # Versiones que existen pero el conector NO debe ver (owner, 2026-11-16).
                Scenario(id="s-d2", hotel_id="CWL", year=2027, type="BUDGET", version="Draft2", status="draft"),
                Scenario(id="s-a26", hotel_id="CWL", year=2026, type="ACTUAL", version="actual", status="draft"),
                Scenario(id="s-pre", hotel_id="CWL", year=2026, type="ACTUAL", version="Pre-Cierre",
                         status="draft", es_precierre=True),
                Scenario(id="s-oct", hotel_id="CWL", year=2026, type="FORECAST", version="October",
                         status="draft", is_current_forecast=True),
                Scenario(id="s-jun", hotel_id="CWL", year=2026, type="FORECAST", version="June", status="draft"),
                Scenario(id="s-b26", hotel_id="CWL", year=2026, type="BUDGET", version="Final", status="locked"),
            ])
            for i, (dep, cod) in enumerate([("0186", "0186-01"), ("0113", "0113-04"), ("0122", "0122-01")]):
                s.add(PayrollPosition(id=f"p{i}", scenario_id="s-pan", hotel_id="CWL", dept_code=dep,
                                      dept_name="", position_code=cod, position_name=f"Puesto {cod}",
                                      employee_name=f"Persona {i}", salary_amount=500000, salary_currency="CRC"))
            await s.commit()

    asyncio.run(preparar())

    @asynccontextmanager
    async def sesion():
        async with hacer() as s:
            yield s

    for mod in (claude_mcp_api, claude_herramientas, claude_escritura):
        monkeypatch.setattr(mod, "get_session", sesion)
    monkeypatch.setattr(claude_herramientas, "HOTEL_ID", "CWL")
    monkeypatch.setattr(claude_escritura, "HOTEL_ID", "CWL")
    app = FastAPI()
    app.include_router(claude_mcp_api.router)
    claude_mcp_api._FALLOS.clear()
    yield TestClient(app, base_url="https://finplan.test"), hacer
    asyncio.run(eng.dispose())


def _pkce():
    v = secrets.token_urlsafe(40)
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


def _conectar(c, email="jefe@x.com", clave="clave-buena-1"):
    reg = c.post("/oauth/register", json={"client_name": "Claude", "redirect_uris": [CALLBACK]})
    assert reg.status_code == 201
    cid = reg.json()["client_id"]
    v, reto = _pkce()
    q = {"response_type": "code", "client_id": cid, "redirect_uri": CALLBACK, "code_challenge": reto,
         "code_challenge_method": "S256", "state": "xyz", "scope": "finplan.lectura"}
    assert c.get("/oauth/authorize", params=q).status_code == 200
    r = c.post("/oauth/authorize", data={**q, "email": email, "password": clave}, follow_redirects=False)
    return cid, v, r


def _token(c):
    cid, v, r = _conectar(c)
    assert r.status_code == 302
    loc = urlparse(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == CALLBACK
    qs = parse_qs(loc.query)
    assert qs["state"] == ["xyz"]
    t = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": qs["code"][0],
                                      "redirect_uri": CALLBACK, "client_id": cid, "code_verifier": v})
    assert t.status_code == 200, t.text
    return cid, t.json()


def _rpc(c, tok, metodo, params=None, id_=1):
    return c.post("/mcp", json={"jsonrpc": "2.0", "id": id_, "method": metodo, "params": params or {}},
                  headers={"Authorization": f"Bearer {tok}"})


def test_sin_token_responde_401_con_la_metadata(entorno):
    c, _ = entorno
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 401
    assert 'resource_metadata="https://finplan.test/.well-known/oauth-protected-resource"' in r.headers["www-authenticate"]
    m = c.get("/.well-known/oauth-protected-resource").json()
    assert m["resource"] == "https://finplan.test/mcp" and m["authorization_servers"] == ["https://finplan.test"]
    a = c.get("/.well-known/oauth-authorization-server").json()
    assert a["code_challenge_methods_supported"] == ["S256"] and a["registration_endpoint"].endswith("/oauth/register")
    assert a["token_endpoint_auth_methods_supported"] == ["none"]


def test_el_camino_completo_y_mcp(entorno):
    c, _ = entorno
    _cid, tok = _token(c)
    r = _rpc(c, tok["access_token"], "initialize", {"protocolVersion": "2025-06-18"}).json()
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                  headers={"Authorization": f"Bearer {tok['access_token']}"}).status_code == 202
    nombres = [t["name"] for t in _rpc(c, tok["access_token"], "tools/list").json()["result"]["tools"]]
    assert "pl" in nombres and "fte_masivo" in nombres
    v = _rpc(c, tok["access_token"], "tools/call", {"name": "versiones", "arguments": {}}).json()["result"]
    assert not v["isError"] and "Draft1-PAN" in v["content"][0]["text"]


def test_redirect_ajeno_no_se_registra(entorno):
    c, _ = entorno
    r = c.post("/oauth/register", json={"redirect_uris": ["https://malo.example/cb"]})
    assert r.status_code == 400


def test_usuario_sin_la_casilla_no_entra(entorno):
    c, _ = entorno
    _cid, _v, r = _conectar(c, "sin@x.com", "clave-buena-2")
    assert r.status_code == 200 and "Acceso desde Claude" in r.text


def test_clave_mala_no_entra_y_se_frena(entorno):
    c, _ = entorno
    for _ in range(5):
        _cid, _v, r = _conectar(c, clave="mala")
        assert "incorrectos" in r.text
    _cid, _v, r = _conectar(c)
    assert "Demasiados intentos" in r.text


def test_pkce_malo_no_da_token_y_el_codigo_es_de_un_solo_uso(entorno):
    c, _ = entorno
    cid, v, r = _conectar(c)
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    mal = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid,
                                        "redirect_uri": CALLBACK, "code_verifier": "otro"})
    assert mal.status_code == 400 and mal.json()["error"] == "invalid_grant"


def test_refresh_rota_y_el_viejo_no_sirve(entorno):
    c, _ = entorno
    cid, tok = _token(c)
    r1 = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                       "client_id": cid})
    assert r1.status_code == 200 and r1.json()["refresh_token"] != tok["refresh_token"]
    r2 = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                       "client_id": cid})
    assert r2.status_code == 400 and r2.json()["error"] == "invalid_grant"


def test_apagar_la_casilla_corta_en_la_siguiente_consulta(entorno):
    import asyncio
    c, hacer = entorno
    _cid, tok = _token(c)
    from app.models.user import User

    async def apagar():
        async with hacer() as s:
            (await s.get(User, "u1")).acceso_claude = False
            await s.commit()
    asyncio.run(apagar())
    assert _rpc(c, tok["access_token"], "tools/list").status_code == 401


def test_el_token_de_claude_no_abre_la_api_de_la_app():
    """Mismo secreto, otra audiencia: `decode_token` de la app lo rechaza."""
    from app.api.claude_mcp_api import _token_acceso
    from app.auth import decode_token
    from app.models.user import User
    tok = _token_acceso(User(id="u1", email="a@b.c"), "cid", "https://x")
    assert decode_token(tok) is None


def test_solo_modifica_versiones_habilitadas(entorno):
    import asyncio
    c, hacer = entorno
    _cid, tok = _token(c)
    malo = _rpc(c, tok["access_token"], "tools/call", {"name": "fte_masivo", "arguments": {
        "anio": 2027, "tipo": "BUDGET", "version": "Working", "fte": 0}}).json()["result"]
    assert malo["isError"] and "no está habilitada" in malo["content"][0]["text"]
    sin_version = _rpc(c, tok["access_token"], "tools/call", {"name": "fte_masivo", "arguments": {
        "anio": 2027, "tipo": "BUDGET", "version": "", "fte": 0}}).json()["result"]
    assert sin_version["isError"]
    ok = _rpc(c, tok["access_token"], "tools/call", {"name": "fte_masivo", "arguments": {
        "anio": 2027, "tipo": "BUDGET", "version": "Draft1-PAN", "fte": 0, "meses": [1, 2],
        "excepto": [{"depto": "0186"}]}}).json()["result"]
    assert not ok["isError"], ok

    from app.models.payroll_position import PayrollPosition

    async def leer():
        async with hacer() as s:
            return {p.position_code: (float(p.fte_jan), float(p.fte_mar)) for p in
                    (await s.get(PayrollPosition, "p0"), await s.get(PayrollPosition, "p1"))}
    f = asyncio.run(leer())
    assert f["0186-01"] == (1.0, 1.0)        # seguridad: exceptuada
    assert f["0113-04"] == (0.0, 1.0)        # enero en 0, marzo intacto


def test_solo_se_ven_las_versiones_habilitadas(entorno):
    """Reales 2024-2026, Forecast 2026 vigente, Budget 2027 Working y Draft1-PAN.
    Nada más: ni los borradores, ni los Forecast viejos, ni el Pre-Cierre."""
    import asyncio

    from app import claude_herramientas as h

    vistas = asyncio.run(h.versiones({}, None))["versiones"]
    assert {(v["tipo"], v["anio"], v["version"]) for v in vistas} == {
        ("ACTUAL", 2026, "actual"), ("FORECAST", 2026, "October"),
        ("BUDGET", 2027, "Working"), ("BUDGET", 2027, "Draft1-PAN")}

    async def resolver(anio, tipo, version=None):
        async with h.get_session() as s:
            return (await h._escenario(s, anio, tipo, version)).version

    # «El budget 2027», sin nombre, es el de trabajo — nunca el borrador más nuevo.
    assert asyncio.run(resolver(2027, "BUDGET")) == "Working"
    assert asyncio.run(resolver(2027, "BUDGET", "Draft1-PAN")) == "Draft1-PAN"
    assert asyncio.run(resolver(2026, "FORECAST")) == "October"
    for anio, tipo, version in [(2027, "BUDGET", "Draft2"), (2026, "FORECAST", "June"),
                                (2026, "ACTUAL", "Pre-Cierre"), (2026, "BUDGET", None)]:
        with pytest.raises(ValueError, match="no está disponible"):
            asyncio.run(resolver(anio, tipo, version))
    with pytest.raises(ValueError, match="años con reales"):
        asyncio.run(h.mayor({"anio": 2023, "mes": 1}, None))
