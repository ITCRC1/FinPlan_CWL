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
    </div>
  );
}
