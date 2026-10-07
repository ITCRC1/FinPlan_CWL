"use client";
/**
 * Auditoría del detalle del mayor.
 *
 * Owner, 2026-10-05: *«este es el máximo detalle que tira el sistema de
 * contabilidad. Yo debo revisar línea por línea… necesito una herramienta de
 * revisión para asegurarme que la descripción de los gastos sea correctamente
 * con la cuenta contable, el departamento»*.
 *
 * Se sube el Full Detail P&L de Integrity y salen los casos a revisar. **No
 * guarda nada**: no hay escenario, no toca el P&L. Es una lupa sobre un
 * archivo.
 *
 * ⚠️ La pantalla no esconde cuánto NO revisó. Arriba van las líneas del
 * archivo, las revisadas y las señaladas, los tres juntos: una herramienta que
 * muestra 29 casos sin decir que miró 6.617 líneas se lee como «hay 29
 * problemas», cuando lo que dice es «empezá por estos 29».
 */
import { useCallback, useEffect, useState } from "react";
import {
  auditarMayor, auditarMayorExcel, auditoriaGuardada, mesesDelMayor,
  type AuditoriaGL, type AuditoriaHallazgo, type MesGuardado,
} from "@/lib/api";

const SEV: Record<string, { fondo: string; texto: string; rotulo: string }> = {
  alta: { fondo: "#FFD6D6", texto: "#8B1A1A", rotulo: "Alta" },
  media: { fondo: "#FFF0CC", texto: "#7A5200", rotulo: "Media" },
  baja: { fondo: "#EDEDED", texto: "#4C505E", rotulo: "Baja" },
};

const card: React.CSSProperties = {
  background: "var(--bg-surface)", border: "1px solid var(--border-medium)",
  borderRadius: 8, padding: 16,
};
const th: React.CSSProperties = {
  padding: "6px 8px", fontSize: 11, textAlign: "left", whiteSpace: "nowrap",
  borderBottom: "1px solid var(--border-medium)", color: "var(--text-secondary)",
};
const td: React.CSSProperties = {
  padding: "6px 8px", fontSize: 12, borderBottom: "1px solid var(--border-subtle)",
  verticalAlign: "top",
};
const num: React.CSSProperties = {
  ...td, textAlign: "right", whiteSpace: "nowrap",
  fontFamily: "var(--font-mono, monospace)",
};

const crc = (v: number) =>
  v.toLocaleString("es-CR", { maximumFractionDigits: 0 });

function Dato({ rotulo, valor, tono }: { rotulo: string; valor: string; tono?: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{rotulo}</div>
      <div style={{ fontSize: 20, fontWeight: 600, fontFamily: "var(--font-mono, monospace)",
                    color: tono || "var(--text-primary)" }}>{valor}</div>
    </div>
  );
}

function Fila({ h }: { h: AuditoriaHallazgo }) {
  const [abierto, setAbierto] = useState(false);
  const s = SEV[h.severidad] ?? SEV.baja;
  return (
    <>
      <tr onClick={() => setAbierto(a => !a)} style={{ cursor: "pointer" }}>
        <td style={{ ...td, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{h.grupo}</td>
        <td style={td}>
          <span style={{ background: s.fondo, color: s.texto, borderRadius: 4,
                         padding: "1px 6px", fontSize: 11, fontWeight: 600 }}>
            {s.rotulo}
          </span>
        </td>
        <td style={{ ...td, fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>
          {h.cuenta}
        </td>
        <td style={td}>{h.concepto}</td>
        <td style={num}>{h.n_lineas}</td>
        <td style={num}>{crc(h.monto_crc)}</td>
        <td style={{ ...td, fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>
          {h.sugerencia || <span style={{ color: "var(--text-secondary)" }}>—</span>}
        </td>
        <td style={{ ...td, color: "var(--text-secondary)", maxWidth: 520 }}>{h.porque}</td>
      </tr>
      {abierto && (
        <tr>
          <td colSpan={8} style={{ ...td, background: "var(--bg-base)" }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>{["Asiento", "Línea", "Fecha", "Origen", "Descripción", "Referencia", "CRC", "USD"]
                  .map(c => <th key={c} style={th}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {h.lineas.map((l, i) => (
                  <tr key={`${l.asiento}-${l.linea}-${i}`}>
                    <td style={{ ...td, fontFamily: "var(--font-mono, monospace)" }}>{l.asiento}</td>
                    <td style={td}>{l.linea}</td>
                    <td style={td}>{l.fecha}</td>
                    <td style={td}>{l.origen}</td>
                    <td style={td}>{l.descripcion}</td>
                    <td style={td}>{l.referencia}</td>
                    <td style={num}>{crc(l.monto_crc)}</td>
                    <td style={num}>{l.monto_usd.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

const MES_ROTULO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                    "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre",
                    "Diciembre"];

export default function AuditoriaDelMayor() {
  const [file, setFile] = useState<File | null>(null);
  const [data, setData] = useState<AuditoriaGL | null>(null);
  const [ocupado, setOcupado] = useState<"" | "revisar" | "excel">("");
  const [err, setErr] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<string>("");
  // Owner, 2026-10-05: «me gustaría tener las discrepancias por tipo de cuenta.
  // Costos empieza con 5, payroll 6, Opex 7 y property expenses 8». Son
  // revisiones distintas, con gente distinta al lado.
  const [tipo, setTipo] = useState<string>("");
  /** Los meses que ya estan guardados, para poder volver a cualquiera.
   *
   *  Owner, 2026-10-07: *«me gustaria que el analisis de diferencias una vez que
   *  se suba no desaparezca, que quede ahi hasta subir la otra version… veo que
   *  todo desaparece una vez que uno sale y entra otra vez»*.
   *
   *  Tenia razon: esta pantalla no cargaba NADA al entrar. Los hallazgos vivian
   *  en la memoria del navegador desde la subida, asi que salir los borraba.
   *
   *  ⚠️ Los hallazgos NO se guardan: se recalculan del mayor almacenado. Asi hay
   *  una sola fuente —el libro— y el dia que la auditoria gane una regla, los
   *  meses viejos la aplican sin volver a subir nada. */
  const [meses, setMeses] = useState<MesGuardado[]>([]);
  const [elegido, setElegido] = useState<string>("");

  const cargarGuardado = useCallback(async (anio: number, mes: number) => {
    setOcupado("revisar"); setErr(null);
    try {
      const r = await auditoriaGuardada(anio, mes);
      setData(r.hay ? r : null);
      if (!r.hay) setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setOcupado(""); }
  }, []);

  // Al entrar: que haya guardado y, si hay, el mas reciente.
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const r = await mesesDelMayor();
        if (!vivo) return;
        setMeses(r.meses);
        if (r.meses.length) {
          const m = r.meses[0];          // el backend los manda del mas nuevo
          setElegido(`${m.anio}-${m.mes}`);
          await cargarGuardado(m.anio, m.mes);
        }
      } catch { /* sin guardado, la pantalla queda como siempre */ }
    })();
    return () => { vivo = false; };
  }, [cargarGuardado]);

  const correr = async (f: File) => {
    setOcupado("revisar"); setErr(null); setData(null);
    try {
      setData(await auditarMayor(f));
      // El mes acaba de quedar guardado: que aparezca en el selector sin
      // recargar la pagina.
      try {
        const r = await mesesDelMayor();
        setMeses(r.meses);
        if (r.meses.length) setElegido(`${r.meses[0].anio}-${r.meses[0].mes}`);
      } catch { /* el selector es ayuda, no bloquea la revision */ }
    }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setOcupado(""); }
  };

  const elegir = (l: FileList | null) => {
    const f = l?.[0];
    if (!f) return;
    setFile(f);
    void correr(f);
  };

  const bajar = async () => {
    if (!file) return;
    setOcupado("excel"); setErr(null);
    try { await auditarMayorExcel(file); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setOcupado(""); }
  };

  const visibles = (data?.hallazgos ?? [])
    .filter(h => (!filtro || h.severidad === filtro) && (!tipo || h.grupo === tipo));

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 1500 }}>
      <div style={card}>
        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>
          Auditoría del detalle del mayor
        </div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
          Subí el <b>Full Detail P&amp;L</b> de Integrity —el Balance de Comprobación con
          el detalle de asientos— y se revisan las cuentas de la clase 4 en adelante:
          que la descripción corresponda a la cuenta y al departamento.{" "}
          <b>El mes queda guardado</b> y la revisión sigue acá al volver a entrar,
          hasta que subas otra versión. No toca el P&amp;L.
        </div>
        {/* Los meses que ya estan guardados. Sin esto, la unica forma de ver un
            mes era volver a subir su archivo. */}
        {meses.length > 0 && (
          <div style={{ display: "flex", gap: 8, alignItems: "center",
                        marginBottom: 12, fontSize: 12, flexWrap: "wrap" }}>
            <span style={{ color: "var(--text-secondary)" }}>Mes guardado</span>
            <select value={elegido}
                    onChange={e => {
                      setElegido(e.target.value);
                      const [a, m] = e.target.value.split("-").map(Number);
                      void cargarGuardado(a, m);
                    }}
                    style={{ fontSize: 12, padding: "4px 8px", borderRadius: 5 }}>
              {meses.map(m => (
                <option key={`${m.anio}-${m.mes}`} value={`${m.anio}-${m.mes}`}>
                  {MES_ROTULO[m.mes - 1]} {m.anio} · {m.movimientos.toLocaleString("en-US")} mov
                  {m.archivo ? ` · ${m.archivo}` : ""}
                </option>
              ))}
            </select>
          </div>
        )}
        <label style={{ display: "block", border: "2px dashed var(--border-medium)",
                        borderRadius: 8, padding: 22, textAlign: "center",
                        cursor: "pointer", fontSize: 13 }}
               onDragOver={e => e.preventDefault()}
               onDrop={e => { e.preventDefault(); elegir(e.dataTransfer.files); }}>
          {file ? file.name : "Arrastrá el Excel acá o hacé clic para elegirlo"}
          <input type="file" accept=".xlsx,.xlsm" style={{ display: "none" }}
                 onChange={e => elegir(e.target.files)} />
        </label>
        {ocupado === "revisar" && (
          <div style={{ fontSize: 12, marginTop: 8 }}>Revisando el archivo…</div>
        )}
        {err && (
          <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: 6, fontSize: 12,
                        background: "#FFD6D6", color: "#8B1A1A" }}>{err}</div>
        )}
      </div>

      {data && (
        <>
          <div style={card}>
            <div style={{ display: "flex", gap: 34, flexWrap: "wrap", alignItems: "flex-end" }}>
              <Dato rotulo="Período" valor={data.periodo || "—"} />
              <Dato rotulo="Líneas del archivo" valor={data.lineas_del_archivo.toLocaleString("es-CR")} />
              <Dato rotulo="Revisadas (clase 4+)" valor={data.lineas_revisadas.toLocaleString("es-CR")} />
              <Dato rotulo="Casos a revisar" valor={String(data.hallazgos.length)}
                    tono="var(--brand)" />
              <Dato rotulo="Líneas señaladas" valor={data.lineas_senaladas.toLocaleString("es-CR")} />
              <Dato rotulo="Monto señalado (CRC)" valor={crc(data.monto_en_revision_crc)} />
              <button onClick={bajar} disabled={ocupado !== ""}
                      style={{ padding: "7px 14px", borderRadius: 6, fontSize: 12,
                               border: "1px solid var(--border-medium)",
                               background: "var(--brand)", color: "#fff", cursor: "pointer" }}>
                {ocupado === "excel" ? "Generando…" : "Bajar hoja de trabajo"}
              </button>
            </div>
            <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[["", "Todas"], ["alta", "Alta"], ["media", "Media"], ["baja", "Baja"]]
                .map(([k, r]) => {
                  const n = k ? (data.por_severidad[k] ?? 0) : data.hallazgos.length;
                  if (k && !n) return null;
                  return (
                    <button key={k || "todas"} onClick={() => setFiltro(k)}
                            style={{ padding: "4px 10px", borderRadius: 5, fontSize: 12,
                                     cursor: "pointer",
                                     border: `1px solid ${filtro === k ? "var(--brand)" : "var(--border-medium)"}`,
                                     background: filtro === k ? "var(--brand)" : "transparent",
                                     color: filtro === k ? "#fff" : "var(--text-primary)" }}>
                      {r} ({n})
                    </button>
                  );
                })}
            </div>
          </div>

          {/* El corte por tipo de cuenta. Los que no aparecen salieron limpios:
              el backend no manda un tipo sin hallazgos a propósito, porque una
              pestaña vacía se lee como «no revisé esto». */}
          <div style={card}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 12, color: "var(--text-secondary)", marginRight: 4 }}>
                Tipo de cuenta
              </span>
              {[["", "Todas", data.hallazgos.length, 0] as const,
                ...Object.entries(data.por_grupo).map(([g, d]) =>
                  [g, g, d.casos, d.alta] as const)].map(([k, rot, n, alta]) => (
                <button key={k || "todas"} onClick={() => setTipo(k)}
                        style={{ padding: "5px 11px", borderRadius: 6, fontSize: 12,
                                 cursor: "pointer", display: "flex", gap: 6,
                                 border: `1px solid ${tipo === k ? "var(--brand)" : "var(--border-medium)"}`,
                                 background: tipo === k ? "var(--brand)" : "transparent",
                                 color: tipo === k ? "#fff" : "var(--text-primary)" }}>
                  <span>{rot}</span>
                  <span style={{ opacity: 0.75 }}>{n}</span>
                  {alta > 0 && (
                    <span style={{ background: tipo === k ? "rgba(255,255,255,.25)" : "#FFD6D6",
                                   color: tipo === k ? "#fff" : "#8B1A1A",
                                   borderRadius: 4, padding: "0 5px", fontSize: 11 }}>
                      {alta} alta
                    </span>
                  )}
                </button>
              ))}
            </div>
            {!!tipo && data.por_grupo[tipo] && (
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
                {data.por_grupo[tipo].casos} casos · {data.por_grupo[tipo].lineas} líneas
                · CRC {crc(data.por_grupo[tipo].monto_crc)}
              </div>
            )}
          </div>

          <div style={card}>
            {/* `fin-scroll-x` y no un `overflow-x` suelto: un div que scrollea
                en horizontal tambien lo hace en vertical, y ahi el `thead`
                sticky de la app resuelve contra la caja —no contra el nav— y
                se come la primera fila. Ver
                `test_encabezado_no_tapa_la_primera_fila`. */}
            <div className="fin-scroll-x">
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1100 }}>
                <thead>
                  <tr>{["Tipo", "Severidad", "Cuenta", "Concepto", "Líneas",
                        "Monto CRC", "Debería ir en", "Por qué"]
                        .map(c => <th key={c} style={th}>{c}</th>)}</tr>
                </thead>
                <tbody>
                  {visibles.map((h, i) => <Fila key={`${h.regla}-${h.cuenta}-${h.concepto}-${i}`} h={h} />)}
                  {!visibles.length && (
                    <tr><td style={td} colSpan={8}>
                      No hay casos con ese filtro. Si el archivo está limpio, eso es
                      exactamente lo que se espera ver.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
              Hacé clic en un renglón para ver los asientos y poder buscarlos en Integrity.
            </div>
          </div>

          {!!Object.keys(data.que_mira).length && (
            <div style={card}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
                Qué mira cada regla
              </div>
              {Object.entries(data.que_mira).map(([regla, texto]) => (
                <div key={regla} style={{ marginBottom: 8, fontSize: 12 }}>
                  <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>
                    {regla}
                  </span>
                  <span style={{ color: "var(--text-secondary)" }}> · {data.por_regla[regla]} casos</span>
                  <div style={{ color: "var(--text-secondary)" }}>{texto}</div>
                </div>
              ))}
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 10 }}>
                Esto no decide si un asiento está bien: señala los que no se parecen al
                resto, para que la revisión empiece por ahí.
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
