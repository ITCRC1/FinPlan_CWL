"use client";
/**
 * El estudio de un mes: «Pacing Diciembre 2026», como pantalla.
 *
 * Owner, 2026-09-30: *«mete acá el análisis que se hizo para noviembre por
 * separado en un tab llamado Noviembre 2026 y otro tab para Diciembre 2026.
 * Mismo análisis, debe darme igual al que compartí»*. Las secciones siguen el
 * orden del Word que se mandó a Revenue y Ventas; los números salen de
 * `/pacing/mes` (`backend/app/engine/pacing_mes.py`) y se recalculan solos con
 * cada carga de XML.
 */
import { useEffect, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getPacingMes, type PacingMes } from "@/lib/api";
import {
  Aviso, Kpi, Tabla, boton, card, colorDe, filaTotal, n0, pct, signo, td, tdL, th, tooltipStyle, usd0, useMeses,
} from "./comun";

const eje = { fontSize: 11, fill: "var(--text-secondary)" };
const GARANTIAS = ["LA", "CC", "DP", "GRP", "CORP", "WED", "HOLD72", "HOLD", "NON", "COMP", "HOUSE", "MEDIA"];

function H1({ n, children }: { n: number | string; children: ReactNode }) {
  return (
    <h2 style={{ fontSize: 16, fontWeight: 700, margin: "28px 0 10px", paddingBottom: 6,
                 borderBottom: "2px solid var(--brand)" }}>{n}. {children}</h2>
  );
}
function H2({ children }: { children: ReactNode }) {
  return <h3 style={{ fontSize: 13, fontWeight: 700, margin: "16px 0 6px" }}>{children}</h3>;
}
function Nota({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 11, color: "var(--text-secondary)", fontStyle: "italic", margin: "6px 0 10px" }}>{children}</div>;
}
function Callout({ titulo, children, color = "var(--negative)" }: { titulo: string; children: ReactNode; color?: string }) {
  return (
    <div style={{ borderLeft: `4px solid ${color}`, background: "var(--bg-elevated)", padding: "12px 16px", borderRadius: 4, margin: "10px 0" }}>
      <div style={{ fontWeight: 700, color, marginBottom: 6 }}>{titulo}</div>
      <div style={{ fontSize: 13, lineHeight: 1.6 }}>{children}</div>
    </div>
  );
}
const Li = ({ children }: { children: ReactNode }) => <li style={{ margin: "4px 0", lineHeight: 1.55 }}>{children}</li>;

export function AnalisisMes({ year, month }: { year: number; month: number }) {
  const t = useTranslations("pacing.mes");
  const M = useMeses();
  const tm = useTranslations("months");
  const largos = (tm.raw("long") as string[]) ?? M;
  const [a, setA] = useState<PacingMes | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    setA(null); setErr(null);
    getPacingMes(year, month).then(r => { if (vivo) setA(r); }).catch(e => { if (vivo) setErr(String(e?.message ?? e)); });
    return () => { vivo = false; };
  }, [year, month]);

  if (err) return <Aviso tipo="error">{err}</Aviso>;
  if (!a) return <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("cargando")}</div>;
  if (a.vacio) return <Aviso tipo="alerta">{t("vacio")}</Aviso>;

  const mesNombre = `${largos[month - 1]} ${year}`;
  const mesLy = `${M[month - 1].toLowerCase()}-${String(year - 1).slice(2)}`;
  const mesT = `${M[month - 1].toLowerCase()}-${String(year).slice(2)}`;
  const L = a.libros, P = a.anterior, R = a.ritmo, meta = a.meta;
  const esc = Object.fromEntries(a.escenarios.map(e => [e.clave, e])) as Record<string, PacingMes["escenarios"][number]>;
  const ly = esc.ritmoLy;
  const v = (d: number) => R.ventanas.find(x => x.dias === d)!;
  const nec = R.necesario ?? 0;
  const brecha = meta ? ly.ingreso - meta.total : 0;
  const sobre = brecha >= 0;
  const fechaCorte = a.corte;
  const ultimo = R.llenado_ly[R.llenado_ly.length - 1];
  const leadTotal = R.lead_ly.reduce((s, x) => s + x.rn, 0) || 1;
  const creadas = R.creadas.filter(c => c.mes >= (a.migracion ?? "").slice(0, 7));
  const topCreadas = [...creadas].sort((x, y) => y.activas - x.activas).slice(0, 2);
  const ultCreada = creadas[creadas.length - 1];
  const canales = a.canales.filter(c => c.canal);
  const caidas = [...canales].sort((x, y) => (x.rn - x.rn_ly) - (y.rn - y.rn_ly)).filter(c => c.rn < c.rn_ly).slice(0, 2);
  const suben = [...canales].filter(c => c.rn > c.rn_ly).sort((x, y) => (y.rn - y.rn_ly) - (x.rn - x.rn_ly)).slice(0, 5);
  const peor = [...a.periodos].sort((x, y) => (x.rn - x.ly) - (y.rn - y.ly))[0];
  const flojas = a.noches.filter(n => n.rn <= 5).map(n => n.dia);
  // Rango de ADR: primera quincena contra el cierre del mes (en diciembre, la
  // temporada festiva del 21 al 31, como en el estudio).
  const rango = (d1: number, d2: number) => {
    const x = a.noches.filter(n => n.dia >= d1 && n.dia <= d2 && n.adr_rooms && n.rn > 0).map(n => n.adr_rooms as number);
    return x.length ? { min: Math.min(...x), max: Math.max(...x) } : null;
  };
  const adrIni = rango(1, 15), adrFin = rango(month === 12 ? 21 : 16, a.dias);
  const finDesde = month === 12 ? 21 : 16;
  const T = a.tarifas;
  // Las líneas del mismo huésped/itinerario con el mismo motivo y tarifa van juntas
  // («71911075 / 71909033 · 2 hab.»), como en el estudio.
  const filasT = (() => {
    const g = new Map<string, PacingMes["tarifas"]["filas"][number] & { ids: string[]; lineas: number }>();
    for (const f of T.filas) {
      const k = [f.grupo || f.id, f.motivo, f.tarifa, f.arr, f.nts, f.motivo === "perfil_hold" ? "" : f.guest].join("|");
      const x = g.get(k);
      if (x) { x.ids.push(f.id); x.lineas += 1; x.bajo += f.bajo; x.alto += f.alto;
               if (f.guest && !(x.guest ?? "").includes(f.guest)) x.guest = `${x.guest} / ${f.guest}`; }
      else g.set(k, { ...f, ids: [f.id], lineas: 1 });
    }
    return [...g.values()];
  })();
  const crec = P.valor_noche ? L.valor_noche / P.valor_noche - 1 : 0;
  const dirIdx = canales.findIndex(c => c.canal === "Directo / sin agencia");
  const dir = dirIdx >= 0 ? canales[dirIdx] : null;
  const nom = (c: string | null, otros?: number) => (c ? c : t("canales.otros", { n: otros ?? 0 }));
  const hitoFin = a.hitos[a.hitos.length - 1];

  // ── gráficas ───────────────────────────────────────
  const curva = R.curva.filter((_, i) => i % 2 === 0).map(p => ({ x: p.dias, anio: p.anio, ant: p.anterior }));
  const barrasCreadas = creadas.map(c => ({ mes: `${M[Number(c.mes.slice(5)) - 1]}-${c.mes.slice(2, 4)}`, activas: c.activas, canceladas: c.canceladas }));
  const barrasNoche = a.noches.map(n => ({ dia: n.dia, anio: n.rn, ly: n.ly }));
  const barrasEsc = a.escenarios.map(e => ({ nombre: t(`esc.${e.clave}`), ingreso: Math.round(e.ingreso), rn: e.rn }));

  return (
    <div style={{ maxWidth: 1100 }}>
      <div className="no-print" style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button style={boton} onClick={() => window.print()}>{t("imprimir")}</button>
      </div>

      {/* Portada */}
      <div style={{ ...card, padding: 22 }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", color: "var(--text-secondary)" }}>{t("encabezado")}</div>
        <div style={{ fontSize: 30, fontWeight: 800, color: "var(--brand)", margin: "6px 0 2px" }}>{mesNombre}</div>
        <div style={{ fontSize: 17, marginBottom: 12 }}>{t("subtitulo")}</div>
        <div style={{ fontSize: 12, lineHeight: 1.7 }}>
          <div><b>{t("para")}</b> {t("paraValor")}</div>
          <div><b>{t("corte")}</b> {t("corteValor", { fecha: fechaCorte })}</div>
          <div><b>{t("fuentes")}</b> {t("fuentesValor", { meta: meta?.source ?? "—" })}</div>
        </div>
        <Callout titulo={t("mensaje")} color={sobre ? "var(--positive)" : "var(--negative)"}>
          <p style={{ margin: "0 0 6px" }}>
            {meta ? t(nec > v(90).por_semana ? "m1Debajo" : "m1Alcanza", {
              mes: mesNombre, rn: n0(L.rn), meta: n0(meta.rn), nec: n0(Math.round(nec)),
              r90: n0(v(90).por_semana), r30: n0(v(30).por_semana) }) : t("m1SinMeta", { mes: mesNombre, rn: n0(L.rn) })}
          </p>
          {meta && <p style={{ margin: 0 }}>{t(sobre ? "m2Arriba" : "m2Debajo", {
            ly: mesLy, rn: n0(ly.rn), ing: usd0(ly.ingreso), gap: usd0(Math.abs(brecha)),
            pct: pct(Math.abs(brecha) / meta.total, 0), meta: usd0(meta.total) })}</p>}
        </Callout>
      </div>

      {/* 1. Resumen ejecutivo */}
      <H1 n={1}>{t("s1")}</H1>
      <p style={{ fontSize: 13, lineHeight: 1.6 }}>{t("s1Intro", { mes: mesNombre })}</p>
      <Tabla minWidth={700}>
        <thead><tr>{["indicador", "meta", "libros", "alcance", "brecha"].map((c, i) =>
          <th key={c} style={i === 0 ? { ...th, textAlign: "left" } : th}>{t(`r.${c}`, { ly: year - 1 })}</th>)}</tr></thead>
        <tbody>
          <tr><td style={tdL}>{t("r.rn")}</td><td style={td}>{n0(meta?.rn)}</td><td style={td}>{n0(L.rn)}</td>
            <td style={td}>~{n0(ly.rn)}</td><td style={{ ...td, color: colorDe(ly.rn - (meta?.rn ?? 0)) }}>{meta ? signo(ly.rn - meta.rn, n0) : "—"}</td></tr>
          <tr><td style={tdL}>{t("r.occ")}</td><td style={td}>{meta ? pct(meta.rn / meta.avail, 1) : "—"}</td><td style={td}>{pct(L.occ, 1)}</td>
            <td style={td}>{pct(ly.occ, 1)}</td><td style={td}>{meta ? `${signo((ly.occ - meta.rn / meta.avail) * 100, x => x.toFixed(1))} pts` : "—"}</td></tr>
          <tr><td style={tdL}>{t("r.ingreso")}</td><td style={td}>{usd0(meta?.total)}</td><td style={td}>{usd0(L.ingreso)}</td>
            <td style={td}>~{usd0(ly.ingreso)}</td><td style={{ ...td, color: colorDe(brecha) }}>{meta ? signo(brecha, usd0) : "—"}</td></tr>
          <tr><td style={tdL}>{t("r.porNoche")}</td><td style={td}>{meta?.rn ? usd0(meta.total / meta.rn) : "—"}</td>
            <td style={td}>{usd0(L.rn ? L.ingreso / L.rn : 0)}</td><td style={td}>{usd0(ly.rn ? ly.ingreso / ly.rn : 0)}</td>
            <td style={td}>{meta?.rn && ly.rn ? signo(ly.ingreso / ly.rn - meta.total / meta.rn, usd0) : "—"}</td></tr>
        </tbody>
      </Tabla>
      <Nota>{t("s1Nota", { total: usd0(L.total), pct: pct(a.pct_en_sitio), sitio: usd0(L.en_sitio), ly: mesLy, corte: fechaCorte })}</Nota>
      <H2>{t("hallazgos")}</H2>
      <ul style={{ fontSize: 13, paddingLeft: 20, margin: 0 }}>
        <Li><b>{t(L.rn_reservas >= P.stly ? "h1aAdelante" : "h1aAtras")}</b>{" "}
          {t("h1b", { rn: n0(L.rn_reservas), st: n0(P.stly), ly: mesLy, d: signo(P.stly ? L.rn_reservas / P.stly - 1 : 0, x => pct(x, 0)),
                      meta: meta ? signo(meta.rn / (P.rn || 1) - 1, x => pct(x, 0)) : "—", cierre: n0(P.rn) })}</Li>
        <Li><b>{t(v(30).por_semana < nec ? "h2aFreno" : "h2aRitmo")}</b>{" "}
          {t("h2b", { r30: n0(v(30).rn), r14: n0(v(14).rn), m1: topCreadas[0] ? `${M[Number(topCreadas[0].mes.slice(5)) - 1]} (${n0(topCreadas[0].activas)} RN)` : "—",
                      m2: topCreadas[1] ? `${M[Number(topCreadas[1].mes.slice(5)) - 1]} (${n0(topCreadas[1].activas)} RN)` : "—",
                      ult: ultCreada ? `${M[Number(ultCreada.mes.slice(5)) - 1]} (${n0(ultCreada.activas)} RN)` : "—" })}</Li>
        <Li><b>{t(a.cancelaciones.tasa > P.cancel_tasa * 1.5 ? "h3aAlta" : "h3aNormal")}</b>{" "}
          {t("h3b", { rn: n0(a.cancelaciones.rn), pct: pct(a.cancelaciones.tasa, 0), mes: mesT, rnly: n0(P.cancel_rn), pctly: pct(P.cancel_tasa, 0),
                      ly: mesLy, hold: n0(a.cancelaciones.hold_rn) })}</Li>
        {peor && <Li><b>{t("h4a", { a: peor.desde, b: peor.hasta })}</b>{" "}
          {t("h4b", { rn: n0(peor.rn), occ: pct(peor.cap ? peor.rn / peor.cap : 0, 0), ly: n0(peor.ly), occly: pct(peor.cap ? peor.ly / peor.cap : 0, 0),
                      flojas: flojas.length ? flojas.join(", ") : "—" })}</Li>}
        {caidas.length > 0 && <Li><b>{t("h5a", { c: caidas.map(c => c.canal).join(" / ") })}</b>{" "}
          {caidas.map(c => t("h5b", { c: c.canal ?? "", rn: n0(c.rn), rnly: n0(c.rn_ly), pick: n0(c.pick_ly) })).join(" ")}</Li>}
        <Li><b>{t(crec >= 0 ? "h6aMejor" : "h6aPeor")}</b>{" "}
          {t(sobre ? "h6bConVolumen" : "h6b", { v: usd0(L.valor_noche), d: signo(crec, x => pct(x, 0)), ly: mesLy, vly: usd0(P.valor_noche) })}</Li>
        <Li><b>{t("h7a")}</b>{" "}
          {t("h7b", { n: T.filas.length, bajo: usd0(T.bajo), alto: usd0(T.alto) })}</Li>
      </ul>

      {/* 2. Posición */}
      <H1 n={2}>{t("s2")}</H1>
      <p style={{ fontSize: 13 }}>{t("s2Intro", { mes: mesNombre, ly: mesLy })}</p>
      <Tabla minWidth={700}>
        <thead><tr>{["concepto", "libros", "real", "var"].map((c, i) =>
          <th key={c} style={i === 0 ? { ...th, textAlign: "left" } : th}>{t(`p.${c}`, { mes: mesT, ly: mesLy })}</th>)}</tr></thead>
        <tbody>
          <tr><td style={tdL}>{t("p.rnHf")}</td><td style={td}>{n0(L.rn)}</td><td style={td}>{n0(P.rn)}*</td><td style={td}>{signo(L.rn - P.rn, n0)}</td></tr>
          <tr><td style={{ ...tdL, paddingLeft: 22 }}>{t("p.rnRes")}</td><td style={td}>{n0(L.rn_reservas)}</td><td style={td}>{n0(P.rn)}</td><td style={td}>{signo(L.rn_reservas - P.rn, n0)}</td></tr>
          <tr><td style={{ ...tdL, paddingLeft: 22 }}>{t("p.bloq", { a: a.bloqueos.desde ?? "—", b: a.bloqueos.hasta ?? "—" })}</td><td style={td}>{n0(L.bloqueos)}</td><td style={td}>—</td><td style={td} /></tr>
          <tr><td style={tdL}>{t("p.occ", { cap: n0(a.cap) })}</td><td style={td}>{pct(L.occ, 1)}</td><td style={td}>{pct(P.occ, 1)}</td><td style={td}>{signo((L.occ - P.occ) * 100, x => x.toFixed(1))} pts</td></tr>
          <tr><td style={tdL}>{t("p.reservas")}</td><td style={td}>{n0(L.reservas)}</td><td style={td}>—</td><td style={td} /></tr>
          <tr><td style={tdL}>{t("p.estancia")}</td><td style={td}>{L.estancia.toFixed(1)}</td><td style={td}>—</td><td style={td} /></tr>
          <tr><td style={tdL}>{t("p.rooms")}</td><td style={td}>{usd0(L.rooms)}</td><td style={td}>—</td><td style={td} /></tr>
          <tr><td style={tdL}>{t("p.adr")}</td><td style={td}>{usd0(L.adr_rooms)}</td><td style={td}>—</td><td style={td} /></tr>
          <tr><td style={tdL}>{t("p.total")}</td><td style={td}>{usd0(L.total)}</td><td style={td}>—</td><td style={td} /></tr>
          <tr><td style={tdL}>{t("p.valor")}</td><td style={td}>{usd0(L.valor_noche)}</td><td style={td}>{usd0(P.valor_noche)}</td><td style={td}>{signo(crec, x => pct(x, 1))}</td></tr>
        </tbody>
      </Tabla>
      <Nota>{t("s2Nota", { ly: mesLy, mig: a.migracion ?? "—" })}</Nota>
      <H2>{t("garantia")}</H2>
      <Tabla minWidth={700}>
        <thead><tr>{["codigo", "rn", "pct", "lectura"].map((c, i) =>
          <th key={c} style={i === 0 || i === 3 ? { ...th, textAlign: "left" } : th}>{t(`g.${c}`)}</th>)}</tr></thead>
        <tbody>{a.garantias.map(g => (
          <tr key={g.codigo}>
            <td style={tdL}>{g.codigo}</td><td style={td}>{n0(g.rn)}</td><td style={td}>{pct(L.rn_reservas ? g.rn / L.rn_reservas : 0)}</td>
            <td style={{ ...tdL, whiteSpace: "normal" }}>{t(`gl.${GARANTIAS.includes(g.codigo) ? g.codigo : "OTRO"}`)}</td>
          </tr>))}
        </tbody>
      </Tabla>
      <Nota>{t("gNota", { debil: n0(a.riesgo.garantia_debil), la: pct(L.rn_reservas ? a.riesgo.agencia / L.rn_reservas : 0) })}</Nota>
      <H2>{t("tipos")}</H2>
      <Tabla minWidth={600}>
        <thead><tr><th style={{ ...th, textAlign: "left" }}>{t("tipo")}</th>{a.tipos.map(x => <th key={x.tipo} style={th}>{x.tipo}</th>)}<th style={th}>{t("total")}</th></tr></thead>
        <tbody><tr><td style={tdL}>{t("rnMes", { mes: mesT })}</td>{a.tipos.map(x => <td key={x.tipo} style={td}>{n0(x.rn)}</td>)}<td style={td}><b>{n0(L.rn_reservas)}</b></td></tr></tbody>
      </Tabla>

      {/* 3. Ritmo */}
      <H1 n={3}>{t("s3")}</H1>
      <p style={{ fontSize: 13 }}>{t("s3Intro", { mes: largos[month - 1].toLowerCase(), ly: mesLy, anio: mesT })}</p>
      <div style={card}>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={curva}>
            <CartesianGrid stroke="var(--border-subtle)" />
            <XAxis dataKey="x" tick={eje} type="number" domain={["dataMin", "dataMax"]} tickFormatter={x => (x === 0 ? `1-${M[month - 1].toLowerCase()}` : `${x} d`)} />
            <YAxis tick={eje} />
            <Tooltip {...tooltipStyle} labelFormatter={x => `${x} d`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line dataKey="ant" name={t("curvaLy", { ly: mesLy })} stroke="#EB6834" strokeWidth={2} dot={false} connectNulls />
            <Line dataKey="anio" name={t("curvaAnio", { anio: mesT })} stroke="var(--brand)" strokeWidth={2} dot={false} connectNulls />
            {meta && <ReferenceLine y={meta.rn} stroke="var(--positive)" strokeDasharray="4 4" label={{ value: t("meta"), fill: "var(--positive)", fontSize: 11 }} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Nota>{t("curvaNota", { mig: a.migracion ?? "—" })}</Nota>
      <H2>{t(L.rn_reservas >= P.stly ? "s3aAdelante" : "s3aAtras")}</H2>
      <ul style={{ fontSize: 13, paddingLeft: 20, margin: 0 }}>
        <Li>{t("s3b", { corte: fechaCorte, rn: n0(L.rn_reservas), ly: mesLy, d: a.stly_fecha, st: n0(P.stly),
                        dif: signo(L.rn_reservas - P.stly, n0), pct: signo(P.stly ? L.rn_reservas / P.stly - 1 : 0, x => pct(x, 0)) })}</Li>
      </ul>
      <H2>{t(v(90).por_semana < nec ? "s3cNoAlcanza" : "s3cAlcanza")}</H2>
      <div style={card}>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={barrasCreadas}>
            <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
            <XAxis dataKey="mes" tick={eje} /><YAxis tick={eje} />
            <Tooltip {...tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="activas" stackId="a" name={t("creadasActivas")} fill="var(--brand)" />
            <Bar dataKey="canceladas" stackId="a" name={t("creadasCanc")} fill="#B7D3F6" />
            {nec > 0 && <ReferenceLine y={nec * 52 / 12} stroke="var(--positive)" strokeDasharray="4 4"
                                         label={{ value: t("necesarioMes", { n: n0(nec * 52 / 12) }), fill: "var(--positive)", fontSize: 11 }} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Tabla minWidth={700}>
        <thead><tr>{["ventana", "rn", "porSemana", "vsNec"].map((c, i) =>
          <th key={c} style={i === 0 ? { ...th, textAlign: "left" } : th}>{t(`v.${c}`, { mes: mesT, nec: n0(Math.round(nec)) })}</th>)}</tr></thead>
        <tbody>
          {R.ventanas.map(w => (
            <tr key={w.dias}><td style={tdL}>{t("v.ultimos", { n: w.dias })}</td><td style={td}>{n0(w.rn)}</td>
              <td style={td}>{w.por_semana.toFixed(1)}</td><td style={{ ...td, color: w.por_semana < nec ? "var(--negative)" : "var(--positive)" }}>{nec ? pct(w.por_semana / nec) : "—"}</td></tr>))}
          <tr style={{ color: "var(--text-secondary)" }}><td style={tdL}>{t("v.ref", { ly: mesLy })}</td><td style={td}>{n0(P.pickup)}</td>
            <td style={td}>{P.por_semana.toFixed(1)}</td><td style={td}>{nec ? pct(P.por_semana / nec) : "—"}</td></tr>
        </tbody>
      </Tabla>
      <Nota>{t("vNota", { meta: n0(meta?.rn), rn: n0(L.rn), falta: n0((meta?.rn ?? 0) - L.rn), sem: a.semanas.toFixed(1) })}</Nota>
      <H2>{t("llenado", { ly: mesLy })}</H2>
      <Tabla minWidth={600}>
        <thead><tr>{["mesVenta", "rn", "acum", "pct"].map((c, i) =>
          <th key={c} style={i === 0 ? { ...th, textAlign: "left" } : th}>{t(`ll.${c}`, { ly: mesLy })}</th>)}</tr></thead>
        <tbody>{R.llenado_ly.map((f, i) => (
          <tr key={i}><td style={tdL}>{f.mes ? `${largos[Number(f.mes.slice(5)) - 1]} ${f.mes.slice(0, 4)}` : t("ll.enLibros", { d: a.stly_fecha })}</td>
            <td style={td}>{n0(f.rn)}</td><td style={td}>{n0(f.acum)}</td><td style={td}>{pct(f.pct)}</td></tr>))}
        </tbody>
      </Tabla>
      <ul style={{ fontSize: 13, paddingLeft: 20, margin: "8px 0 0" }}>
        <Li><b>{t("leadA")}</b>{" "}{t("leadB", { pct: pct(R.lead_ly[0].rn / leadTotal), rn: n0(R.lead_ly[0].rn), r60: n0(R.lead_ly[2].rn),
                                                   r30: n0(R.lead_ly[1].rn), r90: n0(R.lead_ly[3].rn) })}</Li>
        {ultimo && R.llenado_ly.length > 2 && (() => {
          const fuerte = [...R.llenado_ly.slice(1)].sort((x, y) => y.rn - x.rn)[0];
          return <Li><b>{t("decideA", { m: `${largos[Number(fuerte.mes!.slice(5)) - 1]}` })}</b>{" "}
            {t("decideB", { m: largos[Number(fuerte.mes!.slice(5)) - 1].toLowerCase(), rn: n0(fuerte.rn), anio: year - 1 })}</Li>;
        })()}
      </ul>

      {/* 4. Brecha */}
      <H1 n={4}>{t("s4")}</H1>
      <p style={{ fontSize: 13 }}>{t("s4Intro", { tadr: usd0(a.t_adr), pct: pct(a.pct_en_sitio) })}</p>
      <div style={card}>
        <ResponsiveContainer width="100%" height={230}>
          <BarChart data={barrasEsc} layout="vertical" margin={{ left: 40 }}>
            <CartesianGrid stroke="var(--border-subtle)" horizontal={false} />
            <XAxis type="number" tick={eje} tickFormatter={x => `$${Math.round(Number(x) / 1000)}k`} />
            <YAxis type="category" dataKey="nombre" tick={eje} width={150} />
            <Tooltip {...tooltipStyle} formatter={(x) => usd0(Number(x))} />
            <Bar dataKey="ingreso" name={t("ingreso")} fill="var(--brand)" />
            {meta && <ReferenceLine x={meta.total} stroke="var(--negative)" strokeDasharray="4 4" label={{ value: t("metaK", { m: usd0(meta.total) }), fill: "var(--negative)", fontSize: 11 }} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Tabla minWidth={800}>
        <thead><tr>{["escenario", "supuesto", "rn", "occ", "ingreso", "vsMeta"].map((c, i) =>
          <th key={c} style={i < 2 ? { ...th, textAlign: "left" } : th}>{t(`e.${c}`)}</th>)}</tr></thead>
        <tbody>{a.escenarios.map(e => (
          <tr key={e.clave} style={e.clave === "ritmoLy" ? filaTotal : undefined}>
            <td style={tdL}>{t(`esc.${e.clave}`)}</td>
            <td style={tdL}>{t(`sup.${e.clave}`, { s: (e.por_semana ?? 0).toFixed(1), ly: mesLy })}</td>
            <td style={td}>{e.clave === "libros" || e.clave === "meta" ? n0(e.rn) : `~${n0(e.rn)}`}</td>
            <td style={td}>{pct(e.occ, 1)}</td>
            <td style={td}>{e.clave === "libros" ? usd0(e.ingreso) : `~${usd0(e.ingreso)}`}</td>
            <td style={{ ...td, color: colorDe(e.vs_meta) }}>{e.vs_meta == null ? "—" : signo(e.vs_meta, usd0)}</td>
          </tr>))}
        </tbody>
      </Tabla>
      {meta && (
        <Callout titulo={t("lectura")} color="var(--warning)">
          {sobre
            ? <p style={{ margin: 0 }}>{t("lecArriba", { ing: usd0(ly.ingreso), gap: usd0(brecha) })}</p>
            : <>
                <p style={{ margin: "0 0 6px" }}>{t("lec1", { ing: usd0(esc.ritmo90.ingreso), pct: pct(Math.abs(esc.ritmo90.vs_meta ?? 0) / meta.total, 0) })}</p>
                {esc.meta && (esc.meta.vs_meta ?? 0) < 0 && a.noche_para_meta &&
                  <p style={{ margin: "0 0 6px" }}>{t("lec2", { rn: n0(meta.rn), falta: usd0(Math.abs(esc.meta.vs_meta ?? 0)), noche: usd0(a.noche_para_meta),
                                                             d: pct(a.noche_para_meta / a.t_adr - 1, 0), tadr: usd0(a.t_adr) })}</p>}
                <p style={{ margin: 0 }}>{t("lec3")}</p>
              </>}
        </Callout>
      )}
      <H2>{t("hitos")}</H2>
      <Tabla minWidth={700}>
        <thead><tr>{["fecha", "ritmo", "ruta", "alerta"].map((c, i) =>
          <th key={c} style={i === 0 ? { ...th, textAlign: "left" } : th}>{t(`hi.${c}`, { ly: year - 1, nec: n0(Math.round(nec)) })}</th>)}</tr></thead>
        <tbody>{a.hitos.map(h => (
          <tr key={h.fecha}><td style={tdL}>{h.fecha}</td>
            <td style={td}>{h === hitoFin ? `~${n0(ly.rn)}–${n0(h.ritmo)}` : `~${n0(h.ritmo)}`}</td>
            <td style={td}>{h.ruta == null ? "—" : h === hitoFin ? n0(h.ruta) : `~${n0(h.ruta)}`}</td>
            <td style={td}>{h.alerta == null ? "—" : n0(h.alerta)}</td></tr>))}
        </tbody>
      </Tabla>
      <Nota>{t("hitosNota", { ly: year - 1 })}</Nota>

      {/* 5. Noche por noche */}
      <H1 n={5}>{t("s5")}</H1>
      <div style={card}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={barrasNoche}>
            <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
            <XAxis dataKey="dia" tick={eje} /><YAxis tick={eje} domain={[0, 36]} />
            <Tooltip {...tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="ly" name={t("nocheLy", { ly: mesLy })} fill="#EB6834" />
            <Bar dataKey="anio" name={t("nocheAnio", { anio: mesT })} fill="var(--brand)" />
            <ReferenceLine y={30} stroke="var(--positive)" strokeDasharray="4 4" />
            {meta && <ReferenceLine y={meta.rn / a.dias} stroke="#4A3AA7" strokeDasharray="2 3"
                                    label={{ value: t("metaNoche", { n: (meta.rn / a.dias).toFixed(1) }), fill: "#4A3AA7", fontSize: 11 }} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Tabla minWidth={800}>
        <thead><tr>{["periodo", "noches", "cap", "libros", "occ", "real", "occLy", "dif"].map((c, i) =>
          <th key={c} style={i === 0 ? { ...th, textAlign: "left" } : th}>{t(`d.${c}`, { mes: mesT, ly: mesLy })}</th>)}</tr></thead>
        <tbody>
          {a.periodos.map(p => (
            <tr key={p.desde}><td style={tdL}>{p.desde}–{p.hasta} {M[month - 1].toLowerCase()}</td><td style={td}>{p.noches}</td><td style={td}>{n0(p.cap)}</td>
              <td style={td}>{n0(p.rn)}</td><td style={td}>{pct(p.cap ? p.rn / p.cap : 0)}</td><td style={td}>{n0(p.ly)}</td>
              <td style={td}>{pct(p.cap ? p.ly / p.cap : 0)}</td><td style={{ ...td, color: colorDe(p.rn - p.ly) }}>{signo(p.rn - p.ly, n0)}</td></tr>))}
          <tr style={filaTotal}><td style={tdL}>{t("d.total", { mes: largos[month - 1].toLowerCase() })}</td><td style={td}>{a.dias}</td><td style={td}>{n0(a.cap)}</td>
            <td style={td}>{n0(L.rn)}</td><td style={td}>{pct(L.occ, 1)}</td><td style={td}>{n0(P.rn)}</td><td style={td}>{pct(P.occ, 1)}</td>
            <td style={{ ...td, color: colorDe(L.rn - P.rn) }}>{signo(L.rn - P.rn, n0)}</td></tr>
        </tbody>
      </Tabla>
      <ul style={{ fontSize: 13, paddingLeft: 20, margin: "8px 0 0" }}>
        {peor && <Li><b>{t("n1a", { a: peor.desde, b: peor.hasta, m: M[month - 1].toLowerCase() })}</b>{" "}
          {t(P.rn > L.rn && peor.ly > peor.rn ? "n1b" : "n1bSinBrecha", { occ: pct(peor.cap ? peor.rn / peor.cap : 0), occly: pct(peor.cap ? peor.ly / peor.cap : 0), dif: n0(peor.ly - peor.rn), tot: n0(Math.max(P.rn - L.rn, 0)) })}</Li>}
        {flojas.length > 0 && <Li><b>{t("n2a", { d: flojas.join(", ") })}</b>{" "}{t("n2b")}</Li>}
        {adrIni && adrFin && <Li><b>{t("n3a")}</b>{" "}{t("n3b", { d: finDesde, fin: a.dias, min: usd0(adrFin.min), max: usd0(adrFin.max),
                                                                   min1: usd0(adrIni.min), max1: usd0(adrIni.max) })}</Li>}
      </ul>

      {/* 6. Canales */}
      <H1 n={6}>{t("s6")}</H1>
      <p style={{ fontSize: 13 }}>{t("s6Intro", { ly: mesLy, d: a.stly_fecha })}</p>
      <Tabla minWidth={900}>
        <thead><tr>{["canal", "rn", "valor", "adr", "rnLy", "pickLy", "dif"].map((c, i) =>
          <th key={c} style={i === 0 ? { ...th, textAlign: "left" } : th}>{t(`c.${c}`, { mes: mesT, ly: mesLy, d: a.stly_fecha })}</th>)}</tr></thead>
        <tbody>
          {a.canales.map((c, i) => (
            <tr key={i}><td style={tdL}>{nom(c.canal, c.otros)}</td><td style={td}>{n0(c.rn)}</td><td style={td}>{usd0(c.valor)}</td>
              <td style={td}>{c.rn ? usd0(c.valor / c.rn) : "—"}</td><td style={td}>{n0(c.rn_ly)}</td><td style={td}>{n0(c.pick_ly)}</td>
              <td style={{ ...td, color: colorDe(c.rn - c.rn_ly) }}>{signo(c.rn - c.rn_ly, n0)}</td></tr>))}
          <tr style={filaTotal}><td style={tdL}>{t("total")}</td><td style={td}>{n0(L.rn_reservas)}</td><td style={td}>{usd0(L.valor_total)}</td>
            <td style={td}>{usd0(L.valor_noche)}</td><td style={td}>{n0(P.rn)}</td><td style={td}>{n0(P.pickup)}</td>
            <td style={{ ...td, color: colorDe(L.rn_reservas - P.rn) }}>{signo(L.rn_reservas - P.rn, n0)}</td></tr>
        </tbody>
      </Tabla>
      <Nota>{t("s6Nota")}</Nota>
      <ul style={{ fontSize: 13, paddingLeft: 20, margin: 0 }}>
        {dir && <Li><b>{t("c1a")}</b>{" "}{t("c1b", { rn: n0(dir.rn), rnly: n0(dir.rn_ly), pick: n0(dir.pick_ly), tot: n0(P.pickup) })}</Li>}
        {caidas.filter(c => c !== dir).slice(0, 1).map(c => (
          <Li key={c.canal}><b>{c.canal}:</b>{" "}{t("c2b", { rn: n0(c.rn), rnly: n0(c.rn_ly), d: n0(c.rn - c.rn_ly), pick: n0(c.pick_ly) })}</Li>))}
        {suben.length > 0 && <Li><b>{t("c3a")}</b>{" "}{suben.map(c => `${c.canal} (${signo(c.rn - c.rn_ly, n0)})`).join(", ")}.</Li>}
        {a.canc_por_canal.length > 0 && <Li><b>{t("c4a")}</b>{" "}
          {a.canc_por_canal.map(c => `${c.canal} ${n0(c.rn)} RN`).join(", ")}. {t("c4b", { n: a.cancelaciones.hold_reservas, rn: n0(a.cancelaciones.hold_rn) })}</Li>}
      </ul>

      {/* 7. Tarifas */}
      <H1 n={7}>{t("s7")}</H1>
      <p style={{ fontSize: 13 }}>{t("s7Intro", { n: L.reservas, mes: mesNombre })}</p>
      {T.filas.length ? (
        <Tabla minWidth={1100}>
          <thead><tr>{["resv", "huesped", "canal", "codigo", "llegada", "noches", "tarifa", "obs", "potencial"].map((c, i) =>
            <th key={c} style={[0, 1, 2, 3, 7].includes(i) ? { ...th, textAlign: "left" } : th}>{t(`t.${c}`)}</th>)}</tr></thead>
          <tbody>{filasT.map(f => (
            <tr key={f.ids.join("/")}>
              <td style={tdL}>{f.ids.join(" / ")}</td>
              <td style={{ ...tdL, whiteSpace: "normal" }}>{f.guest}{f.rms > 1 || f.lineas > 1 ? ` (${f.rms > 1 ? f.rms : f.lineas} ${t("t.hab")})` : ""}</td><td style={tdL}>{f.canal}</td>
              <td style={tdL}>{f.rate}</td><td style={td}>{f.arr.slice(5)}</td><td style={td}>{f.nts}</td><td style={td}>{usd0(f.tarifa)}</td>
              <td style={{ ...tdL, whiteSpace: "normal", minWidth: 220 }}>{t(`obs.${f.motivo}`, {
                pp: usd0(f.pp), pax: f.pax, med: usd0(f.mediana_pp), tope: usd0(f.tope ?? 0), gar: f.garantia ?? "" })}</td>
              <td style={td}>{f.alto > 0 ? (Math.round(f.bajo) === Math.round(f.alto) ? usd0(f.alto) : `${usd0(f.bajo)}–${usd0(f.alto)}`)
                : t(f.motivo === "sin_garantia" ? "t.riesgo" : "t.dato")}</td>
            </tr>))}
          </tbody>
        </Tabla>
      ) : <Aviso>{t("sinTarifas")}</Aviso>}
      <div style={{ height: 8 }} />
      <Tabla minWidth={600}>
        <thead><tr><th style={{ ...th, textAlign: "left" }}>{t("t.resumen")}</th><th style={{ ...th, textAlign: "left" }}>{t("t.valor")}</th></tr></thead>
        <tbody>
          <tr><td style={tdL}>{t("t.marcadas")}</td><td style={{ ...tdL, whiteSpace: "normal" }}>{t("t.marcadasV", {
            n: T.filas.length, tar: (T.por_motivo.cero ?? 0) + (T.por_motivo.por_persona ?? 0) + (T.por_motivo.itinerario ?? 0),
            gar: T.por_motivo.sin_garantia ?? 0, hold: T.por_motivo.perfil_hold ?? 0 })}</td></tr>
          <tr><td style={tdL}>{t("t.potencial")}</td><td style={tdL}>{usd0(T.bajo)} – {usd0(T.alto)}</td></tr>
          {meta && <tr><td style={tdL}>{t("t.pctMeta", { mes: largos[month - 1].toLowerCase() })}</td><td style={tdL}>{pct(T.bajo / meta.total, 1)} – {pct(T.alto / meta.total, 1)}</td></tr>}
          <tr><td style={tdL}>{t("t.bloqueo", { a: a.bloqueos.desde ?? "—", b: a.bloqueos.hasta ?? "—" })}</td>
            <td style={tdL}>{t("t.bloqueoV", { rn: n0(a.bloqueos.rn), h: n0(a.bloqueos.por_noche) })}</td></tr>
          <tr><td style={tdL}>{t("t.debil")}</td><td style={tdL}>{n0(a.riesgo.garantia_debil)} RN</td></tr>
        </tbody>
      </Tabla>
      <Nota>{t("tNota")}</Nota>

      {/* 8. Riesgos */}
      <H1 n={8}>{t("s8")}</H1>
      <Tabla minWidth={800}>
        <thead><tr>{["riesgo", "dato", "impacto"].map(c => <th key={c} style={{ ...th, textAlign: "left" }}>{t(`k.${c}`)}</th>)}</tr></thead>
        <tbody>
          <tr><td style={tdL}>{t("k.canc")}</td><td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.cancD", { rn: n0(a.cancelaciones.rn), pct: pct(a.cancelaciones.tasa), ly: mesLy, pctly: pct(P.cancel_tasa) })}</td>
            <td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.cancI", { pct: pct(P.cancel_tasa), rn: n0(P.cancel_tasa * L.rn_reservas) })}</td></tr>
          <tr><td style={tdL}>{t("k.la")}</td><td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.laD", { rn: n0(a.riesgo.agencia), pct: pct(L.rn_reservas ? a.riesgo.agencia / L.rn_reservas : 0) })}</td>
            <td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.laI")}</td></tr>
          <tr><td style={tdL}>{t("k.bloq")}</td><td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.bloqD", { rn: n0(a.bloqueos.rn), debil: n0(a.riesgo.garantia_debil) })}</td>
            <td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.bloqI", { rn: n0(a.bloqueos.rn + a.riesgo.garantia_debil) })}</td></tr>
          {a.riesgo.semana_max && <tr><td style={tdL}>{t("k.conc")}</td>
            <td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.concD", { rn: n0(a.riesgo.semana_max.rn), pct: pct(L.rn ? a.riesgo.semana_max.rn / L.rn : 0),
                                                                     a: a.riesgo.semana_max.desde, b: a.riesgo.semana_max.hasta })}</td>
            <td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.concI")}</td></tr>}
          <tr><td style={tdL}>{t("k.sitio")}</td><td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.sitioD", { pct: pct(a.pct_en_sitio) })}</td>
            <td style={{ ...tdL, whiteSpace: "normal" }}>{t("k.sitioI", { m: usd0(a.riesgo.en_sitio_punto) })}</td></tr>
        </tbody>
      </Tabla>

      {/* 9. Acciones */}
      <H1 n={9}>{t("s9")}</H1>
      <H2>{t("a.ventas")}</H2>
      <ol style={{ fontSize: 13, paddingLeft: 22, margin: 0 }}>
        {caidas.filter(c => c !== dir).slice(0, 1).map(c => <Li key={c.canal}><b>{c.canal}:</b> {t("a.v1", { rnly: n0(c.rn_ly), rn: n0(c.rn) })}</Li>)}
        {a.canc_por_canal.length > 0 && <Li><b>{t("a.v2a")}</b> {t("a.v2b", { c: a.canc_por_canal.slice(0, 4).map(c => c.canal).join(", ") })}</Li>}
        {flojas.length > 0 && <Li><b>{t("a.v3a", { d: flojas.slice(0, 6).join(", ") })}</b> {t("a.v3b")}</Li>}
        {a.bloqueos.rn > 0 && <Li><b>{t("a.v4a", { a: a.bloqueos.desde ?? "", b: a.bloqueos.hasta ?? "" })}</b> {t("a.v4b", { h: n0(a.bloqueos.por_noche) })}</Li>}
      </ol>
      <H2>{t("a.rm")}</H2>
      <ol style={{ fontSize: 13, paddingLeft: 22, margin: 0 }}>
        {dir && <Li><b>{t("a.r1a")}</b> {t("a.r1b", { pick: n0(dir.pick_ly) })}</Li>}
        <Li><b>{t("a.r2a")}</b> {t("a.r2b")}</Li>
        <Li><b>{t("a.r3a")}</b> {t("a.r3b", { f: a.hitos[0]?.fecha ?? "—", n: n0(a.hitos[0]?.alerta ?? 0) })}</Li>
      </ol>
      <H2>{t("a.res")}</H2>
      <ol style={{ fontSize: 13, paddingLeft: 22, margin: 0 }}>
        <Li>{t("a.s1", { n: T.filas.length, f: a.hitos[0]?.fecha ?? "—" })}</Li>
        <Li>{t("a.s2")}</Li>
        <Li>{t("a.s3")}</Li>
      </ol>
      <H2>{t("a.fin")}</H2>
      <ol style={{ fontSize: 13, paddingLeft: 22, margin: 0 }}>
        {meta && <Li><b>{t("a.f1a", { mes: largos[month - 1].toLowerCase() })}</b> {sobre
          ? t("a.f1Arriba", { ing: usd0(ly.ingreso), meta: usd0(meta.total) })
          : t("a.f1Debajo", { a: usd0(esc.ritmo90.ingreso), b: usd0(ly.ingreso), r: usd0(Math.round(ly.ingreso / 10000) * 10000), meta: usd0(meta.total) })}</Li>}
        <Li>{t("a.f2")}</Li>
      </ol>

      {/* Anexo */}
      <H1 n={t("anexoN")}>{t("anexo")}</H1>
      <ul style={{ fontSize: 12, paddingLeft: 20, margin: 0, color: "var(--text-secondary)" }}>
        <Li><b>{t("x.fuentes")}</b> {t("x.fuentesT", { corte: fechaCorte })}</Li>
        <Li><b>{t("x.rn")}</b> {t("x.rnT", { hf: n0(L.rn), res: n0(L.rn_reservas) })}</Li>
        <Li><b>{t("x.ly", { ly: mesLy })}</b> {t("x.lyT", { mig: a.migracion ?? "—" })}</Li>
        <Li><b>{t("x.canc")}</b> {t("x.cancT")}</Li>
        <Li><b>{t("x.alcance")}</b> {t("x.alcanceT", { ly: mesLy, pick: n0(P.pickup), tasa: pct(ly.tasa ?? 0) })}</Li>
        <Li><b>{t("x.ingreso")}</b> {t("x.ingresoT", { pct: pct(a.pct_en_sitio), tadr: usd0(a.t_adr), radr: usd0(P.valor_noche) })}</Li>
        {meta && <Li><b>{t("x.meta")}</b> {t("x.metaT", { src: meta.source ?? "—", rn: n0(meta.rn), avail: n0(meta.avail), rooms: usd0(meta.rooms), total: usd0(meta.total) })}</Li>}
        <Li><b>{t("x.tarifa")}</b> {t("x.tarifaT")}</Li>
      </ul>
    </div>
  );
}
