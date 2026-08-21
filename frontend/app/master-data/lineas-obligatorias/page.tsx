"use client";
/**
 * Master Data → Líneas obligatorias.
 *
 * El reporte que contesta la pregunta del owner: **qué tengo que cargar y en
 * qué orden**. Por escenario, qué línea que el histórico usa quedó en cero, y
 * cuánto vale esa línea en el histórico.
 *
 * Es el par de la verificación del upload: aquélla cuida los **actuales** en la
 * puerta; ésta avisa cuando un **presupuesto** deja un agujero. Importa ahora
 * porque el owner está por clonar propiedades y **cada clon hereda los
 * agujeros**.
 *
 * **No corre solo.** Hay que apretar «Correr»: calcula el P&L de cada escenario
 * con el motor de hoy y eso cuesta segundos por escenario. No se lee `pl_lines`
 * a propósito — está vacío o viejo en 6 de los 20 escenarios y avisar desde ahí
 * inventaría agujeros que no existen.
 *
 * **Avisa, no bloquea.** Un presupuesto en construcción tiene líneas vacías con
 * todo derecho.
 */
import { useState } from "react";
import { useTranslations } from "next-intl";

import {
  getListaObligatorias, getReporteObligatorias,
  type ListaObligatorias, type ReporteObligatorias, type FilaReporteObligatorias,
} from "@/lib/api";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const BTN: React.CSSProperties = {
  padding: "9px 18px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 14, fontWeight: 600,
};
const TD: React.CSSProperties = {
  padding: "4px 10px", borderBottom: "1px solid var(--border-subtle, #3334)",
};
const USD = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });

export default function LineasObligatoriasPage() {
  const t = useTranslations("reqLines");
  const tc = useTranslations("common");
  const [rep, setRep] = useState<ReporteObligatorias | null>(null);
  const [lista, setLista] = useState<ListaObligatorias | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [verLista, setVerLista] = useState(false);
  const [corriendo, setCorriendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function correr() {
    setCorriendo(true); setError(null);
    try {
      const [r, l] = await Promise.all([getReporteObligatorias(), getListaObligatorias()]);
      setRep(r); setLista(l);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setCorriendo(false); }
  }

  function bajar() {
    if (!rep) return;
    const columnas: ColumnaCuadro[] = [
      { label: tc("scenario"), ancho: 28 },
      { label: tc("line"), ancho: 26, formato: "texto" },
      { label: tc("name"), ancho: 34, formato: "texto" },
      { label: t("historicoUsd"), ancho: 16, formato: "usd" },
      { label: tc("year"), ancho: 8, formato: "texto" },
      { label: t("dondeSeCarga"), ancho: 30, formato: "texto" },
    ];
    const filas: FilaCuadro[] = [];
    for (const e of rep.escenarios) {
      for (const f of e.faltan ?? []) {
        filas.push({
          label: e.etiqueta,
          valores: [f.line_code, f.nombre, f.referencia_usd,
                    String(f.referencia_anio ?? ""), f.donde_se_carga],
        });
      }
    }
    bajarCuadros("lineas_obligatorias", [{
      titulo: t("excelTitulo"),
      subtitulo: t("listaDel", { fecha: rep.generado, n: rep.obligatorias }),
      hoja: t("hojaFaltantes"), columnas, filas,
    }]);
  }

  const conAgujeros = (rep?.escenarios ?? []).filter(e => !e.vacio && (e.cuantas_faltan ?? 0) > 0);
  const vacios = (rep?.escenarios ?? []).filter(e => e.vacio);
  const sanos = (rep?.escenarios ?? []).filter(e => !e.vacio && (e.cuantas_faltan ?? 0) === 0);
  conAgujeros.sort((a, b) => (b.magnitud_historica_usd ?? 0) - (a.magnitud_historica_usd ?? 0));

  const b = (c: React.ReactNode) => <strong>{c}</strong>;
  const i = (c: React.ReactNode) => <em>{c}</em>;

  return (
    <div className="pag pag-media" style={{ padding: "20px 24px" }}>
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("titulo")}</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 18 }}>
        {t.rich("intro", { b, i })}
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20 }}>
        <button onClick={correr} disabled={corriendo} style={{ ...BTN, opacity: corriendo ? 0.5 : 1 }}>
          {corriendo ? t("corriendo") : t("correr")}
        </button>
        {rep && <button onClick={bajar} style={BTN}>{t("bajarCuadro")}</button>}
        {lista && (
          <button onClick={() => setVerLista(v => !v)} style={BTN}>
            {verLista ? t("ocultarLista") : t("verLista")}
          </button>
        )}
        {rep && (
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t("resumenLista", { n: rep.obligatorias, fecha: rep.generado })}
          </span>
        )}
      </div>

      {corriendo && (
        <p style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
          {t("avisoTarda")}
        </p>
      )}

      {error && (
        <div style={{ border: "1px solid #C0392B", borderRadius: 8, padding: 14,
                      color: "#C0392B", fontSize: 13 }}>{error}</div>
      )}

      {verLista && lista && (
        <div style={{ border: "1px solid var(--border-subtle)", borderRadius: 8,
                      padding: 14, marginBottom: 20, background: "var(--bg-surface)" }}>
          <strong style={{ fontSize: 14 }}>{t("laListaYCriterio")}</strong>
          <ul style={{ fontSize: 12.5, color: "var(--text-secondary)", margin: "8px 0 12px 18px" }}>
            {(lista.criterio.regla ?? []).map(r => <li key={r}>{r}</li>)}
          </ul>
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 10 }}>
            {t.rich("esUnaLista", { b, code: (c: React.ReactNode) => <code>{c}</code> })}
          </p>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
                <th style={TD}>{tc("line")}</th><th style={TD}>{tc("name")}</th>
                <th style={{ ...TD, textAlign: "right" }}>{t("referencia")}</th>
                <th style={TD}>{t("dondeSeCarga")}</th>
                <th style={{ ...TD, textAlign: "right" }}>{t("reglas")}</th>
              </tr>
            </thead>
            <tbody>
              {lista.lineas.map(l => (
                <tr key={l.line_code}>
                  <td style={{ ...TD, fontFamily: "monospace" }}>{l.line_code}</td>
                  <td style={TD}>{l.nombre}</td>
                  <td style={{ ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {USD(l.referencia_usd)}{" "}
                    <span style={{ color: "var(--text-secondary)" }}>({l.referencia_anio})</span>
                  </td>
                  <td style={TD}>{l.donde_se_carga}</td>
                  <td style={{ ...TD, textAlign: "right" }}>{l.reglas_de_mapeo}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {conAgujeros.map(e => <Escenario key={e.scenario_id} e={e}
                                       abierto={abierto === e.scenario_id}
                                       toggle={() => setAbierto(abierto === e.scenario_id ? null : e.scenario_id)} />)}

      {sanos.length > 0 && (
        <p style={{ fontSize: 13, marginTop: 16, color: "var(--accent-green, #1A7F4B)" }}>
          {t("sinAgujeros")} {sanos.map(e => e.etiqueta).join(" · ")}
        </p>
      )}

      {vacios.length > 0 && (
        <div style={{ marginTop: 16, fontSize: 13, color: "var(--text-secondary)" }}>
          {t.rich("sinEmpezar", { b, n: vacios.length })}{" "}
          {vacios.map(e => e.etiqueta).join(" · ")}
        </div>
      )}
    </div>
  );
}

function Escenario({ e, abierto, toggle }: {
  e: FilaReporteObligatorias; abierto: boolean; toggle: () => void;
}) {
  const t = useTranslations("reqLines");
  const tc = useTranslations("common");
  return (
    <div style={{
      border: "1px solid var(--border-subtle)",
      borderLeft: "3px solid var(--accent-gold, #856404)",
      borderRadius: 8, background: "var(--bg-surface)",
      padding: "12px 14px", marginBottom: 10,
    }}>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
        <strong style={{ fontSize: 14 }}>{e.etiqueta}</strong>
        <span style={{ fontSize: 13 }}>
          {t("enCero", { faltan: e.cuantas_faltan ?? 0, total: e.obligatorias ?? 0 })}
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {t("valenEnHistorico", { usd: USD(e.magnitud_historica_usd ?? 0) })}
        </span>
        <button onClick={toggle} style={{
          background: "none", border: "none", cursor: "pointer",
          color: "var(--brand)", fontSize: 12.5, marginLeft: "auto",
        }}>{abierto ? t("ocultar") : t("verCuales")}</button>
      </div>

      {(e.meses_no_revisados?.length ?? 0) > 0 && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
          {t("soloMeses", {
            meses: (e.meses_revisados ?? []).map(m => String(m).padStart(2, "0")).join(", "),
          })}{" "}
          {e.motivo_meses_no_revisados}
        </div>
      )}

      {abierto && (
        <table style={{ marginTop: 8, borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={TD}>{tc("line")}</th><th style={TD}>{tc("name")}</th>
              <th style={{ ...TD, textAlign: "right" }}>{t("historicoUsdTh")}</th>
              <th style={TD}>{t("dondeSeCarga")}</th>
            </tr>
          </thead>
          <tbody>
            {(e.faltan ?? []).map(f => (
              <tr key={f.line_code}>
                <td style={{ ...TD, fontFamily: "monospace" }}>{f.line_code}</td>
                <td style={TD}>{f.nombre}</td>
                <td style={{ ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {USD(f.referencia_usd)}{" "}
                  <span style={{ color: "var(--text-secondary)" }}>({f.referencia_anio})</span>
                </td>
                <td style={TD}>
                  {f.pantalla
                    ? <a href={f.pantalla} style={{ color: "var(--brand)" }}>{f.donde_se_carga}</a>
                    : f.donde_se_carga}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
