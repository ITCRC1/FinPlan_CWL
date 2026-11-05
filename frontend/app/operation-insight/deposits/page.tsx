"use client";
/**
 * Deposit Analysis — la plata de huéspedes que el hotel tiene en custodia.
 *
 * Owner, 2026-11-04: *«puedes crearme un sub tab llamado Deposit Analysis. Que
 * revisa el reporte tal como esta en el xml y despues sub tab que analice por
 * mes arrival. y todos los analisis. yo quiero seguir el tracking. que lleve la
 * version para comparar una subida a otra y que vea cuales salieron y cuales
 * entraron.»*
 *
 * Cuatro pestañas, en ese orden:
 *
 *   Ledger      el reporte tal como está en el XML — mismo signo, mismos campos
 *   Por llegada cuánto depósito se vuelve ingreso en cada mes de llegada
 *   Análisis    estado, garantía, antigüedad, vencidos y concentración
 *   Versiones   subir un corte y comparar uno contra otro
 *
 * ⚠️ **El signo cambia entre la primera pestaña y las demás, a propósito.** En
 * Opera el depósito es un crédito a favor del huésped y viaja negativo; el
 * Ledger tiene que poder leerse al lado del reporte de Opera, columna con
 * columna, así que ahí se muestra negativo. En los análisis es plata en
 * custodia y va positiva. El cartel de la pestaña Ledger lo dice.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  getDepositLoads, getDepositLedger, getDepositAnalisis, compararDepositos,
  subirDepositLedger, borrarDepositLoad,
  type DepositLoad, type DepositRow, type DepositAnalisis,
  type DepositComparacion, type DepositCambio, type DepositGrupoCambio,
} from "@/lib/api";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const GOLD = "#c8a24a";
type Tab = "ledger" | "llegada" | "analisis" | "versiones";
const TABS: Tab[] = ["ledger", "llegada", "analisis", "versiones"];

const usd = (n: number, d = 2) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD",
                              minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n: number) => `${n.toFixed(1)}%`;
const fecha = (s: string | null | undefined) => s ?? "—";

/** Color del delta: entra plata = verde, sale = rojo. */
const tono = (n: number) => (n > 0 ? "#1a7f5a" : n < 0 ? "#b3261e" : "#666");

export default function DepositAnalysisPage() {
  const t = useTranslations("deposits");
  const tc = useTranslations("common");

  const [tab, setTab] = useState<Tab>("ledger");
  const [cortes, setCortes] = useState<DepositLoad[]>([]);
  const [loadId, setLoadId] = useState<string>("");
  const [ledger, setLedger] = useState<{ corte: DepositLoad; filas: DepositRow[];
                                         total_paid_amt: number } | null>(null);
  const [analisis, setAnalisis] = useState<DepositAnalisis | null>(null);
  const [cmp, setCmp] = useState<DepositComparacion | null>(null);
  const [antes, setAntes] = useState<string>("");
  const [despues, setDespues] = useState<string>("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [arrastrando, setArrastrando] = useState(false);

  /**
   * Trae la lista de cortes y deja todo apuntando a lo correcto.
   *
   * `forzar` después de subir: el corte nuevo pasa a ser el que se mira y los
   * dos más recientes quedan elegidos para comparar. Sin eso, el usuario sube
   * un archivo y la pantalla le sigue mostrando el corte viejo — tiene que
   * adivinar que hay un selector arriba y cambiarlo a mano.
   */
  const recargarCortes = useCallback(async (forzar = false) => {
    const r = await getDepositLoads();
    setCortes(r.cortes);
    if (r.cortes.length && (forzar || !r.cortes.some(c => c.id === loadId))) {
      setLoadId(r.cortes[0].id);
    }
    if (r.cortes.length >= 2) {
      setDespues(d => (forzar ? r.cortes[0].id : d || r.cortes[0].id));
      setAntes(a => (forzar ? r.cortes[1].id : a || r.cortes[1].id));
    }
    return r.cortes;
  }, [loadId]);

  useEffect(() => {
    (async () => {
      try { await recargarCortes(); }
      catch (e) { setError(String(e)); }
      finally { setCargando(false); }
    })();
    // Solo al montar: después se recarga a mano tras subir o borrar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!loadId) { setLedger(null); setAnalisis(null); return; }
    (async () => {
      setError(null);
      try {
        const [l, a] = await Promise.all([getDepositLedger(loadId), getDepositAnalisis(loadId)]);
        setLedger(l); setAnalisis(a);
      } catch (e) { setError(String(e)); }
    })();
  }, [loadId]);

  useEffect(() => {
    if (tab !== "versiones" || !antes || !despues || antes === despues) { setCmp(null); return; }
    (async () => {
      try { setCmp(await compararDepositos(antes, despues)); }
      catch (e) { setError(String(e)); setCmp(null); }
    })();
  }, [tab, antes, despues]);

  /**
   * Sube un XML y deja la pantalla acomodada sola.
   *
   * El archivo dice de qué fecha es (su último movimiento), así que no hay que
   * preguntar nada: se sube, se guarda, el corte nuevo pasa a ser el que se
   * mira y —si ya había otro— el mensaje dice de una vez cuántas entraron y
   * cuántas salieron. Subir dos veces el mismo corte lo reemplaza.
   */
  const subir = useCallback(async (f: File) => {
    if (!/\.xml$/i.test(f.name)) { setError(t("soloXml", { archivo: f.name })); return; }
    setSubiendo(true); setError(null); setMsg(null);
    try {
      const r = await subirDepositLedger(f);
      const lista = await recargarCortes(true);
      setLoadId(lista.find(c => c.id === r.load_id)?.id ?? lista[0]?.id ?? "");
      setMsg(r.cambio
        ? t("subidoConCambio", { n: r.cuenta, corte: r.as_of, contra: r.cambio.contra,
                                 entraron: r.cambio.entraron, salieron: r.cambio.salieron })
        : t("subido", { n: r.cuenta, corte: r.as_of }));
    } catch (e) { setError(String(e)); }
    finally { setSubiendo(false); }
  }, [recargarCortes, t]);

  async function borrar(id: string) {
    if (!confirm(t("confirmarBorrar"))) return;
    try {
      await borrarDepositLoad(id);
      const lista = await recargarCortes(true);
      setLoadId(lista[0]?.id ?? "");
      setMsg(t("borrado"));
    } catch (e) { setError(String(e)); }
  }

  // Arrastrar el XML sobre cualquier parte de la pantalla también sirve.
  const alSoltar = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setArrastrando(false);
    const f = e.dataTransfer.files?.[0];
    if (f) subir(f);
  }, [subir]);

  // ── Excel ────────────────────────────────────────────────────────────────
  const bajar = useCallback(async () => {
    if (!ledger || !analisis) return;
    const corte = analisis.corte.as_of;
    const cuadros: Cuadro[] = [];

    cuadros.push({
      titulo: `Deposit Ledger · corte ${corte}`,
      subtitulo: t("excelLedgerSub"), hoja: "Ledger",
      columnas: [
        { label: "Resv ID", ancho: 12, formato: "texto" },
        { label: "Confirmación", ancho: 14, formato: "texto" },
        { label: "Huésped", ancho: 30, formato: "texto" },
        { label: "Hab", ancho: 7, formato: "texto" },
        { label: "Llegada", ancho: 12, formato: "texto" },
        { label: "Salida", ancho: 12, formato: "texto" },
        { label: "Noches", ancho: 8, formato: "num" },
        { label: "Últ. mov.", ancho: 12, formato: "texto" },
        { label: "Estado", ancho: 9, formato: "texto" },
        { label: "Garantía", ancho: 10, formato: "texto" },
        { label: "Depósito", ancho: 15, formato: "usd2", abre_grupo: true },
      ],
      filas: [
        ...ledger.filas.map<FilaCuadro>(f => ({
          label: f.resv_name_id,
          valores: [f.confirmation_no, f.name, f.room, f.arrival, f.departure,
                    f.nights, f.last_date, f.resv_status, f.guarantee_code,
                    f.total_paid_amt],
        })),
        { label: "TOTAL", es_total: true,
          valores: [null, null, null, null, null,
                    ledger.filas.reduce((s, f) => s + f.nights, 0),
                    null, null, null, ledger.total_paid_amt] },
      ],
      comentarios: [t("notaSigno")],
    });

    const pm = analisis.por_mes;
    cuadros.push({
      titulo: `Depósito por mes de llegada · corte ${corte}`,
      subtitulo: t("excelLlegadaSub"), hoja: "Por llegada",
      columnas: [
        { label: t("colMes"), ancho: 14, formato: "texto" },
        { label: t("colReservas"), ancho: 11, formato: "num" },
        { label: t("colNoches"), ancho: 10, formato: "num" },
        { label: t("colMonto"), ancho: 16, formato: "usd2" },
        { label: t("colPromedio"), ancho: 14, formato: "usd2" },
        { label: "%", ancho: 9, formato: "pct" },
        { label: t("colAcumulado"), ancho: 16, formato: "usd2", abre_grupo: true },
        { label: t("colPctAcum"), ancho: 10, formato: "pct" },
      ],
      filas: [
        ...pm.meses.map<FilaCuadro>(m => ({
          label: m.etiqueta,
          valores: [m.reservas, m.noches, m.monto, m.promedio, m.pct / 100,
                    m.acumulado, m.pct_acumulado / 100],
        })),
        ...(pm.sin_llegada ? [{ label: t("sinLlegada"),
            valores: [pm.sin_llegada.reservas, pm.sin_llegada.noches,
                      pm.sin_llegada.monto, pm.sin_llegada.promedio, null, null, null],
          } as FilaCuadro] : []),
        { label: "TOTAL", es_total: true,
          valores: [pm.total.reservas, pm.total.noches, pm.total.monto,
                    pm.total.promedio, 1, pm.total.monto, 1] },
      ],
    });

    const grupo = (titulo: string, hoja: string, filas: typeof analisis.por_estado) => ({
      titulo: `${titulo} · corte ${corte}`, hoja,
      columnas: [
        { label: titulo, ancho: 16, formato: "texto" as const },
        { label: t("colReservas"), ancho: 11, formato: "num" as const },
        { label: t("colNoches"), ancho: 10, formato: "num" as const },
        { label: t("colMonto"), ancho: 16, formato: "usd2" as const },
        { label: t("colPromedio"), ancho: 14, formato: "usd2" as const },
        { label: "%", ancho: 9, formato: "pct" as const },
      ],
      filas: [
        ...filas.map<FilaCuadro>(g => ({
          label: g.clave,
          valores: [g.reservas, g.noches, g.monto, g.promedio, g.pct / 100],
        })),
        { label: "TOTAL", es_total: true,
          valores: [analisis.total.reservas, analisis.total.noches,
                    analisis.total.monto, analisis.total.promedio, 1] },
      ],
    });
    cuadros.push(grupo(t("porEstado"), "Por estado", analisis.por_estado));
    cuadros.push(grupo(t("porGarantia"), "Por garantía", analisis.por_garantia));

    cuadros.push({
      titulo: `${t("antiguedad")} · corte ${corte}`,
      subtitulo: t("antiguedadNota"), hoja: "Antigüedad",
      columnas: [
        { label: t("colTramo"), ancho: 14, formato: "texto" },
        { label: t("colReservas"), ancho: 11, formato: "num" },
        { label: t("colMonto"), ancho: 16, formato: "usd2" },
        { label: t("colPromedio"), ancho: 14, formato: "usd2" },
        { label: "%", ancho: 9, formato: "pct" },
      ],
      filas: [
        ...analisis.antiguedad.tramos.map<FilaCuadro>(x => ({
          label: `${x.tramo} ${t("dias")}`,
          valores: [x.reservas, x.monto, x.promedio, x.pct / 100],
        })),
        { label: "TOTAL", es_total: true,
          valores: [analisis.total.reservas, analisis.total.monto,
                    analisis.total.promedio, 1] },
      ],
    });

    cuadros.push({
      titulo: `${t("concentracion")} · corte ${corte}`, hoja: "Mayores",
      columnas: [
        { label: t("colHuesped"), ancho: 34, formato: "texto" },
        { label: t("colLlegada"), ancho: 12, formato: "texto" },
        { label: t("colEstado"), ancho: 9, formato: "texto" },
        { label: t("colNoches"), ancho: 9, formato: "num" },
        { label: t("colMonto"), ancho: 16, formato: "usd2" },
        { label: "%", ancho: 9, formato: "pct" },
      ],
      filas: analisis.concentracion.top.map<FilaCuadro>(m => ({
        label: m.name ?? m.resv_name_id,
        valores: [m.arrival, m.resv_status, m.nights, m.monto, m.pct / 100],
      })),
      comentarios: [t("concentracionNota", { pct: pct(analisis.concentracion.pct_top) })],
    });

    if (cmp) {
      const bloque = (rot: string, g: DepositGrupoCambio, conDelta: boolean) => ({
        titulo: `${rot} · ${cmp.corte_antes.as_of} → ${cmp.corte_despues.as_of}`,
        hoja: rot.slice(0, 28),
        columnas: [
          { label: t("colHuesped"), ancho: 32, formato: "texto" as const },
          { label: t("colLlegada"), ancho: 12, formato: "texto" as const },
          { label: t("colEstado"), ancho: 9, formato: "texto" as const },
          { label: t("colNoches"), ancho: 9, formato: "num" as const },
          ...(conDelta ? [{ label: t("colAntes"), ancho: 14, formato: "usd2" as const }] : []),
          { label: conDelta ? t("colDespues") : t("colMonto"), ancho: 14, formato: "usd2" as const },
          ...(conDelta ? [{ label: t("colDelta"), ancho: 14, formato: "usd2" as const }] : []),
        ],
        filas: [
          ...g.filas.map<FilaCuadro>(f => ({
            label: f.name ?? f.resv_name_id,
            valores: [f.arrival, f.resv_status, f.nights,
                      ...(conDelta ? [f.monto_antes ?? null] : []),
                      f.monto, ...(conDelta ? [f.delta ?? null] : [])],
          })),
          { label: "TOTAL", es_total: true,
            valores: [null, null, null, ...(conDelta ? [null] : []),
                      conDelta ? null : g.monto, ...(conDelta ? [g.monto] : [])] },
        ],
      });
      cuadros.push(bloque(t("entraron"), cmp.entraron, false));
      cuadros.push(bloque(t("salieron"), cmp.salieron, false));
      if (cmp.subieron.filas.length) cuadros.push(bloque(t("subieron"), cmp.subieron, true));
      if (cmp.bajaron.filas.length) cuadros.push(bloque(t("bajaron"), cmp.bajaron, true));
    }

    await bajarCuadros(`Deposit_Ledger_${corte}`, cuadros);
  }, [ledger, analisis, cmp, t]);

  // ── pintado ──────────────────────────────────────────────────────────────
  const corteActual = cortes.find(c => c.id === loadId) ?? null;

  if (cargando) return <div style={{ padding: 24 }}>{tc("loading")}</div>;

  return (
    <div style={{ padding: "18px 24px 48px", position: "relative" }}
         onDragOver={e => { e.preventDefault(); setArrastrando(true); }}
         onDragLeave={e => { if (e.currentTarget === e.target) setArrastrando(false); }}
         onDrop={alSoltar}>
      {arrastrando && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 50, pointerEvents: "none",
          background: "#c8a24a18", border: `3px dashed ${GOLD}`,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{ background: "#fff", border: `1px solid ${GOLD}`, borderRadius: 10,
                        padding: "18px 34px", fontSize: 16, fontWeight: 600 }}>
            {t("suelteAqui")}
          </div>
        </div>
      )}
      <IrA />
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>{t("titulo")}</h1>
        {corteActual && (
          <span style={{ color: "#666", fontSize: 13 }}>
            {t("corteDel", { fecha: corteActual.as_of })} · {corteActual.cuenta} {t("reservas")} ·{" "}
            <b style={{ color: GOLD }}>{usd(Math.abs(corteActual.total_amt))}</b>
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {cortes.length > 1 && (
            <select value={loadId} onChange={e => setLoadId(e.target.value)}
                    style={sel}>
              {cortes.map(c => (
                <option key={c.id} value={c.id}>
                  {c.as_of} · {c.cuenta} {t("reservas")} · {usd(Math.abs(c.total_amt), 0)}
                </option>
              ))}
            </select>
          )}
          {/* La subida va acá y no sólo adentro de «Versiones»: es lo primero
              que se hace al llegar con un archivo nuevo en la mano. */}
          <SubirXml subir={subir} subiendo={subiendo} t={t} destacado />
          <button onClick={bajar} disabled={!ledger} style={btn}>↓ Excel</button>
        </div>
      </div>
      <p style={{ color: "#666", fontSize: 13, marginTop: 6, maxWidth: 940 }}>{t("intro")}</p>

      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid #ddd", marginTop: 14 }}>
        {TABS.map(x => (
          <button key={x} onClick={() => setTab(x)} style={{
            ...tabBtn, color: tab === x ? "#111" : "#777",
            borderBottomColor: tab === x ? GOLD : "transparent",
            fontWeight: tab === x ? 600 : 400,
          }}>{t(`tab_${x}`)}</button>
        ))}
      </div>

      {error && <div style={aviso("#b3261e")}>{error}</div>}
      {msg && <div style={aviso("#1a7f5a")}>{msg}</div>}

      {!cortes.length && (
        <ZonaVacia subir={subir} subiendo={subiendo} t={t} />
      )}

      {tab === "ledger" && ledger && <Ledger d={ledger} t={t} />}
      {tab === "llegada" && analisis && <PorLlegada a={analisis} t={t} />}
      {tab === "analisis" && analisis && <Analisis a={analisis} t={t} />}
      {tab === "versiones" && (
        <Versiones
          cortes={cortes} cmp={cmp} antes={antes} despues={despues}
          setAntes={setAntes} setDespues={setDespues}
          subir={subir} borrar={borrar} subiendo={subiendo} t={t}
        />
      )}
    </div>
  );
}

// ═══════════════════════════ Pestaña 1 · Ledger ═════════════════════════════
function Ledger({ d, t }: {
  d: { corte: DepositLoad; filas: DepositRow[]; total_paid_amt: number };
  t: ReturnType<typeof useTranslations>;
}) {
  const [q, setQ] = useState("");
  const filas = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return d.filas;
    return d.filas.filter(f =>
      [f.name, f.sname, f.resv_name_id, f.confirmation_no, f.room, f.resv_status]
        .some(v => (v ?? "").toLowerCase().includes(s)));
  }, [d.filas, q]);

  return (
    <>
      <div style={nota}>{t("notaSigno")}</div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "12px 0 8px" }}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder={t("buscar")}
               style={{ ...sel, width: 300 }} />
        <span style={{ color: "#666", fontSize: 12 }}>
          {filas.length} / {d.filas.length} {t("reservas")}
        </span>
      </div>
      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
        <table style={tabla}>
          <thead>
            <tr>
              {["Resv ID", t("colConfirmacion"), t("colHuesped"), t("colHab"),
                t("colLlegada"), t("colSalida"), t("colNoches"), t("colUltMov"),
                t("colEstado"), t("colGarantia"), "TOTAL_PAID_AMT"].map((h, i) => (
                <th key={h} style={{ ...th, textAlign: i >= 6 ? "right" : "left" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map(f => (
              <tr key={f.resv_name_id}>
                <td style={td}>{f.resv_name_id}</td>
                <td style={td}>{fecha(f.confirmation_no)}</td>
                <td style={td}>{fecha(f.name)}</td>
                <td style={td}>{fecha(f.room)}</td>
                <td style={td}>{fecha(f.arrival)}</td>
                <td style={td}>{fecha(f.departure)}</td>
                <td style={tdN}>{f.nights}</td>
                <td style={tdN}>{fecha(f.last_date)}</td>
                <td style={tdN}>{fecha(f.resv_status)}</td>
                <td style={tdN}>{fecha(f.guarantee_code)}</td>
                <td style={{ ...tdN, fontVariantNumeric: "tabular-nums" }}>
                  {f.total_paid_amt.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td style={{ ...tdT, textAlign: "left" }} colSpan={6}>
                TOTAL · {filas.length} {t("reservas")}
              </td>
              <td style={tdT}>{filas.reduce((s, f) => s + f.nights, 0)}</td>
              <td style={tdT} colSpan={3} />
              <td style={tdT}>
                {filas.reduce((s, f) => s + f.total_paid_amt, 0).toFixed(2)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  );
}

// ═════════════════════════ Pestaña 2 · Por llegada ══════════════════════════
function PorLlegada({ a, t }: { a: DepositAnalisis; t: ReturnType<typeof useTranslations> }) {
  const pm = a.por_mes;
  const max = Math.max(1, ...pm.meses.map(m => m.monto));
  return (
    <>
      <div style={nota}>{t("llegadaNota")}</div>
      <Tarjetas items={[
        { rot: t("enCustodia"), val: usd(a.total.monto, 0) },
        { rot: t("reservas"), val: String(a.total.reservas) },
        { rot: t("promedio"), val: usd(a.total.promedio, 0) },
        { rot: t("mesesConDeposito"), val: String(pm.meses.length) },
      ]} />
      <table style={{ ...tabla, marginTop: 14 }}>
        <thead>
          <tr>
            <th style={th}>{t("colMes")}</th>
            <th style={thN}>{t("colReservas")}</th>
            <th style={thN}>{t("colNoches")}</th>
            <th style={thN}>{t("colMonto")}</th>
            <th style={thN}>{t("colPromedio")}</th>
            <th style={thN}>%</th>
            <th style={thN}>{t("colPctAcum")}</th>
            <th style={th}>{t("colEstados")}</th>
          </tr>
        </thead>
        <tbody>
          {pm.meses.map(m => (
            <tr key={m.mes}>
              <td style={td}><b>{m.etiqueta}</b></td>
              <td style={tdN}>{m.reservas}</td>
              <td style={tdN}>{m.noches}</td>
              <td style={{ ...tdN, fontWeight: 600 }}>{usd(m.monto)}</td>
              <td style={tdN}>{usd(m.promedio)}</td>
              <td style={tdN}>
                <span style={{ display: "inline-block", width: 70, textAlign: "right" }}>
                  {pct(m.pct)}
                </span>
                <span style={{
                  display: "inline-block", marginLeft: 6, height: 8, borderRadius: 2,
                  background: GOLD, width: Math.round((m.monto / max) * 90),
                  verticalAlign: "middle",
                }} />
              </td>
              <td style={tdN}>{pct(m.pct_acumulado)}</td>
              <td style={{ ...td, fontSize: 11, color: "#666" }}>
                {Object.entries(m.por_estado).slice(0, 4)
                  .map(([k, v]) => `${k} ${usd(v, 0)}`).join(" · ")}
              </td>
            </tr>
          ))}
          {pm.sin_llegada && (
            <tr>
              <td style={td}><i>{t("sinLlegada")}</i></td>
              <td style={tdN}>{pm.sin_llegada.reservas}</td>
              <td style={tdN}>{pm.sin_llegada.noches}</td>
              <td style={tdN}>{usd(pm.sin_llegada.monto)}</td>
              <td style={tdN}>{usd(pm.sin_llegada.promedio)}</td>
              <td style={tdN} colSpan={3} />
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr>
            <td style={{ ...tdT, textAlign: "left" }}>TOTAL</td>
            <td style={tdT}>{pm.total.reservas}</td>
            <td style={tdT}>{pm.total.noches}</td>
            <td style={tdT}>{usd(pm.total.monto)}</td>
            <td style={tdT}>{usd(pm.total.promedio)}</td>
            <td style={tdT}>100.0%</td>
            <td style={tdT} colSpan={2} />
          </tr>
        </tfoot>
      </table>
    </>
  );
}

// ═══════════════════════════ Pestaña 3 · Análisis ═══════════════════════════
function Analisis({ a, t }: { a: DepositAnalisis; t: ReturnType<typeof useTranslations> }) {
  return (
    <>
      <Tarjetas items={[
        { rot: t("enCustodia"), val: usd(a.total.monto, 0) },
        { rot: t("top10"), val: pct(a.concentracion.pct_top) },
        { rot: t("vencidos"), val: String(a.vencidos.length),
          tono: a.vencidos.length ? "#b3261e" : undefined },
        { rot: t("masDe180"), val: usd(
            a.antiguedad.tramos.filter(x => x.tramo === "181–365" || x.tramo === "365+")
              .reduce((s, x) => s + x.monto, 0), 0) },
      ]} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 22, marginTop: 18 }}>
        <Grupo titulo={t("porEstado")} filas={a.por_estado} t={t} />
        <Grupo titulo={t("porGarantia")} filas={a.por_garantia} t={t} />
      </div>

      <h3 style={h3}>{t("antiguedad")}</h3>
      <div style={nota}>{t("antiguedadNota")}</div>
      <table style={{ ...tabla, maxWidth: 680 }}>
        <thead>
          <tr>
            <th style={th}>{t("colTramo")}</th>
            <th style={thN}>{t("colReservas")}</th>
            <th style={thN}>{t("colMonto")}</th>
            <th style={thN}>{t("colPromedio")}</th>
            <th style={thN}>%</th>
          </tr>
        </thead>
        <tbody>
          {a.antiguedad.tramos.map(x => (
            <tr key={x.tramo}>
              <td style={td}>{x.tramo} {t("dias")}</td>
              <td style={tdN}>{x.reservas}</td>
              <td style={tdN}>{usd(x.monto)}</td>
              <td style={tdN}>{usd(x.promedio)}</td>
              <td style={tdN}>{pct(x.pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={h3}>{t("vencidosTitulo")}</h3>
      <div style={nota}>{t("vencidosNota")}</div>
      {a.vencidos.length === 0 ? (
        <div style={{ ...aviso("#1a7f5a"), maxWidth: 680 }}>{t("sinVencidos")}</div>
      ) : (
        <table style={{ ...tabla, maxWidth: 900 }}>
          <thead>
            <tr>
              <th style={th}>{t("colHuesped")}</th>
              <th style={th}>{t("colLlegada")}</th>
              <th style={thN}>{t("colDias")}</th>
              <th style={thN}>{t("colEstado")}</th>
              <th style={thN}>{t("colMonto")}</th>
            </tr>
          </thead>
          <tbody>
            {a.vencidos.map(v => (
              <tr key={v.resv_name_id}>
                <td style={td}>{fecha(v.name)}</td>
                <td style={td}>{fecha(v.arrival)}</td>
                <td style={{ ...tdN, color: "#b3261e", fontWeight: 600 }}>{v.dias_vencido}</td>
                <td style={tdN}>{fecha(v.resv_status)}</td>
                <td style={tdN}>{usd(v.monto)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 style={h3}>{t("concentracion")}</h3>
      <div style={nota}>{t("concentracionNota", { pct: pct(a.concentracion.pct_top) })}</div>
      <table style={{ ...tabla, maxWidth: 900 }}>
        <thead>
          <tr>
            <th style={th}>{t("colHuesped")}</th>
            <th style={th}>{t("colLlegada")}</th>
            <th style={thN}>{t("colEstado")}</th>
            <th style={thN}>{t("colNoches")}</th>
            <th style={thN}>{t("colMonto")}</th>
            <th style={thN}>%</th>
          </tr>
        </thead>
        <tbody>
          {a.concentracion.top.map(m => (
            <tr key={m.resv_name_id}>
              <td style={td}>{fecha(m.name)}</td>
              <td style={td}>{fecha(m.arrival)}</td>
              <td style={tdN}>{fecha(m.resv_status)}</td>
              <td style={tdN}>{m.nights}</td>
              <td style={{ ...tdN, fontWeight: 600 }}>{usd(m.monto)}</td>
              <td style={tdN}>{pct(m.pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Grupo({ titulo, filas, t }: {
  titulo: string; filas: DepositAnalisis["por_estado"];
  t: ReturnType<typeof useTranslations>;
}) {
  const max = Math.max(1, ...filas.map(f => f.monto));
  return (
    <div>
      <h3 style={{ ...h3, marginTop: 0 }}>{titulo}</h3>
      <table style={tabla}>
        <thead>
          <tr>
            <th style={th}>{titulo}</th>
            <th style={thN}>{t("colReservas")}</th>
            <th style={thN}>{t("colMonto")}</th>
            <th style={thN}>%</th>
          </tr>
        </thead>
        <tbody>
          {filas.map(g => (
            <tr key={g.clave}>
              <td style={td}><b>{g.clave}</b></td>
              <td style={tdN}>{g.reservas}</td>
              <td style={tdN}>{usd(g.monto)}</td>
              <td style={tdN}>
                {pct(g.pct)}
                <span style={{
                  display: "inline-block", marginLeft: 6, height: 7, borderRadius: 2,
                  background: GOLD, width: Math.round((g.monto / max) * 50),
                  verticalAlign: "middle",
                }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ══════════════════════════ Pestaña 4 · Versiones ═══════════════════════════
function Versiones({ cortes, cmp, antes, despues, setAntes, setDespues,
                     subir, borrar, subiendo, t }: {
  cortes: DepositLoad[]; cmp: DepositComparacion | null;
  antes: string; despues: string;
  setAntes: (s: string) => void; setDespues: (s: string) => void;
  subir: (f: File) => void; borrar: (id: string) => void;
  subiendo: boolean; t: ReturnType<typeof useTranslations>;
}) {
  return (
    <>
      <h3 style={h3}>{t("subirTitulo")}</h3>
      <div style={nota}>{t("subirNota")}</div>
      <SubirXml subir={subir} subiendo={subiendo} t={t} />

      <h3 style={h3}>{t("cortesTitulo")}</h3>
      {cortes.length === 0 ? (
        <div style={nota}>{t("sinCortes")}</div>
      ) : (
        <table style={{ ...tabla, maxWidth: 980 }}>
          <thead>
            <tr>
              <th style={th}>{t("colCorte")}</th>
              <th style={thN}>{t("colReservas")}</th>
              <th style={thN}>{t("colMonto")}</th>
              <th style={th}>{t("colLlegadas")}</th>
              <th style={th}>{t("colArchivo")}</th>
              <th style={th}>{t("colSubido")}</th>
              <th style={thN} />
            </tr>
          </thead>
          <tbody>
            {cortes.map(c => (
              <tr key={c.id}>
                <td style={td}><b>{c.as_of}</b></td>
                <td style={tdN}>{c.cuenta}</td>
                <td style={tdN}>{usd(Math.abs(c.total_amt))}</td>
                <td style={{ ...td, fontSize: 11, color: "#666" }}>
                  {fecha(c.min_arrival)} → {fecha(c.max_arrival)}
                </td>
                <td style={{ ...td, fontSize: 11, color: "#666" }}>{fecha(c.file_name)}</td>
                <td style={{ ...td, fontSize: 11, color: "#666" }}>
                  {c.uploaded_at?.slice(0, 16).replace("T", " ") ?? "—"}
                  {c.uploaded_by ? ` · ${c.uploaded_by}` : ""}
                </td>
                <td style={tdN}>
                  <button onClick={() => borrar(c.id)} style={btnMini}>{t("borrar")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 style={h3}>{t("compararTitulo")}</h3>
      {cortes.length < 2 ? (
        <div style={nota}>{t("hacenFaltaDos")}</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, color: "#666" }}>{t("compararDe")}</span>
            <select value={antes} onChange={e => setAntes(e.target.value)} style={sel}>
              {cortes.map(c => <option key={c.id} value={c.id}>{c.as_of}</option>)}
            </select>
            <span style={{ fontSize: 13, color: "#666" }}>{t("compararA")}</span>
            <select value={despues} onChange={e => setDespues(e.target.value)} style={sel}>
              {cortes.map(c => <option key={c.id} value={c.id}>{c.as_of}</option>)}
            </select>
          </div>
          {antes === despues && <div style={nota}>{t("elijaDistintos")}</div>}
          {cmp && <Comparacion cmp={cmp} t={t} />}
        </>
      )}
    </>
  );
}

function Comparacion({ cmp, t }: {
  cmp: DepositComparacion; t: ReturnType<typeof useTranslations>;
}) {
  const [ver, setVer] = useState<"entraron" | "salieron" | "subieron" | "bajaron">("salieron");
  const grupos = [
    { k: "entraron" as const, g: cmp.entraron, signo: 1 },
    { k: "salieron" as const, g: cmp.salieron, signo: -1 },
    { k: "subieron" as const, g: cmp.subieron, signo: 1 },
    { k: "bajaron" as const, g: cmp.bajaron, signo: 1 },
  ];
  const activo = grupos.find(x => x.k === ver)!;
  const conDelta = ver === "subieron" || ver === "bajaron";

  return (
    <>
      <div style={{ display: "flex", gap: 18, marginTop: 16, flexWrap: "wrap" }}>
        <Tarjeta rot={t("antesDe", { f: cmp.corte_antes.as_of })}
                 val={usd(cmp.antes.monto, 0)} sub={`${cmp.antes.reservas} ${t("reservas")}`} />
        <Tarjeta rot={t("despuesDe", { f: cmp.corte_despues.as_of })}
                 val={usd(cmp.despues.monto, 0)} sub={`${cmp.despues.reservas} ${t("reservas")}`} />
        <Tarjeta rot={t("variacion")} val={usd(cmp.variacion.monto, 0)}
                 sub={`${cmp.variacion.reservas >= 0 ? "+" : ""}${cmp.variacion.reservas} ${t("reservas")}`}
                 tono={tono(cmp.variacion.monto)} />
      </div>

      {Math.abs(cmp.cuadre) > 0.004 && (
        <div style={aviso("#b3261e")}>{t("noCuadra", { v: cmp.cuadre.toFixed(2) })}</div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
        {grupos.map(({ k, g, signo }) => (
          <button key={k} onClick={() => setVer(k)} style={{
            ...chip,
            borderColor: ver === k ? GOLD : "#ddd",
            background: ver === k ? "#fdf8ec" : "#fff",
          }}>
            <div style={{ fontSize: 11, color: "#777", textTransform: "uppercase",
                          letterSpacing: .4 }}>{t(k)}</div>
            <div style={{ fontSize: 19, fontWeight: 600,
                          color: tono(k === "salieron" ? -1 : signo * g.monto) }}>
              {g.reservas}
            </div>
            <div style={{ fontSize: 12, color: "#666" }}>
              {k === "salieron" ? "−" : ""}{usd(Math.abs(g.monto), 0)}
            </div>
          </button>
        ))}
        <div style={{ ...chip, borderColor: "#eee", background: "#fafafa" }}>
          <div style={{ fontSize: 11, color: "#777", textTransform: "uppercase",
                        letterSpacing: .4 }}>{t("iguales")}</div>
          <div style={{ fontSize: 19, fontWeight: 600, color: "#666" }}>
            {cmp.iguales.reservas}
          </div>
          <div style={{ fontSize: 12, color: "#666" }}>{usd(cmp.iguales.monto, 0)}</div>
        </div>
      </div>

      <div style={{ ...nota, marginTop: 14 }}>{t(`nota_${ver}`)}</div>
      {activo.g.filas.length === 0 ? (
        <div style={nota}>{t("ningunaEnEsteGrupo")}</div>
      ) : (
        <table style={{ ...tabla, maxWidth: 1040 }}>
          <thead>
            <tr>
              <th style={th}>{t("colHuesped")}</th>
              <th style={th}>{t("colLlegada")}</th>
              <th style={thN}>{t("colNoches")}</th>
              <th style={thN}>{t("colEstado")}</th>
              {conDelta && <th style={thN}>{t("colAntes")}</th>}
              <th style={thN}>{conDelta ? t("colDespues") : t("colMonto")}</th>
              {conDelta && <th style={thN}>{t("colDelta")}</th>}
            </tr>
          </thead>
          <tbody>
            {activo.g.filas.map(f => <FilaCambio key={f.resv_name_id} f={f} conDelta={conDelta} />)}
          </tbody>
          <tfoot>
            <tr>
              <td style={{ ...tdT, textAlign: "left" }} colSpan={conDelta ? 5 : 4}>
                TOTAL · {activo.g.reservas} {t("reservas")}
              </td>
              <td style={tdT}>{conDelta ? "" : usd(activo.g.monto)}</td>
              {conDelta && <td style={tdT}>{usd(activo.g.monto)}</td>}
            </tr>
          </tfoot>
        </table>
      )}
    </>
  );
}

function FilaCambio({ f, conDelta }: { f: DepositCambio; conDelta: boolean }) {
  return (
    <tr>
      <td style={td}>
        {fecha(f.name)}
        {f.estado_antes && (
          <span style={{ color: "#8a6d1f", fontSize: 11, marginLeft: 6 }}>
            ({f.estado_antes} → {f.resv_status})
          </span>
        )}
      </td>
      <td style={td}>{fecha(f.arrival)}</td>
      <td style={tdN}>{f.nights}</td>
      <td style={tdN}>{fecha(f.resv_status)}</td>
      {conDelta && <td style={tdN}>{usd(f.monto_antes ?? 0)}</td>}
      <td style={{ ...tdN, fontWeight: 600 }}>{usd(f.monto)}</td>
      {conDelta && (
        <td style={{ ...tdN, color: tono(f.delta ?? 0), fontWeight: 600 }}>
          {(f.delta ?? 0) > 0 ? "+" : ""}{usd(f.delta ?? 0)}
        </td>
      )}
    </tr>
  );
}

// ─────────────────────────────── subir el XML ───────────────────────────────
/**
 * El botón de subir. Vive en el encabezado —visible desde cualquier pestaña— y
 * otra vez dentro de «Versiones», que es su casa natural.
 *
 * No pregunta la fecha del corte ni ninguna otra cosa: el archivo la trae.
 * Cualquier campo que se le pida acá es un paso más entre el owner y el dato.
 */
function SubirXml({ subir, subiendo, t, destacado }: {
  subir: (f: File) => void; subiendo: boolean;
  t: ReturnType<typeof useTranslations>; destacado?: boolean;
}) {
  return (
    <label title={t("subirNota")} style={{
      ...btn, display: "inline-flex", alignItems: "center", gap: 6,
      cursor: subiendo ? "wait" : "pointer",
      ...(destacado ? { borderColor: GOLD, background: "#fdf8ec", fontWeight: 600 } : {}),
    }}>
      {subiendo ? "⏳" : "↑"} {subiendo ? t("subiendo") : t("subirXml")}
      <input type="file" accept=".xml,.XML" style={{ display: "none" }} disabled={subiendo}
             onChange={e => { const f = e.target.files?.[0]; if (f) subir(f); e.target.value = ""; }} />
    </label>
  );
}

/** Lo que se ve cuando todavía no hay ningún corte: la puerta, no un aviso. */
function ZonaVacia({ subir, subiendo, t }: {
  subir: (f: File) => void; subiendo: boolean; t: ReturnType<typeof useTranslations>;
}) {
  return (
    <label style={{
      display: "block", marginTop: 20, padding: "40px 24px", textAlign: "center",
      border: `2px dashed ${GOLD}`, borderRadius: 12, background: "#fdfbf5",
      cursor: subiendo ? "wait" : "pointer", maxWidth: 720,
    }}>
      <div style={{ fontSize: 30, lineHeight: 1 }}>↑</div>
      <div style={{ fontSize: 16, fontWeight: 600, marginTop: 10 }}>
        {subiendo ? t("subiendo") : t("vacioTitulo")}
      </div>
      <div style={{ fontSize: 12.5, color: "#666", marginTop: 8,
                    maxWidth: 520, marginInline: "auto", lineHeight: 1.6 }}>
        {t("vacioNota")}
      </div>
      <input type="file" accept=".xml,.XML" style={{ display: "none" }} disabled={subiendo}
             onChange={e => { const f = e.target.files?.[0]; if (f) subir(f); e.target.value = ""; }} />
    </label>
  );
}

// ─────────────────────────────── piezas sueltas ─────────────────────────────
function Tarjetas({ items }: { items: { rot: string; val: string; tono?: string }[] }) {
  return (
    <div style={{ display: "flex", gap: 18, marginTop: 16, flexWrap: "wrap" }}>
      {items.map(i => <Tarjeta key={i.rot} rot={i.rot} val={i.val} tono={i.tono} />)}
    </div>
  );
}

function Tarjeta({ rot, val, sub, tono: c }: {
  rot: string; val: string; sub?: string; tono?: string;
}) {
  return (
    <div style={{ border: "1px solid #e6e6e6", borderRadius: 8, padding: "10px 16px",
                  minWidth: 160, background: "#fff" }}>
      <div style={{ fontSize: 11, color: "#777", textTransform: "uppercase",
                    letterSpacing: .4 }}>{rot}</div>
      <div style={{ fontSize: 22, fontWeight: 600, color: c ?? "#111",
                    fontVariantNumeric: "tabular-nums" }}>{val}</div>
      {sub && <div style={{ fontSize: 12, color: "#666" }}>{sub}</div>}
    </div>
  );
}

const btn: React.CSSProperties = {
  border: "1px solid #ccc", borderRadius: 6, padding: "6px 14px",
  background: "#fff", cursor: "pointer", fontSize: 13,
};
const btnMini: React.CSSProperties = {
  border: "1px solid #e0cfcf", borderRadius: 5, padding: "2px 9px",
  background: "#fff", cursor: "pointer", fontSize: 11, color: "#b3261e",
};
const sel: React.CSSProperties = {
  border: "1px solid #ccc", borderRadius: 6, padding: "5px 9px", fontSize: 13,
};
const tabBtn: React.CSSProperties = {
  background: "none", border: "none", borderBottom: "2px solid transparent",
  padding: "8px 16px", cursor: "pointer", fontSize: 14,
};
const chip: React.CSSProperties = {
  border: "1px solid #ddd", borderRadius: 8, padding: "8px 16px",
  cursor: "pointer", minWidth: 120, textAlign: "left",
};
const h3: React.CSSProperties = { fontSize: 15, margin: "26px 0 6px" };
const nota: React.CSSProperties = {
  fontSize: 12, color: "#666", margin: "10px 0", maxWidth: 940, lineHeight: 1.5,
};
const tabla: React.CSSProperties = {
  borderCollapse: "collapse", fontSize: 12.5, width: "100%", marginTop: 8,
};
const th: React.CSSProperties = {
  textAlign: "left", padding: "7px 9px", borderBottom: "2px solid #ddd",
  fontWeight: 600, fontSize: 11.5, color: "#555", whiteSpace: "nowrap",
};
const thN: React.CSSProperties = { ...th, textAlign: "right" };
const td: React.CSSProperties = {
  padding: "5px 9px", borderBottom: "1px solid #f0f0f0", whiteSpace: "nowrap",
};
const tdN: React.CSSProperties = {
  ...td, textAlign: "right", fontVariantNumeric: "tabular-nums",
};
const tdT: React.CSSProperties = {
  ...tdN, borderTop: "2px solid #ddd", borderBottom: "none",
  fontWeight: 700, background: "#fafafa",
};
const aviso = (c: string): React.CSSProperties => ({
  border: `1px solid ${c}33`, background: `${c}0f`, color: c,
  borderRadius: 6, padding: "8px 12px", fontSize: 12.5, margin: "12px 0",
  maxWidth: 940,
});
