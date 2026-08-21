"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { getScenarios, importGLDetail, exportDetailUrl, bulkCreateStandardVersions, deleteScenario, renameScenario, getMesesCerrados, getDivergencia, ErrorDeVerificacion, type Scenario, type ImportGLDetailResult, type VerificacionReporte, type VerificacionBloqueada, type MesesCerrados, type Divergencia } from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const fmt = (n: number) => (n < 0 ? `(${Math.round(-n).toLocaleString()})` : Math.round(n).toLocaleString());
const scenLabel = (s: Scenario) => `${s.type} · ${s.version} · ${s.year}${s.is_current_forecast ? " ★ Current" : ""}`;
// Working y Final son versiones protegidas: no se pueden borrar (regla de negocio).
const isProtected = (s: Scenario) => /working|final/i.test(s.version);

/**
 * La comparación del bloque de control contra el detalle consolidado.
 *
 * Se muestra **bucket por bucket, con la diferencia**, y no solo cuando falla:
 * un control que solo se ve cuando revienta es un control del que nadie sabe si
 * está funcionando. Los cuatro que pidió el owner —ingresos, GOP, EBITDA,
 * utilidad neta— frenan la carga; el desglose explica dónde está la diferencia.
 */
function TablaVerificacion({ rep }: { rep: VerificacionReporte }) {
  const t = useTranslations("import");
  const MESES = useTranslations("months").raw("long") as string[];
  if (!rep?.hay_verificacion) {
    return (
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8 }}>
        {t("verif.noBlock", { motivo: rep?.motivo ? ` (${rep.motivo})` : "" })}
      </div>
    );
  }
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6,
        color: rep.cuadra ? "var(--positive)" : rep.bloquea ? "var(--accent-red, #C0392B)" : "var(--accent-amber, #856404)" }}>
        {rep.cuadra ? t("verif.matches")
          : rep.bloquea ? t("verif.blocked")
            : t("verif.warnings")}
      </div>
      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
        <table className="fin-table" style={{ width: "100%", minWidth: 620 }}>
          <thead><tr>
            <th style={{ textAlign: "left" }}>{t("verif.control")}</th>
            <th style={{ textAlign: "right" }}>{t("verif.file")}</th>
            <th style={{ textAlign: "right" }}>{t("verif.detail")}</th>
            <th style={{ textAlign: "right" }}>{t("verif.difference")}</th>
            <th style={{ textAlign: "center" }}>{t("verif.effect")}</th>
          </tr></thead>
          <tbody>{(rep.lineas ?? []).map(L => (
            <tr key={L.codigo}>
              <td style={{ textAlign: "left", fontWeight: L.bloquea ? 700 : 400 }}>
                {L.etiqueta}
                {L.nota && <div style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 400 }}>{L.nota}</div>}
                {!L.cuadra && L.meses_que_no_cuadran.length > 0 && (
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 400 }}>
                    {t("verif.months", { lista: L.meses_que_no_cuadran.map(d => `${MESES[d.mes - 1]} ${fmt(d.dif)}`).join(" · ") })}
                  </div>
                )}
              </td>
              <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(L.archivo)}</td>
              <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(L.detalle)}</td>
              <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 700,
                color: L.cuadra ? "var(--text-secondary)" : L.bloquea ? "var(--accent-red, #C0392B)" : "var(--accent-amber, #856404)" }}>
                {L.cuadra ? "—" : fmt(L.dif)}
              </td>
              <td style={{ textAlign: "center", fontSize: 11, color: "var(--text-secondary)" }}>
                {L.bloquea ? t("verif.blocks") : t("verif.warns")}
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {(rep.meses_no_comparados?.length ?? 0) > 0 && (
        <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 8, lineHeight: 1.5 }}>
          {t("verif.notCompared", {
            meses: rep.meses_no_comparados!.map(m => MESES[m - 1]).join(", "),
            motivo: rep.motivo_meses_no_comparados ?? "",
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Los meses cerrados del escenario elegido, y si hay foto que los cubra.
 *
 * Se muestra ANTES de elegir camino, no después de escribir: es la diferencia
 * entre avisar y enterarse.
 */
function EstadoDelEscenario({ est }: { est: MesesCerrados }) {
  const t = useTranslations("import");
  const MESES = useTranslations("months").raw("long") as string[];
  const b = (c: React.ReactNode) => <b>{c}</b>;
  if (!est.tiene_datos) {
    return (
      <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 10 }}>
        {t.rich("state.noMonths", { esc: est.escenario, b })}
      </div>
    );
  }
  return (
    <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 10, lineHeight: 1.6 }}>
      {t.rich("state.hasMonths", {
        esc: est.escenario,
        n: est.meses_cerrados.length,
        lista: est.meses_cerrados.map(m => MESES[m - 1]).join(", "),
        b,
      })}
      {est.ultima_foto
        ? <> {t.rich("state.lastSnapshot", { etiqueta: est.ultima_foto.etiqueta, b })}</>
        : <> <span style={{ color: "var(--accent-amber, #856404)" }}>{t("state.noSnapshot")}</span></>}
      {est.meses_cerrados_sin_foto.length > 0 && (
        <div style={{ color: "var(--accent-amber, #856404)", marginTop: 4 }}>
          {t.rich("state.closedWithoutSnapshot", {
            meses: est.meses_cerrados_sin_foto.map(m => MESES[m - 1]).join(", "),
            b,
          })}
        </div>
      )}
    </div>
  );
}

/** Qué se movió en un mes YA CERRADO desde la última foto. No impide: muestra. */
function SenalDeDivergencia({ d }: { d: Divergencia }) {
  const t = useTranslations("import");
  const tc = useTranslations("common");
  const tMc = useTranslations("mesesCerrados");
  const MESES = useTranslations("months").raw("long") as string[];
  // El aviso lo NOMBRA el motor —no puede enterarse del idioma— y lo redacta esta
  // pantalla: los conteos van sueltos y el plural se arma con ICU en el catalogo.
  // La lista de meses viaja como numeros (dato) y se nombra con el catalogo de
  // meses, para que coincida con el resto de la app. Sin clave queda el `mensaje`.
  const aviso = d.mensaje_key
    ? tMc(d.mensaje_key, {
        ...(d.mensaje_params ?? {}),
        lista: (d.mensaje_params?.lista ?? []).map(m => MESES[m - 1]).join(", "),
      })
    : d.mensaje;
  const malo = d.veredicto === "cambio_en_mes_cerrado";
  const color = malo ? "var(--accent-red, #C0392B)"
    : d.veredicto === "sin_cambios" ? "var(--positive)" : "var(--accent-amber, #856404)";
  return (
    <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--border-medium)" }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--brand)" }}>
        {t("div.closedMonths")} · {d.escenario}
      </div>
      <div style={{ fontSize: 12.5, color, marginTop: 6, lineHeight: 1.6 }}>
        {malo ? "⚠ " : d.veredicto === "sin_cambios" ? "✓ " : "· "}{aviso}
      </div>
      {d.diferencias.length > 0 && (
        <div className="fin-scroll-x" style={{ overflowX: "auto", marginTop: 8 }}>
          <table className="fin-table" style={{ width: "100%", minWidth: 560 }}>
            <thead><tr>
              <th style={{ textAlign: "left" }}>{tc("month")}</th>
              <th style={{ textAlign: "left" }}>{tc("line")}</th>
              <th style={{ textAlign: "right" }}>{t("div.inSnapshot")}</th>
              <th style={{ textAlign: "right" }}>{t("div.now")}</th>
              <th style={{ textAlign: "right" }}>{t("verif.difference")}</th>
            </tr></thead>
            <tbody>{d.diferencias.slice(0, 40).map((f, i) => (
              <tr key={i}>
                <td style={{ textAlign: "left" }}>{MESES[f.mes - 1]}</td>
                <td style={{ textAlign: "left" }}>{f.line_name || f.line_code}</td>
                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(f.foto)}</td>
                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(f.ahora)}</td>
                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--accent-red, #C0392B)" }}>{fmt(f.delta)}</td>
              </tr>
            ))}</tbody>
          </table>
          {d.diferencias.length > 40 && (
            <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 6 }}>
              {t("div.andMore", { n: d.diferencias.length - 40 })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ImportActualsPage() {
  const t = useTranslations("import");
  const tc = useTranslations("common");
  const MESES = useTranslations("months").raw("long") as string[];
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  /**
   * Los dos caminos, tal como los pidió el owner (2026-08-16): «¿Por qué no
   * hacemos 2 botones, uno para los históricos 12 meses y el otro mes a mes?
   * Así queda todo bien configurado y protegido.»
   *
   * Se elige la INTENCIÓN, no un parámetro. Antes había que traducir «voy a
   * cerrar julio» a «alcance = mes», y esa traducción es donde se colaba el
   * error — más cuando el default era el que abarca todo.
   *
   * Arranca en `null` a propósito: el camino se elige, no te lo encontrás
   * abierto.
   */
  const [camino, setCamino] = useState<"historico" | "mensual" | null>(null);
  const [month, setMonth] = useState(1);
  const [estado, setEstado] = useState<MesesCerrados | null>(null);
  const [divergencias, setDivergencias] = useState<Divergencia[]>([]);

  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportGLDetailResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // La verificación que no cuadró. No se rechaza a secas: se muestra la
  // comparación bucket por bucket y el owner decide con el número delante.
  const [bloqueo, setBloqueo] = useState<VerificacionBloqueada | null>(null);

  useEffect(() => {
    getScenarios(HOTEL_ID).then(all => {
      const order = { ACTUAL: 0, FORECAST: 1, BUDGET: 2 } as Record<string, number>;
      const sorted = [...all].sort((a, b) => (order[a.type] ?? 9) - (order[b.type] ?? 9) || b.year - a.year || a.version.localeCompare(b.version));
      setScenarios(sorted);
      if (sorted.length && !scenarioId) setScenarioId(sorted[0].id);
    }).catch(e => setError(e instanceof Error ? e.message : t("errLoadingVersions")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const scen = useMemo(() => scenarios.find(s => s.id === scenarioId), [scenarios, scenarioId]);
  const monthParam = camino === "mensual" ? month : 0;

  // El estado del escenario se pide al elegirlo, no al escribir: avisar después
  // de escribir no es avisar.
  useEffect(() => {
    setEstado(null); setDivergencias([]);
    if (!scenarioId) return;
    let vivo = true;
    getMesesCerrados(scenarioId).then(e => { if (vivo) setEstado(e); }).catch(() => {});
    return () => { vivo = false; };
  }, [scenarioId]);

  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const reloadScenarios = async () => {
    const all = await getScenarios(HOTEL_ID);
    const order = { ACTUAL: 0, FORECAST: 1, BUDGET: 2 } as Record<string, number>;
    setScenarios([...all].sort((a, b) => (order[a.type] ?? 9) - (order[b.type] ?? 9) || b.year - a.year || a.version.localeCompare(b.version)));
  };
  const createVersions = async () => {
    setCreating(true); setCreateMsg(null); setError(null);
    try {
      const r = await bulkCreateStandardVersions(2027, HOTEL_ID);
      setCreateMsg(t("createdVersions", { creadas: r.created_count, omitidas: r.skipped_count }));
      await reloadScenarios();
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setCreating(false); }
  };
  const renameVersion = async () => {
    if (!scen) return;
    const nv = window.prompt(t("renamePrompt", { tipo: scen.type, anio: String(scen.year), version: scen.version }), scen.version);
    if (!nv || nv.trim() === scen.version) return;
    setCreating(true); setCreateMsg(null); setError(null);
    try {
      await renameScenario(scen.id, nv.trim());
      setCreateMsg(t("renamed", { nombre: nv.trim() }));
      await reloadScenarios();
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setCreating(false); }
  };
  const removeVersion = async () => {
    if (!scen) return;
    if (!window.confirm(t("deleteConfirm", { version: scenLabel(scen) }))) return;
    setCreating(true); setCreateMsg(null); setError(null);
    try {
      await deleteScenario(scen.id);
      setCreateMsg(t("deleted", { version: scenLabel(scen) }));
      const remaining = scenarios.filter(s => s.id !== scen.id);
      setScenarioId(remaining[0]?.id ?? "");
      await reloadScenarios();
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setCreating(false); }
  };

  const upload = async (dryRun: boolean, confirmar = false) => {
    if (!file || !scenarioId || !camino) return;
    // ⚠️ La carga histórica reemplaza meses que ya están cerrados. Se confirma
    // con el número delante —cuántos y cuáles— y solo al escribir de verdad: una
    // vista previa no toca nada, así que preguntar ahí sería ruido.
    if (camino === "historico" && !dryRun && estado?.tiene_datos) {
      const ms = estado.meses_cerrados.map(m => MESES[m - 1]).join(", ");
      const ok = window.confirm(t("historicConfirm", {
        esc: estado.escenario, n: estado.meses_cerrados.length, meses: ms,
      }));
      if (!ok) return;
    }
    setBusy(true); setError(null); setResult(null); setBloqueo(null); setDivergencias([]);
    try {
      const r = await importGLDetail(file, dryRun, true, scenarioId, confirmar,
                                     camino === "mensual" ? month : undefined);
      setResult(r);
      // Al terminar un cierre mensual, mirar los meses cerrados del forecast que
      // acaba de mover su corte. Es el enganche entre las dos pantallas: acá se
      // sube, la foto se saca en Escenarios, y en el medio hay días.
      if (!dryRun && (r.cut_advanced?.length ?? 0) > 0) {
        const ds = await Promise.all(
          r.cut_advanced!.map(c => getDivergencia(c.scenario_id).catch(() => null)));
        setDivergencias(ds.filter((d): d is Divergencia => d !== null));
      }
      if (!dryRun) getMesesCerrados(scenarioId).then(setEstado).catch(() => {});
    }
    catch (e) {
      if (e instanceof ErrorDeVerificacion) setBloqueo(e.informe);
      else setError(e instanceof Error ? e.message : tc("error"));
    }
    finally { setBusy(false); }
  };

  // El cuadro que vale de esta pantalla es el consolidado de la Vista previa:
  // es contra ESE que el owner compara el Dashboard antes de importar. Bajarlo
  // permite pegarlo al lado del Dashboard en vez de cotejarlo de memoria.
  const bajarExcel = async () => {
    if (!result) return;
    setError(null);
    const filas: FilaCuadro[] = result.blocks.map(b => {
      const p = b.pl_preview;
      return {
        label: b.label,
        valores: [b.matched ?? t("noTarget"),
          p ? p.revenue : null, p ? p.gop : null, p ? p.ebitda : null, p ? p.net : null,
          p ? p.stat_months.length : null],
      };
    });
    const sinMapear = result.blocks.flatMap(b => b.unmapped_depts).filter((v, i, a) => a.indexOf(v) === i);
    if (sinMapear.length) {
      filas.push({ label: t("unmappedDepts", { lista: sinMapear.join(", ") }),
        valores: [null, null, null, null, null, null] });
    }
    try {
      await bajarCuadros(`Import_Actuals_${result.dry_run ? "VistaPrevia" : "Importado"}`, [{
        titulo: result.dry_run ? t("previewTitle") : t("importedTitle"),
        subtitulo: `${scen ? scenLabel(scen) : ""} · `
          + (camino === "mensual" ? t("xls.onlyMonth", { mes: MESES[month - 1] }) : t("xls.allMonths"))
          + " · USD",
        hoja: t("xls.sheet"),
        columnas: [
          { label: t("xls.block"), ancho: 34, formato: "texto" },
          { label: t("targetVersion"), ancho: 30, formato: "texto" },
          { label: t("xls.revenue"), ancho: 16, formato: "usd" },
          { label: "GOP", ancho: 16, formato: "usd" },
          { label: "EBITDA", ancho: 16, formato: "usd" },
          { label: "Net", ancho: 16, formato: "usd" },
          { label: t("xls.months"), ancho: 8, formato: "num" },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelError"));
    }
  };

  const card: React.CSSProperties = { background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "18px 20px", marginBottom: 18 };
  const btn = (bg: string): React.CSSProperties => ({ padding: "9px 16px", borderRadius: 6, cursor: "pointer", background: bg, color: "#fff", border: "none", fontSize: 13, fontWeight: 600, textDecoration: "none", display: "inline-block" });
  const sel: React.CSSProperties = { padding: "7px 10px", borderRadius: 6, background: "var(--bg-input, #1b2130)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", fontSize: 13 };
  const step: React.CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--brand)", marginBottom: 8 };

  return (
    <div className="pag pag-media" style={{ padding: 24 }}>
      <IrA />
      <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>{t("title")}</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 18, maxWidth: "72ch" }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <strong>{c}</strong> })}
      </p>

      {/* 1 · versión + alcance */}
      <div style={card}>
        <div style={step}>{t("step1")}</div>
        <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("versionLabel")}&nbsp;
            <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} style={sel}>
              {scenarios.map(s => <option key={s.id} value={s.id}>{scenLabel(s)}</option>)}
            </select>
          </label>
          {scen && (
            <button onClick={renameVersion} disabled={creating} style={{ ...btn(creating ? "#555" : "#3a3f4b"), fontWeight: 500 }}>{t("rename")}</button>
          )}
          <button onClick={createVersions} disabled={creating} style={{ ...btn(creating ? "#555" : "#3a3f4b"), fontWeight: 500 }}>{creating ? t("creating") : t("createVersions")}</button>
          {scen && scen.status === "draft" && !isProtected(scen) && (
            <button onClick={removeVersion} disabled={creating} style={{ ...btn(creating ? "#555" : "#7a2e2e"), fontWeight: 500 }}>{t("deleteVersion")}</button>
          )}
          {scen && isProtected(scen) && (
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("protectedHint")}</span>
          )}
        </div>
        {createMsg && <div style={{ fontSize: 12, color: "var(--accent-green, #1A7F4B)", marginTop: 8 }}>{createMsg}</div>}
        {estado && <EstadoDelEscenario est={estado} />}
      </div>

      {/* 2 · el camino. Dos botones, no un parámetro que hay que traducir. */}
      <div style={card}>
        <div style={step}>{t("step2")}</div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <button
            onClick={() => setCamino("historico")}
            style={{
              textAlign: "left", padding: "14px 16px", borderRadius: 8, cursor: "pointer",
              background: camino === "historico" ? "rgba(26,107,60,.14)" : "transparent",
              border: `2px solid ${camino === "historico" ? "var(--positive)" : "var(--border-medium)"}`,
              color: "var(--text-primary)",
            }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>{t("historicTitle")}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6, lineHeight: 1.5 }}>
              {t.rich("historicDesc", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </div>
          </button>
          <button
            onClick={() => setCamino("mensual")}
            style={{
              textAlign: "left", padding: "14px 16px", borderRadius: 8, cursor: "pointer",
              background: camino === "mensual" ? "rgba(26,107,60,.14)" : "transparent",
              border: `2px solid ${camino === "mensual" ? "var(--positive)" : "var(--border-medium)"}`,
              color: "var(--text-primary)",
            }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>{t("monthlyTitle")}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6, lineHeight: 1.5 }}>
              {t.rich("monthlyDesc", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </div>
          </button>
        </div>

        {camino === "mensual" && (
          <div style={{ marginTop: 14, padding: "12px 14px", borderRadius: 8,
            border: "1px solid var(--positive)", background: "rgba(26,107,60,.08)" }}>
            <label style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("monthToClose")}&nbsp;
              <select value={month} onChange={e => setMonth(Number(e.target.value))} style={sel}>
                {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
              </select>
            </label>
            {/* El mes que se va a escribir, a la vista antes de subir — no
                enterrado en un texto. Es el camino que se recorre todos los
                meses con cada hotel: ahí un error se repite doce veces al año. */}
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--positive)", marginTop: 8 }}>
              {t.rich("willWrite", {
                mes: MESES[month - 1],
                grande: (c: React.ReactNode) => <span style={{ fontSize: 17 }}>{c}</span>,
              })}
            </div>
            {estado?.meses_cerrados.includes(month) && (
              <div style={{ fontSize: 12, color: "var(--accent-amber, #856404)", marginTop: 6 }}>
                {t("monthHasData", { mes: MESES[month - 1] })}
              </div>
            )}
          </div>
        )}

        {camino === "historico" && estado?.tiene_datos && (
          <div style={{ marginTop: 14, padding: "12px 14px", borderRadius: 8,
            border: "2px solid var(--accent-amber, #856404)", background: "rgba(133,100,4,.10)" }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--accent-amber, #856404)" }}>
              {t("historicWarnTitle", { n: estado.meses_cerrados.length })}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 5, lineHeight: 1.55 }}>
              {t.rich("historicWarnBody", {
                meses: estado.meses_cerrados.map(m => MESES[m - 1]).join(", "),
                b: (c: React.ReactNode) => <b>{c}</b>,
              })}
            </div>
          </div>
        )}

        {camino && scenarioId && (
          <div style={{ marginTop: 14 }}>
            <a href={exportDetailUrl(scenarioId, monthParam)} style={btn("var(--brand)")}>
              {camino === "mensual"
                ? t("downloadTemplateMonth", { mes: MESES[month - 1] })
                : t("downloadTemplateYear")}
            </a>
          </div>
        )}
      </div>

      {/* 3 · subir */}
      <div style={{ ...card, borderColor: camino ? "var(--brand)" : "var(--border-medium)", borderWidth: 2,
        opacity: camino ? 1 : .5 }}>
        <div style={step}>{t("step3")}</div>
        {!camino && (
          <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 10 }}>
            {t("pickPathFirst")}
          </div>
        )}
        {/* Los dos botones dicen QUE HACE CADA UNO. Antes decian «Vista previa»
            y «Cerrar Junio», y el owner (2026-08-18): «selecciono y dice vista
            previa y dice cerrar junio, no entiendo». «Cerrar» sonaba a tramite
            contable, no a guardar — y no habia forma de saber cual escribia. */}
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input type="file" accept=".xlsx" onChange={e => setFile(e.target.files?.[0] ?? null)} className="fin-input" />
          <button onClick={() => upload(true)} disabled={!file || !scenarioId || !camino || busy}
                  title={t("reviewHint")}
                  style={btn(file && scenarioId && camino && !busy ? "var(--brand)" : "#555")}>
            {busy ? "…" : t("reviewBtn")}
          </button>
          <button onClick={() => upload(false)} disabled={!file || !scenarioId || !camino || busy}
                  title={camino === "mensual"
                    ? t("saveMonthHint", { mes: MESES[month - 1] })
                    : t("saveYearHint")}
                  style={btn(file && scenarioId && camino && !busy ? "var(--accent-excel)" : "#555")}>
            {busy ? t("processing")
              : camino === "mensual" ? t("saveMonth", { mes: MESES[month - 1] })
                : t("saveYear")}
          </button>
        </div>
        {file && !busy && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8 }}>
            {t.rich("reviewVsSave", { b: (c: React.ReactNode) => <b>{c}</b> })}
          </div>
        )}
        {scen?.is_locked && (
          <div style={{ fontSize: 12, color: "var(--accent-amber, #856404)", marginTop: 10 }}>
            {t.rich("lockedWarn", {
              version: scenLabel(scen),
              b: (c: React.ReactNode) => <strong>{c}</strong>,
            })}
          </div>
        )}
        {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginTop: 10 }}>{error}</div>}
      </div>

      {/* La verificación frenó la carga. No se escribió nada: el 409 sale ANTES
          de tocar una sola fila. Se muestra la comparación completa y se exige
          una confirmación explícita — el owner puede tener una razón legítima,
          pero tiene que verla y aceptarla, no descubrirla meses después. */}
      {bloqueo && (
        <div style={{ ...card, borderColor: "var(--accent-red, #C0392B)", borderWidth: 2 }}>
          <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--accent-red, #C0392B)", marginBottom: 4 }}>
            {t("blockedNothingWritten", { error: bloqueo.error })}
          </div>
          <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 8, maxWidth: "72ch" }}>
            {bloqueo.que_hacer}
          </div>
          {bloqueo.bloques.map((b, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 700 }}>{b.label}</div>
              <TablaVerificacion rep={b.verificacion} />
            </div>
          ))}
          <button onClick={() => upload(false, true)} disabled={busy}
            style={{ ...btn(busy ? "#555" : "#7a2e2e"), marginTop: 6 }}>
            {busy ? t("processing") : t("uploadAnyway")}
          </button>
        </div>
      )}

      {result && (
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: result.dry_run ? "var(--accent-amber, #856404)" : "var(--accent-green, #1A7F4B)" }}>
              {result.dry_run ? t("previewHeading") : t("importedHeading")}
            </div>
            <button onClick={bajarExcel}
              title={t("excelHint")}
              style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer",
                background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
              ⬇ Excel
            </button>
          </div>
          <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ width: "100%", minWidth: 640 }}>
              <thead><tr>
                <th style={{ textAlign: "left" }}>{t("xls.block")}</th><th style={{ textAlign: "left" }}>{t("targetVersion")}</th>
                <th style={{ textAlign: "right" }}>{t("xls.revenue")}</th><th style={{ textAlign: "right" }}>GOP</th>
                <th style={{ textAlign: "right" }}>EBITDA</th><th style={{ textAlign: "right" }}>Net</th>
                <th style={{ textAlign: "center" }}>{t("xls.months")}</th>
              </tr></thead>
              <tbody>{result.blocks.map((b, i) => {
                const p = b.pl_preview;
                return (
                  <tr key={i}>
                    <td style={{ textAlign: "left" }}>{b.label}</td>
                    <td style={{ textAlign: "left", color: b.matched ? "var(--accent-green, #1A7F4B)" : "var(--accent-red, #C0392B)" }}>{b.matched ?? t("noTarget")}</td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{p ? fmt(p.revenue) : "—"}</td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{p ? fmt(p.gop) : "—"}</td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{p ? fmt(p.ebitda) : "—"}</td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 700 }}>{p ? fmt(p.net) : "—"}</td>
                    <td style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: 12 }}>{p ? `${p.stat_months.length}` : "—"}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
          {/* El corte del forecast se movió solo. Tiene que verse: es lo que
              decide qué meses del Forecast Working salen del Actual y cuáles
              siguen siendo proyección. */}
          {(result.cut_advanced?.length ?? 0) > 0 && (
            <div style={{ fontSize: 12.5, color: "var(--positive)", marginTop: 10, lineHeight: 1.6 }}>
              {result.cut_advanced!.map(c => (
                <div key={c.scenario_id}>
                  {t.rich("cutAdvanced", {
                    version: c.version,
                    hasta: MESES[c.actuals_through - 1],
                    desde: c.actuals_through < 12 ? MESES[c.actuals_through] : "—",
                    b: (x: React.ReactNode) => <b>{x}</b>,
                  })}
                </div>
              ))}
            </div>
          )}
          {result.blocks.filter(b => b.verificacion).map((b, i) => (
            <div key={`v${i}`} style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--border-medium)" }}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--brand)" }}>
                {t("verificationOf")} · {b.label}
              </div>
              <TablaVerificacion rep={b.verificacion!} />
            </div>
          ))}
          {/* Meses que el archivo traía y el cierre mensual NO escribió. Que se
              vea: el owner tiene que saber que el archivo tenía más de lo que
              entró, y que eso fue a propósito. */}
          {(result.meses_descartados?.length ?? 0) > 0 && (
            <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 10, lineHeight: 1.6 }}>
              {t.rich("discardedMonths", {
                meses: result.meses_descartados!.map(m => MESES[m - 1]).join(", "),
                mes: MESES[(result.mes_de_cierre ?? 1) - 1],
                b: (c: React.ReactNode) => <b>{c}</b>,
              })}
            </div>
          )}

          {/* El paso siguiente del ciclo, que hoy vive en OTRA pantalla. No se
              hace solo: el owner revisa durante DÍAS antes de sacar la foto, así
              que la foto tiene que ser un acto suyo. Alcanza con no dejarlo
              huérfano. */}
          {!result.dry_run && divergencias.some(d => d.meses_cerrados_sin_foto.length > 0) && (
            <div style={{ marginTop: 12, padding: "12px 14px", borderRadius: 8,
              border: "1px solid var(--brand)", background: "rgba(45,58,92,.12)" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
                {t("snapshotReminderTitle")}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 5, lineHeight: 1.55 }}>
                {t.rich("snapshotReminderBody", { b: (c: React.ReactNode) => <b>{c}</b> })}
              </div>
              <a href="/scenarios" style={{ ...btn("var(--brand)"), marginTop: 10 }}>{t("goToScenarios")}</a>
            </div>
          )}

          {divergencias.map(d => <SenalDeDivergencia key={d.scenario_id} d={d} />)}

          {result.blocks.some(b => b.unmapped_depts.length > 0) && (
            <div style={{ fontSize: 12, color: "var(--accent-amber, #856404)", marginTop: 10 }}>
              {t("unmappedDepts", { lista: result.blocks.flatMap(b => b.unmapped_depts).filter((v, i, a) => a.indexOf(v) === i).join(", ") })}
            </div>
          )}
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12 }}>
            {t("compareBeforeImport")}
          </p>
        </div>
      )}
    </div>
  );
}
