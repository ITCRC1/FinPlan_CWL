"use client";
/**
 * Presupuesto desde el pacing.
 *
 * Owner, 2026-09-30: *«ahí voy a hacer el presupuesto»*. Se arma mes a mes con
 * tres supuestos —noches, ADR de habitación y cuánto suma el resto del hotel
 * sobre el Room Revenue— y al guardar queda como la META del año en el pacing.
 * Desde ese momento el resumen, la posición y el cierre se miden contra él.
 *
 * ⚠️ No escribe en ningún escenario del P&L. Es la meta del pacing; si se quiere
 * llevar a un Budget, se copia de acá (botón «Copiar para Excel»).
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { getPacingAnalisis, putPacingConfig, type PacingAnalisis } from "@/lib/api";
import {
  Aviso, Kpi, Tabla, boton, botonPrimario, colorDe, filaTotal, n0, pct, signo, td, tdL, th, usd0, useMeses, usePacing,
} from "./comun";

interface Fila { rn: number; adr: number; otros: number }

const inp = {
  width: 76, padding: "3px 6px", fontSize: 12, textAlign: "right" as const, border: "1px solid var(--border-medium)",
  borderRadius: 4, background: "var(--bg-input)", color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" as const,
};

export function Presupuesto() {
  const t = useTranslations("pacing.presupuesto");
  const tp = useTranslations("pacing");
  const M = useMeses();
  const { datos, filtros, recargar } = usePacing();
  const T = datos!.posicion!.T;
  const [otro, setOtro] = useState<PacingAnalisis | null>(null);
  const [filas, setFilas] = useState<Fila[] | null>(null);
  const [ajuste, setAjuste] = useState({ adr: 0, rn: 0 });
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // Rooms y Total juntos: el presupuesto necesita los dos.
  const otroKind = datos!.kind === "total" ? "rooms" : "total";
  useEffect(() => {
    let vivo = true;
    getPacingAnalisis({ ...filtros, year: T, kind: otroKind }).then(r => { if (vivo) setOtro(r); }).catch(() => {});
    return () => { vivo = false; };
  }, [filtros, T, otroKind]);
  const R = (datos!.kind === "rooms" ? datos : otro)?.posicion;
  const Tt = (datos!.kind === "total" ? datos : otro)?.posicion;
  const meta = datos!.config.meta.years[String(T)];

  const desdeProyeccion = (): Fila[] | null => {
    if (!R) return null;
    return R.rows.map((r, i) => {
      const tot = Tt?.rows[i]?.proj_rev ?? r.proj_rev;
      return { rn: Math.round(r.proj), adr: r.proj ? Math.round(r.proj_rev / r.proj) : 0,
               otros: r.proj_rev ? Math.max(0, tot / r.proj_rev - 1) : 0 };
    });
  };
  const desdeAnterior = (): Fila[] | null => {
    if (!R) return null;
    return R.rows.map((r, i) => {
      const tot = Tt?.rows[i]?.ly_rev ?? r.ly_rev;
      return { rn: Math.round(r.ly_rn), adr: r.ly_rn ? Math.round(r.ly_rev / r.ly_rn) : 0,
               otros: r.ly_rev ? Math.max(0, tot / r.ly_rev - 1) : 0 };
    });
  };
  const desdeMeta = (): Fila[] | null => {
    if (!meta?.rn || !meta.rooms || !meta.total) return null;
    return meta.rn.map((rn, i) => ({
      rn: Math.round(rn || 0), adr: rn ? Math.round((meta.rooms![i] || 0) / rn) : 0,
      otros: meta.rooms![i] ? Math.max(0, (meta.total![i] || 0) / meta.rooms![i] - 1) : 0,
    }));
  };

  useEffect(() => {
    if (filas || !R) return;
    setFilas(desdeMeta() ?? desdeProyeccion());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [R]);

  const calc = useMemo(() => (filas ?? []).map((f, i) => {
    const cap = R?.rows[i]?.cap ?? 0;
    const rooms = f.rn * f.adr, total = rooms * (1 + f.otros);
    return { ...f, cap, rooms, total, occ: cap ? f.rn / cap : 0 };
  }), [filas, R]);
  const sum = (k: "rn" | "rooms" | "total" | "cap") => calc.reduce((a, c) => a + c[k], 0);

  if (!R || !filas) return <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tp("cargando")}</div>;

  const set = (i: number, k: keyof Fila, v: number) =>
    setFilas(fs => fs!.map((f, j) => (j === i ? { ...f, [k]: isNaN(v) ? 0 : v } : f)));
  const aplicarAjuste = () => setFilas(fs => fs!.map((f, i) => ({
    ...f,
    adr: Math.round(f.adr * (1 + ajuste.adr / 100)),
    rn: R.rows[i].cerrado ? f.rn : Math.min(R.rows[i].cap, Math.round(f.rn * (1 + ajuste.rn / 100))),
  })));

  const guardar = async () => {
    setGuardando(true); setMsg(null);
    try {
      const years = { ...datos!.config.meta.years };
      years[String(T)] = {
        rn: calc.map(c => c.rn), avail: calc.map(c => c.cap),
        rooms: calc.map(c => Math.round(c.rooms * 100) / 100), total: calc.map(c => Math.round(c.total * 100) / 100),
        source: t("fuente", { fecha: new Date().toISOString().slice(0, 10) }), actualMonths: 0,
      };
      await putPacingConfig({ meta: { years } });
      setMsg(t("guardado")); recargar();
    } catch (e) { setMsg(String((e as Error)?.message ?? e)); }
    finally { setGuardando(false); }
  };

  const copiar = async () => {
    const enc = [t("c.mes"), "RN", "Occ", "ADR", "Rooms", t("c.otros"), "Total"].join("\t");
    const lineas = calc.map((c, i) => [M[i], c.rn, (c.occ * 100).toFixed(1) + "%", c.adr, c.rooms.toFixed(2),
      (c.otros * 100).toFixed(1) + "%", c.total.toFixed(2)].join("\t"));
    try { await navigator.clipboard.writeText([enc, ...lineas].join("\n")); setMsg(t("copiado")); }
    catch { setMsg(t("noCopiado")); }
  };

  const lyRooms = R.tot.ly_rev, lyTotal = Tt?.tot.ly_rev ?? 0, prTotal = Tt?.tot.proj_rev ?? 0;
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Aviso>{t("nota", { anio: T, ly: T - 1 })}</Aviso>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
        <Kpi titulo={t("kRn")} valor={n0(sum("rn"))} sub={t("kOcc", { occ: pct(sum("cap") ? sum("rn") / sum("cap") : 0, 1) })} />
        <Kpi titulo={t("kRooms")} valor={usd0(sum("rooms"))} sub={`ADR ${usd0(sum("rn") ? sum("rooms") / sum("rn") : 0)}`} />
        <Kpi titulo={t("kTotal")} valor={usd0(sum("total"))} />
        <Kpi titulo={t("kVsLy", { ly: T - 1 })} valor={lyTotal ? signo(sum("total") / lyTotal - 1, x => pct(x, 1)) : "—"}
             color={colorDe(sum("total") - lyTotal)} sub={t("kVsLySub", { total: usd0(lyTotal), rooms: usd0(lyRooms) })} />
        <Kpi titulo={t("kVsProj")} valor={signo(sum("total") - prTotal, usd0)} color={colorDe(sum("total") - prTotal)}
             sub={t("kVsProjSub", { total: usd0(prTotal) })} />
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button style={boton} onClick={() => setFilas(desdeProyeccion())}>{t("desdeProyeccion")}</button>
        <button style={boton} onClick={() => setFilas(desdeAnterior())}>{t("desdeAnterior", { ly: T - 1 })}</button>
        {meta && <button style={boton} onClick={() => setFilas(desdeMeta())}>{t("desdeGuardado")}</button>}
        <span style={{ fontSize: 12, marginLeft: 8 }}>{t("ajusteAdr")}</span>
        <input style={{ ...inp, width: 56 }} type="number" value={ajuste.adr} onChange={e => setAjuste(a => ({ ...a, adr: Number(e.target.value) }))} />
        <span style={{ fontSize: 12 }}>{t("ajusteRn")}</span>
        <input style={{ ...inp, width: 56 }} type="number" value={ajuste.rn} onChange={e => setAjuste(a => ({ ...a, rn: Number(e.target.value) }))} />
        <button style={boton} onClick={aplicarAjuste}>{t("aplicar")}</button>
        <span style={{ flex: 1 }} />
        <button style={boton} onClick={copiar}>{t("copiar")}</button>
        <button style={botonPrimario} disabled={guardando} onClick={guardar}>{guardando ? t("guardando") : t("guardar", { anio: T })}</button>
      </div>
      {msg && <Aviso>{msg}</Aviso>}
      {meta?.source && <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("actual", { fuente: String(meta.source) })}</div>}

      <Tabla minWidth={1400}>
        <thead><tr>
          {["mes", "cap", "lyRn", "lyRooms", "lyTotal", "otb", "proj", "projTotal", "rn", "occ", "adr", "rooms", "otros", "total", "vsLy"].map(c =>
            <th key={c} style={c === "mes" ? { ...th, textAlign: "left" } : ["rn", "adr", "otros"].includes(c)
              ? { ...th, color: "var(--brand)" } : th}>{t(`c.${c}`)}</th>)}
        </tr></thead>
        <tbody>
          {calc.map((c, i) => {
            const r = R.rows[i], lyT = Tt?.rows[i]?.ly_rev ?? 0;
            return (
              <tr key={i}>
                <td style={tdL}>{M[i]}{r.cerrado ? " ✓" : ""}</td>
                <td style={td}>{n0(c.cap)}</td>
                <td style={td}>{n0(r.ly_rn)}{r.ly_alcance ? " *" : ""}</td>
                <td style={td}>{usd0(r.ly_rev)}</td><td style={td}>{usd0(lyT)}</td>
                <td style={td}>{n0(r.otb_rn)}</td><td style={td}>{n0(r.proj)}</td>
                <td style={td}>{usd0(Tt?.rows[i]?.proj_rev)}</td>
                <td style={td}><input style={inp} type="number" value={c.rn} onChange={e => set(i, "rn", Number(e.target.value))} /></td>
                <td style={{ ...td, color: c.occ > 1 ? "var(--negative)" : undefined }}>{pct(c.occ, 1)}</td>
                <td style={td}><input style={inp} type="number" value={c.adr} onChange={e => set(i, "adr", Number(e.target.value))} /></td>
                <td style={td}>{usd0(c.rooms)}</td>
                <td style={td}><input style={{ ...inp, width: 60 }} type="number" step="0.1" value={Math.round(c.otros * 1000) / 10}
                                      onChange={e => set(i, "otros", Number(e.target.value) / 100)} />%</td>
                <td style={td}><b>{usd0(c.total)}</b></td>
                <td style={{ ...td, color: colorDe(c.total - lyT) }}>{lyT ? signo(c.total / lyT - 1, x => pct(x, 1)) : "—"}</td>
              </tr>
            );
          })}
          <tr style={filaTotal}>
            <td style={tdL}>{tp("col.total")}</td><td style={td}>{n0(sum("cap"))}</td>
            <td style={td}>{n0(R.tot.ly_rn)}</td><td style={td}>{usd0(lyRooms)}</td><td style={td}>{usd0(lyTotal)}</td>
            <td style={td}>{n0(R.tot.otb_rn)}</td><td style={td}>{n0(R.tot.proj)}</td><td style={td}>{usd0(prTotal)}</td>
            <td style={td}>{n0(sum("rn"))}</td><td style={td}>{pct(sum("cap") ? sum("rn") / sum("cap") : 0, 1)}</td>
            <td style={td}>{usd0(sum("rn") ? sum("rooms") / sum("rn") : 0)}</td><td style={td}>{usd0(sum("rooms"))}</td>
            <td style={td}>{pct(sum("rooms") ? sum("total") / sum("rooms") - 1 : 0, 1)}</td><td style={td}>{usd0(sum("total"))}</td>
            <td style={{ ...td, color: colorDe(sum("total") - lyTotal) }}>{lyTotal ? signo(sum("total") / lyTotal - 1, x => pct(x, 1)) : "—"}</td>
          </tr>
        </tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("leyenda")}</div>
    </div>
  );
}
