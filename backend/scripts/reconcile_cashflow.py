"""Conciliación Cash Flow DIRECTO vs INDIRECTO — el puente auditable.

Corre LOS DOS ENDPOINTS REALES (no los motores pelados: el motor directo sin la
matriz inyectada cae al camino viejo `credit_pct` y reporta otra cosa) contra la
base de un escenario, y emite:

  1. Guardas — condiciones que invalidan la comparación (si fallan, se avisa).
  2. Tabla mensual: Net Change (indirecto) vs Flujo Neto (directo) y su brecha.
  3. Tabla de saldos: Ending Cash vs Saldo Final de Caja.
  4. El puente por concepto: de dónde sale cada pedazo de la brecha.

Uso:
    python -m scripts.reconcile_cashflow --list
    python -m scripts.reconcile_cashflow <scenario_id>
    python -m scripts.reconcile_cashflow <scenario_id> --json salida.json

La conexión sale de DATABASE_URL (asyncpg). Ver scripts/_prodenv.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from scripts._prodenv import usar_produccion

usar_produccion()   # antes de importar cualquier app.* (app.db arma el engine al importarse)

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _fila(rows, key=None, label=None):
    """Busca una fila por `key` (indirecto) o por etiqueta exacta (directo)."""
    for r in rows:
        if key is not None and r.get("key") == key:
            return r
        if label is not None and r.get("label") == label:
            return r
    return None


def _vals(row) -> list[float]:
    if not row:
        return [0.0] * 12
    return [float(v or 0) for v in (row.get("values") or [])][:12] + \
           [0.0] * max(0, 12 - len(row.get("values") or []))


def _suma(rows, pred) -> list[float]:
    out = [0.0] * 12
    for r in rows:
        if pred(r):
            for i, v in enumerate(_vals(r)):
                out[i] += v
    return out


async def listar_escenarios():
    from sqlalchemy import select
    from app.db import get_session
    from app.models.scenario import Scenario
    async with get_session() as s:
        rows = (await s.execute(select(Scenario).order_by(
            Scenario.year, Scenario.type))).scalars().all()
        for sc in rows:
            print(f"{sc.id}  {sc.year}  {sc.type:<9} {sc.version or '':<12} "
                  f"hotel={sc.hotel_id} locked={getattr(sc, 'is_locked', None)}")


async def conciliar(scenario_id: str) -> dict:
    from app.api.cashflow_directo_api import get_cashflow_directo
    from app.api.pl_api import get_cashflow_budget

    ind = await get_cashflow_budget(scenario_id)
    dir_ = await get_cashflow_directo(scenario_id)

    irows = ind.get("rows") or []
    drows = dir_.get("resumen") or []

    # ── Guardas ──────────────────────────────────────────────────────────────
    guardas = []
    params = dir_.get("params") or {}
    if params.get("timing_matrix") is None:
        guardas.append("G1 CRÍTICA: el directo NO recibió matriz de timing → está "
                       "cobrando con el camino viejo `credit_pct`. Comparación inválida.")
    fin = _vals(_fila(drows, label="(informativo) Financiamiento requerido"))
    if any(abs(v) > 0.005 for v in fin):
        meses = ", ".join(MESES[i] for i, v in enumerate(fin) if abs(v) > 0.005)
        guardas.append(f"G2: la caja proyectada queda NEGATIVA en {meses} "
                       f"(máximo ${max(fin):,.2f}). Ya no se inyecta caja "
                       f"automática, así que los saldos siguen siendo comparables.")
    for a in (dir_.get("avisos_timing") or []):
        guardas.append(f"G3: la fila {MESES[a['mes']-1]} de la matriz suma "
                       f"{a['suma']*100:.1f}%, no 100%.")
    oi, od = float(ind.get("opening_cash") or 0), float(dir_.get("opening_cash") or 0)
    if abs(oi - od) > 0.01:
        guardas.append(f"G4 CRÍTICA: caja inicial distinta — indirecto ${oi:,.2f} "
                       f"vs directo ${od:,.2f}")
    wcm = ind.get("wc_model") or {}
    if not wcm.get("enabled"):
        guardas.append("G6 CRÍTICA: el modelo de timing está DESACTIVADO. El "
                       "indirecto lo ignora y el directo lo aplica igual → los dos "
                       "métodos están en universos distintos.")
    if not (ind.get("wc_integrated") or {}).get("prior"):
        guardas.append("G7: el indirecto no encontró escenario del año anterior "
                       "(sin arrastre de cruce de año).")

    # ── Flujo neto y saldos ──────────────────────────────────────────────────
    net_ind = _vals(_fila(irows, key="NET_CHANGE"))
    end_ind = _vals(_fila(irows, key="ENDING_CASH"))
    net_dir = _vals(_fila(drows, label="FLUJO NETO TOTAL"))
    end_dir = _vals(_fila(drows, label="SALDO FINAL DE CAJA"))
    brecha_net = [net_dir[i] - net_ind[i] for i in range(12)]
    brecha_end = [end_dir[i] - end_ind[i] for i in range(12)]

    # ── Bloques comparables por concepto ─────────────────────────────────────
    # INDIRECTO: NOI − CapEx + ΔWC + Other
    noi = _vals(_fila(irows, key="NET_OPERATING_INCOME"))
    capex_i = _vals(_fila(irows, key="SUBTOTAL_CAPEX"))
    wc_i = _vals(_fila(irows, key="SUBTOTAL_WC"))
    other_i = _suma(irows, lambda r: r.get("section") == "Other Cash Movements")
    rev_i = _vals(_fila(irows, key="REVENUE"))

    # DIRECTO: Cobros − Pagos
    cobro_d = _vals(_fila(drows, label="TOTAL ENTRADAS"))
    salidas_d = _vals(_fila(drows, label="TOTAL SALIDAS OPERATIVAS"))
    flujo_op_d = _vals(_fila(drows, label="FLUJO OPERATIVO"))
    prov_d = _vals(_fila(drows, label="Pago a proveedores y planilla (con IVA)"))
    iva_d = _vals(_fila(drows, label="Impuestos a Hacienda (ver tab IVA)"))
    aguin_d = _vals(_fila(drows, label="Pago de aguinaldo"))
    capex_d = _vals(_fila(drows, label="CapEx del presupuesto (del P&L)"))
    cobroop_d = _vals(_fila(drows, label="Cobro a clientes (con IVA)"))
    manual_d = [net_dir[i] - flujo_op_d[i] + capex_d[i] for i in range(12)]

    # Auxiliares del directo para abrir el ingreso
    aux_ing = dir_.get("aux_ingresos") or []
    cobro_caja = _vals(_fila(aux_ing, label="  = COBRO OPERATIVO"))
    ident = dir_.get("identidad") or {}

    puente = {
        "INDIRECTO Net Change": net_ind,
        "  (+) NOI": noi,
        "  (−) CapEx": [-v for v in capex_i],
        "  (+) Δ Working Capital": wc_i,
        "  (+) Other Cash Movements": other_i,
        "DIRECTO Flujo Neto": net_dir,
        "  (+) Total entradas de caja": cobro_d,
        "  (−) Salidas operativas": [-v for v in salidas_d],
        "  (−) CapEx": [-v for v in capex_d],
        "  (−) Secciones manuales": [-v for v in manual_d],
        "BRECHA (directo − indirecto)": brecha_net,
    }

    detalle = {
        "ingreso_devengado_pl": rev_i,
        "cobro_con_iva": cobroop_d,
        "total_entradas": cobro_d,
        "pago_proveedores": prov_d,
        "impuestos_hacienda": iva_d,
        "aguinaldo": aguin_d,
        "capex_directo": capex_d,
        "ident_noi": ident.get("noi") or [0.0] * 12,
        "ident_wc": ident.get("wc") or [0.0] * 12,
        "noi_indirecto": noi,
        "wc_indirecto": wc_i,
        "capex_indirecto": capex_i,
        "other_indirecto": other_i,
    }
    # Partidas WC del indirecto, una por una
    for key, _lbl in [("WC_DEP_RECV", ""), ("WC_DEP_APPL", ""), ("WC_AP", ""),
                      ("WC_AR", ""), ("WC_TAX", ""), ("WC_PROV", ""),
                      ("WC_RENTTAX", ""), ("WC_SERVICE", "")]:
        detalle[f"ind_{key}"] = _vals(_fila(irows, key=key))

    return {
        "scenario_id": scenario_id,
        "year": ind.get("year"),
        "opening_cash": oi,
        "guardas": guardas,
        "net_indirecto": net_ind, "net_directo": net_dir, "brecha_net": brecha_net,
        "end_indirecto": end_ind, "end_directo": end_dir, "brecha_end": brecha_end,
        "puente": puente,
        "detalle": detalle,
        "params_directo": {k: v for k, v in params.items()
                           if k not in ("timing_matrix", "timing_matrix_prev",
                                        "timing_matrix_next", "rev_prev", "rev_next")},
        "params_indirecto": {k: v for k, v in (wcm.get("params") or {}).items()
                             if k not in ("timing_matrix", "aguinaldo_series")},
        "wc_enabled": bool(wcm.get("enabled")),
        "wc_integrated": ind.get("wc_integrated"),
    }


def _tabla(titulo: str, filas: dict[str, list[float]]) -> None:
    print(f"\n{titulo}")
    print("-" * 132)
    print(f"{'':<38}" + "".join(f"{m:>11}" for m in MESES) + f"{'AÑO':>13}")
    print("-" * 132)
    for nombre, vals in filas.items():
        print(f"{nombre:<38}" + "".join(f"{v:>11,.0f}" for v in vals)
              + f"{sum(vals):>13,.0f}")


def imprimir(r: dict) -> None:
    print("=" * 132)
    print(f"CONCILIACIÓN CASH FLOW — escenario {r['scenario_id']} · año {r['year']}")
    print(f"Caja inicial: ${r['opening_cash']:,.2f}   ·   "
          f"Modelo de timing: {'ACTIVO' if r['wc_enabled'] else 'DESACTIVADO'}")
    print("=" * 132)

    if r["guardas"]:
        print("\n### GUARDAS")
        for g in r["guardas"]:
            print(f"  ⚠ {g}")
    else:
        print("\n### GUARDAS: todas OK")

    _tabla("### FLUJO NETO POR MES", {
        "Indirecto (Net Change)": r["net_indirecto"],
        "Directo (Flujo Neto)": r["net_directo"],
        "BRECHA": r["brecha_net"]})

    print("\n### SALDO DE CAJA (acumulado — la BRECHA es lo que hay que llevar a 0)")
    print("-" * 132)
    print(f"{'':<38}" + "".join(f"{m:>11}" for m in MESES))
    print("-" * 132)
    for nombre, vals in (("Indirecto (Ending Cash)", r["end_indirecto"]),
                         ("Directo (Saldo Final)", r["end_directo"]),
                         ("BRECHA", r["brecha_end"])):
        print(f"{nombre:<38}" + "".join(f"{v:>11,.0f}" for v in vals))

    _tabla("### PUENTE POR BLOQUE", r["puente"])
    _tabla("### DETALLE POR CONCEPTO", r["detalle"])

    print("\n### PARÁMETROS — ¿los dos métodos usan el mismo criterio?")
    print("-" * 132)
    pd, pi = r["params_directo"], r["params_indirecto"]
    claves = sorted(set(pd) | set(pi))
    print(f"{'parámetro':<26}{'INDIRECTO':>20}{'DIRECTO':>20}   estado")
    for k in claves:
        vi, vd = pi.get(k, "—"), pd.get(k, "—")
        if isinstance(vi, (list, dict)) or isinstance(vd, (list, dict)):
            continue
        if vi == "—" or vd == "—":
            estado = "SOLO UNO LO USA"
        elif abs(float(vi) - float(vd)) > 1e-9:
            estado = "◆ DISTINTO"
        else:
            estado = "ok"
        print(f"{k:<26}{str(vi):>20}{str(vd):>20}   {estado}")

    print(f"\n>>> BRECHA FINAL DE CAJA (dic): ${r['brecha_end'][11]:,.2f}")
    print(f">>> BRECHA MÁXIMA EN EL AÑO:    ${max(r['brecha_end'], key=abs):,.2f}")


async def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario_id", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.list or not a.scenario_id:
        await listar_escenarios()
        return
    r = await conciliar(a.scenario_id)
    imprimir(r)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
        print(f"\n(json → {a.json})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(_main())
