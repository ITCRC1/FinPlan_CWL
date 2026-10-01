"use client";
/**
 * Análisis técnico del año, debajo de la tabla de «Posición mensual».
 *
 * Owner, 2026-09-30: «análisis técnico para todo el año, por mes y después en
 * forma general… por qué el proyectado es un buen parámetro… y que se pueda
 * bajar a Excel en forma profesional, listo para compartir con la Junta».
 *
 * Sólo dibuja. Las cifras y los TEXTOS vienen del backend (`/pacing/tecnico`)
 * en el idioma de la pantalla: el Excel de la Junta sale del mismo análisis y
 * dice palabra por palabra lo mismo que se lee acá.
 */
import { Fragment, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { bajarPacingTecnicoExcel, getPacingTecnico, type PacingConfianza, type PacingTecnico } from "@/lib/api";
import {
  Aviso, Kpi, Tabla, boton, botonPrimario, card, colorDe, filaTotal, n0, pct, td, tdL, th, tooltipStyle, usd0,
  useMeses, usePacing,
} from "./comun";

const COLOR: Record<PacingConfianza, string> = {
  alta: "var(--positive)", media: "var(--warning)", baja: "var(--negative)", sin_operacion: "var(--text-secondary)",
};
const eje = { fontSize: 11, fill: "var(--text-secondary)" };
const kfmt = (v: number) => (Math.abs(v) >= 1000 ? `${Math.round(v / 1000)}k` : String(Math.round(v)));
const h2 = { fontSize: 15, fontWeight: 700, margin: "4px 0 8px" } as const;

function Chip({ c, txt }: { c: PacingConfianza; txt: string }) {
  return (
    <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", background: COLOR[c], borderRadius: 10,
                   padding: "2px 8px", textTransform: "uppercase", whiteSpace: "nowrap" }}>{txt}</span>
  );
}

export function AnalisisTecnico() {
  const tt = useTranslations("pacing.tecnico");
  const locale = useLocale();
  const lang = locale.startsWith("en") ? "en" : "es";
  const M = useMeses();
  const { datos, filtros } = usePacing();
  const [A, setA] = useState<PacingTecnico | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bajando, setBajando] = useState(false);
  const [comentarios, setComentarios] = useState(true);

  const year = datos?.anio;
  const params = { year, kind: filtros.kind, escenario: filtros.escenario, fuente: filtros.fuente, lang };
  useEffect(() => {
    if (!year) return;
    let vivo = true;
    setError(null);
    getPacingTecnico(params)
      .then(d => { if (vivo) setA(d); })
      .catch(e => { if (vivo) setError(String(e?.message ?? e)); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, filtros.kind, filtros.escenario, filtros.fuente, lang]);

  const bajar = async () => {
    setBajando(true); setError(null);
    try { await bajarPacingTecnicoExcel(params); }
    catch (e) { setError(String((e as Error)?.message ?? e)); }
    finally { setBajando(false); }
  };

  if (error) return <Aviso tipo="error">{error}</Aviso>;
  if (!A) return <div style={{ ...card, fontSize: 12, color: "var(--text-secondary)" }}>{tt("cargando")}</div>;
  if (A.vacio) return null;
  const g = A.general, T = A.anio, B = A.base.anio;
  const graf = A.meses.map(m => ({ mes: M[m.i], ly: m.ly, otb: m.otb, proj: m.proj }));
  const nomMet = { avail: tt("metAvail"), add: tt("metAdd"), mult: tt("metMult") } as const;

  return (
    <div style={{ display: "grid", gap: 14, marginTop: 8 }}>
      <div style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontSize: 17, fontWeight: 700 }}>{tt("titulo", { anio: T })}</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
            {tt("sub", { corte: A.corte, base: B, metodo: nomMet[A.escenario] })}
          </div>
        </div>
        <button style={botonPrimario} onClick={bajar} disabled={bajando}>
          {bajando ? tt("bajando") : tt("excel")}
        </button>
      </div>
      {filtros.escenario !== A.escenario && <Aviso tipo="alerta">{tt("avisoEscenario", { metodo: nomMet[A.escenario] })}</Aviso>}

      {/* ── general ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 10 }}>
        <Kpi titulo={tt("kProj")} valor={n0(g.proj)} sub={`${pct(g.proj_occ, 1)} · ${usd0(g.proj_rev)}`} />
        <Kpi titulo={tt("kVsLy", { base: B })} valor={pct(g.ly ? g.proj / g.ly - 1 : null, 0)}
             color={colorDe(g.ly ? g.proj / g.ly - 1 : null)} sub={tt("kVsLySub", { base: B, rn: n0(g.ly), rev: usd0(g.ly_rev) })} />
        <Kpi titulo={tt("kAseg")} valor={pct(g.asegurado)} sub={tt("kAsegSub", { otb: n0(g.otb), rev: usd0(g.otb_rev) })} />
        <Kpi titulo={tt("kEsf")} valor={pct(g.esfuerzo)} color={g.esfuerzo != null && g.esfuerzo <= 1 ? "var(--positive)" : "var(--warning)"}
             sub={tt("kEsfSub", { falta: n0(g.falta), pick: n0(g.ly_pick) })} />
        <Kpi titulo={tt("kPace")} valor={pct(g.pace)} color={colorDe(g.pace == null ? null : g.pace - 1)}
             sub={tt("kPaceSub", { st: n0(g.stly) })} />
      </div>

      <div style={card}>
        <div style={h2}>{tt("conclusiones")}</div>
        <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6, fontSize: 13, lineHeight: 1.5 }}>
          {g.conclusiones.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      </div>

      <div style={card}>
        <div style={h2}>{tt("porque")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
          {g.porque.map((r, i) => (
            <div key={i} style={{ borderLeft: "3px solid var(--positive)", background: "var(--bg-elevated)", borderRadius: 4, padding: "8px 12px" }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{i + 1}. {r.titulo}</div>
              <div style={{ fontSize: 12, marginTop: 4, lineHeight: 1.5, color: "var(--text-primary)" }}>{r.texto}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={card}>
        <div style={h2}>{tt("grafico", { base: B, anio: T })}</div>
        <div style={{ height: 260 }}>
          <ResponsiveContainer>
            <ComposedChart data={graf} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
              <XAxis dataKey="mes" tick={eje} />
              <YAxis tick={eje} tickFormatter={kfmt} />
              <Tooltip {...tooltipStyle} formatter={(v) => n0(Number(v))} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="ly" name={tt("serieLy", { base: B })} fill="#363B52" />
              <Bar dataKey="otb" name={tt("serieOtb")} fill="#2962FF" />
              <Line dataKey="proj" name={tt("serieProj")} stroke="#26A69A" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── por mes ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={h2}>{tt("porMes", { anio: T })}</div>
        <button style={boton} onClick={() => setComentarios(v => !v)}>
          {comentarios ? tt("ocultar") : tt("mostrar")}
        </button>
      </div>
      <Tabla minWidth={1100}>
        <thead><tr>
          {(["mes", "otb", "pace", "proj", "vsLy", "aseg", "falta", "esf", "sem", "tarifa", "conf"] as const).map(c =>
            <th key={c} style={c === "mes" ? { ...th, textAlign: "left" } : th}>{tt(`col.${c}`)}</th>)}
        </tr></thead>
        <tbody>
          {A.meses.map(m => (
            <Fragment key={m.i}>
              <tr>
                <td style={{ ...tdL, fontWeight: 700 }}>{M[m.i]} {T}</td>
                <td style={td}>{n0(m.otb)}</td>
                <td style={{ ...td, color: m.pace == null ? undefined : colorDe(m.pace - 1) }}>{pct(m.pace)}</td>
                <td style={td}><b>{n0(m.proj)}</b></td>
                <td style={{ ...td, color: colorDe(m.proj_vs_ly == null ? null : m.proj_vs_ly - 1) }}>
                  {m.proj_vs_ly == null ? "—" : (m.proj_vs_ly >= 1 ? "+" : "") + pct(m.proj_vs_ly - 1)}{m.ly_base === "alcance" ? " *" : ""}
                </td>
                <td style={td}>{pct(m.asegurado)}</td>
                <td style={td}>{n0(m.falta)}</td>
                <td style={{ ...td, color: m.esfuerzo == null ? undefined : m.esfuerzo <= 0.9 ? "var(--positive)" : m.esfuerzo <= 1.1 ? "var(--warning)" : "var(--negative)" }}>
                  {pct(m.esfuerzo)}
                </td>
                <td style={td}>{n0(m.por_semana)}</td>
                <td style={{ ...td, color: colorDe(m.tarifa_vs_stly) }}>
                  {m.tarifa_vs_stly == null ? "—" : (m.tarifa_vs_stly >= 0 ? "+" : "") + pct(m.tarifa_vs_stly, 1)}
                </td>
                <td style={{ ...td, textAlign: "center" }}><Chip c={m.confianza} txt={m.confianza_txt} /></td>
              </tr>
              {comentarios && (
                <tr>
                  <td colSpan={11} style={{ padding: "4px 10px 10px", fontSize: 12, lineHeight: 1.55, whiteSpace: "normal",
                                            borderBottom: "1px solid var(--border-medium)", color: "var(--text-primary)" }}>
                    {m.comentario}
                    {m.razones_txt.length > 0 && (
                      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3, fontStyle: "italic" }}>
                        {tt("razones")} {m.razones_txt.join("; ")}.
                      </div>
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{tt("leyendaMes")}</div>

      {/* ── base del año anterior ── */}
      <div style={h2}>{tt("base", { base: B })}</div>
      <Aviso>{tt("baseNota", { anio: T, st: A.stly?.as_of ?? "—" })}</Aviso>
      <Tabla minWidth={1000}>
        <thead><tr>
          {(["mes", "estado", "rn", "occ", "rev", "vsMeta", "stly", "pick", "tasa", "recon"] as const).map(c =>
            <th key={c} style={c === "mes" || c === "estado" ? { ...th, textAlign: "left" } : th}>
              {tt(`b.${c}`, { st: A.stly?.as_of ?? "—" })}
            </th>)}
        </tr></thead>
        <tbody>
          {A.base.filas.map(x => (
            <tr key={x.i}>
              <td style={tdL}>{M[x.i]} {B}</td>
              <td style={{ ...tdL, color: x.cerrado ? undefined : "var(--text-secondary)" }}>
                {x.cerrado ? tt("real") : x.abierto ? tt("enCurso") : tt("sinOp")}
              </td>
              <td style={td}>{n0(x.rn)}</td>
              <td style={td}>{pct(x.occ, 1)}</td>
              <td style={td}>{usd0(x.rev)}</td>
              <td style={{ ...td, color: colorDe(x.meta_rn ? x.rn / x.meta_rn - 1 : null) }}>
                {x.meta_rn ? (x.rn >= x.meta_rn ? "+" : "") + pct(x.rn / x.meta_rn - 1) : "—"}
              </td>
              <td style={td}>{n0(x.stly)}</td>
              <td style={td}>{n0(x.pick)}</td>
              <td style={td}><b>{pct(x.tasa, 1)}</b></td>
              <td style={td}>{pct(x.reconcilia, 1)}</td>
            </tr>
          ))}
          <tr style={filaTotal}>
            <td style={tdL}>{tt("total")}</td><td style={td} />
            <td style={td}>{n0(A.base.tot.rn)}</td><td style={td}>{pct(A.base.tot.occ, 1)}</td>
            <td style={td}>{usd0(A.base.tot.rev)}</td>
            <td style={td}>{A.base.tot.meta_rn ? (A.base.tot.rn >= A.base.tot.meta_rn ? "+" : "") + pct(A.base.tot.rn / A.base.tot.meta_rn - 1) : "—"}</td>
            <td style={td}>{n0(A.base.filas.reduce((s, x) => s + (x.stly ?? 0), 0))}</td>
            <td style={td}>{n0(A.base.filas.reduce((s, x) => s + (x.pick ?? 0), 0))}</td>
            <td style={td} /><td style={td}>{pct(A.base.tot.reconcilia, 1)}</td>
          </tr>
        </tbody>
      </Tabla>

      {/* ── métodos ── */}
      <div style={h2}>{tt("metodos")}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
        {(["avail", "add", "mult"] as const).map(k => (
          <div key={k} style={{ ...card, padding: 14, border: k === A.escenario ? "2px solid var(--brand)" : card.border }}>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase" }}>
              {nomMet[k]}{k === A.escenario ? ` · ${tt("usado")}` : ""}
            </div>
            <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{n0(g.metodos[k].rn)} RN</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{usd0(g.metodos[k].rev)}</div>
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={h2}>{tt("limites")}</div>
        <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          {g.limites.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      </div>
    </div>
  );
}
