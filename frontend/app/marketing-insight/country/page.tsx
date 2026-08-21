"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getScenarios, getCountryMix, getCountryMixEntry, saveCountryMixEntry, importCountryXml,
  urlPlantillaCountry, subirPlantillaCountry, authHeaders, CountryXmlPisaria, CountryXmlElegirMes,
  type Scenario, type CountryMix, type CountryMixEntryRow, type ChannelMetric,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro, type Cuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const numF = (v: string) => { const n = parseFloat((v || "").toString().replace(/[, %]/g, "")); return isNaN(n) ? 0 : n; };
const pct1 = (v: number) => (v * 100).toFixed(1) + "%";
const pp1 = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(1) + "pp";
const int0 = (v: number) => Math.round(v).toLocaleString("en-US");
const BLANK_ROWS = 6;   // filas vacías extra para agregar países
const PIE_COLORS = ["#1b3a6b","#3A6FD8","#6aa84f","#8e5fc0","#1f9bb3","#e8923a","#5a6b82","#9b2d2d","#5a7d2a","#9aa1ad"];
// Recharts tipa el label del Pie con SUS props, y `pct` es un campo nuestro: no
// entra en ese tipo. Va acá arriba y no inline porque el `<Pie>` ocupa dos
// líneas y el eslint-disable-next-line cubría la equivocada.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const pieLabel = (p: any) => `${(p.pct * 100).toFixed(0)}%`;

export default function CountryMixPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("country");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cada selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca
  // se eligio abre con el preferido del owner.
  const [actId, setActId] = useEscenarioDe("marketing-insight/country:actual", scenarios, "actual");
  const [budId, setBudId] = useEscenarioDe("marketing-insight/country:budget", scenarios, "budget", undefined, true);
  const [ytd, setYtd] = useState(12);
  const [metric, setMetric] = useState<ChannelMetric>("rooms");
  const [act, setAct] = useState<CountryMix | null>(null);
  const [bud, setBud] = useState<CountryMix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  // editor
  const [editing, setEditing] = useState(false);
  const [editScn, setEditScn] = useState("");
  const [grid, setGrid] = useState<{ country: string; values: string[] }[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  // YTD por defecto = último mes con datos del Actual (métrica rooms). Se hace
  // una sola vez, cuando el Actual queda resuelto: si se recalculara en cada
  // cambio de escenario le pisaría al usuario el YTD que eligió a mano.
  const yaFijoYtd = useRef(false);
  const xmlRef = useRef<HTMLInputElement>(null);
  const plaRef = useRef<HTMLInputElement>(null);
  /** El archivo en revisión, esperando el «Guardar». */
  const [pendiente, setPendiente] = useState<File | null>(null);
  /** El XML que el backend frenó por pisar meses ya corregidos a mano, con los
   *  meses en cuestión. Mientras esté, se ofrece sobrescribir. */
  const [xmlPisaria, setXmlPisaria] = useState<{ archivo: File; meses: number[] } | null>(null);
  /** El XML trae varios meses y se sube uno por vez: acá esperan los meses que
   *  el archivo ofrece, hasta que se elija uno. */
  const [xmlMeses, setXmlMeses] = useState<{ archivo: File; meses: number[] } | null>(null);

  /** Baja la grilla EDITABLE. El «⬇ Excel» de al lado es un reporte —trae
   *  variance en puntos porcentuales— y no se puede volver a subir. */
  async function bajarPlantilla() {
    if (!actId) return;
    setMsgXml(null);
    try {
      const res = await fetch(urlPlantillaCountry(actId), { headers: authHeaders() });
      if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `CountryMix_${actId.slice(0, 8)}.xlsx`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (ex) { setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`); }
  }

  /** Sube la plantilla. Primero REVISA —muestra qué cambia— y recién con el
   *  segundo clic guarda: esto reemplaza el mix entero del escenario. */
  async function subirPlantilla(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !actId) return;
    setSubiendo(true); setMsgXml(null);
    try {
      const r = await subirPlantillaCountry(actId, f, false);
      if (!r.total_cambios) {
        setMsgXml(t("archivoSinCambios"));
        setPendiente(null);
      } else {
        const det = r.cambios.slice(0, 6).map(c =>
          `${c.pais} (${c.metric === "rooms" ? t("abrevHab") : "pax"}): ${c.antes ?? "—"} → ${c.ahora ?? "—"}`).join(" · ");
        setMsgXml(t("revision", { n: r.total_cambios, filas: r.filas, det })
                  + (r.total_cambios > 6 ? t("revisionMas", { n: r.total_cambios - 6 }) : "")
                  + t("revisionAplicar"));
        setPendiente(f);
      }
    } catch (ex) {
      setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
      setPendiente(null);
    } finally {
      setSubiendo(false);
      if (plaRef.current) plaRef.current.value = "";
    }
  }

  async function guardarPlantilla() {
    if (!pendiente || !actId) return;
    setSubiendo(true);
    try {
      const r = await subirPlantillaCountry(actId, pendiente, true);
      setMsgXml(t("guardadoPlantilla", { n: r.total_cambios, celdas: r.celdas ?? 0, filas: r.filas }));
      setPendiente(null);
      load(actId, budId, ytd, metric);
    } catch (ex) { setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`); }
    finally { setSubiendo(false); }
  }
  const [subiendo, setSubiendo] = useState(false);
  const [msgXml, setMsgXml] = useState<string | null>(null);

  /** Sube el `res_statistics1` de Opera al escenario ACTUAL.
   *
   *  El mensaje dice qué países cayeron en «Others» y con cuántas noches. No
   *  es adorno: con el archivo del owner, Alemania (64), Francia (53) y España
   *  (45) están fuera de la lista y son MÁS grandes que Suecia (33) o Dinamarca
   *  (20), que sí están. Sin verlo, promover un país se decide de memoria. */
  async function subirXml(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !actId) return;
    await correrImport(f, false);
    if (xmlRef.current) xmlRef.current.value = "";
  }

  /** El import de verdad. Sale aparte de `subirXml` porque se repite: la
   *  primera vez sin sobrescribir, y —si el backend frenó y el usuario
   *  acepta— una segunda con `sobrescribir`. */
  async function correrImport(f: File, sobrescribir: boolean, mes?: number) {
    if (!actId) return;
    setSubiendo(true); setMsgXml(null);
    if (!sobrescribir) setXmlPisaria(null);
    try {
      const r = await importCountryXml(actId, f, { sobrescribir, month: mes });
      const meses = r.meses.map(m => MONTHS[m - 1]).join(", ");
      const cola = r.en_others.length
        ? t("othersCabeza", { n: r.en_others.length })
          + r.en_others.slice(0, 5).map(x => `${x.pais} ${Math.round(x.noches)}`).join(" · ")
          + t("othersCola")
        : "";
      setMsgXml(
        t("xmlCargado", {
          year: r.year, meses,
          noches: Math.round(r.total_noches).toLocaleString("en-US"),
          pax: Math.round(r.total_pax).toLocaleString("en-US"),
          paises: r.paises,
        })
        + (r.lista_inferida ? t("listaInferida") : "")
        + cola);
      load(actId, budId, ytd, metric);
      setXmlPisaria(null); setXmlMeses(null);
    } catch (ex) {
      if (ex instanceof CountryXmlElegirMes) {
        // No es un fallo: falta elegir el mes.
        setXmlMeses({ archivo: f, meses: ex.meses });
        setMsgXml(ex.message);
      } else if (ex instanceof CountryXmlPisaria) {
        // No es un fallo: es una decisión de quien sube.
        setXmlPisaria({ archivo: f, meses: ex.meses });
        setMsgXml(`⚠️ ${ex.message}`);
      } else {
        setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
        setXmlPisaria(null); setXmlMeses(null);
      }
    } finally {
      setSubiendo(false);
    }
  }
  useEffect(() => {
    if (!actId || yaFijoYtd.current) return;
    yaFijoYtd.current = true;
    (async () => {
      try {
        const e = await getCountryMixEntry(actId, "rooms");
        let maxM = 0;
        e.rows.forEach(r => r.values.forEach((v, i) => { if (v) maxM = Math.max(maxM, i + 1); }));
        if (maxM) setYtd(maxM);
      } catch { /* ignore */ }
    })();
  }, [actId]);

  const load = useCallback(async (aid: string, bid: string, y: number, mt: ChannelMetric) => {
    if (!aid || !bid) return;
    setLoading(true); setError(null);
    try { const [a, b] = await Promise.all([getCountryMix(aid, y, mt), getCountryMix(bid, y, mt)]); setAct(a); setBud(b); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (actId && budId) load(actId, budId, ytd, metric); }, [actId, budId, ytd, metric, load]);

  const isOther = (c: string) => /^(others?|otros?|otro|resto)$/i.test(c.trim());
  const rows = useMemo(() => {
    if (!act) return [];
    const budByC = new Map((bud?.countries ?? []).map(c => [c.country, c.pct]));
    const mapped = act.countries.map(c => {
      const bPct = budByC.get(c.country) ?? 0;
      return { country: c.country, value: c.value, aPct: c.pct, bPct, varpp: (c.pct - bPct) * 100 };
    });
    // "Others"/"Otros" siempre al final, aunque tenga % alto
    return [...mapped.filter(r => !isOther(r.country)), ...mapped.filter(r => isOther(r.country))];
  }, [act, bud]); // eslint-disable-line react-hooks/exhaustive-deps
  // Donut: top 9 países + "Otros" agrupado (para no saturar)
  const pie = useMemo(() => {
    if (!rows.length) return [] as { country: string; pct: number }[];
    const top = rows.slice(0, 9).map(r => ({ country: r.country, pct: r.aPct }));
    const rest = rows.slice(9).reduce((t, r) => t + r.aPct, 0);
    return rest > 0 ? [...top, { country: t("otros"), pct: rest }] : top;
  }, [rows, t]);
  const top2 = rows.slice(0, 2);
  const top2pct = top2.reduce((t, r) => t + r.aPct, 0);

  function blankRows(n: number) { return Array.from({ length: n }, () => ({ country: "", values: Array(12).fill("") })); }
  async function openEditor(target: string) {
    if (!target) return;
    setMsg(null);
    try {
      const e = await getCountryMixEntry(target, metric);
      const existing = e.rows.map(r => ({ country: r.country, values: r.values.map(v => v ? String(v) : "") }));
      setGrid([...existing, ...blankRows(BLANK_ROWS)]);
      setEditScn(target);
      setEditing(true);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }
  async function reloadEditor(target: string) {
    try {
      const e = await getCountryMixEntry(target, metric);
      const existing = e.rows.map(r => ({ country: r.country, values: r.values.map(v => v ? String(v) : "") }));
      setGrid([...existing, ...blankRows(BLANK_ROWS)]);
    } catch { /* ignore */ }
  }
  function setCountry(ri: number, v: string) { setGrid(prev => prev.map((row, i) => i === ri ? { ...row, country: v } : row)); }
  function setCell(ri: number, mi: number, v: string) { setGrid(prev => prev.map((row, i) => i === ri ? { ...row, values: row.values.map((c, j) => j === mi ? v : c) } : row)); }
  // ci: 0 = país, 1..12 = meses
  function paste(ri: number, ci: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const cells = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    setGrid(prev => {
      const next = prev.map(r => ({ country: r.country, values: [...r.values] }));
      const need = ri + cells.length - next.length;
      for (let k = 0; k < need + 2; k++) next.push({ country: "", values: Array(12).fill("") });
      cells.forEach((rowc, dr) => {
        const r = ri + dr;
        rowc.forEach((cell, dc) => {
          const c = ci + dc;
          if (c === 0) next[r].country = cell.trim();
          else if (c >= 1 && c <= 12) next[r].values[c - 1] = String(numF(cell));
        });
      });
      return next;
    });
  }
  async function saveEntry() {
    if (!editScn) return;
    setSaving(true); setMsg(null);
    try {
      const payload: CountryMixEntryRow[] = grid
        .filter(r => r.country.trim())
        .map(r => ({ country: r.country.trim(), values: r.values.map(c => numF(c)) }));
      const res = await saveCountryMixEntry(editScn, payload, metric);
      const sLbl = scenarios.find(s => s.id === editScn);
      setMsg(t("guardadoEntry", { metric: metric === "pax" ? "Pax" : t("metricRooms"), scn: sLbl ? scnLabel(sLbl) : editScn, n: res.rows_saved }));
      setEditing(false);
      load(actId, budId, ytd, metric);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setSaving(false); }
  }

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // DOS hojas —Habitaciones y Pax— con los DOCE meses en orden.
  //
  // «Necesito que el Excel aparezca por separado rooms y pax en tabs diferentes
  // y meses en orden» (owner, 18-ago-2026). Antes bajaba UNA sola hoja, con la
  // métrica que estuviera puesta en pantalla y SIN meses: solo el acumulado
  // YTD. O sea que para tener las dos había que bajar dos archivos, y el
  // detalle mensual no salía por ningún lado.
  //
  // Los porcentajes van como FRACCIÓN y la variación en puntos también
  // (0.012 = +1.2pp), para que Excel los sume y los formatee como porcentaje.
  async function bajarExcel() {
    setMsg(null);
    if (!actId || !budId) { setMsg(`Error: ${t("faltaEscenario")}`); return; }
    const aScn = scenarios.find(s => s.id === actId), bScn = scenarios.find(s => s.id === budId);
    try {
      const cuadros: Cuadro[] = [];
      for (const mt of ["rooms", "pax"] as ChannelMetric[]) {
        // El detalle por mes sale de la grilla cruda; los % del mismo cálculo
        // que usa la pantalla, para que el Excel y la pantalla no discrepen.
        const [grilla, aMix, bMix] = await Promise.all([
          getCountryMixEntry(actId, mt),
          getCountryMix(actId, ytd, mt),
          getCountryMix(budId, ytd, mt),
        ]);
        const porMes = new Map(grilla.rows.map(r => [r.country, r.values]));
        const bPct = new Map(bMix.countries.map(c => [c.country, c.pct]));
        const orden = [...aMix.countries.filter(c => !isOther(c.country)),
                       ...aMix.countries.filter(c => isOther(c.country))];
        if (!orden.length) continue;

        const filas: FilaCuadro[] = orden.map(c => {
          const v = porMes.get(c.country) ?? new Array(12).fill(0);
          const b = bPct.get(c.country) ?? 0;
          return { label: c.country, valores: [...v, c.value, c.pct, b, c.pct - b] };
        });
        const sum = (i: number) => orden.reduce((t, c) => t + ((porMes.get(c.country) ?? [])[i] ?? 0), 0);
        filas.push({
          label: t("totalPaises", { n: orden.length }), es_total: true,
          valores: [...Array.from({ length: 12 }, (_, i) => sum(i)),
                    aMix.total,
                    orden.reduce((t, c) => t + c.pct, 0),
                    orden.reduce((t, c) => t + (bPct.get(c.country) ?? 0), 0),
                    orden.reduce((t, c) => t + c.pct - (bPct.get(c.country) ?? 0), 0)],
        });

        cuadros.push({
          titulo: `Country Mix — ${mt === "pax" ? "Pax" : t("metricRooms")}`,
          subtitulo: `${aScn ? scnLabel(aScn) : "Actual"} vs ${bScn ? scnLabel(bScn) : "Budget"}`
            + t("excelSubtitulo", { mes: MONTHS[ytd - 1] }),
          hoja: mt === "pax" ? "Pax" : t("metricRooms"),
          columnas: [
            { label: t("countryMarket"), ancho: 26, formato: "texto" as const },
            // Los doce meses, en orden.
            ...MONTHS.map(m => ({ label: m, ancho: 9, formato: "num" as const })),
            { label: `YTD ${MONTHS[ytd - 1]}`, ancho: 12, formato: "num" as const },
            { label: "Mix Actual", ancho: 12, formato: "pct" as const },
            { label: "Mix Budget", ancho: 12, formato: "pct" as const },
            { label: "Variance (pp)", ancho: 14, formato: "pct" as const },
          ],
          filas,
        });
      }
      if (!cuadros.length) { setMsg(`Error: ${t("noDataExport")}`); return; }
      await bajarCuadros("Country_Mix", cuadros);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const th: React.CSSProperties = { padding: "8px 14px", fontSize: 11, color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.4 };
  const td: React.CSSProperties = { padding: "9px 14px", fontSize: 14, textAlign: "right" };
  const inp: React.CSSProperties = { width: "100%", textAlign: "right", padding: "4px 6px", background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 3, color: "var(--text-primary)", fontSize: 12.5, outline: "none" };

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "22px 26px 48px" }}>
      <IrA esc={budId} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Country Mix <span style={{ color: "var(--brand)" }}>vs Budget</span></h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>{t("subtitle", { hotel: hotel.nombre })}<b style={{ color: "var(--text-primary)" }}>YTD {MONTHS[ytd-1]}</b> · <b style={{ color: "var(--text-primary)" }}>{metric === "pax" ? "Pax" : t("metricRooms")}</b> · {t("variancePp")}</p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("metric")}</span>
            <div style={{ display: "flex", border: "1px solid var(--border-medium)", borderRadius: 5, overflow: "hidden" }}>
              {(["rooms", "pax"] as ChannelMetric[]).map(mt => (
                <button key={mt} onClick={() => setMetric(mt)} style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none", background: metric === mt ? "var(--brand)" : "var(--bg-input)", color: metric === mt ? "#fff" : "var(--text-secondary)" }}>{mt === "rooms" ? t("metricRooms") : "Pax"}</button>
              ))}
            </div>
          </div>
          <input ref={xmlRef} type="file" accept=".xml,.XML" style={{ display: "none" }} onChange={subirXml} />
          <button onClick={() => xmlRef.current?.click()} disabled={subiendo}
            title={t("xmlTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: subiendo ? "default" : "pointer", background: "var(--accent-xml)", color: "#fff", border: "none", alignSelf: "flex-end", opacity: subiendo ? 0.6 : 1 }}>
            {subiendo ? t("uploading") : "⬆ XML Opera"}
          </button>
          <input ref={plaRef} type="file" accept=".xlsx,.XLSX" style={{ display: "none" }} onChange={subirPlantilla} />
          <button onClick={bajarPlantilla} title={t("plantillaTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--brand)", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{t("plantillaBtn")}</button>
          <button onClick={() => plaRef.current?.click()} disabled={subiendo}
            title={t("plantillaUpTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: subiendo ? "default" : "pointer", background: "var(--brand)", color: "#fff", border: "none", alignSelf: "flex-end", opacity: subiendo ? 0.6 : 1 }}>{t("plantillaUpBtn")}</button>
          <button onClick={() => openEditor(actId)} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--positive)", color: "#fff", border: "none", alignSelf: "flex-end" }}>{t("loadCountries")}</button>
          <button onClick={bajarExcel} title={t("excelTitle")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", alignSelf: "flex-end" }}>⬇ Excel</button>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{tc("print")}</button>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("ytdThrough")}</span><select value={ytd} onChange={e => setYtd(Number(e.target.value))} style={sel}>{MONTHS.map((m, i) => <option key={i} value={i+1} style={{ background: "var(--bg-input)" }}>{m}</option>)}</select></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Actual</span><select value={actId} onChange={e => setActId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Budget</span><select value={budId} onChange={e => setBudId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        </div>
      </div>

      {msgXml && (
        <div style={{ fontSize: 12.5, marginBottom: 8, padding: "8px 12px", borderRadius: 6,
                      whiteSpace: "pre-line",
                      border: `1px solid ${msgXml.startsWith("Error") ? "var(--negative)" : "var(--positive)"}`,
                      background: msgXml.startsWith("Error") ? "rgba(239,68,68,.08)" : "rgba(38,166,154,.08)",
                      color: msgXml.startsWith("Error") ? "var(--negative)" : "var(--positive)" }}>
          {msgXml}
          {xmlMeses && (
            <div style={{ marginTop: 8, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              {xmlMeses.meses.map(m => (
                <button key={m} disabled={subiendo}
                  onClick={() => correrImport(xmlMeses.archivo, false, m)}
                  style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "none" }}>
                  {MONTHS[m - 1]}
                </button>
              ))}
              <button onClick={() => { setXmlMeses(null); setMsgXml(null); }}
                style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
                {tc("cancel")}
              </button>
            </div>
          )}
          {xmlPisaria && (
            <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <button onClick={() => correrImport(xmlPisaria.archivo, true, xmlPisaria.meses[0])} disabled={subiendo}
                style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--negative)", color: "#fff", border: "none" }}>
                {t("overwriteXml", { meses: xmlPisaria.meses.map(m => MONTHS[m - 1]).join(", ") })}
              </button>
              <button onClick={() => { setXmlPisaria(null); setMsgXml(null); }}
                style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
                {t("leaveAsIs")}
              </button>
            </div>
          )}
          {pendiente && (
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button onClick={guardarPlantilla} disabled={subiendo}
                style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--positive)", color: "#fff", border: "none" }}>
                {t("saveChanges")}
              </button>
              <button onClick={() => { setPendiente(null); setMsgXml(null); }}
                style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
                {t("discard")}
              </button>
            </div>
          )}
        </div>
      )}
      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {msg && <div style={{ color: msg.startsWith("Error") ? "var(--negative)" : "var(--positive)", fontSize: 12.5, marginBottom: 8 }}>{msg}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{tc("loading")}</div>}

      {/* Editor */}
      {editing && (
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--positive)", borderRadius: 8, overflow: "hidden", marginBottom: 16 }}>
          <div style={{ padding: "10px 16px", background: "rgba(38,166,154,0.1)", borderBottom: "1px solid var(--border-medium)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{t("loadTitle")}</span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 700 }}>{t("saveIn")}</span>
              <select value={editScn} onChange={e => { setEditScn(e.target.value); reloadEditor(e.target.value); }} style={{ ...sel, padding: "4px 8px", fontSize: 12 }}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select>
              <button onClick={() => setGrid(prev => [...prev, ...blankRows(3)])} style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>{t("addRows")}</button>
              <button onClick={saveEntry} disabled={saving} style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: saving ? "default" : "pointer", background: "var(--positive)", color: "#fff", border: "none" }}>{saving ? tc("saving") : `💾 ${tc("save")}`}</button>
              <button onClick={() => setEditing(false)} style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{tc("close")}</button>
            </div>
          </div>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead><tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ ...th, textAlign: "left", minWidth: 160 }}>{t("countryMarket")}</th>
                {MONTHS.map(m => <th key={m} style={{ ...th, textAlign: "right" }}>{m}</th>)}
              </tr></thead>
              <tbody>
                {grid.map((row, ri) => (
                  <tr key={ri} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "2px 6px" }}><input value={row.country} placeholder={t("countryPlaceholder")} onChange={e => setCountry(ri, e.target.value)} onPaste={e => paste(ri, 0, e)} style={{ ...inp, textAlign: "left", fontWeight: 600 }} /></td>
                    {row.values.map((c, mi) => (
                      <td key={mi} style={{ padding: "2px 6px" }}><input className="mono" value={c} onChange={e => setCell(ri, mi, e.target.value)} onPaste={e => paste(ri, mi + 1, e)} onFocus={e => e.target.select()} style={inp} /></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: "8px 14px", fontSize: 11.5, color: "var(--text-secondary)" }}>{t("pasteHint")}</div>
        </div>
      )}

      {!loading && act && bud && <>
        {/* Tabla */}
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, overflow: "hidden", marginBottom: 18 }}>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                  <th style={{ ...th, textAlign: "left" }}>{t("countryMarket")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{metric === "pax" ? "Pax" : t("nights")}</th>
                  <th style={{ ...th, textAlign: "right" }}>Actual YTD {MONTHS[ytd-1]}</th>
                  <th style={{ ...th, textAlign: "right" }}>Budget</th>
                  <th style={{ ...th, textAlign: "right" }}>Variance</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.country} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "9px 14px", fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>{r.country}</td>
                    <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{int0(r.value)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 700, color: "var(--text-primary)" }}>{pct1(r.aPct)}</td>
                    <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{pct1(r.bPct)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: Math.abs(r.varpp) < 0.05 ? "var(--text-secondary)" : r.varpp >= 0 ? "var(--positive)" : "var(--negative)" }}>{pp1(r.varpp)}</td>
                  </tr>
                ))}
                {rows.length > 0 && (
                  <tr style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(58,111,216,0.08)", fontWeight: 800 }}>
                    <td style={{ padding: "9px 14px", fontSize: 14, fontWeight: 800 }}>{t("totalPaises", { n: rows.length })}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800 }}>{int0(act.total)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800 }}>{pct1(rows.reduce((t, r) => t + r.aPct, 0))}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{pct1(rows.reduce((t, r) => t + r.bPct, 0))}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{pp1(rows.reduce((t, r) => t + r.varpp, 0))}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Donut: rooms sold by country mix */}
        {pie.length > 0 && (
          <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "16px 18px" }}>
            <div style={{ fontSize: 14, fontWeight: 700, textAlign: "center", marginBottom: 4 }}>{metric === "pax" ? "Pax" : "Rooms sold"} by Country Mix · Actual YTD {MONTHS[ytd-1]}</div>
            <div style={{ position: "relative", width: "100%", height: 360 }}>
              <ResponsiveContainer width="100%" height={360}>
                <PieChart>
                  <Pie data={pie} dataKey="pct" nameKey="country" cx="50%" cy="50%" innerRadius={92} outerRadius={140} paddingAngle={1} stroke="var(--bg-elevated)" strokeWidth={2}
                       label={pieLabel} labelLine={false}>
                    {pie.map((p, i) => <Cell key={p.country} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} formatter={(v: any, n: any) => [`${(v*100).toFixed(1)}%`, n]} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
              {top2.length >= 2 && (
                <div style={{ position: "absolute", top: "calc(50% - 14px)", left: 0, right: 0, textAlign: "center", transform: "translateY(-50%)", pointerEvents: "none" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5 }}>{top2.map(r => r.country).join(" + ")}</div>
                  <div style={{ fontSize: 30, fontWeight: 800, color: "var(--brand)", lineHeight: 1.1 }}>{(top2pct*100).toFixed(0)}%</div>
                  <div style={{ fontSize: 10.5, color: "var(--text-secondary)" }}>{t("deTotal", { unidad: metric === "pax" ? "pax" : t("nightsLower") })}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {!act.has_data && <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 12 }}>{t("noCountries")}<b>{t("loadCountries")}</b>{t("noCountriesTail")}</p>}
        <p style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 12, fontStyle: "italic" }}>{t("note")}</p>
      </>}
    </div>
  );
}
