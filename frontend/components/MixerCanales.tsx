"use client";
/**
 * Master Data → Canales. El mixer y el panorama de las tres listas.
 *
 * **Qué resuelve.** El sistema tenía tres listas de canales que describen el
 * mismo negocio y no decían lo mismo: los market codes de Opera (¿cómo entró?),
 * los 7 canales comerciales (¿quién cobra?) y los 3 de comisión (¿cuánto pago?).
 * Acá se planifica en los 7 y los 3 se calculan — una sola se mantiene.
 *
 * **Por qué Aplicar es un botón.** El mixer mueve el Net Factor, y ese factor
 * multiplica el ingreso de habitaciones de todo el presupuesto. La pantalla
 * muestra el antes, el después y la diferencia en plata; escribir es aparte.
 */
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  aplicarMixer, borrarCanalComision, borrarSubCanal, crearCanalComision,
  crearSubCanal, getEscenariosMixer, getMixer, getPanoramaCanales,
  guardarBaseMixer, guardarMixer, recalculateScenario,
  type EscenarioMixer, type MixerVista, type PanoramaCanales,
} from "@/lib/api";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import { sharedScenarioOr } from "@/lib/planningScenario";

const BTN: React.CSSProperties = {
  padding: "7px 14px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 13, fontWeight: 600,
};
const BTN_FUERTE: React.CSSProperties = {
  ...BTN, background: "var(--accent-primary, #1A7F4B)", color: "#fff",
  borderColor: "transparent",
};
const BTN_CHICO: React.CSSProperties = {
  padding: "6px 12px", fontSize: 12.5, fontWeight: 600, borderRadius: 6,
  cursor: "pointer", border: "1px solid var(--brand)",
  background: "transparent", color: "var(--brand)",
};
const BTN_PLANO: React.CSSProperties = {
  ...BTN_CHICO, border: "1px solid var(--border-medium)",
  color: "var(--text-secondary)", fontWeight: 400,
};
const INP: React.CSSProperties = {
  padding: "6px 9px", fontSize: 12.5, borderRadius: 6,
  border: "1px solid var(--border-subtle)", background: "var(--bg-input)",
  color: "var(--text-primary)",
};
const TH: React.CSSProperties = {
  textAlign: "left", padding: "8px 10px", fontSize: 12, fontWeight: 700,
  borderBottom: "1px solid var(--border-medium)", color: "var(--text-secondary)",
  textTransform: "uppercase", letterSpacing: ".03em", whiteSpace: "nowrap",
};
const TD: React.CSSProperties = {
  padding: "7px 10px", fontSize: 13, borderBottom: "1px solid var(--border-subtle)",
};
const NUM: React.CSSProperties = { ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" };
const CAJA: React.CSSProperties = {
  border: "1px solid var(--border-subtle)", borderRadius: 8,
  background: "var(--bg-surface)", padding: 16, marginBottom: 20,
};

const pct = (v: number, d = 2) => `${(v * 100).toFixed(d)}%`;
const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** Un input de porcentaje que guarda fracción y muestra número entero. */
function CeldaPct({ valor, onChange }: { valor: number; onChange: (v: number) => void }) {
  const [texto, setTexto] = useState(String(+(valor * 100).toFixed(4)));
  useEffect(() => { setTexto(String(+(valor * 100).toFixed(4))); }, [valor]);
  return (
    <input
      value={texto}
      onChange={e => setTexto(e.target.value)}
      onBlur={() => {
        const n = parseFloat(texto.replace(/[%\s,]/g, ""));
        onChange(isNaN(n) ? 0 : n / 100);
      }}
      style={{
        width: 64, textAlign: "right", padding: "3px 6px", fontSize: 13,
        borderRadius: 4, border: "1px solid var(--border-medium)",
        background: "var(--bg-base)", color: "var(--text-primary)",
        fontVariantNumeric: "tabular-nums",
      }}
    />
  );
}

/** Con cuál abre la pantalla.
 *
 * Owner (2026-08-14): «necesito por default Budget Working 2027». Caía en
 * Draft1 2027 porque la lista viene ordenada por año/tipo/versión y ese es el
 * primero que el mixer gobierna — o sea, se abría en una versión vieja.
 *
 * El *Working* es el borrador vivo: el que se está construyendo. Se busca por
 * versión y no por nombre fijo, así el día que el año en curso sea 2028 la
 * pantalla sigue abriendo en el borrador correcto sin tocar código.
 */
function preferido(escs: EscenarioMixer[]): EscenarioMixer | undefined {
  const gobernados = escs.filter(e => e.aplica);
  // Si ya venía uno elegido en otro tab y el mixer lo gobierna, se respeta:
  // es la convención de la app (`planningScenario`) y evita que esta pantalla
  // le cambie el escenario por debajo a quien venía trabajando en otro.
  const compartido = sharedScenarioOr("");
  return gobernados.find(e => e.id === compartido)
    ?? gobernados.find(e => e.version.toLowerCase() === "working")
    ?? gobernados[0] ?? escs[0];
}

export default function MixerCanales() {
  const t = useTranslations("channels");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  //: «Anual» + los doce meses cortos del catálogo. Índice 0 = el mix anual.
  const MESES = [tc("annual"), ...(tm.raw("short") as string[])];
  const b = { b: (c: React.ReactNode) => <b>{c}</b> };
  const [escenarios, setEscenarios] = useState<EscenarioMixer[]>([]);
  const [desdeElAno, setDesdeElAno] = useState(2027);
  const [escId, setEscId] = useState("");
  const [mes, setMes] = useState(0);
  const [vista, setVista] = useState<MixerVista | null>(null);
  const [panorama, setPanorama] = useState<PanoramaCanales | null>(null);
  const [edit, setEdit] = useState<Record<string, { mix: number; com: number }>>({});
  //: El «rueda a» editado, por sub-canal. Solo viaja en «Guardar como base»:
  //: cambiar el destino es una decisión de la BASE, no de un escenario.
  const [destinos, setDestinos] = useState<Record<string, string>>({});
  const [sucio, setSucio] = useState(false);
  //: Los formularios de alta, cerrados por defecto.
  const [nuevoSub, setNuevoSub] = useState<{ code: string; nombre: string; rueda_a: string } | null>(null);
  const [nuevoCanal, setNuevoCanal] = useState<{ code: string; nombre: string } | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [aplicando, setAplicando] = useState(false);
  const [regenerar, setRegenerar] = useState(false);
  const [baseSim, setBaseSim] = useState<"rooms" | "comisionable" | "total">("comisionable");
  // Los que se aplicaron y todavia no se recalcularon. Aplicar escribe el
  // factor; hasta que no se recalcula, el P&L sigue mostrando el numero viejo —
  // y no hay nada en pantalla que lo delate.
  const [porRecalcular, setPorRecalcular] = useState<string[]>([]);
  const [recalculando, setRecalculando] = useState<string>("");

  const cargarEscenarios = useCallback(async () => {
    const r = await getEscenariosMixer();
    setEscenarios(r.escenarios);
    setDesdeElAno(r.desde_el_ano);
    // Vienen premarcados los que el mixer gobierna. El owner puede desmarcar,
    // pero no tiene que ir a buscarlos uno por uno.
    setMarcados(new Set(r.escenarios.filter(e => e.aplica).map(e => e.id)));
    return r.escenarios;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const escs = await cargarEscenarios();
        const prefe = preferido(escs);
        if (prefe) setEscId(prefe.id);
      } catch (e) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally { setCargando(false); }
    })();
  }, [cargarEscenarios]);

  const cargarVista = useCallback(async (sid: string, m: number) => {
    if (!sid) return;
    try {
      const [v, p] = await Promise.all([getMixer(sid, m), getPanoramaCanales(sid)]);
      setVista(v); setPanorama(p);
      setEdit(Object.fromEntries(v.subcanales.map(c =>
        [c.code, { mix: c.mix_pct, com: c.comision_pct }])));
      setSucio(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    }
  }, []);

  useEffect(() => { cargarVista(escId, mes); }, [escId, mes, cargarVista]);

  const escActual = escenarios.find(e => e.id === escId);
  const subcanales = vista?.subcanales ?? [];

  // El derivado se recalcula en la pantalla mientras se edita: sin esto habría
  // que guardar para ver el efecto, y el punto del mixer es justamente verlo.
  const derivadosVivos = (() => {
    // ⚠️ Los canales salen de la LISTA que manda el backend, no de tres códigos
    // escritos acá. Antes eran `{TA, OTA, DIRECT}` fijos y, peor, lo que rodara
    // a otro lado caía en `acum.DIRECT` por el `??`: un canal nuevo sumaba su
    // mix a DIRECT y cobraba la comisión de DIRECT, sin que nada avisara.
    const acum: Record<string, { mix: number; pond: number }> = {};
    for (const d of vista?.canales ?? []) acum[d.code] = { mix: 0, pond: 0 };
    for (const c of subcanales) {
      const e = edit[c.code] ?? { mix: c.mix_pct, com: c.comision_pct };
      const destino = destinos[c.code] ?? c.destino;
      // Un destino que todavía no está en la lista se crea al vuelo para que su
      // mix se VEA en la suma, en vez de mezclarse con DIRECT.
      const d = (acum[destino] ??= { mix: 0, pond: 0 });
      d.mix += e.mix; d.pond += e.mix * e.com;
    }
    return Object.entries(acum).map(([channel, v]) => ({
      channel, mix_pct: v.mix, commission_pct: v.mix ? v.pond / v.mix : 0,
    }));
  })();
  const sumaMix = derivadosVivos.reduce((a, d) => a + d.mix_pct, 0);
  const cierra = Math.abs(sumaMix - 1) <= 0.0001;
  const nfNuevo = derivadosVivos.reduce((a, d) => a + d.mix_pct * (1 - d.commission_pct), 0);
  const nfHoy = vista?.net_factor_hoy ?? null;
  const rooms = vista?.impacto?.rooms_usd ?? 0;
  const deltaUsd = nfHoy ? rooms * (nfNuevo / nfHoy - 1) : null;

  // ── Cuanto es en plata cada % ──────────────────────────────────────────────
  // ⚠️ El mix se aplica sobre la venta RACK y la comision se resta de ahi. Lo
  // que sale del P&L ya es NETO, asi que primero hay que devolverlo a rack
  // dividiendo por el factor vigente. Repartir el neto daria una comision
  // calculada sobre una base ya comisionada — mal, y sin que nada avise.
  const netoBase = vista?.bases?.[baseSim] ?? 0;
  const rack = nfHoy ? netoBase / nfHoy : 0;
  const simulacion = subcanales.map(c => {
    const e = edit[c.code] ?? { mix: c.mix_pct, com: c.comision_pct };
    const bruto = rack * e.mix;
    const comision = bruto * e.com;
    return { code: c.code, nombre: c.nombre, mix: e.mix, com: e.com,
             bruto, comision, neto: bruto - comision };
  });
  const totBruto = simulacion.reduce((a, x) => a + x.bruto, 0);
  const totComision = simulacion.reduce((a, x) => a + x.comision, 0);
  const totNeto = totBruto - totComision;

  /** Alta de un sub-canal. `rueda_a` es obligatorio: es lo que evita que entre
   *  como DIRECT por default y cobre 9,27% en vez del 30% de TA. */
  async function altaSubCanal() {
    if (!nuevoSub?.code.trim() || !nuevoSub.rueda_a) return;
    setError(null);
    try {
      await crearSubCanal({
        code: nuevoSub.code.trim().toUpperCase(),
        nombre: nuevoSub.nombre.trim() || nuevoSub.code.trim(),
        rueda_a: nuevoSub.rueda_a, mix_pct: 0, comision_pct: 0,
      });
      setNuevoSub(null);
      setAviso(t("mixer.subCreated"));
      await cargarVista(escId, mes);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  async function bajaSubCanal(code: string, nombre: string) {
    if (!window.confirm(t("mixer.confirmDeleteSub", { nombre }))) return;
    setError(null);
    try {
      const r = await borrarSubCanal(code);
      setAviso(r.aviso ?? t("mixer.subDeleted", { mix: pct(r.mix_suma, 1) }));
      await cargarVista(escId, mes);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  async function altaCanal() {
    if (!nuevoCanal?.code.trim()) return;
    setError(null);
    try {
      await crearCanalComision({
        code: nuevoCanal.code.trim().toUpperCase(),
        nombre: nuevoCanal.nombre.trim() || nuevoCanal.code.trim(),
      });
      setNuevoCanal(null);
      setAviso(t("mixer.channelCreated"));
      await cargarVista(escId, mes);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  async function bajaCanal(code: string) {
    if (!window.confirm(t("mixer.confirmDeleteChannel", { code }))) return;
    setError(null);
    try {
      await borrarCanalComision(code);
      setAviso(t("mixer.channelDeleted", { code }));
      await cargarVista(escId, mes);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  async function guardar() {
    if (!escId) return;
    if (!cierra) { setError(t("mixer.mixSumError", { mix: pct(sumaMix, 1) })); return; }
    setError(null);
    try {
      await guardarMixer(escId, subcanales.map(c => ({
        code: c.code, month: mes,
        mix_pct: edit[c.code]?.mix ?? c.mix_pct,
        comision_pct: edit[c.code]?.com ?? c.comision_pct,
      })));
      setAviso(t("mixer.saved", { periodo: MESES[mes] }));
      await cargarVista(escId, mes);
      await cargarEscenarios();
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  async function guardarBase() {
    if (!cierra) { setError(t("mixer.mixSumError", { mix: pct(sumaMix, 1) })); return; }
    setError(null);
    try {
      await guardarBaseMixer(subcanales.map(c => ({
        code: c.code, month: 0,
        mix_pct: edit[c.code]?.mix ?? c.mix_pct,
        comision_pct: edit[c.code]?.com ?? c.comision_pct,
        rueda_a: destinos[c.code] ?? c.destino,
      })));
      setAviso(t("mixer.savedBase"));
      await cargarVista(escId, mes);
      await cargarEscenarios();
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  async function aplicar() {
    const ids = [...marcados];
    if (!ids.length) return;
    setAplicando(true); setError(null);
    try {
      const r = await aplicarMixer(ids, regenerar);
      const tarifas = r.aplicados.reduce((a, x) => a + (x.tarifas ?? 0), 0);
      const partes = [tarifas
        ? t("mixer.appliedRates", { n: r.aplicados.length, tarifas })
        : t("mixer.applied", { n: r.aplicados.length })];
      if (r.saltados.length) {
        partes.push(t("mixer.skipped", {
          lista: r.saltados.map(s => `${s.nombre} (${s.motivo})`).join("; "),
        }));
      }
      if (r.aviso) partes.push(r.aviso);
      setAviso(partes.join(" "));
      setPorRecalcular(r.aplicados.map(x => x.id));
      await cargarEscenarios();
      await cargarVista(escId, mes);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setAplicando(false); }
  }

  async function recalcular() {
    // Uno por uno y no en paralelo: recalcular un escenario recorre los 12 meses
    // y reescribe todo el P&L. Siete a la vez tumbarian el backend, y el error
    // llegaria como un fallo cualquiera sin decir que fue por eso.
    const ids = porRecalcular.length ? porRecalcular
      : [...marcados].filter(id => escenarios.find(e => e.id === id)?.aplica);
    if (!ids.length) return;
    setError(null);
    const listos = new Set<string>();
    const fallaron: string[] = [];
    const avisos: string[] = [];
    for (const id of ids) {
      const nombre = escenarios.find(e => e.id === id)?.nombre ?? id;
      setRecalculando(nombre);
      try {
        const r = await recalculateScenario(id);
        listos.add(id);
        (r.avisos ?? []).forEach(a => avisos.push(`${nombre}: ${a}`));
      } catch (e) {
        fallaron.push(`${nombre} (${e instanceof Error ? e.message : tc("error")})`);
      }
    }
    setRecalculando("");
    // Solo salen de la cola los que de verdad pasaron: si uno fallo tiene que
    // seguir pendiente, o queda con el factor nuevo escrito y el P&L viejo.
    setPorRecalcular(p => p.filter(id => !listos.has(id)));
    const partes = [t("mixer.recalculated", { ok: listos.size, total: ids.length })];
    if (fallaron.length) partes.push(t("mixer.recalcFailed", { lista: fallaron.join("; ") }));
    if (avisos.length) partes.push(avisos.join(" · "));
    if (fallaron.length) setError(partes.join(" ")); else setAviso(partes.join(" "));
    await cargarVista(escId, mes);
    await cargarEscenarios();
  }

  function bajar() {
    // Los % van como FRACCIÓN con formato "pct": un "30.00%" en texto no se
    // puede sumar ni graficar, que es para lo que se baja el archivo.
    const cols: ColumnaCuadro[] = [
      { label: t("mixer.colSub"), ancho: 34 },
      { label: t("mixer.colDescribes"), ancho: 18, formato: "texto" },
      { label: t("mixer.colRolls"), ancho: 12, formato: "texto" },
      { label: t("mixer.colMix"), formato: "pct" },
      { label: t("mixer.colCommission"), formato: "pct" },
      { label: t("mixer.colSource"), ancho: 16, formato: "texto" },
    ];
    const filas: FilaCuadro[] = subcanales.map(c => {
      const e = edit[c.code] ?? { mix: c.mix_pct, com: c.comision_pct };
      return {
        label: c.nombre,
        valores: [
          c.eje === "entrada" ? t("mixer.byEntry") : t("mixer.byWho"),
          c.destino, e.mix, e.com,
          c.origen === "base" ? t("mixer.srcBase")
            : c.origen === "escenario" ? t("mixer.srcScenario") : MESES[mes],
        ],
      };
    });
    filas.push({
      label: t("mixer.mixSum"), es_total: true,
      valores: [null, null, sumaMix, null, null],
    });

    const colsDer: ColumnaCuadro[] = [
      { label: t("mixer.colChannel"), ancho: 20 },
      { label: t("mixer.colMix"), formato: "pct" },
      { label: t("mixer.colCommission"), formato: "pct" },
      { label: t("mixer.colNetContrib"), formato: "num" },
    ];
    const derivadas: FilaCuadro[] = derivadosVivos.map(d => ({
      label: d.channel,
      valores: [d.mix_pct, d.commission_pct, d.mix_pct * (1 - d.commission_pct)],
    }));
    derivadas.push({
      label: "Net Factor", es_total: true, valores: [null, null, nfNuevo],
    });

    bajarCuadros("mixer_canales", [
      {
        titulo: t("mixer.xlsSubTitle"),
        subtitulo: `${escActual?.nombre ?? ""} · ${MESES[mes]}`,
        hoja: t("mixer.xlsSubSheet"), columnas: cols, filas,
      },
      {
        titulo: t("mixer.xlsDerivedTitle"),
        subtitulo: nfHoy === null
          ? t("mixer.xlsNoChannels")
          : t("mixer.xlsNfChange", { hoy: nfHoy.toFixed(4), nuevo: nfNuevo.toFixed(4) }),
        hoja: t("mixer.xlsDerivedSheet"), columnas: colsDer, filas: derivadas,
      },
    ]);
  }

  if (cargando) return <div style={{ padding: 24 }}>{tc("loading")}</div>;

  const totalImpacto = escenarios
    .filter(e => marcados.has(e.id) && e.aplica)
    .reduce((a, e) => a + (e.impacto.delta_usd ?? 0), 0);

  return (
    <div className="pag pag-ancha" style={{ padding: "20px 24px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("mixer.title")}</h1>
      <p style={{ maxWidth: "80ch", fontSize: 13, color: "var(--text-secondary)", marginBottom: 20 }}>
        {t.rich("mixer.intro", b)}
      </p>

      {error && (
        <div style={{ ...CAJA, borderColor: "#C0392B", color: "#C0392B" }}>{error}</div>
      )}
      {aviso && (
        <div style={{ ...CAJA, borderColor: "#1A7F4B" }}>
          {aviso}
          <button onClick={() => setAviso(null)} style={{ ...BTN, marginLeft: 12, padding: "3px 10px" }}>
            {tc("close")}
          </button>
        </div>
      )}

      {/* ── El mixer ───────────────────────────────────────────────────── */}
      <div style={CAJA}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
          <select value={escId} onChange={e => setEscId(e.target.value)}
                  style={{ ...BTN, fontWeight: 500, minWidth: 240 }}>
            {escenarios.map(e => (
              <option key={e.id} value={e.id}>
                {e.nombre}{e.aplica ? "" : t("mixer.notApplied")}
              </option>
            ))}
          </select>
          <select value={mes} onChange={e => setMes(Number(e.target.value))}
                  style={{ ...BTN, fontWeight: 500 }}>
            {MESES.map((m, i) => <option key={m} value={i}>{m}</option>)}
          </select>
          <div style={{ flex: 1 }} />
          <button onClick={bajar} style={BTN}>{t("mixer.download")}</button>
          <button onClick={guardarBase} disabled={!sucio || mes !== 0}
                  title={t("mixer.saveBaseHint")}
                  style={{ ...BTN, opacity: sucio && mes === 0 ? 1 : 0.45 }}>
            {t("mixer.saveBase")}
          </button>
          <button onClick={guardar} disabled={!sucio || !escActual?.aplica}
                  title={t("mixer.saveScenarioHint")}
                  style={{ ...BTN, opacity: sucio && escActual?.aplica ? 1 : 0.45 }}>
            {t("mixer.saveScenario")}
          </button>
        </div>

        <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
          {t.rich("mixer.saveHelp", b)}
        </p>
        {escActual && !escActual.aplica && (
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
            {t.rich("mixer.locked", { ...b, motivo: escActual.motivo })}
          </p>
        )}
        {mes > 0 && (
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
            {t.rich("mixer.monthException", { ...b, mes: MESES[mes], anual: MESES[0] })}
          </p>
        )}

        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={TH}>{t("mixer.colSub")}</th>
                <th style={TH}>{t("mixer.colDescribes")}</th>
                <th style={TH}>{t("mixer.colRolls")}</th>
                <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colMix")}</th>
                <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colCommission")}</th>
                <th style={TH}>{t("mixer.colSource")}</th>
                <th style={{ ...TH, width: 34 }}></th>
              </tr>
            </thead>
            <tbody>
              {subcanales.map(c => {
                const e = edit[c.code] ?? { mix: c.mix_pct, com: c.comision_pct };
                return (
                  <tr key={c.code}>
                    <td style={TD}>
                      <strong>{c.nombre}</strong>
                      <span style={{ color: "var(--text-secondary)", marginLeft: 6, fontSize: 11 }}>
                        {c.code}
                      </span>
                    </td>
                    <td style={{ ...TD, color: "var(--text-secondary)", fontSize: 12 }}>
                      {c.eje === "entrada" ? t("mixer.byEntry") : t("mixer.byWho")}
                    </td>
                    <td style={TD}>
                      {/* Editable: es el dato que decide a qué comisión rueda.
                          Antes se deducía de `entrada` con DIRECT de default. */}
                      <select
                        className="fin-input"
                        style={{ fontSize: 12, padding: "3px 6px", borderRadius: 5 }}
                        value={destinos[c.code] ?? c.destino}
                        onChange={ev => {
                          setDestinos(p => ({ ...p, [c.code]: ev.target.value }));
                          setSucio(true);
                        }}>
                        {(vista?.canales ?? []).map(d => (
                          <option key={d.code} value={d.code}>{d.code}</option>
                        ))}
                        {/* El destino actual, si el canal ya no existe: que se
                            vea en vez de saltar a otro en silencio. */}
                        {!(vista?.canales ?? []).some(d => d.code === (destinos[c.code] ?? c.destino)) && (
                          <option value={destinos[c.code] ?? c.destino}>
                            {t("mixer.missing", { code: destinos[c.code] ?? c.destino })}
                          </option>
                        )}
                      </select>
                    </td>
                    <td style={NUM}>
                      <CeldaPct valor={e.mix} onChange={v => {
                        setEdit(p => ({ ...p, [c.code]: { ...e, mix: v } })); setSucio(true);
                      }} />
                    </td>
                    <td style={NUM}>
                      <CeldaPct valor={e.com} onChange={v => {
                        setEdit(p => ({ ...p, [c.code]: { ...e, com: v } })); setSucio(true);
                      }} />
                    </td>
                    <td style={{ ...TD, fontSize: 12, color: "var(--text-secondary)" }}>
                      {c.origen === "base" ? t("mixer.srcBase")
                        : c.origen === "escenario" ? t("mixer.srcScenario") : `${MESES[mes]}`}
                    </td>
                    <td style={{ ...TD, textAlign: "center" }}>
                      <button
                        onClick={() => void bajaSubCanal(c.code, c.nombre)}
                        title={t("mixer.deleteSub")}
                        style={{
                          border: "none", background: "transparent", cursor: "pointer",
                          color: "var(--text-secondary)", fontSize: 15, lineHeight: 1,
                          padding: "2px 6px",
                        }}>×</button>
                    </td>
                  </tr>
                );
              })}
              <tr>
                <td style={{ ...TD, fontWeight: 700 }} colSpan={3}>{t("mixer.mixSum")}</td>
                <td style={{ ...NUM, fontWeight: 700, color: cierra ? "inherit" : "#C0392B" }}>
                  {pct(sumaMix, 1)}
                </td>
                <td style={TD} colSpan={3}>
                  {!cierra && (
                    <span style={{ color: "#C0392B", fontSize: 12 }}>
                      {t("mixer.mixMustBe100")}
                    </span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* ── Crear ────────────────────────────────────────────────────────
            Owner 2026-08-17: «dejame crear más mix y borrar también, y que el
            derivado lo tome... deben estar sincronizados para que ruede donde
            corresponde». `rueda a` es obligatorio y se valida contra la tabla:
            es lo que evita que un sub-canal nuevo entre como DIRECT y cobre
            9,27% en vez del 30% de TA. */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center",
          marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border-subtle)" }}>
          {!nuevoSub ? (
            <button onClick={() => setNuevoSub({ code: "", nombre: "", rueda_a: vista?.canales?.[0]?.code ?? "" })}
              style={BTN_CHICO}>{t("mixer.addSub")}</button>
          ) : (
            <>
              <input className="fin-input" placeholder={t("mixer.codePlaceholderSub")} autoFocus
                style={{ ...INP, width: 170 }} value={nuevoSub.code}
                onChange={e => setNuevoSub({ ...nuevoSub, code: e.target.value })} />
              <input className="fin-input" placeholder={tc("name")}
                style={{ ...INP, width: 200 }} value={nuevoSub.nombre}
                onChange={e => setNuevoSub({ ...nuevoSub, nombre: e.target.value })} />
              <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                {t("mixer.rollsTo")}{" "}
                <select className="fin-input" style={INP} value={nuevoSub.rueda_a}
                  onChange={e => setNuevoSub({ ...nuevoSub, rueda_a: e.target.value })}>
                  {(vista?.canales ?? []).map(d => (
                    <option key={d.code} value={d.code}>{d.code}</option>))}
                </select>
              </label>
              <button onClick={() => void altaSubCanal()} style={BTN_CHICO}>{t("mixer.create")}</button>
              <button onClick={() => setNuevoSub(null)} style={BTN_PLANO}>{tc("cancel")}</button>
              <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                {t("mixer.newSubHint")}
              </span>
            </>
          )}

          <span style={{ width: 1, height: 20, background: "var(--border-subtle)" }} />

          {!nuevoCanal ? (
            <button onClick={() => setNuevoCanal({ code: "", nombre: "" })}
              style={BTN_PLANO}>{t("mixer.addChannel")}</button>
          ) : (
            <>
              <input className="fin-input" placeholder={t("mixer.codePlaceholderChannel")} autoFocus
                style={{ ...INP, width: 170 }} value={nuevoCanal.code}
                onChange={e => setNuevoCanal({ ...nuevoCanal, code: e.target.value })} />
              <input className="fin-input" placeholder={tc("name")}
                style={{ ...INP, width: 200 }} value={nuevoCanal.nombre}
                onChange={e => setNuevoCanal({ ...nuevoCanal, nombre: e.target.value })} />
              <button onClick={() => void altaCanal()} style={BTN_CHICO}>{t("mixer.create")}</button>
              <button onClick={() => setNuevoCanal(null)} style={BTN_PLANO}>{tc("cancel")}</button>
            </>
          )}
        </div>

        {/* Los canales que existen, con el borrar de cada uno. Uno con
            sub-canales colgando NO se puede borrar: su mix quedaría sin destino
            y el Net Factor saldría sobre menos del 100%. */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
          marginTop: 10, fontSize: 12, color: "var(--text-secondary)" }}>
          <span>{t("mixer.channelsLabel")}</span>
          {(vista?.canales ?? []).map(d => {
            const cuelgan = subcanales.filter(
              c => (destinos[c.code] ?? c.destino) === d.code).length;
            return (
              <span key={d.code} style={{
                display: "inline-flex", alignItems: "center", gap: 5,
                padding: "3px 9px", borderRadius: 999,
                border: "1px solid var(--border-subtle)",
              }}>
                {d.code}
                <span style={{ opacity: .6 }}>· {cuelgan}</span>
                {cuelgan === 0 && (
                  <button onClick={() => void bajaCanal(d.code)} title={t("mixer.deleteChannel")}
                    style={{ border: "none", background: "transparent", cursor: "pointer",
                      color: "var(--text-secondary)", padding: 0, lineHeight: 1 }}>×</button>
                )}
              </span>
            );
          })}
        </div>
      </div>

      {/* ── Lo que se deriva · y cuanto es en plata ───────────────────── */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>
      <div style={{ ...CAJA, flex: "1 1 460px", minWidth: 380 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>
          {t("mixer.derivedTitle")}
        </h2>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
          {t.rich("mixer.derivedHelp", b)}
        </p>
        <table style={{ width: "100%", borderCollapse: "collapse", maxWidth: 620 }}>
          <thead>
            <tr>
              <th style={TH}>{t("mixer.colChannel")}</th>
              <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colMix")}</th>
              <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colCommission")}</th>
              <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colNetContrib")}</th>
            </tr>
          </thead>
          <tbody>
            {derivadosVivos.map(d => (
              <tr key={d.channel}>
                <td style={TD}><strong>{d.channel}</strong></td>
                <td style={NUM}>{pct(d.mix_pct, 1)}</td>
                <td style={NUM}>{pct(d.commission_pct)}</td>
                <td style={NUM}>{(d.mix_pct * (1 - d.commission_pct)).toFixed(4)}</td>
              </tr>
            ))}
            <tr>
              <td style={{ ...TD, fontWeight: 700 }} colSpan={3}>Net Factor</td>
              <td style={{ ...NUM, fontWeight: 700 }}>{nfNuevo.toFixed(4)}</td>
            </tr>
          </tbody>
        </table>

        <div style={{ display: "flex", gap: 28, marginTop: 16, flexWrap: "wrap", fontSize: 13 }}>
          <div>
            <div style={{ color: "var(--text-secondary)", fontSize: 11, textTransform: "uppercase" }}>
              {t("mixer.nfToday")}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>
              {nfHoy === null ? t("mixer.unsaved") : nfHoy.toFixed(4)}
            </div>
          </div>
          <div>
            <div style={{ color: "var(--text-secondary)", fontSize: 11, textTransform: "uppercase" }}>
              {t("mixer.nfWithMixer")}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{nfNuevo.toFixed(4)}</div>
          </div>
          <div>
            <div style={{ color: "var(--text-secondary)", fontSize: 11, textTransform: "uppercase" }}>
              {t("mixer.roomsRevenue")}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{usd(rooms)}</div>
          </div>
          <div>
            <div style={{ color: "var(--text-secondary)", fontSize: 11, textTransform: "uppercase" }}>
              {t("mixer.moves")}
            </div>
            <div style={{
              fontSize: 20, fontWeight: 700,
              color: deltaUsd === null ? "inherit" : deltaUsd < 0 ? "#C0392B" : "#1A7F4B",
            }}>
              {deltaUsd === null ? "—" : usd(deltaUsd)}
            </div>
          </div>
        </div>
        {nfHoy === null && (
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 10 }}>
            {t("mixer.noFactorHelp")}
          </p>
        )}
        {vista?.manda === "tarifas" && (
          <p style={{
            fontSize: 12, marginTop: 12, padding: "9px 11px", borderRadius: 6,
            borderLeft: "3px solid #856404", background: "var(--bg-base)",
          }}>
            {t.rich("mixer.ratesWin", {
              ...b, code: (c: React.ReactNode) => <code>{c}</code>,
            })}
          </p>
        )}
      </div>

      {/* ── Cuanto es en plata cada % ─────────────────────────────────── */}
      <div style={{ ...CAJA, flex: "1 1 460px", minWidth: 400 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "baseline",
                      justifyContent: "space-between", flexWrap: "wrap" }}>
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>{t("mixer.moneyTitle")}</h2>
          <select value={baseSim} onChange={e => setBaseSim(e.target.value as typeof baseSim)}
                  style={{ ...BTN, fontWeight: 500, padding: "5px 10px", fontSize: 12 }}>
            <option value="rooms">{t("mixer.baseRooms")}</option>
            <option value="comisionable">{t("mixer.baseCommissionable")}</option>
            <option value="total">{t("mixer.baseTotal")}</option>
          </select>
        </div>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "6px 0 12px" }}>
          {t.rich("mixer.moneyHelp", { ...b, nf: nfHoy ? nfHoy.toFixed(4) : "—" })}
          {baseSim === "comisionable" && ` ${t("mixer.moneyHelpCommissionable")}`}
          {baseSim === "total" && ` ${t("mixer.moneyHelpTotal")}`}
        </p>

        {!nfHoy ? (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t("mixer.noRack")}
          </p>
        ) : (
          <>
            <div style={{ display: "flex", gap: 22, marginBottom: 14, flexWrap: "wrap" }}>
              <div>
                <div style={{ color: "var(--text-secondary)", fontSize: 11, textTransform: "uppercase" }}>
                  {t("mixer.netInPl")}
                </div>
                <div style={{ fontSize: 17, fontWeight: 700 }}>{usd(netoBase)}</div>
              </div>
              <div>
                <div style={{ color: "var(--text-secondary)", fontSize: 11, textTransform: "uppercase" }}>
                  {t("mixer.rackSale", { nf: nfHoy.toFixed(4) })}
                </div>
                <div style={{ fontSize: 17, fontWeight: 700 }}>{usd(rack)}</div>
              </div>
            </div>

            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={TH}>{t("mixer.colSub")}</th>
                    <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colRack")}</th>
                    <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colCommission")}</th>
                    <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colNet")}</th>
                  </tr>
                </thead>
                <tbody>
                  {simulacion.map(x => (
                    <tr key={x.code}>
                      <td style={TD}>
                        {x.nombre}
                        <span style={{ color: "var(--text-secondary)", fontSize: 11, marginLeft: 6 }}>
                          {pct(x.mix, 0)} · {pct(x.com, 0)}
                        </span>
                      </td>
                      <td style={NUM}>{usd(x.bruto)}</td>
                      <td style={{ ...NUM, color: x.comision ? "#C0392B" : "inherit" }}>
                        {x.comision ? `−${usd(x.comision)}` : usd(0)}
                      </td>
                      <td style={NUM}>{usd(x.neto)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td style={{ ...TD, fontWeight: 700 }}>{tc("total")}</td>
                    <td style={{ ...NUM, fontWeight: 700 }}>{usd(totBruto)}</td>
                    <td style={{ ...NUM, fontWeight: 700, color: "#C0392B" }}>
                      −{usd(totComision)}
                    </td>
                    <td style={{ ...NUM, fontWeight: 700 }}>{usd(totNeto)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12 }}>
              {t.rich("mixer.diffHelp", {
                ...b,
                d: (c: React.ReactNode) => (
                  <strong style={{ color: totNeto - netoBase < 0 ? "#C0392B" : "#1A7F4B" }}>{c}</strong>
                ),
                hoy: usd(netoBase),
                nuevo: usd(totNeto),
                dif: `${totNeto - netoBase < 0 ? "" : "+"}${usd(totNeto - netoBase)}`,
              })}
            </p>
          </>
        )}
      </div>
      </div>

      {/* ── Aplicar ────────────────────────────────────────────────────── */}
      <div style={CAJA}>
        <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>
          {t("mixer.applyTitle")}
        </h2>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
          {t.rich("mixer.applyHelp", { ...b, ano: String(desdeElAno) })}
        </p>
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...TH, width: 30 }} />
                <th style={TH}>{tc("scenario")}</th>
                <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colNfToday")}</th>
                <th style={TH}>{t("mixer.colComesFrom")}</th>
                <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colNfNew")}</th>
                <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colRooms")}</th>
                <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colMoves")}</th>
                <th style={TH}>{t("mixer.colNote")}</th>
              </tr>
            </thead>
            <tbody>
              {escenarios.map(e => (
                <tr key={e.id} style={{ opacity: e.aplica ? 1 : 0.55 }}>
                  <td style={TD}>
                    <input type="checkbox" checked={marcados.has(e.id)} disabled={!e.aplica}
                      onChange={ev => setMarcados(p => {
                        const n = new Set(p);
                        if (ev.target.checked) n.add(e.id); else n.delete(e.id);
                        return n;
                      })} />
                  </td>
                  <td style={TD}>{e.nombre}</td>
                  <td style={NUM}>{e.net_factor_hoy === null ? "—" : e.net_factor_hoy.toFixed(4)}</td>
                  <td style={{ ...TD, fontSize: 12 }}>
                    {e.manda === "tarifas"
                      ? <span style={{ color: "#856404", fontWeight: 600 }}>{t("mixer.fromRates")}</span>
                      : e.manda === "mix" ? t("mixer.fromMix") : "—"}
                  </td>
                  <td style={NUM}>{e.net_factor_nuevo.toFixed(4)}</td>
                  <td style={NUM}>{e.impacto.rooms_usd ? usd(e.impacto.rooms_usd) : "—"}</td>
                  <td style={{
                    ...NUM,
                    color: (e.impacto.delta_usd ?? 0) < 0 ? "#C0392B" : "inherit",
                  }}>
                    {e.impacto.delta_usd === null ? "—" : usd(e.impacto.delta_usd)}
                  </td>
                  <td style={{ ...TD, fontSize: 12, color: "var(--text-secondary)" }}>
                    {e.motivo}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {porRecalcular.length > 0 && !recalculando && (
          <p style={{
            fontSize: 13, marginTop: 14, padding: "9px 11px", borderRadius: 6,
            borderLeft: "3px solid #856404", background: "var(--bg-base)",
          }}>
            {t.rich("mixer.pendingRecalc", { ...b, n: porRecalcular.length })}
          </p>
        )}
        <label style={{
          display: "flex", gap: 8, alignItems: "flex-start", marginTop: 16,
          fontSize: 13, cursor: "pointer",
        }}>
          <input type="checkbox" checked={regenerar} style={{ marginTop: 3 }}
                 onChange={e => setRegenerar(e.target.checked)} />
          <span>
            {t.rich("mixer.regenRates", {
              ...b, code: (c: React.ReactNode) => <code>{c}</code>,
            })}
            <span style={{ color: "var(--text-secondary)" }}>
              {" "}{t("mixer.regenRatesHelp")}
            </span>
          </span>
        </label>
        <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
          <button onClick={aplicar} disabled={aplicando || !marcados.size} style={{
            ...BTN_FUERTE, opacity: aplicando || !marcados.size ? 0.5 : 1,
          }}>
            {aplicando ? t("mixer.applying") : t("mixer.applyN", { n: marcados.size })}
          </button>
          <button onClick={recalcular}
                  disabled={!!recalculando || (!porRecalcular.length && !marcados.size)}
                  style={{
                    ...BTN,
                    borderColor: porRecalcular.length ? "#856404" : "var(--border-medium)",
                    opacity: recalculando || (!porRecalcular.length && !marcados.size) ? 0.5 : 1,
                  }}>
            {recalculando ? t("mixer.recalcOne", { nombre: recalculando })
              : porRecalcular.length ? t("mixer.recalcPending", { n: porRecalcular.length })
              : t("mixer.recalcMarked")}
          </button>
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t.rich("mixer.totalMoves", {
              b: (c: React.ReactNode) => (
                <strong style={{ color: totalImpacto < 0 ? "#C0392B" : "inherit" }}>{c}</strong>
              ),
              usd: usd(totalImpacto),
            })}
          </span>
        </div>
      </div>

      {/* ── El panorama ────────────────────────────────────────────────── */}
      {panorama && (
        <div style={CAJA}>
          <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>
            {t("mixer.panoramaTitle")}
          </h2>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 14 }}>
            {t("mixer.panoramaHelp")}
          </p>

          {panorama.discrepancias.length > 0 && (
            <div style={{ marginBottom: 18 }}>
              {panorama.discrepancias.map((d, i) => (
                <div key={i} style={{
                  padding: "10px 12px", marginBottom: 8, borderRadius: 6,
                  borderLeft: `3px solid ${d.gravedad === "alta" ? "#C0392B"
                    : d.gravedad === "estructural" ? "#856404" : "var(--border-medium)"}`,
                  background: "var(--bg-base)",
                }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{d.detalle}</div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 3 }}>
                    {d.porque}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 320px" }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                {t("mixer.marketCodesTitle")}
              </h3>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={TH}>{tc("code")}</th><th style={TH}>{t("mixer.colChannel")}</th><th style={TH}>{t("mixer.colRolls")}</th>
                  </tr>
                </thead>
                <tbody>
                  {panorama.market_codes.map(m => (
                    <tr key={m.code}>
                      <td style={TD}>{m.code}</td>
                      <td style={TD}>{m.canal || <em style={{ color: "#C0392B" }}>{t("mixer.noChannel")}</em>}</td>
                      <td style={TD}>{m.canal_comision || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ flex: "1 1 320px" }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                {t("mixer.commissionCompare")}
              </h3>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={TH}>{t("mixer.colChannel")}</th>
                    <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colFinplanToday")}</th>
                    <th style={{ ...TH, textAlign: "right" }}>{t("mixer.colDerived")}</th>
                  </tr>
                </thead>
                <tbody>
                  {derivadosVivos.map(d => (
                    <tr key={d.channel}>
                      <td style={TD}>{d.channel}</td>
                      <td style={NUM}>
                        {panorama.comision_finplan[d.channel] === undefined
                          ? "—" : pct(panorama.comision_finplan[d.channel], 1)}
                      </td>
                      <td style={NUM}>{pct(d.commission_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
