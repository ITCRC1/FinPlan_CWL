"use client";
/**
 * La grilla de pax: huéspedes por habitación ocupada, por categoría × mes.
 *
 * Owner, 2026-10-04, mirando el Inventario y su «Pax min / Pax max»: *«evalúa
 * poner mejor un tab solo para pax que ya existe pero que tome los datos por
 * mes y por unidad»* · *«y que permita poner decimales»*.
 *
 * ## ⚠️ Esto escribe el campo que el MOTOR multiplica
 *
 * `rate_cards.pax_per_room`. De ahí salen los huéspedes y, con ellos, Food,
 * Activities, Transportation y Sustainability. Lo que se escriba acá mueve el
 * presupuesto de verdad — que es exactamente lo que el tab NO hacía: su botón
 * Guardar escribía el pax del hotel, nadie lo copiaba a las tarjetas, y la
 * grilla de abajo se recalculaba en pantalla mientras el P&L no se movía.
 *
 * ## ⚠️ Decimales, con coma o con punto
 *
 * El owner escribe `2,1`. Un `<input type="number">` en configuración regional
 * española deja ese valor INVÁLIDO —el navegador devuelve cadena vacía—, así
 * que el campo nunca cambiaba y no se guardaba nada: se veía como si tomara el
 * dato y volviera solo. Es un `type="text"` y la coma se convierte al parsear.
 *
 * ## ⚠️ Una celda sin tarifa no se escribe
 *
 * Sin tarjeta de tarifa, esa categoría no está en el presupuesto de ese mes: el
 * motor la saltea entera. Crear una para alojar un pax la metería en el cálculo
 * con tarifa cero y movería la ocupación y el ADR sin que nadie lo pidiera.
 */
import { useEffect, useMemo, useState } from "react";

import { getPaxGrid, setPaxGrid, rtLabel, type PaxGrid } from "@/lib/api";
import { manejarPegado, repartirPegado, numeroDeExcel } from "@/lib/pegarGrilla";

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

/** `2,1` y `2.1` son el mismo número. El owner escribe con coma.
 *
 *  ⚠️ Es el MISMO parser que usa el pegado. Con uno para teclear y otro para
 *  pegar, el mismo `2,1` puede entrar como 2,1 por un camino y como 21 por el
 *  otro — y la celda se ve igual en los dos casos. */
export const aNumero = numeroDeExcel;

/** Un pax se lee con un decimal: `2,0` · `2,1`. Dos serían ruido y cero
 *  escondería justo la diferencia que se está cargando. */
export const verPax = (n: number) =>
  n.toLocaleString("es-CR", { minimumFractionDigits: 1, maximumFractionDigits: 2 });

export interface PaxPorCelda {
  /** `${room_type_id}:${mes}` → pax. Lo que la pantalla de abajo multiplica. */
  (id: string, mes1: number): number;
}

export default function GrillaPax({
  scenarioId, bloqueado, onCambio,
}: {
  scenarioId: string;
  bloqueado: boolean;
  /** Se llama con el mapa de pax cada vez que cambia, para que la explosión de
   *  abajo use lo que se está viendo —no hace falta guardar para verla—. */
  onCambio: (porCelda: Record<string, number>) => void;
}) {
  const [grid, setGrid] = useState<PaxGrid | null>(null);
  const [borr, setBorr] = useState<Record<string, string>>({});
  const [sucias, setSucias] = useState<Set<string>>(new Set());
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarioId) return;
    setCargando(true);
    getPaxGrid(scenarioId)
      .then(g => {
        setGrid(g);
        const b: Record<string, string> = {};
        for (const f of g.filas) {
          for (const c of f.meses) b[`${f.room_type_id}:${c.month}`] = c.pax;
        }
        setBorr(b);
        setSucias(new Set());
        setError(null);
      })
      .catch(e => setError(e instanceof Error ? e.message : "no se pudo cargar"))
      .finally(() => setCargando(false));
  }, [scenarioId]);

  const porCelda = useMemo(() => {
    const m: Record<string, number> = {};
    for (const [k, v] of Object.entries(borr)) m[k] = aNumero(v);
    return m;
  }, [borr]);

  useEffect(() => { onCambio(porCelda); }, [porCelda, onCambio]);

  const conTarifa = useMemo(() => {
    const s = new Set<string>();
    for (const f of grid?.filas ?? []) {
      for (const c of f.meses) if (c.hay_tarifa) s.add(`${f.room_type_id}:${c.month}`);
    }
    return s;
  }, [grid]);

  /**
   * Pegar un bloque de Excel desde la celda en la que se está parado.
   *
   * Owner, 2026-10-04: *«modifica para que yo pueda hacer un copy paste desde
   * excel, rate y todo queda en la primera celda»*. Sin esto, los doce meses
   * entraban como un texto largo dentro de la primera celda.
   *
   * ⚠️ **Las celdas sin tarifa se saltean y se cuentan.** Esa categoría no está
   * en el presupuesto de ese mes; escribirle un pax no serviría de nada —el
   * guardado lo rechaza— y pisar la celda de al lado para «no perder» el valor
   * correría todo el bloque un mes. Se dice cuántas quedaron fuera.
   */
  function pegar(fi: number, mi: number, bloque: string[][]) {
    if (!grid || bloqueado) return;
    const nuevos: Record<string, string> = {};
    const nuevasSucias = new Set(sucias);
    let saltadas = 0;
    repartirPegado(bloque, fi, mi, grid.filas.length, 12, (f, c, valor) => {
      const fila = grid.filas[f];
      const k = `${fila.room_type_id}:${c + 1}`;
      if (!conTarifa.has(k)) { saltadas += 1; return; }
      // Se guarda el texto tal cual vino: la celda muestra lo que se pegó y
      // `aNumero` lo interpreta igual que si se hubiera tecleado.
      nuevos[k] = valor.trim();
      nuevasSucias.add(k);
    });

    setBorr(b => ({ ...b, ...nuevos }));
    setSucias(nuevasSucias);
    setAviso(
      `Pegadas ${Object.keys(nuevos).length} celdas`
      + (saltadas ? ` · ${saltadas} se saltearon: esa categoría no tiene `
                    + `tarifa en ese mes` : "")
      + ". Todavía hay que guardar.");
    setError(null);
  }

  async function guardar() {
    if (!grid) return;
    setGuardando(true); setError(null); setAviso(null);
    try {
      const celdas = Array.from(sucias).map(k => {
        const [room_type_id, mes] = k.split(":");
        return { room_type_id, month: Number(mes), pax: aNumero(borr[k]) };
      });
      const r = await setPaxGrid(scenarioId, celdas);
      setSucias(new Set());
      setAviso(r.sin_tarifa.length
        ? `Guardadas ${r.guardadas}. ⚠️ ${r.sin_tarifa.length} celdas no se `
          + `guardaron: esa categoría no tiene tarifa en ese mes, así que no `
          + `está en el presupuesto.`
        : `Guardadas ${r.guardadas} celdas. El P&L se mueve al recalcular.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  if (cargando) return <div style={{ color: "var(--text-secondary)" }}>Cargando pax…</div>;
  if (!grid) return error ? <div style={{ color: "var(--negative)" }}>{error}</div> : null;

  const prom = (f: PaxGrid["filas"][number]) => {
    const vs = f.meses
      .filter(c => conTarifa.has(`${f.room_type_id}:${c.month}`))
      .map(c => porCelda[`${f.room_type_id}:${c.month}`] ?? 0);
    // ⚠️ El promedio es de los meses que ESTÁN en el presupuesto. Incluir los
    // que no tienen tarifa lo arrastraría hacia abajo con ceros que no son
    // ocupación cero: son meses que esa categoría no vende.
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : 0;
  };

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
                    marginBottom: 8 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>
          Huéspedes por habitación ocupada <span style={{ fontWeight: 400,
            color: "var(--text-secondary)" }}>(digitar)</span>
        </h2>
        <button onClick={guardar} disabled={guardando || bloqueado || !sucias.size}
          style={{ padding: "5px 14px", fontSize: 12.5, borderRadius: 4, fontWeight: 600,
                   border: "none",
                   cursor: (guardando || bloqueado || !sucias.size) ? "not-allowed" : "pointer",
                   background: sucias.size && !bloqueado ? "var(--brand)" : "var(--bg-surface)",
                   color: sucias.size && !bloqueado ? "#fff" : "var(--text-disabled)" }}>
          {guardando ? "Guardando…" : sucias.size ? `Guardar ${sucias.size}` : "Guardado"}
        </button>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          Acepta decimales con coma o con punto · se escribe en la tarifa del
          escenario, que es lo que el motor multiplica
        </span>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 12.5,
                              marginBottom: 6 }}>{error}</div>}
      {aviso && <div style={{ color: "var(--text-secondary)", fontSize: 12.5,
                              marginBottom: 6 }}>{aviso}</div>}

      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
        <table className="fin-table" style={{ minWidth: 1200 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", minWidth: 220 }}>#</th>
              {MESES.map(m => <th key={m} style={{ textAlign: "right", minWidth: 72 }}>{m}</th>)}
              <th style={{ textAlign: "right", minWidth: 80,
                           borderLeft: "1px solid var(--border-medium)" }}>Prom.</th>
            </tr>
          </thead>
          <tbody>
            {grid.filas.map((f, i) => (
              <tr key={f.room_type_id}>
                <td style={{ textAlign: "left", fontWeight: 500 }}>
                  <span className="mono" style={{ color: "var(--text-disabled)",
                                                  marginRight: 6 }}>{i + 1}</span>
                  {rtLabel(f.code, f.name)}
                </td>
                {f.meses.map(c => {
                  const k = `${f.room_type_id}:${c.month}`;
                  if (!c.hay_tarifa) {
                    return (
                      <td key={c.month} className="mono"
                          title="Esta categoría no tiene tarifa en este mes: no está en el presupuesto"
                          style={{ textAlign: "right", color: "var(--text-disabled)" }}>—</td>
                    );
                  }
                  return (
                    <td key={c.month} style={{ textAlign: "right" }}>
                      {/* ⚠️ `type="text"`, no `number`: con la coma del teclado
                          español un input numérico deja el valor inválido y la
                          edición no llega nunca a guardarse. */}
                      <input className="fin-input mono" type="text" inputMode="decimal"
                        value={borr[k] ?? ""} disabled={bloqueado}
                        onPaste={e => manejarPegado(e, b => pegar(i, c.month - 1, b))}
                        onFocus={e => e.target.select()}
                        onChange={e => {
                          setBorr(b => ({ ...b, [k]: e.target.value }));
                          setSucias(s => new Set(s).add(k));
                        }}
                        style={{ width: 62, textAlign: "right",
                                 borderColor: sucias.has(k)
                                   ? "var(--brand)" : undefined }} />
                    </td>
                  );
                })}
                <td className="mono" style={{ textAlign: "right", fontWeight: 600,
                      borderLeft: "1px solid var(--border-medium)" }}>{verPax(prom(f))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
