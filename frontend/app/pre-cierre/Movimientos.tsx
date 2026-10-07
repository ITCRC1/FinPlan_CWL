"use client";
/**
 * Pre-Cierre → Movimientos: el mayor del mes, hasta el asiento.
 *
 * Owner, 2026-10-06: *«es solo para poder revisar detalladamente a nivel de
 * detalle»* · *«dale, máximo detalle y descripción del asiento»*.
 *
 * Abre una cuenta y muestra los asientos que la forman: fecha, número de
 * asiento, la descripción de la línea, la del asiento entero, la referencia y
 * la plata. Es el nivel que ninguna otra pantalla tiene — los demás tabs llegan
 * hasta la cuenta, o hasta el tercer segmento (`Opex by Detail`).
 *
 * ## El total NO es la suma de lo que se ve
 *
 * ⚠️ El listado viene recortado (`limite`) y el total viene aparte, del
 * servidor. Si la pantalla sumara lo dibujado, una cuenta con 600 asientos
 * mostraría un total que no es el de la cuenta — y el cuadro mentiría sin
 * avisar. Cuando hay recorte se dice en pantalla, en vez de dejar creer que eso
 * es todo.
 *
 * ## De dónde sale
 *
 * Del Balance de Comprobación que se sube en **Auditoría del mayor**, guardado
 * desde el 2026-10-06 (migración 151). Un mes por hotel: subir el mismo mes
 * otra vez lo reemplaza. Si el mes no está subido, se dice — una tabla vacía se
 * lee como «no hubo movimiento».
 */
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";

interface Movimiento {
  cuenta: string; seg2: string; seg3: string;
  asiento: string; linea: string; fecha: string;
  descripcion: string; desc_asiento: string;
  origen: string; referencia: string; num_doc: string;
  debito: number; credito: number; neto: number;
  tc: number; moneda: string;
}

interface Cambio {
  que: "aparecio" | "desaparecio" | "cambio_de_monto";
  cuenta: string; asiento: string; linea: string; fecha: string;
  descripcion: string; desc_asiento: string; origen: string;
  antes: number; ahora: number; diferencia: number;
}

interface CuentaCambiada {
  cuenta: string; antes: number; ahora: number; diferencia: number;
}

interface Cambios {
  hay: boolean; motivo?: string;
  anterior?: { archivo: string; subido_en: string | null; movimientos: number;
               debito: number; credito: number; reemplazado_en: string | null };
  vigente?: { archivo: string; subido_en: string | null; movimientos: number;
              debito: number; credito: number };
  diferencia?: { movimientos: number; debito: number; credito: number };
  cuentas_que_cambiaron?: number; movimientos_que_cambiaron?: number;
  cuentas?: CuentaCambiada[]; movimientos?: Cambio[]; recortado?: boolean;
}

interface Respuesta {
  anio: number; mes: number; hay_mes: boolean;
  movimientos: number; debito: number; credito: number; neto: number;
  recortado: boolean; filas: Movimiento[];
}

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");

export default function Movimientos({ anio, mes }: { anio: number; mes: number }) {
  const [cuenta, setCuenta] = useState("");
  const [depto, setDepto] = useState("");
  const [q, setQ] = useState("");
  const [datos, setDatos] = useState<Respuesta | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  /** Qué se está mirando: los movimientos, o qué cambió contra la subida
   *  anterior. Dos vistas del mismo mes, no dos tabs: el tab ya existe. */
  const [vista, setVista] = useState<"movimientos" | "cambios">("movimientos");
  const [cambios, setCambios] = useState<Cambios | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true); setError("");
    try {
      const p = new URLSearchParams();
      if (cuenta.trim()) p.set("cuenta", cuenta.trim());
      if (depto.trim()) p.set("depto", depto.trim());
      if (q.trim()) p.set("q", q.trim());
      setDatos(await api.get<Respuesta>(
        `/mayor/${anio}/${mes}/movimientos/?${p.toString()}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo cargar");
      setDatos(null);
    } finally {
      setCargando(false);
    }
  }, [anio, mes, cuenta, depto, q]);

  // Carga sola al entrar y al cambiar de mes. Los filtros se aplican con el
  // botón: escribir «7310-0110» dispararía una consulta por cada tecla.
  useEffect(() => { cargar(); /* eslint-disable-next-line */ }, [anio, mes]);

  // La comparación se pide cuando se mira, no "por las dudas": trae las dos
  // versiones del mes enteras y es la consulta más cara de esta pantalla.
  useEffect(() => {
    if (vista !== "cambios") return;
    let vivo = true;
    setCargando(true); setError("");
    api.get<Cambios>(`/mayor/${anio}/${mes}/cambios/`)
      .then(r => { if (vivo) setCambios(r); })
      .catch(e => { if (vivo) setError(e instanceof Error ? e.message : "no se pudo cargar"); })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [vista, anio, mes]);

  const campo: React.CSSProperties = {
    fontSize: 12, padding: "5px 8px", borderRadius: 5,
    border: "1px solid var(--border-medium)", background: "var(--bg-input)",
    color: "var(--text-primary)",
  };
  const th: React.CSSProperties = {
    textAlign: "left", fontSize: 11, fontWeight: 700, padding: "6px 8px",
    borderBottom: "1px solid var(--border-medium)", whiteSpace: "nowrap",
  };
  const td: React.CSSProperties = {
    fontSize: 12, padding: "5px 8px",
    borderBottom: "1px solid var(--border-subtle)",
  };
  const num: React.CSSProperties = {
    ...td, textAlign: "right", fontVariantNumeric: "tabular-nums",
    whiteSpace: "nowrap",
  };

  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 12px" }}>
        El mayor del mes, asiento por asiento. Sale del archivo que se sube en{" "}
        <b>Auditoría del mayor</b>. La cuenta acepta la raíz:{" "}
        <code>7310</code> trae todos los departamentos y{" "}
        <code>7310-0110</code> sólo Habitaciones.
      </p>

      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {([["movimientos", "Movimientos"],
           ["cambios", "Qué cambió contra la subida anterior"]] as const).map(([v, rot]) => (
          <button key={v} onClick={() => setVista(v)}
                  style={{ padding: "6px 12px", borderRadius: 6, fontSize: 12,
                           cursor: "pointer",
                           border: "1px solid " + (vista === v ? "var(--brand)" : "var(--border-medium)"),
                           background: vista === v ? "var(--brand)" : "transparent",
                           color: vista === v ? "#fff" : "var(--text-primary)" }}>
            {rot}
          </button>
        ))}
      </div>

      {vista === "cambios" ? (
        <Comparacion datos={cambios} cargando={cargando} error={error} />
      ) : (<>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap",
                    alignItems: "center", marginBottom: 12 }}>
        <input value={cuenta} onChange={e => setCuenta(e.target.value)}
               onKeyDown={e => e.key === "Enter" && cargar()}
               placeholder="Cuenta — 7310 o 7310-0110" style={{ ...campo, width: 210 }} />
        <input value={depto} onChange={e => setDepto(e.target.value)}
               onKeyDown={e => e.key === "Enter" && cargar()}
               placeholder="Depto — 0110" style={{ ...campo, width: 120 }} />
        <input value={q} onChange={e => setQ(e.target.value)}
               onKeyDown={e => e.key === "Enter" && cargar()}
               placeholder="Texto en la descripción, el asiento o la referencia"
               style={{ ...campo, width: 320 }} />
        <button onClick={cargar} style={{ ...campo, cursor: "pointer",
                                          background: "var(--brand)", color: "#fff",
                                          border: "none", padding: "6px 14px" }}>
          Buscar
        </button>
      </div>

      {error && <p style={{ fontSize: 13, color: "var(--negative)" }}>{error}</p>}
      {cargando && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>Cargando…</p>
      )}

      {!cargando && datos && !datos.hay_mes && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Este mes todavía no está guardado. Subí el Balance de Comprobación en
          <b> Auditoría del mayor</b> y vuelve — se guarda solo al subirlo.
        </p>
      )}

      {!cargando && datos && datos.hay_mes && (
        <>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap",
                        fontSize: 12, marginBottom: 10 }}>
            <span><b>{datos.movimientos.toLocaleString("en-US")}</b> movimientos</span>
            <span>Débito <b>{usd(datos.debito)}</b></span>
            <span>Crédito <b>{usd(datos.credito)}</b></span>
            <span>Neto <b>{usd(datos.neto)}</b></span>
          </div>
          {datos.recortado && (
            // El total de arriba es el de TODOS; abajo se dibuja una parte.
            // Decirlo es la diferencia entre un recorte y una mentira.
            <p style={{ fontSize: 12, color: "var(--warning)", margin: "0 0 10px" }}>
              Se muestran los primeros {datos.filas.length.toLocaleString("en-US")} de{" "}
              {datos.movimientos.toLocaleString("en-US")}. Los totales de arriba son
              de todos — afiná la cuenta o el departamento para verlos completos.
            </p>
          )}

          {/* `fin-scroll-x`: scroll horizontal sin tocar el alto. Sin esa clase
              el encabezado de la tabla se pega al tope del NAV y tapa la
              primera fila — la convención de la app, y lo vigila
              `test_encabezado_no_tapa_la_primera_fila`. */}
          <div className="fin-scroll-x">
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>
                  <th style={th}>Cuenta</th>
                  <th style={th}>Fecha</th>
                  <th style={th}>Asiento</th>
                  <th style={th}>Descripción</th>
                  <th style={th}>Descripción del asiento</th>
                  <th style={th}>Origen</th>
                  <th style={th}>Referencia</th>
                  <th style={{ ...th, textAlign: "right" }}>Débito</th>
                  <th style={{ ...th, textAlign: "right" }}>Crédito</th>
                  <th style={{ ...th, textAlign: "right" }}>Neto</th>
                </tr>
              </thead>
              <tbody>
                {datos.filas.map((f, i) => (
                  <tr key={`${f.asiento}-${f.linea}-${i}`}>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{f.cuenta}</td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{f.fecha}</td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>
                      {f.asiento}<span style={{ color: "var(--text-secondary)" }}>
                        ·{f.linea}</span>
                    </td>
                    <td style={td}>{f.descripcion}</td>
                    <td style={{ ...td, color: "var(--text-secondary)" }}>
                      {f.desc_asiento}
                    </td>
                    <td style={td}>{f.origen}</td>
                    <td style={{ ...td, color: "var(--text-secondary)" }}>
                      {f.referencia}
                    </td>
                    <td style={num}>{usd(f.debito)}</td>
                    <td style={num}>{usd(f.credito)}</td>
                    <td style={num}>{usd(f.neto)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {datos.filas.length === 0 && (
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 10 }}>
              El mes está guardado, pero nada coincide con ese filtro.
            </p>
          )}
        </>
      )}

      </>)}
    </div>
  );
}


/** Qué cambió entre la subida vigente y la anterior del mismo mes.
 *
 * Owner, 2026-10-07: *«cómo sé qué cambió con respecto a la primera… para ver
 * si los cambios quedaron»*.
 *
 * Dos niveles, porque son dos preguntas: **por cuenta** contesta «¿se movió la
 * plata a donde la quería mover?», que es el nivel al que se piden y se
 * verifican las correcciones; **por asiento** contesta «¿qué movimiento entró,
 * salió o cambió?», que es el nivel al que se va a Integrity a mirar.
 *
 * ⚠️ Una reclasificación sale en las DOS cuentas, con signo opuesto. Verla en
 * los dos lados es la prueba de que quedó: verla en uno solo no distingue un
 * movimiento movido de uno borrado.
 */
function Comparacion(
  { datos, cargando, error }:
  { datos: Cambios | null; cargando: boolean; error: string },
) {
  const th: React.CSSProperties = {
    textAlign: "left", fontSize: 11, fontWeight: 700, padding: "6px 8px",
    borderBottom: "1px solid var(--border-medium)", whiteSpace: "nowrap",
  };
  const td: React.CSSProperties = {
    fontSize: 12, padding: "5px 8px", borderBottom: "1px solid var(--border-subtle)",
  };
  const num: React.CSSProperties = {
    ...td, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap",
  };
  const QUE: Record<string, { rot: string; color: string }> = {
    aparecio: { rot: "entró", color: "var(--positive)" },
    desaparecio: { rot: "salió", color: "var(--negative)" },
    cambio_de_monto: { rot: "cambió de monto", color: "var(--warning)" },
  };
  const cuando = (v: string | null | undefined) =>
    v ? new Date(v).toLocaleString("es-CR", { dateStyle: "short", timeStyle: "short" }) : "—";

  if (error) return <p style={{ fontSize: 13, color: "var(--negative)" }}>{error}</p>;
  if (cargando) return <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>Cargando…</p>;
  if (!datos) return null;

  if (!datos.hay) {
    return (
      <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        {datos.motivo === "sin_subida_anterior"
          /* «Sin anterior» y «no cambió nada» son dos cosas distintas, y
             confundirlas haría creer que la corrección no entró. */
          ? "Este mes se subió una sola vez: todavía no hay una versión anterior "
            + "contra la que comparar. Corregí el archivo, volvé a subirlo y acá "
            + "vas a ver qué cambió."
          : "Este mes todavía no está subido."}
      </p>
    );
  }

  const d = datos.diferencia!;
  return (
    <div>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 12,
                    marginBottom: 14 }}>
        <div>
          <div style={{ color: "var(--text-secondary)" }}>Anterior</div>
          <div><b>{datos.anterior!.archivo || "—"}</b></div>
          <div style={{ color: "var(--text-secondary)" }}>
            {cuando(datos.anterior!.subido_en)} ·{" "}
            {datos.anterior!.movimientos.toLocaleString("en-US")} mov
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)" }}>Vigente</div>
          <div><b>{datos.vigente!.archivo || "—"}</b></div>
          <div style={{ color: "var(--text-secondary)" }}>
            {cuando(datos.vigente!.subido_en)} ·{" "}
            {datos.vigente!.movimientos.toLocaleString("en-US")} mov
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)" }}>Diferencia</div>
          <div><b style={{ color: d.movimientos === 0 ? "var(--text-primary)" : "var(--warning)" }}>
            {d.movimientos > 0 ? "+" : ""}{d.movimientos} movimientos
          </b></div>
          <div style={{ color: "var(--text-secondary)" }}>
            débito {usd(d.debito)} · crédito {usd(d.credito)}
          </div>
        </div>
      </div>

      {datos.cuentas_que_cambiaron === 0 && datos.movimientos_que_cambiaron === 0 && (
        <p style={{ fontSize: 13, color: "var(--positive)" }}>
          Las dos subidas dicen exactamente lo mismo: ninguna cuenta y ningún
          asiento cambiaron.
        </p>
      )}

      {!!datos.cuentas?.length && (
        <>
          <h3 style={{ fontSize: 13, fontWeight: 700, margin: "6px 0" }}>
            Por cuenta — {datos.cuentas_que_cambiaron} cambiaron
          </h3>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", margin: "0 0 8px" }}>
            Una reclasificación sale dos veces: en la cuenta de donde salió y en
            la que entró, con signo opuesto. Las dos juntas son la prueba de que quedó.
          </p>
          <div className="fin-scroll-x" style={{ marginBottom: 20 }}>
            <table style={{ borderCollapse: "collapse", minWidth: 560 }}>
              <thead><tr>
                <th style={th}>Cuenta</th>
                <th style={{ ...th, textAlign: "right" }}>Antes</th>
                <th style={{ ...th, textAlign: "right" }}>Ahora</th>
                <th style={{ ...th, textAlign: "right" }}>Diferencia</th>
              </tr></thead>
              <tbody>
                {datos.cuentas.map(c => (
                  <tr key={c.cuenta}>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{c.cuenta}</td>
                    <td style={num}>{usd(c.antes)}</td>
                    <td style={num}>{usd(c.ahora)}</td>
                    <td style={{ ...num, fontWeight: 700,
                                 color: c.diferencia < 0 ? "var(--negative)" : "var(--positive)" }}>
                      {usd(c.diferencia)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!!datos.movimientos?.length && (
        <>
          <h3 style={{ fontSize: 13, fontWeight: 700, margin: "6px 0" }}>
            Por asiento — {datos.movimientos_que_cambiaron} cambiaron
          </h3>
          <div className="fin-scroll-x">
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead><tr>
                <th style={th}>Qué pasó</th>
                <th style={th}>Cuenta</th>
                <th style={th}>Asiento</th>
                <th style={th}>Fecha</th>
                <th style={th}>Descripción</th>
                <th style={th}>Descripción del asiento</th>
                <th style={{ ...th, textAlign: "right" }}>Antes</th>
                <th style={{ ...th, textAlign: "right" }}>Ahora</th>
                <th style={{ ...th, textAlign: "right" }}>Diferencia</th>
              </tr></thead>
              <tbody>
                {datos.movimientos.map((m, i) => (
                  <tr key={m.cuenta + "-" + m.asiento + "-" + m.linea + "-" + i}>
                    <td style={{ ...td, color: QUE[m.que]?.color, fontWeight: 600,
                                 whiteSpace: "nowrap" }}>
                      {QUE[m.que]?.rot ?? m.que}
                    </td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{m.cuenta}</td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>
                      {m.asiento}<span style={{ color: "var(--text-secondary)" }}>·{m.linea}</span>
                    </td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{m.fecha}</td>
                    <td style={td}>{m.descripcion}</td>
                    <td style={{ ...td, color: "var(--text-secondary)" }}>{m.desc_asiento}</td>
                    <td style={num}>{usd(m.antes)}</td>
                    <td style={num}>{usd(m.ahora)}</td>
                    <td style={{ ...num, fontWeight: 700 }}>{usd(m.diferencia)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {datos.recortado && (
        <p style={{ fontSize: 12, color: "var(--warning)", marginTop: 10 }}>
          Hay más cambios de los que se muestran. Los conteos de arriba son de
          todos.
        </p>
      )}
    </div>
  );
}
