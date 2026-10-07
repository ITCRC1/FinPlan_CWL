"use client";
/**
 * Qué cambió entre la subida vigente del mayor y la anterior, del mismo mes.
 *
 * Owner, 2026-10-07: *«cómo sé qué cambió con respecto a la primera… para ver si
 * los cambios quedaron»* · y después, subiendo: *«no veo reporte de cambios entre
 * uno y otro, solo veo hallazgos»*.
 *
 * Lo segundo era un error de ubicación mío: esto vivía sólo en Pre-Cierre →
 * Movimientos, y quién sube el archivo está en la Auditoría. **Se mira donde se
 * sube.** Ahora lo usan las dos pantallas.
 *
 * ⚠️ Vive acá y no copiado en cada una: dos cuadros que comparan lo mismo pueden
 * decir cosas distintas, y este proyecto ya pagó por eso una vez (owner,
 * 2026-08-27: «el excel no baja lo que está viendo»).
 */
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "\u2014"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");

export interface Cambio {
  que: "aparecio" | "desaparecio" | "cambio_de_monto";
  cuenta: string; asiento: string; linea: string; fecha: string;
  descripcion: string; desc_asiento: string; origen: string;
  antes: number; ahora: number; diferencia: number;
}

export interface CuentaCambiada {
  cuenta: string; antes: number; ahora: number; diferencia: number;
}

export interface Cambios {
  hay: boolean; motivo?: string;
  anterior?: { archivo: string; subido_en: string | null; movimientos: number;
               debito: number; credito: number; reemplazado_en: string | null };
  vigente?: { archivo: string; subido_en: string | null; movimientos: number;
              debito: number; credito: number };
  diferencia?: { movimientos: number; debito: number; credito: number };
  cuentas_que_cambiaron?: number; movimientos_que_cambiaron?: number;
  cuentas?: CuentaCambiada[]; movimientos?: Cambio[]; recortado?: boolean;
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
export function Comparacion(
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


/** La versión que se carga sola: le das el mes y pide la comparación.
 *
 * Existe para que las pantallas no repitan el `useEffect`, el estado de carga y
 * el manejo del error — tres cosas fáciles de escribir distinto en cada lado.
 */
export function CambiosDelMayor({ anio, mes }: { anio: number; mes: number }) {
  const [datos, setDatos] = useState<Cambios | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let vivo = true;
    setCargando(true); setError("");
    api.get<Cambios>(`/mayor/${anio}/${mes}/cambios/`)
      .then(r => { if (vivo) setDatos(r); })
      .catch(e => { if (vivo) setError(e instanceof Error ? e.message : "no se pudo cargar"); })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [anio, mes]);

  return <Comparacion datos={datos} cargando={cargando} error={error} />;
}
