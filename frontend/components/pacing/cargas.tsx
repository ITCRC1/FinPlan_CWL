"use client";
/**
 * Cargas y configuración del PACING.
 *
 * El flujo que pidió el owner: *«solo subo los XMLs actualizados y que
 * refresquen los datos»*. Se sueltan los archivos de Opera juntos —History &
 * Forecast Rooms Only, Total Revenue y los Reservations Entered On— y la
 * pantalla dice qué es cada uno antes de guardar. Rooms vs Total se decide por
 * monto, no por nombre de archivo.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  deletePacingReservations, deletePacingSnapshot, getPacingConfig, getPacingResvSummary, getPacingSnapshots,
  getScenarios, pacingMetaFromScenario, pacingPreview, pacingUpload, putPacingConfig,
  type PacingArchivo, type PacingConfig, type PacingKind, type PacingResvSummary, type PacingSnapshotRow,
  type PacingYearBlock, type Scenario,
} from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { Aviso, Tabla, boton, botonPrimario, card, n0, select, td, tdL, th, usd0, useMeses, usePacing } from "./comun";

const inp = {
  width: 70, padding: "3px 5px", fontSize: 12, textAlign: "right" as const, border: "1px solid var(--border-medium)",
  borderRadius: 4, background: "var(--bg-input)", color: "var(--text-primary)",
};

/**
 * Qué subir cada semana y con qué rango de fechas pedirlo en Opera.
 *
 * Owner, 2026-10-05: *«qué fecha de archivo debo subir… para no perderme cada
 * semana, de qué fecha a qué fecha y qué archivo»*.
 *
 * Las fechas se calculan con el día de hoy en vez de escribirse a mano: una
 * nota con fechas fijas es correcta una semana y mentira la siguiente, y el
 * costo de equivocarse acá no es visible —un export corto no da error, da un
 * STLY que no aparece y un pacing que parece vacío—.
 *
 * ⚠️ El rango de History & Forecast va del año PASADO al que VIENE porque el
 * motor compara cada año contra el anterior (`pacing.construir` arma T y T−1):
 * con el presupuesto 2027 abierto hacen falta 2026 y 2027, y el pacing del año
 * en curso además necesita 2025. Y tiene que ser el AÑO COMPLETO: `stly_foto`
 * descarta una foto con menos de 300 días del año que compara.
 *
 * ⚠️ El de Reservations va por fecha de CREACIÓN, no de llegada, y arranca en
 * la migración: para saber qué había en libros a una fecha pasada hay que
 * tener las reservas creadas ANTES de esa fecha (`reservas_cubren` exige
 * `min_ins <= corte − 1 año`).
 */
function NotaSemanal({ migracion }: { migracion?: string | null }) {
  const t = useTranslations("pacing.cargas");
  const M = useMeses();
  const hoy = new Date();
  const Y = hoy.getFullYear();
  const dia = (d: Date) => `${d.getDate()} ${M[d.getMonth()]} ${d.getFullYear()}`;
  const rangoHF = `${dia(new Date(Y - 1, 0, 1))} → ${dia(new Date(Y + 1, 11, 31))}`;
  const rangoResv = `${migracion || t("notaDesdeMigracion")} → ${dia(hoy)}`;
  const filas: [string, string, string][] = [
    [t("hfTotal"), t("notaEstadia"), rangoHF],
    [t("hfRooms"), t("notaEstadia"), rangoHF],
    [t("tipoResv"), t("notaCreacion"), rangoResv],
  ];
  return (
    <div style={{ border: "1px solid var(--border-medium)", borderRadius: 6,
                  padding: "8px 10px", marginBottom: 10, fontSize: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{t("notaTitulo")}</div>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <tbody>
          {filas.map(([archivo, campo, rango]) => (
            <tr key={archivo}>
              <td style={{ padding: "2px 10px 2px 0", whiteSpace: "nowrap" }}>{archivo}</td>
              <td style={{ padding: "2px 10px 2px 0", color: "var(--text-secondary)",
                           whiteSpace: "nowrap" }}>{campo}</td>
              <td style={{ padding: "2px 0", fontFamily: "var(--font-mono, monospace)",
                           whiteSpace: "nowrap" }}>{rango}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ color: "var(--text-secondary)", marginTop: 6 }}>{t("notaCorte")}</div>
    </div>
  );
}


export function Cargas() {
  const t = useTranslations("pacing.cargas");
  const { recargar } = usePacing();
  const [files, setFiles] = useState<File[]>([]);
  const [vista, setVista] = useState<PacingArchivo[] | null>(null);
  const [kinds, setKinds] = useState<Record<string, PacingKind>>({});
  const [resultado, setResultado] = useState<PacingArchivo[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [snaps, setSnaps] = useState<PacingSnapshotRow[]>([]);
  const [resv, setResv] = useState<PacingResvSummary | null>(null);

  const listas = useCallback(() => {
    getPacingSnapshots().then(setSnaps).catch(() => {});
    getPacingResvSummary().then(setResv).catch(() => {});
  }, []);
  useEffect(() => { listas(); }, [listas]);

  const elegir = async (l: FileList | null) => {
    const fs = Array.from(l ?? []);
    setFiles(fs); setVista(null); setResultado(null); setErr(null); setKinds({});
    if (!fs.length) return;
    setOcupado(true);
    try { setVista((await pacingPreview(fs)).archivos); }
    catch (e) { setErr(String((e as Error)?.message ?? e)); }
    finally { setOcupado(false); }
  };
  const subir = async () => {
    setOcupado(true); setErr(null);
    try {
      const r = await pacingUpload(files, Object.keys(kinds).length ? kinds : undefined);
      setResultado(r.archivos); setVista(null); setFiles([]); listas(); recargar();
    } catch (e) { setErr(String((e as Error)?.message ?? e)); }
    finally { setOcupado(false); }
  };

  const describir = (a: PacingArchivo) => {
    if (a.error) return <span style={{ color: "var(--negative)" }}>{t(`error.${a.error === "sin_dias" ? "sin_dias" : a.error === "no_reconocido" ? "no_reconocido" : "ilegible"}`)}</span>;
    if (a.tipo === "reservations") {
      return <>{t("resv", { n: n0(a.cuenta), pi: n0(a.descartadas_pi), desde: a.min_ins ?? "—", hasta: a.max_ins ?? "—" })}
        {a.nuevas != null && <> · {t("resvResultado", { nuevas: n0(a.nuevas), act: n0(a.actualizadas) })}</>}</>;
    }
    return <>{t("hf", { corte: a.as_of ?? "—", desde: a.date_from ?? "", hasta: a.date_to ?? "", rev: usd0(a.total_revenue) })}
      {a.reemplazo && <> · {t("reemplazo")}</>}</>;
  };

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div style={card}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("titulo")}</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>{t("instrucciones")}</div>
        <NotaSemanal migracion={resv?.desde} />
        <label style={{ display: "block", border: "2px dashed var(--border-medium)", borderRadius: 8, padding: 24,
                        textAlign: "center", cursor: "pointer", fontSize: 13 }}
               onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); elegir(e.dataTransfer.files); }}>
          {files.length ? t("elegidos", { n: files.length }) : t("soltar")}
          <input type="file" accept=".xml,text/xml" multiple style={{ display: "none" }} onChange={e => elegir(e.target.files)} />
        </label>
        {ocupado && <div style={{ fontSize: 12, marginTop: 8 }}>{t("procesando")}</div>}
        {err && <Aviso tipo="error">{err}</Aviso>}
        {vista && (
          <div style={{ marginTop: 12 }}>
            <Tabla minWidth={700}>
              <thead><tr><th style={{ ...th, textAlign: "left" }}>{t("archivo")}</th><th style={{ ...th, textAlign: "left" }}>{t("tipo")}</th>
                <th style={{ ...th, textAlign: "left" }}>{t("detalle")}</th></tr></thead>
              <tbody>{vista.map(a => (
                <tr key={a.nombre}>
                  <td style={tdL}>{a.nombre}</td>
                  <td style={tdL}>{a.tipo === "history_forecast" ? (
                    <select style={select} value={kinds[a.nombre] ?? a.kind ?? "total"}
                            onChange={e => setKinds(k => ({ ...k, [a.nombre]: e.target.value as PacingKind }))}>
                      <option value="total">{t("hfTotal")}</option><option value="rooms">{t("hfRooms")}</option>
                    </select>) : a.tipo === "reservations" ? t("tipoResv") : "—"}
                    {a.kind_detectado === "confirmar" && !kinds[a.nombre] &&
                      <span style={{ color: "var(--warning)", fontSize: 11 }}> {t("confirmar")}</span>}
                  </td>
                  <td style={{ ...tdL, whiteSpace: "normal" }}>{describir(a)}</td>
                </tr>))}
              </tbody>
            </Tabla>
            <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
              <button style={botonPrimario} disabled={ocupado || !vista.some(a => !a.error)} onClick={subir}>{t("subir")}</button>
              <button style={boton} onClick={() => { setFiles([]); setVista(null); }}>{t("cancelar")}</button>
            </div>
          </div>
        )}
        {resultado && (
          <Aviso>{t("listo")}<ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {resultado.map(a => <li key={a.nombre}><b>{a.nombre}</b>: {a.kind ? `${a.kind === "total" ? t("hfTotal") : t("hfRooms")} · ` : ""}{describir(a)}</li>)}
          </ul></Aviso>
        )}
      </div>

      <div>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("fotos")}</div>
        <Tabla minWidth={800}>
          <thead><tr>
            {["corte", "tipo", "rango", "archivo", "ingreso", "subido", ""].map((c, k) =>
              <th key={k} style={{ ...th, textAlign: k < 4 ? "left" : "right" }}>{c ? t(`f.${c}`) : ""}</th>)}
          </tr></thead>
          <tbody>
            {snaps.map(s => (
              <tr key={s.id}>
                <td style={tdL}>{s.as_of}{s.has_forecast ? "" : ` (${t("soloHistoria")})`}</td>
                <td style={tdL}>{s.kind === "total" ? t("hfTotal") : t("hfRooms")}</td>
                <td style={tdL}>{s.date_from} → {s.date_to}</td>
                <td style={tdL}>{s.file_name}</td>
                <td style={td}>{usd0(s.total_revenue)}</td>
                <td style={td}>{s.uploaded_at?.slice(0, 16).replace("T", " ")} {s.uploaded_by ?? ""}</td>
                <td style={td}><button style={{ ...boton, padding: "2px 8px" }} onClick={async () => {
                  if (!confirm(t("confirmarBorrarFoto", { corte: s.as_of }))) return;
                  await deletePacingSnapshot(s.id); listas(); recargar();
                }}>{t("borrar")}</button></td>
              </tr>))}
            {!snaps.length && <tr><td style={tdL} colSpan={7}>{t("sinFotos")}</td></tr>}
          </tbody>
        </Tabla>
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 4 }}>{t("notaFotos")}</div>
      </div>

      <div>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{t("reservas")}</div>
        {resv && <div style={{ fontSize: 12, marginBottom: 6 }}>
          {t("resvResumen", { n: n0(resv.cuenta), act: n0(resv.activas), x: n0(resv.canceladas), desde: resv.desde ?? "—", hasta: resv.hasta ?? "—" })}
          {" "}{resv.cuenta > 0 && <button style={{ ...boton, padding: "2px 8px" }} onClick={async () => {
            if (!confirm(t("confirmarBorrarResv"))) return;
            await deletePacingReservations(); listas(); recargar();
          }}>{t("borrarResv")}</button>}
        </div>}
        <Tabla minWidth={700}>
          <thead><tr>{["archivo", "filas", "nuevas", "act", "pi", "rango", "subido"].map((c, k) =>
            <th key={c} style={{ ...th, textAlign: k === 0 || k === 5 ? "left" : "right" }}>{t(`r.${c}`)}</th>)}</tr></thead>
          <tbody>{(resv?.cargas ?? []).map(c => (
            <tr key={c.id}>
              <td style={tdL}>{c.file_name}</td><td style={td}>{n0(c.cuenta)}</td><td style={td}>{n0(c.nuevas)}</td>
              <td style={td}>{n0(c.actualizadas)}</td><td style={td}>{n0(c.descartadas_pi)}</td>
              <td style={tdL}>{c.min_ins} → {c.max_ins}</td>
              <td style={td}>{c.uploaded_at?.slice(0, 16).replace("T", " ")} {c.uploaded_by ?? ""}</td>
            </tr>))}
          </tbody>
        </Tabla>
      </div>

      <Configuracion />
    </div>
  );
}

// ───────────────────────────── configuración ─────────────────────────────
function Configuracion() {
  const tc = useTranslations("pacing.config");
  const M = useMeses();
  const { recargar } = usePacing();
  const [cfg, setCfg] = useState<PacingConfig | null>(null);
  const [esc, setEsc] = useState<Scenario[]>([]);
  const [escId, setEscId] = useState("");
  const [escAnio, setEscAnio] = useState<number>(new Date().getFullYear() + 1);
  const [msg, setMsg] = useState<string | null>(null);
  const [stlyAnio, setStlyAnio] = useState<string>("");

  useEffect(() => {
    getPacingConfig().then(c => { setCfg(c); setStlyAnio(Object.keys(c.stly.years).sort().pop() ?? String(new Date().getFullYear() + 1)); }).catch(() => {});
    getScenarios(HOTEL_ID).then(setEsc).catch(() => {});
  }, []);
  if (!cfg) return null;

  const guardar = async (parcial: Partial<PacingConfig>, ok: string) => {
    setMsg(null);
    try { const c = await putPacingConfig(parcial); setCfg(c); setMsg(ok); recargar(); }
    catch (e) { setMsg(String((e as Error)?.message ?? e)); }
  };
  const tomar = async () => {
    if (!escId) return;
    setMsg(null);
    try {
      await pacingMetaFromScenario(escId, escAnio);
      setCfg(await getPacingConfig()); setMsg(tc("metaTomada", { anio: escAnio })); recargar();
    } catch (e) { setMsg(String((e as Error)?.message ?? e)); }
  };
  const bloque: PacingYearBlock = cfg.stly.years[stlyAnio] ?? { rn: Array(12).fill(0), rooms: Array(12).fill(0), total: Array(12).fill(0) };
  const setStly = (k: "rn" | "rooms" | "total", i: number, v: number) => {
    const b = { ...bloque, [k]: [...(bloque[k] ?? Array(12).fill(0))] } as PacingYearBlock;
    (b[k] as number[])[i] = isNaN(v) ? 0 : v;
    setCfg({ ...cfg, stly: { years: { ...cfg.stly.years, [stlyAnio]: b } } });
  };
  /** Pegar una fila de Excel (12 celdas separadas por tab) en una línea del STLY. */
  const pegar = (k: "rn" | "rooms" | "total", texto: string) => {
    const v = texto.trim().split(/[\t\n;]+/).map(x => Number(x.replace(/[,$\s]/g, "")));
    if (v.length < 2) return false;
    const b = { ...bloque, [k]: Array.from({ length: 12 }, (_, i) => (isNaN(v[i]) ? 0 : v[i] ?? 0)) } as PacingYearBlock;
    setCfg({ ...cfg, stly: { years: { ...cfg.stly.years, [stlyAnio]: b } } });
    return true;
  };

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{tc("titulo")}</div>
      {msg && <Aviso>{msg}</Aviso>}

      <div style={card}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{tc("enSitio")}</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>{tc("enSitioNota")}</div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
          <select style={select} value={cfg.onsite_mode} onChange={e => setCfg({ ...cfg, onsite_mode: e.target.value as "pct" | "ratio" })}>
            <option value="pct">{tc("modoPct")}</option><option value="ratio">{tc("modoRatio")}</option>
          </select>
          {cfg.onsite_mode === "pct" && <><input style={inp} type="number" step="0.5" value={cfg.onsite_pct}
                   onChange={e => setCfg({ ...cfg, onsite_pct: Number(e.target.value) })} />%</>}
          <button style={botonPrimario} onClick={() => guardar({ onsite_mode: cfg.onsite_mode, onsite_pct: cfg.onsite_pct }, tc("guardado"))}>{tc("guardar")}</button>
        </div>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{tc("metas")}</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>{tc("metasNota")}</div>
        <Tabla minWidth={600}>
          <thead><tr>{["anio", "fuente", "rn", "rooms", "total", ""].map((c, k) =>
            <th key={k} style={{ ...th, textAlign: k < 2 ? "left" : "right" }}>{c ? tc(`m.${c}`) : ""}</th>)}</tr></thead>
          <tbody>{Object.entries(cfg.meta.years).sort().map(([y, b]) => {
            const s = (a?: number[]) => (a ?? []).reduce((x, v) => x + (v || 0), 0);
            return (
              <tr key={y}>
                <td style={tdL}>{y}</td><td style={tdL}>{String(b.source ?? "")}</td>
                <td style={td}>{n0(s(b.rn))}</td><td style={td}>{usd0(s(b.rooms))}</td><td style={td}>{usd0(s(b.total))}</td>
                <td style={td}><button style={{ ...boton, padding: "2px 8px" }} onClick={() => {
                  if (!confirm(tc("confirmarBorrarMeta", { anio: y }))) return;
                  const years = { ...cfg.meta.years }; delete years[y];
                  guardar({ meta: { years } }, tc("metaBorrada", { anio: y }));
                }}>{tc("borrar")}</button></td>
              </tr>);
          })}</tbody>
        </Tabla>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 10, fontSize: 12 }}>
          {tc("tomarDe")}
          <select style={select} value={escId} onChange={e => setEscId(e.target.value)}>
            <option value="">—</option>
            {esc.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>)}
          </select>
          {tc("comoMetaDe")}
          <input style={inp} type="number" value={escAnio} onChange={e => setEscAnio(Number(e.target.value))} />
          <button style={botonPrimario} disabled={!escId} onClick={tomar}>{tc("tomar")}</button>
        </div>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{tc("stly")}</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>{tc("stlyNota")}</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12, marginBottom: 8 }}>
          {tc("anioLlegada")}
          <input style={inp} type="number" value={stlyAnio} onChange={e => setStlyAnio(e.target.value)} />
          {tc("fechaCorte")}
          <input style={{ ...inp, width: 110, textAlign: "left" }} type="date" value={String(bloque.asOf ?? "")}
                 onChange={e => setCfg({ ...cfg, stly: { years: { ...cfg.stly.years, [stlyAnio]: { ...bloque, asOf: e.target.value } } } })} />
          {tc("fuente")}
          <input style={{ ...inp, width: 260, textAlign: "left" }} value={String(bloque.source ?? "")}
                 onChange={e => setCfg({ ...cfg, stly: { years: { ...cfg.stly.years, [stlyAnio]: { ...bloque, source: e.target.value } } } })} />
        </div>
        <Tabla minWidth={1100}>
          <thead><tr><th style={{ ...th, textAlign: "left" }} />{M.map(m => <th key={m} style={th}>{m}</th>)}</tr></thead>
          <tbody>{(["rn", "rooms", "total"] as const).map(k => (
            <tr key={k}>
              <td style={tdL}>{tc(`s.${k}`)}</td>
              {Array.from({ length: 12 }, (_, i) => (
                <td key={i} style={td}><input style={inp} type="number" value={(bloque[k] ?? [])[i] ?? 0}
                  onPaste={e => { if (pegar(k, e.clipboardData.getData("text"))) e.preventDefault(); }}
                  onChange={e => setStly(k, i, Number(e.target.value))} /></td>))}
            </tr>))}
          </tbody>
        </Tabla>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button style={botonPrimario} onClick={() => guardar({ stly: cfg.stly }, tc("guardado"))}>{tc("guardarStly")}</button>
          <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{tc("pegarNota")}</span>
        </div>
      </div>
    </div>
  );
}
