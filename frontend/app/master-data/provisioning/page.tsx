"use client";
import { useCallback, useEffect, useMemo, useState, CSSProperties, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import {
  getProvisioningHotels, getProvisioningDepts, saveProvisioningDepts, copiarProvisioning,
  setHotelLocale,
  type ProvMatrix, type ProvDeptRow,
} from "@/lib/api";
import { setHotelIdentidad, setHotelCodigo } from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { recargarNombreHotel } from "@/lib/useHotel";
import { LOCALES, readLocaleCookie, writeLocaleCookie, type Locale } from "@/lib/locale";
import { bajarCuadros } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

// El idioma con el que abre la app en esta propiedad (decisión D1 del owner).
// Se fija ACÁ, al provisionar, porque es una propiedad del hotel y no de quien
// mira: el default con el que arranca cualquiera que entre. El botón ES/EN del
// header es la otra mitad — la preferencia personal, que pisa a esta.
const NOMBRE_IDIOMA: Record<string, string> = { es: "Español", en: "English" };

const GOLD = "#c8a24a";

const b = (c: ReactNode) => <b>{c}</b>;
const i = (c: ReactNode) => <i>{c}</i>;

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 10.5, textAlign: "left", padding: "9px 12px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.05em", background: "var(--bg-elevated)", whiteSpace: "nowrap" };
const td: CSSProperties = { padding: "7px 12px", borderBottom: "1px solid var(--border-subtle)", fontSize: 12.5 };

type Cambio = { dept_code: string; dimension: string; enabled: boolean };

export default function ProvisioningPage() {
  const tc = useTranslations("common");
  const t = useTranslations("prov");
  const [hotels, setHotels] = useState<{ id: string; name: string; short_name?: string; apagados: number; default_locale?: string }[]>([]);
  const [idioma, setIdioma] = useState<string>("es");
  const [nombre, setNombre] = useState("");
  const [corto, setCorto] = useState("");
  const [guardandoId, setGuardandoId] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [hotelId, setHotelId] = useState("");
  const [data, setData] = useState<ProvMatrix | null>(null);
  // Cambios sin guardar, por (depto|dimensión). Se guardan de un solo golpe:
  // apagar de a uno haría que el aviso de «esto tiene datos» saliera una vez
  // por casilla y se volvería ruido que se acepta sin leer.
  const [cambios, setCambios] = useState<Record<string, boolean>>({});
  const [q, setQ] = useState("");
  const [soloConDatos, setSoloConDatos] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [confirmar, setConfirmar] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const h = await getProvisioningHotels();
        setHotels(h.hotels);
        setHotelId(h.hotels[0]?.id ?? "");
        setIdioma(h.hotels[0]?.default_locale ?? "es");
      } catch (e) { setError(e instanceof Error ? e.message : tc("error")); setLoading(false); }
    })();
  }, [tc]);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError(""); setMsg(""); setConfirmar(null);
    try { setData(await getProvisioningDepts(id)); setCambios({}); }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); setData(null); }
    finally { setLoading(false); }
  }, [tc]);

  useEffect(() => { load(hotelId); }, [hotelId, load]);
  useEffect(() => {
    setIdioma(hotels.find(h => h.id === hotelId)?.default_locale ?? "es");
    const h = hotels.find(x => x.id === hotelId);
    setNombre(h?.name ?? "");
    setCodigo(h?.id ?? "");
    setCorto(h?.short_name ?? "");
  }, [hotelId, hotels]);

  /** Renombra el código y MUEVE el dato. Pide confirmación con el número de
      filas en juego: es una migración, no un cambio de etiqueta. */
  async function guardarCodigo() {
    const nuevo = codigo.trim().toUpperCase();
    if (nuevo === hotelId) return;
    if (!/^[A-Z0-9]{2,10}$/.test(nuevo)) {
      setError(t("codeFormat")); return;
    }
    if (!confirm(t("codeConfirm", { viejo: hotelId, nuevo }))) return;
    setGuardandoId(true); setError(""); setMsg("");
    try {
      const r = await setHotelCodigo(hotelId, nuevo);
      setMsg(t("codeSaved", { anterior: r.anterior, nuevo: r.id, filas: r.filas }));
      const h = await getProvisioningHotels();
      setHotels(h.hotels);
      setHotelId(r.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("codeError"));
    } finally { setGuardandoId(false); }
  }

  /** Cambia SOLO el nombre visible. El código es la llave del dato y no se toca. */
  async function guardarIdentidad() {
    setGuardandoId(true);
    try {
      const r = await setHotelIdentidad(hotelId, nombre.trim(), corto.trim());
      setHotels(hs => hs.map(h => h.id === hotelId
        ? { ...h, name: r.name, short_name: r.short_name } : h));
      // Que la barra de arriba y los reportes lo tomen YA. Sin esto el nombre
      // nuevo no se ve hasta recargar, y se lee como si no hubiera guardado.
      if (hotelId === HOTEL_ID) await recargarNombreHotel();
      setMsg(t("nameSaved", { nombre: r.name }));
    } catch (e) {
      alert(e instanceof Error ? e.message : t("nameError"));
    } finally {
      setGuardandoId(false);
    }
  }

  /** Mueve el default de la propiedad. A quien tenga preferencia propia
      guardada no le cambia nada: `users.locale` en NULL es «usá el del hotel»,
      y con un valor guardado gana el valor. Si el que está mirando no tiene
      preferencia propia, la cookie se sincroniza para que el cambio se vea. */
  async function cambiarIdioma(nuevo: string) {
    setError(""); setMsg("");
    try {
      await setHotelLocale(hotelId, nuevo);
      setIdioma(nuevo);
      setHotels(hs => hs.map(h => h.id === hotelId ? { ...h, default_locale: nuevo } : h));
      setMsg(t("localeSaved", { idioma: NOMBRE_IDIOMA[nuevo] ?? nuevo }));
      if (!readLocaleCookie()) writeLocaleCookie(nuevo);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  const k = (d: string, dim: string) => `${d}|${dim}`;
  const estado = (r: ProvDeptRow, dim: string) =>
    cambios[k(r.dept_code, dim)] ?? r.dims[dim]?.enabled ?? true;

  function toggle(r: ProvDeptRow, dim: string) {
    if (!r.dims[dim]?.aplica) return;
    setConfirmar(null); setMsg("");
    setCambios(c => ({ ...c, [k(r.dept_code, dim)]: !estado(r, dim) }));
  }

  /** Apaga o prende la fila entera: al descartar un departamento que la
      propiedad no tiene, se descarta en todas sus dimensiones. */
  function toggleFila(r: ProvDeptRow, on: boolean) {
    setConfirmar(null); setMsg("");
    setCambios(c => {
      const n = { ...c };
      for (const dim of Object.keys(r.dims)) {
        if (r.dims[dim].aplica) n[k(r.dept_code, dim)] = on;
      }
      return n;
    });
  }

  /** ¿Esta casilla cambia algo si se guarda?
   *
   *  En una casilla normal, cambia si quedó distinta de como estaba. En una
   *  MIXTA no alcanza con comparar: la madre puede estar apagada y sus hijos
   *  prendidos, así que «apagado» ya se muestra apagado pero al guardar recién
   *  ahí se apagan los hijos. Sin esta salvedad, decidir «apagar todo el
   *  paquete» sobre un estado mixto se descartaba en silencio como si no
   *  hubiera cambio, y era justo la decisión que hay que poder tomar. */
  const esCambio = useCallback((dept_code: string, dimension: string): boolean => {
    const v = cambios[k(dept_code, dimension)];
    if (v === undefined) return false;
    const dim = data?.rows.find(r => r.dept_code === dept_code)?.dims[dimension];
    if (!dim) return false;
    return dim.mixto || v !== dim.enabled;
  }, [cambios, data]);

  const pendientes: Cambio[] = useMemo(() => {
    if (!data) return [];
    return Object.entries(cambios).flatMap(([key, enabled]) => {
      const [dept_code, dimension] = key.split("|");
      return esCambio(dept_code, dimension)
        ? [{ dept_code, dimension, enabled }] : [];
    });
  }, [cambios, data, esCambio]);

  // Cuánta información hay detrás de lo que se está por apagar. Es el número
  // que decide si esto es una limpieza o un error.
  const datosEnRiesgo = useMemo(() => {
    if (!data) return 0;
    return pendientes.filter(c => !c.enabled).reduce((a, c) => {
      const r = data.rows.find(x => x.dept_code === c.dept_code);
      return a + (r?.dims[c.dimension]?.datos ?? 0);
    }, 0);
  }, [pendientes, data]);

  async function guardar(force = false) {
    if (!data || !pendientes.length) return;
    setSaving(true); setError(""); setMsg("");
    try {
      const r = await saveProvisioningDepts(hotelId, pendientes, force);
      // Se mandan madres y se escriben paquetes: si no se dijera, «toqué una
      // casilla» y «se guardaron seis» se leería como un error.
      const arrastre = r.casillas > r.recibidas
        ? t("saveDrag", { madres: r.recibidas, casillas: r.casillas })
        : "";
      setMsg(t("saveResult", { apagados: r.apagados, prendidos: r.prendidos, arrastre }));
      setConfirmar(null);
      await load(hotelId);
    } catch (e) {
      const detalle = e instanceof Error ? e.message : tc("error");
      // ⚠️ Se decide por la CLAVE, no por el texto. Antes era
      // `detalle.includes("datos cargados")`, y funcionó mientras el backend
      // hablaba un solo idioma: con los mensajes bilingües, en inglés dice
      // «There is data loaded» y la confirmación NO se abría — apagar un
      // departamento con datos daba error duro y no había forma de seguir.
      const clave = (e as { clave?: string })?.clave;
      if (clave === "provisionamiento.datos_cargados") setConfirmar(detalle);
      else setError(detalle);
    } finally { setSaving(false); }
  }

  // ── Bajar a Excel ────────────────────────────────────────────────────────
  // Esta matriz es la que define qué departamentos existen en una propiedad, y
  // es lo primero que se revisa al abrir un hotel nuevo. Sale con lo que está en
  // pantalla, incluidos los cambios sin guardar: si alguien la baja para
  // revisarla con contabilidad, tiene que ver lo que está por aplicar, no lo que
  // había antes. Por eso el subtítulo lo dice.
  async function bajarExcel() {
    if (!data) return;
    const dims = data.dimensiones;
    const pendientes = Object.keys(cambios).length;
    try {
      await bajarCuadros(t("xlsFile", { hotel: hotelId }), [{
        titulo: t("xlsTitle", { hotel: hotelId }),
        hoja: t("xlsSheet"),
        subtitulo: (pendientes ? t("xlsPending", { n: pendientes }) : "")
          + t("xlsSubtitle"),
        columnas: [
          { label: tc("code"), ancho: 10, formato: "texto" },
          { label: tc("department"), ancho: 34, formato: "texto" },
          { label: t("colInPL"), ancho: 12, formato: "texto" },
          // Antes decía «Padre» y ahora todas las filas SON madres: lo que hace
          // falta ver es al revés, a quién se lleva puesto cada interruptor.
          { label: t("colDrags"), ancho: 40, formato: "texto" },
          ...dims.map(d => ({ label: d.label ?? d.key, ancho: 13, formato: "num" as const })),
          { label: t("colLoadedLines"), ancho: 15, formato: "num" as const },
        ],
        filas: filas.map(r => ({
          label: r.dept_code,
          valores: [
            r.dept_name,
            r.pl_kind === "OVERHEAD" ? t("overhead") : t("operating"),
            r.paquete.filter(m => !m.es_madre).map(m => m.dept_code).join(" ") || null,
            // Vacío cuando la dimensión no aplica: un 0 ahí diría «lo apagaron»,
            // que no es lo mismo que «no existe para este departamento».
            ...dims.map(d => r.dims[d.key]?.aplica ? (estado(r, d.key) ? 1 : 0) : null),
            r.datos_totales || null,
          ],
        })),
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("xlsError")); }
  }

  const filas = useMemo(() => {
    if (!data) return [];
    const t = q.trim().toLowerCase();
    return data.rows.filter(r => {
      if (soloConDatos && !r.datos_totales) return false;
      if (!t) return true;
      // Buscar también adentro del paquete: los hijos ya no tienen fila propia,
      // así que buscar «Housekeeping» tiene que traer Habitaciones. Si no, un
      // departamento que existe parecería haber desaparecido.
      return r.dept_code.includes(t) || r.dept_name.toLowerCase().includes(t)
        || (r.name_en || "").toLowerCase().includes(t)
        || r.paquete.some(m => m.dept_code.includes(t)
          || m.dept_name.toLowerCase().includes(t));
    });
  }, [data, q, soloConDatos]);

  return (
    <div className="pag pag-lectura" style={{ padding: "24px 20px 60px" }}>
      <IrA />
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 25, fontWeight: 800, margin: 0 }}>{t("title")}</h1>
        <select value={hotelId} onChange={e => setHotelId(e.target.value)}
          style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          {hotels.map(h => <option key={h.id} value={h.id}>{h.id} — {h.name}</option>)}
        </select>
        <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}
          title={t("localeHint")}>
          {t("propertyLanguage")}
          <select value={idioma} onChange={e => cambiarIdioma(e.target.value)}
            style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
            {LOCALES.map((l: Locale) => <option key={l} value={l}>{NOMBRE_IDIOMA[l]}</option>)}
          </select>
        </label>
      </div>
      {/* Nombre visible de la propiedad. El CÓDIGO no se edita: es la llave de
          todo el dato — cambiarlo dejaría huérfano el histórico entero. */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 12, flexWrap: "wrap",
                    marginTop: 16, padding: "12px 14px", borderRadius: 8,
                    border: "1px solid var(--border)", background: "var(--bg-surface)" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          {tc("code")}
          <input value={codigo} onChange={e => setCodigo(e.target.value.toUpperCase())}
            className="fin-input mono" style={{ width: 100 }} maxLength={10}
            title={t("codeTitle")} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          {t("propertyName")}
          <input value={nombre} onChange={e => setNombre(e.target.value)}
            className="fin-input" style={{ width: 300 }} placeholder="Oxígen Hotel" />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          {t("shortName")}
          <input value={corto} onChange={e => setCorto(e.target.value)}
            className="fin-input" style={{ width: 160 }} placeholder="Oxígen" />
        </label>
        <button onClick={guardarCodigo}
          disabled={guardandoId || !codigo.trim() || codigo.trim() === hotelId}
          style={{ padding: "7px 14px", fontSize: 13, fontWeight: 600, borderRadius: 5,
                   border: "1px solid var(--border-medium)",
                   cursor: codigo.trim() && codigo.trim() !== hotelId ? "pointer" : "not-allowed",
                   background: "transparent",
                   color: codigo.trim() && codigo.trim() !== hotelId ? "var(--accent-amber, #c8a24a)" : "var(--text-disabled)" }}>
          {t("changeCode")}
        </button>
        <button onClick={guardarIdentidad} disabled={guardandoId || !nombre.trim()}
          style={{ padding: "7px 16px", fontSize: 13, fontWeight: 600, borderRadius: 5, border: "none",
                   cursor: nombre.trim() ? "pointer" : "not-allowed",
                   background: nombre.trim() ? "var(--brand)" : "var(--bg-surface)",
                   color: nombre.trim() ? "#fff" : "var(--text-disabled)" }}>
          {guardandoId ? tc("saving") : t("saveName")}
        </button>
        <span style={{ fontSize: 11, color: "var(--text-disabled)", maxWidth: 380 }}>
          {t("identityHint")}
        </span>
      </div>

      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 6, maxWidth: "80ch" }}>
        {t.rich("catalogHint", { b })}
      </p>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 8, maxWidth: "80ch" }}>
        {t.rich("packageHint", { b })}
      </p>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8, maxWidth: "80ch", borderLeft: `3px solid ${GOLD}`, paddingLeft: 12 }}>
        {t.rich("hideNotDelete", { b })}
      </p>

      {error && <div style={{ color: "var(--negative)", fontSize: 12.5, marginTop: 10 }}>{error}</div>}
      {msg && <div style={{ color: "var(--positive)", fontSize: 12.5, marginTop: 10 }}>{msg}</div>}

      {/* Estados anteriores a esta regla que la regla NO puede representar. No
          se normalizan solos: apagar la madre de Administración arrastraría a
          Gerencia, Finanzas, Compras, RRHH y Seguridad —los que llevan la
          planilla— y eso es una decisión, no una migración. Se muestra y se
          espera. */}
      {data && data.mixtos > 0 && (
        <div style={{ marginTop: 12, padding: "11px 14px", borderRadius: 8, fontSize: 12.5,
          maxWidth: "80ch", border: `1px solid ${GOLD}`, background: "rgba(200,162,74,0.08)" }}>
          {t.rich("mixedNotice", { b, n: data.mixtos })}
        </div>
      )}

      {confirmar && (
        <div style={{ marginTop: 14, padding: "12px 16px", borderRadius: 8, fontSize: 12.5,
          background: "rgba(239,83,80,0.10)", color: "var(--negative)", border: "1px solid var(--negative)" }}>
          {confirmar}
          <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
            <button onClick={() => guardar(true)} disabled={saving}
              style={{ padding: "6px 14px", fontSize: 12, fontWeight: 600, borderRadius: 6, cursor: "pointer", background: "var(--negative)", color: "#fff", border: "none" }}>
              {t("hideAnyway")}
            </button>
            <button onClick={() => setConfirmar(null)}
              style={{ padding: "6px 14px", fontSize: 12, borderRadius: 6, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
              {tc("cancel")}
            </button>
          </div>
        </div>
      )}

      {loading && <div style={{ color: "var(--text-secondary)", padding: 40, textAlign: "center" }}>{tc("loading")}</div>}

      {data && !loading && (
        <>
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 18, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {t("counts", { madres: data.total_madres, todos: data.total_departamentos })}{" "}
              <b style={{ color: data.apagados ? GOLD : "inherit" }}>
                {t("countsOff", { n: data.apagados })}</b>
              {data.mixtos > 0 && <b style={{ color: GOLD }}> · {t("countsMixed", { n: data.mixtos })}</b>}
            </span>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
              title={t("emptyOnPurpose")}>
              <input type="checkbox" checked={soloConDatos} onChange={e => setSoloConDatos(e.target.checked)} />
              {t("onlyWithData")}
            </label>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder={t("searchDept")}
              style={{ padding: "5px 10px", fontSize: 12, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", minWidth: 220, marginLeft: "auto" }} />
            <button onClick={bajarExcel} disabled={!data}
              title={t("xlsHint")}
              style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: data ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
              ⬇ Excel
            </button>
            {hotels.length > 1 && (
              <select defaultValue="" onChange={async e => {
                if (!e.target.value) return;
                await copiarProvisioning(hotelId, e.target.value);
                await load(hotelId);
                setMsg(t("copiedFrom", { hotel: e.target.value }));
                e.target.value = "";
              }} style={{ padding: "5px 10px", fontSize: 12, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
                <option value="">{t("copyFrom")}</option>
                {hotels.filter(h => h.id !== hotelId).map(h => <option key={h.id} value={h.id}>{h.id}</option>)}
              </select>
            )}
          </div>

          <div className="fin-sticky" style={{ marginTop: 12, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 780 }}>
              <thead>
                <tr>
                  <th style={{ ...th, minWidth: 230 }}>{tc("department")}</th>
                  {data.dimensiones.map(d => (
                    <th key={d.key} style={{ ...th, textAlign: "center", textTransform: "none", letterSpacing: 0, minWidth: 96 }}>
                      {d.label}
                    </th>
                  ))}
                  <th style={{ ...th, textAlign: "center", minWidth: 110 }}>{t("wholeRow")}</th>
                </tr>
              </thead>
              <tbody>
                {filas.map(r => {
                  const off = data.dimensiones.every(d => !r.dims[d.key]?.aplica || !estado(r, d.key));
                  return (
                    <tr key={r.dept_code} style={{ opacity: off ? 0.45 : 1 }}>
                      <td style={td}>
                        <span className="mono" style={{ color: "var(--text-disabled)", marginRight: 8, fontSize: 11 }}>
                          {r.dept_code}
                        </span>
                        <b style={{ fontWeight: 500 }}>{r.dept_name}</b>
                        <div style={{ fontSize: 10.5, color: "var(--text-disabled)", marginTop: 1 }}>
                          {r.pl_kind === "OVERHEAD" ? t("overhead") : t("operating")}
                          {r.is_allocation_source && ` · ${t("allocationSource")}`}
                          {r.datos_totales > 0 && ` · ${t("linesAllScenarios", { n: r.datos_totales })}`}
                        </div>
                        {/* El paquete, a la vista. Antes cada hijo tenía su
                            propia fila y su propio juego de casillas; ahora se
                            listan acá para que se vea qué se está prendiendo o
                            apagando junto con la madre. */}
                        {r.paquete.length > 1 && (
                          <div style={{ fontSize: 10.5, color: "var(--text-secondary)", marginTop: 3 }}>
                            {t("dragsN", { n: r.paquete.length - 1 })}{" "}
                            {r.paquete.filter(m => !m.es_madre).map(m => (
                              <span key={m.dept_code} style={{ marginRight: 7, whiteSpace: "nowrap" }}>
                                <span className="mono" style={{ color: "var(--text-disabled)" }}>{m.dept_code}</span>{" "}
                                {m.dept_name}{m.room_set && <span style={{ color: GOLD }}> {t("setTag")}</span>}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      {data.dimensiones.map(d => {
                        const dim = r.dims[d.key];
                        if (!dim?.aplica) {
                          return <td key={d.key} style={{ ...td, textAlign: "center", color: "var(--text-disabled)" }}>—</td>;
                        }
                        const on = estado(r, d.key);
                        const tocado = esCambio(r.dept_code, d.key);
                        // Estado MIXTO: unos del paquete apagados y otros no.
                        // Es un estado anterior a esta regla, que la regla nueva
                        // no puede expresar. Se muestra en indeterminado y NO se
                        // resuelve solo — hasta que alguien decida, queda como
                        // está. Un cambio pendiente ya es una decisión, así que
                        // ahí deja de ser mixto.
                        const mixto = !!dim.mixto && !tocado;
                        return (
                          <td key={d.key} style={{ ...td, textAlign: "center",
                            background: tocado ? "rgba(200,162,74,0.12)"
                              : mixto ? "rgba(200,162,74,0.07)" : undefined }}>
                            <label style={{ cursor: "pointer", display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 2 }}
                              title={mixto
                                ? t("mixedTitle", { lista: dim.apagados.join(", "), miembros: dim.miembros })
                                : dim.apagados.length
                                  ? t("offIn", { lista: dim.apagados.join(", ") })
                                  : undefined}>
                              <input type="checkbox" checked={on}
                                ref={el => { if (el) el.indeterminate = mixto; }}
                                onChange={() => toggle(r, d.key)} />
                              {mixto && <span style={{ fontSize: 9, color: GOLD, fontWeight: 700 }}>{t("mixed")}</span>}
                              {dim.datos > 0 && (
                                <span className="mono" style={{ fontSize: 9.5, color: on ? "var(--text-disabled)" : "var(--negative)" }}>
                                  {dim.datos}
                                </span>
                              )}
                            </label>
                          </td>
                        );
                      })}
                      <td style={{ ...td, textAlign: "center" }}>
                        <button onClick={() => toggleFila(r, off)}
                          style={{ padding: "3px 9px", fontSize: 10.5, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
                          {off ? t("use") : t("discard")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 16, flexWrap: "wrap" }}>
            <button onClick={() => guardar(false)} disabled={!pendientes.length || saving}
              style={{ padding: "8px 18px", fontSize: 13, fontWeight: 600, borderRadius: 8,
                cursor: pendientes.length ? "pointer" : "default",
                background: pendientes.length ? GOLD : "var(--bg-input)",
                color: pendientes.length ? "#1a1a1a" : "var(--text-disabled)", border: "none" }}>
              {saving ? tc("saving") : t("saveChanges", { n: pendientes.length })}
            </button>
            {pendientes.length > 0 && (
              <span style={{ fontSize: 12, color: datosEnRiesgo ? "var(--negative)" : "var(--text-secondary)" }}>
                {datosEnRiesgo > 0
                  ? t("dataAtRisk", { n: datosEnRiesgo })
                  : t("nothingAtRisk")}
              </span>
            )}
            {pendientes.length > 0 && (
              <button onClick={() => setCambios({})}
                style={{ padding: "6px 12px", fontSize: 12, borderRadius: 6, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
                {t("discardChanges")}
              </button>
            )}
          </div>

          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 16, maxWidth: "80ch" }}>
            {t.rich("visibilityNotMath", { b, i })}
          </p>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 8, maxWidth: "80ch" }}>
            {t.rich("revenueOnlyBilling", { b })}
          </p>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 8, maxWidth: "80ch" }}>
            <b>{t("emptyHint")}</b> {t.rich("emptyTail", { i })}
          </p>
        </>
      )}
    </div>
  );
}
