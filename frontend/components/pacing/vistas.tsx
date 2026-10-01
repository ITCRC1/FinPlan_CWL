"use client";
/** Las vistas de análisis del PACING. Sólo dibujan lo que manda el motor. */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getPacingFlagged, type PacingAlerta, type PacingFlagged } from "@/lib/api";
import {
  Aviso, Estado, Kpi, Tabla, card, colorDe, filaTotal, n0, pct, select, signo, td, tdL, th, tooltipStyle, usd0,
  useMeses, usePacing,
} from "./comun";
import { AnalisisTecnico } from "./tecnico";

const eje = { fontSize: 11, fill: "var(--text-secondary)" };
const kfmt = (v: number) => (Math.abs(v) >= 1000 ? `${Math.round(v / 1000)}k` : String(Math.round(v)));

// ───────────────────────────── Resumen ─────────────────────────────
export function Resumen() {
  const t = useTranslations("pacing");
  const M = useMeses();
  const { datos } = usePacing();
  const P = datos!.posicion!;
  const T = P.tot;
  const meta = datos!.config.meta.years[String(P.T)];
  const metaRn = meta?.rn?.reduce((a, b) => a + (b || 0), 0) ?? 0;
  const metaRev = (datos!.kind === "rooms" ? meta?.rooms : meta?.total)?.reduce((a, b) => a + (b || 0), 0) ?? 0;
  const alertas = datos!.alertas ?? [];
  const serie = P.rows.map((r, i) => ({ mes: M[i], otb: r.otb_rn, stly: r.st_rn ?? 0, ly: r.ly_rn, proj: Math.round(r.proj) }));
  const lyAnio = P.T - 1;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
        <Kpi titulo={t("kpi.otb", { anio: P.T })} valor={`${n0(T.otb_rn)} RN`}
             sub={t("kpi.otbSub", { occ: pct(T.occ, 1), adr: usd0(T.adr), rev: usd0(T.otb_rev) })} />
        <Kpi titulo={t("kpi.stly")} valor={T.st_rn ? `${n0(T.st_rn)} RN` : "—"}
             sub={T.pace != null ? t("kpi.pace", { pace: pct(T.pace) }) : t("kpi.sinStly")}
             color={T.pace == null ? undefined : T.pace >= 1 ? "var(--positive)" : "var(--negative)"} />
        <Kpi titulo={t("kpi.proyeccion")} valor={`${n0(T.proj)} RN`}
             sub={t("kpi.proySub", { occ: pct(T.proj_occ, 1), rev: usd0(T.proj_rev) })} />
        <Kpi titulo={t("kpi.vsAnterior", { anio: lyAnio })} valor={signo(T.proj - T.ly_rn, n0) + " RN"}
             color={colorDe(T.proj - T.ly_rn)}
             sub={t("kpi.vsAnteriorSub", { rn: n0(T.ly_rn), rev: usd0(T.ly_rev),
                                            d: T.ly_rev ? signo(T.proj_rev / T.ly_rev - 1, x => pct(x, 1)) : "—" })} />
        <Kpi titulo={t("kpi.asegurado")} valor={pct(T.asegurado)} sub={t("kpi.aseguradoSub", { falta: n0(T.falta) })} />
        <Kpi titulo={t("kpi.meta", { anio: P.T })} valor={meta ? signo(T.proj - metaRn, n0) + " RN" : "—"}
             color={meta ? colorDe(T.proj - metaRn) : undefined}
             sub={meta ? t("kpi.metaSub", { rn: n0(metaRn), rev: usd0(metaRev), d: usd0(T.proj_rev - metaRev) })
                       : <Link href="/pacing/presupuesto">{t("kpi.sinMeta")}</Link>} />
      </div>

      <div style={card}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>{t("resumen.grafico", { anio: P.T, ly: lyAnio })}</div>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={serie}>
            <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
            <XAxis dataKey="mes" tick={eje} /><YAxis tick={eje} />
            <Tooltip {...tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="ly" name={t("series.ly", { anio: lyAnio })} fill="var(--border-medium)" />
            <Bar dataKey="stly" name={t("series.stly")} fill="#C9A227" />
            <Bar dataKey="otb" name={t("series.otb")} fill="var(--brand)" />
            <Line dataKey="proj" name={t("series.proj")} stroke="var(--positive)" strokeWidth={2} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12 }}>
        <div style={card}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{t("resumen.lectura")}</div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.7 }}>
            <li>{t("resumen.l1", { corte: P.corte, st: P.st?.as_of ?? "—", src: t(`fuentes.${P.st?.src ?? "auto"}`) })}</li>
            <li>{t("resumen.l2", { base: n0(T.base_pace), bloq: n0(T.bloqueos) })}</li>
            <li>{t("resumen.l3", { esc: t(`escenarios.${P.escenario}`) })}</li>
            {datos!.en_sitio && datos!.kind === "total" && (
              <li>{t("resumen.l4", { pct: pct(datos!.en_sitio.pct), monto: usd0(T.en_sitio ?? 0) })}</li>
            )}
          </ul>
        </div>
        <div style={card}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{t("resumen.alertas")}</div>
          {(["corregir", "revisar", "info"] as const).map(n => (
            <div key={n} style={{ fontSize: 12, display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
              <span>{t(`nivel.${n}`)}</span><b>{alertas.filter(a => a.nivel === n).length}</b>
            </div>
          ))}
          <Link href="/pacing/alertas" style={{ fontSize: 12 }}>{t("resumen.verAlertas")}</Link>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────── Posición mensual ─────────────────────────────
export function Posicion() {
  const t = useTranslations("pacing");
  const M = useMeses();
  const { datos } = usePacing();
  const P = datos!.posicion!;
  const cols = ["cap", "otbRn", "occ", "adr", "otbRev", "stlyRn", "pace", "bloqueos", "lyRn", "pickup", "proj", "projOcc", "projRev", "estado"] as const;
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <Aviso>{t("posicion.nota", { anio: P.T, corte: P.corte })}</Aviso>
      <Tabla minWidth={1300}>
        <thead><tr>
          <th style={{ ...th, textAlign: "left" }}>{t("col.mes")}</th>
          {cols.map(c => <th key={c} style={th}>{t(`col.${c}`)}</th>)}
        </tr></thead>
        <tbody>
          {P.rows.map((r, i) => (
            <tr key={i} style={r.cerrado ? { color: "var(--text-secondary)" } : undefined}>
              <td style={tdL}>{M[i]} {P.T}</td>
              <td style={td}>{n0(r.cap)}</td>
              <td style={td}><b>{n0(r.otb_rn)}</b></td>
              <td style={td}>{pct(r.occ, 1)}</td>
              <td style={td}>{usd0(r.adr)}</td>
              <td style={td}>{usd0(r.otb_rev)}</td>
              <td style={td}>{n0(r.st_rn)}</td>
              <td style={{ ...td, color: r.pace == null ? undefined : colorDe(r.pace - 1) }}>{pct(r.pace)}</td>
              <td style={td}>{n0(r.bloqueos)}</td>
              <td style={td} title={r.ly_alcance ? t("posicion.alcance") : undefined}>
                {n0(r.ly_rn)}{r.ly_alcance ? " *" : r.ly_de_reservas ? " †" : ""}
              </td>
              <td style={td}>{r.cerrado ? "—" : n0(r.proj - r.otb_rn)}</td>
              <td style={td}><b>{n0(r.proj)}</b></td>
              <td style={td}>{pct(r.proj_occ, 1)}</td>
              <td style={td}><b>{usd0(r.proj_rev)}</b></td>
              <td style={td}><Estado e={r.estado} cerrado={r.cerrado} /></td>
            </tr>
          ))}
          <tr style={filaTotal}>
            <td style={tdL}>{t("col.total")}</td>
            <td style={td}>{n0(P.tot.cap)}</td><td style={td}>{n0(P.tot.otb_rn)}</td><td style={td}>{pct(P.tot.occ, 1)}</td>
            <td style={td}>{usd0(P.tot.adr)}</td><td style={td}>{usd0(P.tot.otb_rev)}</td><td style={td}>{n0(P.tot.st_rn)}</td>
            <td style={td}>{pct(P.tot.pace)}</td><td style={td}>{n0(P.tot.bloqueos)}</td><td style={td}>{n0(P.tot.ly_rn)}</td>
            <td style={td}>{n0(P.tot.proj - P.tot.otb_rn)}</td><td style={td}>{n0(P.tot.proj)}</td>
            <td style={td}>{pct(P.tot.proj_occ, 1)}</td><td style={td}>{usd0(P.tot.proj_rev)}</td><td style={td} />
          </tr>
        </tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("posicion.leyenda")}</div>
      <AnalisisTecnico />
    </div>
  );
}

// ───────────────────────────── Año vs año con alcance ─────────────────────────────
export function Comparativo() {
  const t = useTranslations("pacing");
  const M = useMeses();
  const { datos } = usePacing();
  const P = datos!.posicion!;
  const ly = P.T - 1;
  const serie = P.rows.map((r, i) => ({ mes: M[i], ly: Math.round(r.ly_rev), otb: Math.round(r.otb_rev), proj: Math.round(r.proj_rev) }));
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Aviso>{t("comparativo.nota", { ly, anio: P.T })}</Aviso>
      <Tabla minWidth={1200}>
        <thead>
          <tr>
            <th style={{ ...th, textAlign: "left" }} rowSpan={2}>{t("col.mes")}</th>
            <th style={{ ...th, textAlign: "center" }} colSpan={3}>{t("comparativo.grupoLy", { ly })}</th>
            <th style={{ ...th, textAlign: "center" }} colSpan={2}>{t("comparativo.grupoOtb", { anio: P.T })}</th>
            <th style={{ ...th, textAlign: "center" }} colSpan={3}>{t("comparativo.grupoProj", { anio: P.T })}</th>
            <th style={{ ...th, textAlign: "center" }} colSpan={3}>{t("comparativo.grupoVar")}</th>
          </tr>
          <tr>
            {["rn", "rev", "adr", "rn", "rev", "rn", "rev", "adr", "rn", "rev", "revPct"].map((c, k) =>
              <th key={k} style={th}>{t(`comparativo.${c}`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {P.rows.map((r, i) => {
            const adrP = r.proj ? r.proj_rev / r.proj : 0;
            const dRn = r.proj - r.ly_rn, dRev = r.proj_rev - r.ly_rev;
            return (
              <tr key={i}>
                <td style={tdL}>{M[i]}</td>
                <td style={td}>{n0(r.ly_rn)}{r.ly_alcance ? " *" : ""}</td>
                <td style={td}>{usd0(r.ly_rev)}</td><td style={td}>{usd0(r.ly_adr)}</td>
                <td style={td}>{n0(r.otb_rn)}</td><td style={td}>{usd0(r.otb_rev)}</td>
                <td style={td}><b>{n0(r.proj)}</b></td><td style={td}><b>{usd0(r.proj_rev)}</b></td><td style={td}>{usd0(adrP)}</td>
                <td style={{ ...td, color: colorDe(dRn) }}>{signo(dRn, n0)}</td>
                <td style={{ ...td, color: colorDe(dRev) }}>{signo(dRev, usd0)}</td>
                <td style={{ ...td, color: colorDe(dRev) }}>{r.ly_rev ? signo(r.proj_rev / r.ly_rev - 1, x => pct(x, 1)) : "—"}</td>
              </tr>
            );
          })}
          {(() => {
            const x = P.tot, dRn = x.proj - x.ly_rn, dRev = x.proj_rev - x.ly_rev;
            return (
              <tr style={filaTotal}>
                <td style={tdL}>{t("col.total")}</td>
                <td style={td}>{n0(x.ly_rn)}</td><td style={td}>{usd0(x.ly_rev)}</td><td style={td}>{usd0(x.ly_adr)}</td>
                <td style={td}>{n0(x.otb_rn)}</td><td style={td}>{usd0(x.otb_rev)}</td>
                <td style={td}>{n0(x.proj)}</td><td style={td}>{usd0(x.proj_rev)}</td>
                <td style={td}>{usd0(x.proj ? x.proj_rev / x.proj : 0)}</td>
                <td style={{ ...td, color: colorDe(dRn) }}>{signo(dRn, n0)}</td>
                <td style={{ ...td, color: colorDe(dRev) }}>{signo(dRev, usd0)}</td>
                <td style={{ ...td, color: colorDe(dRev) }}>{x.ly_rev ? signo(x.proj_rev / x.ly_rev - 1, v => pct(v, 1)) : "—"}</td>
              </tr>
            );
          })()}
        </tbody>
      </Tabla>
      <div style={card}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={serie}>
            <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
            <XAxis dataKey="mes" tick={eje} /><YAxis tick={eje} tickFormatter={kfmt} />
            <Tooltip {...tooltipStyle} formatter={(v) => usd0(Number(v))} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="ly" name={t("series.ly", { anio: ly })} fill="var(--border-medium)" />
            <Bar dataKey="otb" name={t("series.otb")} fill="var(--brand)" />
            <Bar dataKey="proj" name={t("series.proj")} fill="var(--positive)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("posicion.leyenda")}</div>
    </div>
  );
}

// ───────────────────────────── Cierre contra la meta ─────────────────────────────
export function Meta() {
  const t = useTranslations("pacing");
  const M = useMeses();
  const { datos } = usePacing();
  const C = datos!.cierre_meta;
  if (!C || !C.meta) {
    return <Aviso tipo="alerta">{t("meta.sinMeta", { anio: C?.year ?? "" })} <Link href="/pacing/cargas">{t("irACargas")}</Link></Aviso>;
  }
  const dRn = C.total.rn - C.total.meta_rn, dRev = C.total.rev - C.total.meta_rev;
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
        <Kpi titulo={t("meta.kMeta", { anio: C.year })} valor={usd0(C.total.meta_rev)} sub={`${n0(C.total.meta_rn)} RN · ${C.meta.source ?? ""}`} />
        <Kpi titulo={t("meta.kCierre")} valor={usd0(C.total.rev)} sub={`${n0(C.total.rn)} RN`} />
        <Kpi titulo={t("meta.kBrecha")} valor={signo(dRev, usd0)} color={colorDe(dRev)}
             sub={`${signo(dRn, n0)} RN · ${C.total.meta_rev ? signo(C.total.rev / C.total.meta_rev - 1, x => pct(x, 1)) : "—"}`} />
        <Kpi titulo={t("meta.kYtd")} valor={signo(C.ytd.rev - C.ytd.meta_rev, usd0)} color={colorDe(C.ytd.rev - C.ytd.meta_rev)}
             sub={t("meta.kYtdSub", { real: usd0(C.ytd.rev), meta: usd0(C.ytd.meta_rev) })} />
        {datos!.kind === "total" && C.total.en_sitio > 0 &&
          <Kpi titulo={t("meta.kEnSitio")} valor={usd0(C.total.en_sitio)} sub={t("meta.kEnSitioSub", { pct: pct(datos!.en_sitio?.pct ?? 0) })} />}
      </div>
      <Tabla minWidth={1100}>
        <thead><tr>
          {["mes", "base", "metaRn", "metaRev", "otbRn", "otbRev", "pickup", "proj", "projRev", "difRn", "difRev", "difPct"].map(c =>
            <th key={c} style={c === "mes" || c === "base" ? { ...th, textAlign: "left" } : th}>{t(`col.${c}`)}</th>)}
        </tr></thead>
        <tbody>
          {C.filas.map(f => {
            const a = f.proj_rev - f.meta_rev, b = f.proj - f.meta_rn;
            return (
              <tr key={f.i}>
                <td style={tdL}>{M[f.i]}</td>
                <td style={{ ...tdL, color: "var(--text-secondary)" }}>{t(`meta.base.${f.base === "real" ? "real" : "abierto"}`)}</td>
                <td style={td}>{n0(f.meta_rn)}</td><td style={td}>{usd0(f.meta_rev)}</td>
                <td style={td}>{f.cerrado ? "—" : n0(f.otb_rn)}</td><td style={td}>{f.cerrado ? "—" : usd0(f.otb_rev)}</td>
                <td style={td}>{f.cerrado ? "—" : n0(f.pick)}</td>
                <td style={td}><b>{n0(f.proj)}</b></td><td style={td}><b>{usd0(f.proj_rev)}</b></td>
                <td style={{ ...td, color: colorDe(b) }}>{signo(b, n0)}</td>
                <td style={{ ...td, color: colorDe(a) }}>{signo(a, usd0)}</td>
                <td style={{ ...td, color: colorDe(a) }}>{f.meta_rev ? signo(f.proj_rev / f.meta_rev - 1, x => pct(x, 1)) : "—"}</td>
              </tr>
            );
          })}
          <tr style={filaTotal}>
            <td style={tdL}>{t("col.total")}</td><td style={tdL} />
            <td style={td}>{n0(C.total.meta_rn)}</td><td style={td}>{usd0(C.total.meta_rev)}</td>
            <td style={td}>{n0(C.total.otb_rn)}</td><td style={td}>{usd0(C.total.otb_rev)}</td><td style={td} />
            <td style={td}>{n0(C.total.rn)}</td><td style={td}>{usd0(C.total.rev)}</td>
            <td style={{ ...td, color: colorDe(dRn) }}>{signo(dRn, n0)}</td>
            <td style={{ ...td, color: colorDe(dRev) }}>{signo(dRev, usd0)}</td>
            <td style={{ ...td, color: colorDe(dRev) }}>{C.total.meta_rev ? signo(C.total.rev / C.total.meta_rev - 1, x => pct(x, 1)) : "—"}</td>
          </tr>
        </tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("meta.nota", { anio: C.year })}</div>
    </div>
  );
}

// ───────────────────────────── Curva de pacing ─────────────────────────────
export function Curva() {
  const t = useTranslations("pacing");
  const { datos } = usePacing();
  const C = datos!.curva;
  const P = datos!.posicion!;
  const ev = datos!.evolucion ?? [];
  if (!C) return <Aviso tipo="alerta">{t("curva.sinReservas")}</Aviso>;
  const serie = C.xs.map((x, i) => ({ x, anio: C.anio[i], ant: C.anterior[i] }));
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Aviso>{t("curva.nota", { anio: P.T, ly: P.T - 1, hoy: n0(C.hoy_anio), hoyLy: n0(C.hoy_anterior) })}</Aviso>
      {C.migracion && <Aviso tipo="alerta">{t("curva.migracion", { fecha: C.migracion })}</Aviso>}
      <div style={card}>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={serie}>
            <CartesianGrid stroke="var(--border-subtle)" />
            <XAxis dataKey="x" tick={eje} minTickGap={40} /><YAxis tick={eje} />
            <Tooltip {...tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Line dataKey="ant" name={t("curva.serieLy", { ly: P.T - 1 })} stroke="var(--border-medium)" strokeWidth={2} dot={false} connectNulls />
            <Line dataKey="anio" name={t("curva.serieAnio", { anio: P.T })} stroke="var(--brand)" strokeWidth={2} dot={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 12 }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, margin: "4px 0 6px" }}>{t("curva.hitos")}</div>
          <Tabla minWidth={300}>
            <thead><tr><th style={{ ...th, textAlign: "left" }}>{t("curva.fecha")}</th><th style={th}>{t("curva.deberia")}</th></tr></thead>
            <tbody>{C.hitos.map(h => <tr key={h.fecha}><td style={tdL}>{h.fecha}</td><td style={td}>{n0(h.deberia)}</td></tr>)}</tbody>
          </Tabla>
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, margin: "4px 0 6px" }}>{t("curva.evolucion", { anio: P.T })}</div>
          <Tabla minWidth={300}>
            <thead><tr><th style={{ ...th, textAlign: "left" }}>{t("curva.foto")}</th><th style={th}>RN</th><th style={th}>{t("col.otbRev")}</th></tr></thead>
            <tbody>{ev.map(e => <tr key={e.as_of}><td style={tdL}>{e.as_of}</td><td style={td}>{n0(e.rn)}</td><td style={td}>{usd0(e.rev)}</td></tr>)}</tbody>
          </Tabla>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────── Pickup y canales ─────────────────────────────
export function Pickup() {
  const t = useTranslations("pacing");
  const M = useMeses();
  const { datos } = usePacing();
  const P = datos!.posicion!;
  const K = datos!.pickup;
  const canales = datos!.canales ?? [];
  if (!K) return <Aviso tipo="alerta">{t("curva.sinReservas")}</Aviso>;
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Aviso>{t("pickup.nota", { anio: P.T, ly: P.T - 1 })}</Aviso>
      <Tabla minWidth={800}>
        <thead><tr>
          <th style={{ ...th, textAlign: "left" }}>{t("pickup.ventana")}</th>
          <th style={th}>{t("pickup.rn", { anio: P.T })}</th><th style={th}>{t("pickup.rev")}</th><th style={th}>{t("pickup.canc")}</th>
          <th style={th}>{t("pickup.rn", { anio: P.T - 1 })}</th><th style={th}>{t("pickup.rev")}</th><th style={th}>{t("pickup.canc")}</th>
          <th style={th}>{t("pickup.ritmo")}</th>
        </tr></thead>
        <tbody>{K.ventanas.map(v => (
          <tr key={v.dias}>
            <td style={tdL}>{t("pickup.dias", { n: v.dias })}</td>
            <td style={td}><b>{n0(v.anio.rn)}</b></td><td style={td}>{usd0(v.anio.tarifa)}</td><td style={td}>{n0(v.anio.canceladas)}</td>
            <td style={td}>{n0(v.anterior.rn)}{v.anterior.migracion ? " ‡" : ""}</td><td style={td}>{usd0(v.anterior.tarifa)}</td>
            <td style={td}>{n0(v.anterior.canceladas)}</td>
            <td style={{ ...td, color: colorDe(v.anio.rn - v.anterior.rn) }}>{v.anterior.rn ? pct(v.anio.rn / v.anterior.rn) : "—"}</td>
          </tr>))}
        </tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("pickup.migracion")}</div>
      <div style={card}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{t("pickup.ultimos30", { anio: P.T })}</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={K.ultimos_30_por_mes.map((v, i) => ({ mes: M[i], v }))}>
            <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
            <XAxis dataKey="mes" tick={eje} /><YAxis tick={eje} />
            <Tooltip {...tooltipStyle} /><Bar dataKey="v" name="RN" fill="var(--brand)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ fontWeight: 600, fontSize: 13 }}>{t("pickup.canales", { anio: P.T })}</div>
      <Tabla minWidth={700}>
        <thead><tr>
          <th style={{ ...th, textAlign: "left" }}>{t("pickup.canal")}</th><th style={th}>RN</th><th style={th}>{t("pickup.rev")}</th>
          <th style={th}>ADR</th><th style={th}>{t("pickup.rnLy", { ly: P.T - 1 })}</th><th style={th}>{t("pickup.mix")}</th>
        </tr></thead>
        <tbody>{(() => {
          const tot = canales.reduce((a, c) => a + c.rn, 0);
          return canales.map(c => (
            <tr key={c.canal}>
              <td style={tdL}>{c.canal}</td><td style={td}>{n0(c.rn)}</td><td style={td}>{usd0(c.tarifa)}</td>
              <td style={td}>{usd0(c.rn ? c.tarifa / c.rn : 0)}</td><td style={td}>{n0(c.rn_anterior)}</td>
              <td style={td}>{pct(tot ? c.rn / tot : 0, 1)}</td>
            </tr>));
        })()}</tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("pickup.notaCanales")}</div>
    </div>
  );
}

// ───────────────────────────── Cancelaciones ─────────────────────────────
export function Cancelaciones() {
  const t = useTranslations("pacing");
  const M = useMeses();
  const { datos } = usePacing();
  const P = datos!.posicion!;
  const C = datos!.cancelaciones;
  if (!C || !datos!.reservas.cuenta) return <Aviso tipo="alerta">{t("curva.sinReservas")}</Aviso>;
  const tasa = (o: { a: number; x: number }) => (o.a + o.x ? o.x / (o.a + o.x) : 0);
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Aviso>{t("canc.nota")}</Aviso>
      <Tabla minWidth={1000}>
        <thead><tr>
          <th style={{ ...th, textAlign: "left" }}>{t("col.mes")}</th>
          <th style={th}>{t("canc.activas", { anio: P.T })}</th><th style={th}>{t("canc.canceladas")}</th><th style={th}>{t("canc.tasa")}</th>
          <th style={th}>{t("canc.activas", { anio: P.T - 1 })}</th><th style={th}>{t("canc.canceladas")}</th><th style={th}>{t("canc.tasa")}</th>
          <th style={th}>≤30d</th><th style={th}>31–90d</th><th style={th}>91–180d</th><th style={th}>&gt;180d</th>
        </tr></thead>
        <tbody>{C.anio.map((o, i) => {
          const l = C.anterior[i];
          return (
            <tr key={i}>
              <td style={tdL}>{M[i]}</td>
              <td style={td}>{n0(o.a)}</td><td style={td}>{n0(o.x)}</td>
              <td style={{ ...td, color: tasa(o) > tasa(l) + 0.05 ? "var(--negative)" : undefined }}>{pct(tasa(o), 1)}</td>
              <td style={td}>{n0(l.a)}</td><td style={td}>{n0(l.x)}</td><td style={td}>{pct(tasa(l), 1)}</td>
              {o.b.map((b, k) => <td key={k} style={td}>{pct(o.a - o.mig ? b / (o.a - o.mig) : 0)}</td>)}
            </tr>
          );
        })}</tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("canc.leyenda")}</div>
    </div>
  );
}

// ───────────────────────────── Alertas y tarifas por corregir ─────────────────────────────
export function Alertas() {
  const t = useTranslations("pacing");
  const M = useMeses();
  const { datos } = usePacing();
  const P = datos!.posicion!;
  const [mes, setMes] = useState<number>(0);
  const [fl, setFl] = useState<PacingFlagged | null>(null);
  useEffect(() => {
    let vivo = true;
    getPacingFlagged(P.T, mes || undefined).then(r => { if (vivo) setFl(r); }).catch(() => { if (vivo) setFl(null); });
    return () => { vivo = false; };
  }, [P.T, mes]);
  const texto = (a: PacingAlerta) => {
    const d = a.datos as Record<string, number | string>;
    const m = typeof d.mes === "number" ? `${M[d.mes]} ${d.anio}` : "";
    const f: Record<string, string> = {
      mes: m, tipo: String(d.tipo ?? ""), dias: n0(Number(d.dias)), monto: usd0(Number(d.monto)),
      adr: usd0(Number(d.adr)), rn: n0(Number(d.rn)), comp: n0(Number(d.comp)), grp: n0(Number(d.grp)),
      pct: pct(Number(d.pct)), ooo: n0(Number(d.ooo)), total: String(d.total ?? ""), rooms: String(d.rooms ?? ""),
      rm: n0(Number(d.rm)), rm_fecha: String(d.rm_fecha ?? ""), opera: n0(Number(d.opera)),
      opera_fecha: String(d.opera_fecha ?? ""), real: pct(Number(d.real)), otb: usd0(Number(d.otb)),
    };
    return t(`alertas.${a.clave}` as "alertas.adrBajo", f);
  };
  const sinTarifa = fl?.reservas.filter(r => r.motivo !== "cortesia") ?? [];
  const cortesias = fl?.reservas.filter(r => r.motivo === "cortesia") ?? [];
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "grid", gap: 6 }}>
        {(datos!.alertas ?? []).map((a, k) => (
          <div key={k} style={{ ...card, padding: "8px 12px", display: "flex", gap: 10, alignItems: "baseline",
                                borderLeft: `3px solid ${a.nivel === "corregir" ? "var(--negative)" : a.nivel === "revisar" ? "var(--warning)" : "var(--brand)"}` }}>
            <span style={{ fontSize: 11, fontWeight: 700, minWidth: 70 }}>{t(`nivel.${a.nivel}`)}</span>
            <span style={{ fontSize: 12 }}>{texto(a)}</span>
          </div>
        ))}
        {!(datos!.alertas ?? []).length && <Aviso>{t("alertas.ninguna")}</Aviso>}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{t("tarifas.titulo", { anio: P.T })}</div>
        <select style={select} value={mes} onChange={e => setMes(Number(e.target.value))}>
          <option value={0}>{t("tarifas.todoElAnio")}</option>
          {M.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
        </select>
        {fl && <span style={{ fontSize: 12 }}>{t("tarifas.potencial", { n: sinTarifa.length, monto: usd0(fl.potencial) })}</span>}
      </div>
      <Aviso>{t("tarifas.nota")}</Aviso>
      <FlagTabla filas={sinTarifa} />
      {cortesias.length > 0 && <>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{t("tarifas.cortesias", { n: cortesias.length })}</div>
        <FlagTabla filas={cortesias} />
      </>}
    </div>
  );
}

function FlagTabla({ filas }: { filas: PacingFlagged["reservas"] }) {
  const tt = useTranslations("pacing.tarifas");
  const orden = useMemo(() => [...filas].sort((a, b) => b.potencial - a.potencial), [filas]);
  if (!filas.length) return <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{tt("ninguna")}</div>;
  return (
    <Tabla minWidth={1100}>
      <thead><tr>
        {["resv", "huesped", "llegada", "noches", "hab", "monto", "noche", "mediana", "potencial", "rate", "canal", "creada", "motivo"].map(c =>
          <th key={c} style={["resv", "huesped", "rate", "canal", "motivo"].includes(c) ? { ...th, textAlign: "left" } : th}>{tt(`c.${c}`)}</th>)}
      </tr></thead>
      <tbody>{orden.map(r => (
        <tr key={r.id}>
          <td style={tdL}>{r.id}</td><td style={tdL}>{r.guest}</td><td style={td}>{r.arr}</td><td style={td}>{r.nts}</td>
          <td style={td}>{r.rms}</td><td style={td}>{usd0(r.amt)}</td><td style={td}>{usd0(r.noche)}</td>
          <td style={td}>{usd0(r.mediana_mes)}</td><td style={td}><b>{usd0(r.potencial)}</b></td>
          <td style={tdL}>{r.rate}</td><td style={tdL}>{r.ch}</td><td style={td}>{r.ins}</td>
          <td style={{ ...tdL, color: r.motivo === "sin_tarifa" ? "var(--negative)" : "var(--warning)" }}>{tt(`m.${r.motivo}`)}</td>
        </tr>))}
      </tbody>
    </Tabla>
  );
}
