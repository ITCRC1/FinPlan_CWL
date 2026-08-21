"use client";
/**
 * Master Data → Estadísticas (cuentas clase 9).
 *
 * **Por qué vive acá.** Las cuentas estadísticas SON cuentas, así que van al
 * lado del catálogo contable. Lo que está separado es la tabla, y por un motivo
 * concreto: una cuenta de dinero solo necesita saber a qué línea del P&L va; una
 * estadística necesita además qué unidad mide, por qué dimensiones se abre y
 * cómo se acumula el año —un headcount no se suma entre meses—.
 *
 * Owner (2026-08-14): «prefiero una base de datos separada pero ahí mismo».
 *
 * **Los códigos no se mueven; los nombres sí.** Misma regla que los tipos de
 * habitación: el código es lo que liga el dato y el nombre es la etiqueta. Una
 * cuenta NUEVA no se crea acá — va en el catálogo del repositorio, para que una
 * propiedad nueva nazca con todas.
 */
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import {
  bajarPlantillaEstadisticas, editarCuentaEstadistica, getCatalogoEstadisticas,
  getEstadisticas, getScenarios, importarEstadisticas,
  type CatalogoEstadisticas, type EstadisticasValores, type Scenario,
} from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const BTN: React.CSSProperties = {
  padding: "7px 14px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 13, fontWeight: 600,
};

export default function EstadisticasPage() {
  const t = useTranslations("stats9");
  const tc = useTranslations("common");

  // Los rótulos de grupo, dimensión y unidad son etiquetas de pantalla, no dato
  // de la base: se arman con el idioma activo.
  const GRUPOS: Record<string, string> = {
    "9000": t("g9000"), "9110": t("g9110"), "9201": t("g9201"),
    "9400": t("g9400"), "9500": t("g9500"), "9600": t("g9600"),
    "9700": t("g9700"), "9900": t("g9900"), "9980": t("g9980"),
  };
  const DIM: Record<string, string> = {
    DEPT: t("dimDept"), POSITION: t("dimPosition"), ROOMTYPE: t("dimRoomtype"),
    CHANNEL: t("dimChannel"), COUNTRY: t("dimCountry"), SEGMENT: t("dimSegment"),
  };
  const UNIDAD: Record<string, string> = {
    rooms: t("uRooms"), nights: t("uNights"), pax: t("uPax"), covers: t("uCovers"),
    treatments: t("uTreatments"), kilos: t("uKilos"), hours: t("uHours"),
    count: t("uCount"), trips: t("uTrips"), fte: "FTE",
  };

  const [cat, setCat] = useState<CatalogoEstadisticas | null>(null);
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner. Antes el default salia del reloj
  // (`BUDGET del ano en curso`): el 1 de enero la pantalla se cambiaba sola de
  // escenario y, si ese Budget no existia, caia en el primero de la lista.
  const [escId, setEscId] = useEscenarioDe("master-data/estadisticas:budget", escenarios, "budget", undefined, true);
  const [datos, setDatos] = useState<EstadisticasValores | null>(null);
  const [editando, setEditando] = useState<string | null>(null);
  const [borrador, setBorrador] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const archivo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const [c, e] = await Promise.all([getCatalogoEstadisticas(), getScenarios(HOTEL_ID)]);
        setCat(c);
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setEscenarios(e);
      } catch (err) {
        setError([err instanceof Error ? err.message : t("errorCatalogo")]);
      } finally { setCargando(false); }
    })();
  }, [t]);

  const recargar = useCallback(async () => {
    if (!escId) { setDatos(null); return; }
    try { setDatos(await getEstadisticas(escId)); }
    catch { setDatos(null); }
  }, [escId]);
  useEffect(() => { recargar(); }, [recargar]);

  async function guardarNombre(code: string) {
    const nombre = borrador.trim();
    setEditando(null);
    if (!nombre || !cat) return;
    await editarCuentaEstadistica(code, { nombre_es: nombre });
    setCat({ ...cat, cuentas: cat.cuentas.map(c =>
      c.code === code ? { ...c, nombre_es: nombre } : c) });
    setAviso(t("nombreGuardado", { nombre }));
  }

  async function alternarActiva(code: string, activa: boolean) {
    if (!cat) return;
    await editarCuentaEstadistica(code, { activa });
    setCat({ ...cat, cuentas: cat.cuentas.map(c =>
      c.code === code ? { ...c, activa } : c) });
  }

  async function subir(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !escId) return;
    setAviso(null); setError(null);
    try {
      const r = await importarEstadisticas(escId, f);
      setAviso(t("cargado", {
        valores: r.valores_guardados ?? 0, filas: r.filas_con_dato ?? 0,
      }));
      await recargar();
    } catch (err: unknown) {
      const d = (err as { detail?: { errores?: string[]; mensaje?: string } })?.detail;
      setError(d?.errores ? [d.mensaje ?? t("noSeCargoNada"), ...d.errores]
        : [err instanceof Error ? err.message : t("noSePudoCargar")]);
    } finally { if (archivo.current) archivo.current.value = ""; }
  }

  /** El catálogo a Excel. El owner lo revisa en Excel, no en pantalla — es como
   *  encontró que faltaba una cuenta y que sobraba la de provisión de vacaciones. */
  function bajarCatalogo() {
    if (!cat) return;
    const columnas: ColumnaCuadro[] = [
      { label: tc("account"), ancho: 10, formato: "texto" },
      { label: tc("concept"), ancho: 34, formato: "texto" },
      { label: t("colQueCuenta"), ancho: 15, formato: "texto" },
      { label: t("colSeAbrePor"), ancho: 30, formato: "texto" },
      { label: t("colDepartamentos"), ancho: 22, formato: "texto" },
      { label: t("colElAnioEs"), ancho: 24, formato: "texto" },
      { label: t("colTieneDato"), ancho: 11, formato: "texto" },
      { label: t("colActiva"), ancho: 9, formato: "texto" },
    ];
    const filas: FilaCuadro[] = [];
    let g = "";
    for (const c of cat.cuentas) {
      if (c.grupo !== g) {
        g = c.grupo;
        filas.push({ label: `${g} · ${GRUPOS[g] ?? ""}`, es_total: true,
                     valores: new Array(columnas.length - 1).fill(null) });
      }
      filas.push({ label: c.code, valores: [
        c.nombre_es, UNIDAD[c.unidad] ?? c.unidad,
        c.dims.length ? c.dims.map(d => DIM[d] ?? d).join(", ") : t("totalDelHotel"),
        c.deptos.join(" "),
        c.agrega === "FIN" ? t("saldoDiciembre") : t("sumaDoceMeses"),
        conDato.has(c.code) ? t("si") : "", c.activa ? t("si") : t("no"),
      ]});
    }
    bajarCuadros("Catalogo_Estadisticas", [{
      titulo: t("excelTitulo"),
      subtitulo: t("excelSubtitulo", {
        cuentas: cat.cuentas.length, dias: cat.jornada.dias_base,
        horas: cat.jornada.horas_dia, horasMes: cat.jornada.horas_mes,
      }),
      hoja: t("hojaCuentas"), columnas, filas,
    }]).catch(e => setAviso(e instanceof Error ? e.message : t("noSePudoBajar")));
  }

  if (cargando) return <div style={{ padding: 28, color: "var(--text-secondary)" }}>{tc("loading")}</div>;

  const esc = escenarios.find(s => s.id === escId);
  const conDato = new Set((datos?.valores ?? []).map(v => v.account_code));
  const descuadres = datos?.jornada_descuadres ?? [];
  let grupoActual = "";
  const b = (c: React.ReactNode) => <strong>{c}</strong>;

  return (
    <div className="pag pag-media" style={{ padding: "26px 28px 64px" }}>
      <IrA esc={escId} />
      <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: 4 }}>
        {t("titulo")}
      </h1>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 900, marginBottom: 18 }}>
        {t.rich("intro", { b })}
      </p>

      {/* El archivo */}
      <div style={{ padding: "14px 16px", borderRadius: 8, marginBottom: 18,
        background: "var(--bg-elevated)", border: "1px solid var(--border-medium)" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 12.5, fontWeight: 600 }}>{tc("scenario")}:</span>
          <select value={escId} onChange={e => setEscId(e.target.value)}
            style={{ ...BTN, fontWeight: 400 }}>
            {escenarios.map(s => (
              <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>
            ))}
          </select>
          <button style={{ ...BTN, background: "var(--accent-excel)", color: "#fff", border: "none" }}
            onClick={() => escId && bajarPlantillaEstadisticas(escId)}>
            {t("bajarArchivo")}
          </button>
          <button style={BTN} onClick={() => archivo.current?.click()}
            disabled={esc?.status === "locked"}>
            {t("subirArchivo")}
          </button>
          <input ref={archivo} type="file" accept=".xlsx" onChange={subir}
            style={{ display: "none" }} />
          {esc?.status === "locked" && (
            <span style={{ fontSize: 12, color: "var(--negative)" }}>
              {t("enllavado")}
            </span>
          )}
        </div>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 10, maxWidth: 900 }}>
          {t.rich("ayudaArchivo", { b })}
        </p>
      </div>

      {aviso && (
        <div style={{ padding: "9px 12px", borderRadius: 6, marginBottom: 14, fontSize: 12.5,
          background: "rgba(26,107,60,0.14)", border: "1px solid rgba(26,107,60,0.45)" }}>{aviso}</div>
      )}
      {error && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 12.5,
          background: "rgba(192,57,43,0.12)", border: "1px solid rgba(192,57,43,0.45)" }}>
          {error.map((e, i) => (
            <div key={i} style={{ fontWeight: i === 0 ? 700 : 400, marginTop: i ? 3 : 0 }}>{e}</div>
          ))}
        </div>
      )}

      {/* El control de la jornada */}
      {cat && (
        <div style={{ padding: "12px 16px", borderRadius: 8, marginBottom: 18, fontSize: 12.5,
          background: descuadres.length ? "rgba(230,168,23,0.12)" : "var(--bg-surface)",
          border: `1px solid ${descuadres.length ? "rgba(230,168,23,0.45)" : "var(--border-medium)"}` }}>
          {t.rich("jornada", {
            b,
            dias: cat.jornada.dias_base,
            horas: cat.jornada.horas_dia,
            horasMes: cat.jornada.horas_mes,
          })}
          {datos && (descuadres.length ? (
            <div style={{ marginTop: 8 }}>
              {t.rich("descuadres", { b, n: descuadres.length })}{" "}
              {descuadres.slice(0, 6).map(d =>
                `${d.dept_code}/${d.position_code} ${t("mes")} ${d.month} (${d.diferencia > 0 ? "+" : ""}${d.diferencia.toFixed(0)}h)`
              ).join(" · ")}{descuadres.length > 6 ? " …" : ""}
            </div>
          ) : (
            <div style={{ marginTop: 8, color: "var(--text-secondary)" }}>
              {conDato.size ? t("todasCierran") : t("sinHoras")}
            </div>
          ))}
        </div>
      )}

      {/* El catálogo */}
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button onClick={bajarCatalogo}
          style={{ ...BTN, background: "var(--accent-excel)", color: "#fff", border: "none" }}>
          {t("excelCatalogo")}
        </button>
      </div>
      <table className="fin-table" style={{ width: "100%" }}>
        <thead>
          <tr>
            {[tc("account"), tc("concept"), t("colQueCuenta"), t("colSeAbrePor"),
              t("colElAnioEs"), t("colDato"), t("colActiva")]
              .map((h, i) => (
                <th key={h} style={{ padding: "8px 10px", textAlign: i > 1 ? "left" : "left",
                  color: "var(--brand)", fontWeight: 700, position: "static" }}>{h}</th>
              ))}
          </tr>
        </thead>
        <tbody>
          {(cat?.cuentas ?? []).map(c => {
            const cabecera = c.grupo !== grupoActual;
            grupoActual = c.grupo;
            return (
              // `key` en el FRAGMENTO, no solo en los <tr> de adentro: sin
              // esto React avisa «Each child in a list should have a unique
              // key» en cada render.
              <Fragment key={c.code}>
                {cabecera && (
                  <tr key={`g${c.grupo}`}>
                    <td colSpan={7} style={{ padding: "12px 10px 5px", fontSize: 10.5,
                      fontWeight: 700, letterSpacing: 0.8, color: "var(--text-secondary)" }}>
                      {c.grupo} · {GRUPOS[c.grupo] ?? ""}
                    </td>
                  </tr>
                )}
                <tr key={c.code} style={{ opacity: c.activa ? 1 : 0.45 }}>
                  <td className="mono" style={{ padding: "5px 10px", fontWeight: 700 }}>{c.code}</td>
                  <td style={{ padding: "5px 10px", fontWeight: 500 }}>
                    {editando === c.code ? (
                      <input autoFocus value={borrador} onChange={e => setBorrador(e.target.value)}
                        onBlur={() => guardarNombre(c.code)}
                        onKeyDown={e => { if (e.key === "Enter") guardarNombre(c.code);
                          if (e.key === "Escape") setEditando(null); }}
                        style={{ ...BTN, fontWeight: 400, width: "100%", padding: "4px 8px" }} />
                    ) : (
                      <span onClick={() => { setEditando(c.code); setBorrador(c.nombre_es); }}
                        title={t("clicParaRenombrar")}
                        style={{ cursor: "text" }}>{c.nombre_es}</span>
                    )}
                  </td>
                  <td style={{ padding: "5px 10px", color: "var(--text-secondary)", fontSize: 12 }}>
                    {UNIDAD[c.unidad] ?? c.unidad}
                  </td>
                  <td style={{ padding: "5px 10px", color: "var(--text-secondary)", fontSize: 12 }}>
                    {c.dims.length ? c.dims.map(d => DIM[d] ?? d).join(", ") : t("totalDelHotel")}
                    {c.deptos.length > 0 && (
                      <span style={{ color: "var(--text-disabled)" }}> · {c.deptos.join(" ")}</span>
                    )}
                  </td>
                  <td style={{ padding: "5px 10px", color: "var(--text-secondary)", fontSize: 12 }}>
                    {c.agrega === "FIN" ? t("saldoDiciembre") : t("sumaDoceMeses")}
                  </td>
                  <td style={{ padding: "5px 10px", fontSize: 12 }}>
                    {conDato.has(c.code)
                      ? <span style={{ color: "var(--positive)" }}>{t("si")}</span>
                      : <span style={{ color: "var(--text-disabled)" }}>—</span>}
                  </td>
                  <td style={{ padding: "5px 10px" }}>
                    <input type="checkbox" checked={c.activa}
                      onChange={e => alternarActiva(c.code, e.target.checked)} />
                  </td>
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>

      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 14, maxWidth: 900 }}>
        {t.rich("nota", { b })}
      </p>
    </div>
  );
}
