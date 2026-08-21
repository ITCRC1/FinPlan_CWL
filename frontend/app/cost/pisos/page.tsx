"use client";
//
// Costos para Negociación de Grupos — el tarifario rack y el descuento máximo.
//
// La pantalla contesta UNA pregunta: *hasta acá podés bajar del rack antes de
// tocar el piso*. Regla del owner (2026-08-19): los grupos se negocian DESDE
// la tarifa rack.
//
// ⚠️ Este tarifario NO es el de `/revenue/rack-rates`. Aquél vive en el
// escenario y mueve el ingreso del presupuesto; éste vive en el módulo y es
// sólo la referencia de negociación. Editarlo no mueve ningún P&L, y es a
// propósito. La pantalla lo dice en voz alta porque tener dos tablas de rack
// sin explicar la diferencia es cómo se edita la equivocada.
//
import { useCallback, useEffect, useMemo, useState } from "react";
import IrA from "@/components/IrA";
import {
  getTarifarioGrupos, saveTarifarioGrupos, getDescuentosGrupos,
  type CategoriaRack, type DescuentosGrupos, type FilaRackGuardar,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

function num(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[, $]/g, ""));
  return isNaN(n) ? 0 : n;
}
function usd(v: string | number): string {
  const n = typeof v === "string" ? num(v) : v;
  return n.toLocaleString("en-US", { minimumFractionDigits: 0,
                                     maximumFractionDigits: 0 });
}
function pct(v: string): string {
  return (num(v) * 100).toFixed(1) + "%";
}

type Campo = "rack" | "neto";

export default function CostosGruposPage() {
  const [cats, setCats] = useState<CategoriaRack[]>([]);
  const [desc, setDesc] = useState<DescuentosGrupos | null>(null);
  const [campo, setCampo] = useState<Campo>("rack");
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [sucio, setSucio] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [t, d] = await Promise.all([
        getTarifarioGrupos(),
        // ⚠️ El de descuentos puede fallar solo (p. ej. si el escenario base
        // no existe) y eso NO debe dejar el tarifario sin poder editarse.
        getDescuentosGrupos().catch((e) => {
          setError(e instanceof Error ? e.message : "no se pudo calcular");
          return null;
        }),
      ]);
      setCats(t.categorias);
      setDesc(d);
      setSucio(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo cargar");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  function editar(ci: number, mi: number, valor: string) {
    setCats((prev) => {
      const copia = prev.map((c) => ({ ...c, meses: c.meses.map((m) => ({ ...m })) }));
      copia[ci].meses[mi][campo] = valor;
      return copia;
    });
    setSucio(true);
  }

  async function guardar() {
    setGuardando(true);
    setError(null);
    setAviso(null);
    try {
      const filas: FilaRackGuardar[] = [];
      for (const c of cats) {
        for (const m of c.meses) {
          filas.push({
            room_type_code: c.room_type_code, mes: m.mes,
            rack: String(num(m.rack)), neto: String(num(m.neto)),
            pax: String(num(m.pax)),
          });
        }
      }
      const r = await saveTarifarioGrupos(filas);
      setAviso(`${r.guardadas} tarifas guardadas`);
      // El descuento depende del rack: recalcular es parte de guardar, no un
      // paso aparte que el owner tenga que acordarse de dar.
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  // ── El descuento, indexado por mes y categoría ────────────────────────────
  const porMes = useMemo(() => {
    const m: Record<string, { d: string; alcanza: boolean; rack: string }> = {};
    for (const f of desc?.filas ?? []) {
      m[`${f.categoria}|${f.mes}`] = { d: f.descuento_max, alcanza: f.alcanza,
                                       rack: f.rack };
    }
    return m;
  }, [desc]);

  const tempDeMes = useMemo(() => {
    const m: Record<number, { t: string; cerrado: boolean }> = {};
    for (const f of desc?.filas ?? []) m[f.mes] = { t: f.temporada, cerrado: f.cerrado };
    return m;
  }, [desc]);

  // ── Excel: las tres tablas, cada una en su hoja ───────────────────────────
  //
  // El descuento va como FRACCIÓN y no como texto «37,4%»: quien baja esto lo
  // baja para hacer cuentas con el número, no para leerlo.
  async function bajarExcel() {
    if (!desc) return;
    try {
      await bajarCuadros("Costos_de_Grupos", [
        {
          titulo: "Los pisos, por temporada",
          subtitulo: `Costos de ${desc.escenario_costos} · comisión ${pct(desc.comision)}`
            + (desc.marginal_estimado ? " · ⚠️ Piso 1 estimado" : ""),
          hoja: "Pisos",
          columnas: [
            { label: "Por habitación-noche", ancho: 30, formato: "texto" },
            ...Object.keys(desc.pisos).map((t) => ({
              label: t, ancho: 14, formato: "usd2" as const })),
          ],
          filas: ([
            ["Piso 1 · marginal", "marginal"],
            ["Piso 2 · departamental", "departamental"],
            ["Piso 3 · integral", "integral"],
            ["Piso 4 · con margen protegido", "con_margen"],
          ] as const).map(([et, k]): FilaCuadro => ({
            label: et, nivel: 1,
            valores: Object.keys(desc.pisos).map((t) => num(desc.pisos[t][k])),
          })),
        },
        {
          titulo: "Tarifario de referencia — RACK",
          subtitulo: "No mueve ningún P&L: es la referencia desde la que se negocia",
          hoja: "Rack",
          columnas: [
            { label: "Categoría", ancho: 30, formato: "texto" },
            ...MESES.map((m) => ({ label: m, ancho: 11, formato: "usd2" as const })),
          ],
          filas: cats.map((c): FilaCuadro => ({
            label: c.nombre, nivel: 1,
            valores: c.meses.map((m) => num(m.rack)),
          })),
        },
        {
          titulo: "Descuento máximo sobre el rack — contra el Piso 4",
          subtitulo: "Negativo = el rack no cubre el piso ni a tarifa plena",
          hoja: "Descuento",
          columnas: [
            { label: "Categoría", ancho: 30, formato: "texto" },
            ...MESES.map((m) => ({ label: m, ancho: 11, formato: "pct" as const })),
          ],
          filas: cats.map((c): FilaCuadro => ({
            label: c.nombre, nivel: 1,
            valores: MESES.map((_, i) => num(porMes[`${c.nombre}|${i + 1}`]?.d ?? "0")),
          })),
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo bajar el Excel");
    }
  }

  const btn = (on: boolean): React.CSSProperties => ({
    padding: "6px 14px", borderRadius: 6, fontSize: 13, fontWeight: 600,
    cursor: on ? "pointer" : "default", border: "1px solid var(--border)",
    background: on ? "var(--brand)" : "var(--bg-surface)",
    color: on ? "#fff" : "var(--text-disabled)",
  });

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA />

      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          Costos de Grupos — descuento máximo sobre el rack
        </h1>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} disabled={!desc}
          style={{ ...btn(true), background: "transparent", color: "var(--positive)",
                   border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={guardar} disabled={guardando || !sucio} style={btn(!guardando && sucio)}>
          {guardando ? "Guardando…" : sucio ? "Guardar" : "Guardado"}
        </button>
      </div>

      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, maxWidth: 900 }}>
        El piso dice cuál es el mínimo; el rack dice desde dónde se baja. Esta pantalla
        muestra la resta. Los costos salen de{" "}
        <b>{desc?.escenario_costos ?? "—"}</b>; las tarifas arrancaron copiadas del
        Budget Working 2027 y se editan acá.
      </p>

      <div style={{
        border: "1px solid var(--border)", borderLeft: "3px solid var(--brand)",
        borderRadius: 6, padding: "10px 14px", marginTop: 12, maxWidth: 900,
        fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6,
      }}>
        <b style={{ color: "var(--text-primary)" }}>Este tarifario no mueve ningún P&amp;L.</b>{" "}
        No es el de <i>Planning → Rack Rates</i>, que vive en el escenario y sí mueve el
        ingreso del presupuesto. Éste es sólo la referencia desde la que se negocia:
        editarlo cambia el descuento, nunca el piso.
      </div>

      {aviso && <div style={{ color: "var(--positive)", fontSize: 13, marginTop: 10 }}>{aviso}</div>}
      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginTop: 10 }}>{error}</div>}

      {cargando ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>Cargando…</div>
      ) : (
        <>
          {/* ── Los pisos por temporada ─────────────────────────────────── */}
          {desc && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 8,
                           color: "var(--text-primary)" }}>
                Los pisos, por temporada · comisión del tarifario {pct(desc.comision)}
              </h2>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 640, maxWidth: 900 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", minWidth: 220 }}>Por habitación-noche</th>
                      {Object.keys(desc.pisos).map((t) => (
                        <th key={t} style={{ textAlign: "right", minWidth: 110 }}>{t}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {([
                      ["Piso 1 · marginal", "marginal"],
                      ["Piso 2 · departamental", "departamental"],
                      ["Piso 3 · integral", "integral"],
                      ["Piso 4 · con margen protegido", "con_margen"],
                    ] as const).map(([et, k]) => (
                      <tr key={k}>
                        <td style={{ textAlign: "left", fontWeight: k === "con_margen" ? 700 : 400 }}>
                          {et}
                          {k === "marginal" && desc.marginal_estimado && (
                            <span style={{ color: "var(--negative)", fontSize: 11, marginLeft: 6 }}>
                              estimado
                            </span>
                          )}
                        </td>
                        {Object.keys(desc.pisos).map((t) => (
                          <td key={t} className="mono" style={{ textAlign: "right",
                                fontWeight: k === "con_margen" ? 700 : 400 }}>
                            ${usd(desc.pisos[t][k])}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr>
                      <td style={{ textAlign: "left", color: "var(--text-secondary)", fontSize: 12 }}>
                        Meses con ocupación
                      </td>
                      {Object.keys(desc.pisos).map((t) => {
                        const p = desc.pisos[t];
                        const pocos = p.meses_con_ocupacion.length <= 1;
                        return (
                          <td key={t} style={{ textAlign: "right", fontSize: 12,
                                color: pocos ? "var(--negative)" : "var(--text-secondary)" }}>
                            {p.meses_con_ocupacion.length} de {p.meses.length}
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              </div>

              {desc.marginal_estimado && (
                <p style={{ fontSize: 12, color: "var(--negative)", marginTop: 8, maxWidth: 900 }}>
                  ⚠️ El <b>Piso 1</b> no está medido: falta la clasificación fijo/variable, así
                  que cae al costo propio completo. Es conservador a propósito — un piso
                  marginal inventado regala negocio.
                </p>
              )}
              {Object.entries(desc.pisos).some(([, p]) => p.meses_con_ocupacion.length <= 1) && (
                <p style={{ fontSize: 12, color: "var(--negative)", marginTop: 4, maxWidth: 900 }}>
                  ⚠️ Hay una temporada que se apoya en <b>un solo mes con ocupación</b>. El piso
                  es correcto y es frágil; las dos cosas importan al negociar.
                </p>
              )}
            </>
          )}

          {/* ── El tarifario editable ───────────────────────────────────── */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 32,
                        marginBottom: 8, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
              Tarifario de referencia
            </h2>
            <div style={{ display: "flex", gap: 4 }}>
              {(["rack", "neto"] as Campo[]).map((c) => (
                <button key={c} onClick={() => setCampo(c)}
                  style={{ ...btn(campo === c), padding: "4px 12px", fontSize: 12 }}>
                  {c === "rack" ? "RACK" : "NETO"}
                </button>
              ))}
            </div>
          </div>

          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 1100 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", minWidth: 200 }}>Categoría</th>
                  {MESES.map((m, i) => (
                    <th key={m} style={{ textAlign: "right", minWidth: 74 }}>
                      {m}
                      {tempDeMes[i + 1]?.cerrado && (
                        <div style={{ fontSize: 10, fontWeight: 400,
                                      color: "var(--text-disabled)" }}>cerrado</div>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cats.map((c, ci) => (
                  <tr key={c.room_type_code}>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>
                      {c.nombre}
                      <span style={{ color: "var(--text-disabled)", fontSize: 11, marginLeft: 6 }}>
                        {c.room_type_code} ×{c.unidades}
                      </span>
                    </td>
                    {c.meses.map((m, mi) => (
                      <td key={m.mes} style={{ padding: "1px 2px" }}>
                        <input
                          className="fin-input mono"
                          value={m[campo]}
                          onChange={(e) => editar(ci, mi, e.target.value)}
                          onFocus={(e) => e.target.select()}
                          style={{ width: "100%", minWidth: 0, textAlign: "right",
                                   padding: "3px 4px" }}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ── El descuento máximo ─────────────────────────────────────── */}
          {desc && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 32, marginBottom: 8,
                           color: "var(--text-primary)" }}>
                Descuento máximo sobre el rack · contra el Piso 4
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10,
                          maxWidth: 900 }}>
                Va por mes y no por temporada a propósito: el rack <b>baja</b> en temporada
                baja justo cuando el piso <b>sube</b>. Un promedio taparía el mes que duele.
                Una celda en <span style={{ color: "var(--negative)" }}>rojo</span> significa
                que el rack publicado no cubre el piso ni vendiendo a tarifa plena.
              </p>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 1100 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", minWidth: 200 }}>Categoría</th>
                      {MESES.map((m, i) => (
                        <th key={m} style={{ textAlign: "right", minWidth: 74 }}>
                          {m}
                          <div style={{ fontSize: 10, fontWeight: 400,
                                        color: "var(--text-disabled)" }}>
                            {tempDeMes[i + 1]?.cerrado ? "cerrado" : (tempDeMes[i + 1]?.t ?? "")}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {cats.map((c) => (
                      <tr key={c.room_type_code}>
                        <td style={{ textAlign: "left", fontWeight: 500 }}>{c.nombre}</td>
                        {MESES.map((_, i) => {
                          const v = porMes[`${c.nombre}|${i + 1}`];
                          if (!v) return <td key={i} style={{ textAlign: "right",
                                              color: "var(--text-disabled)" }}>—</td>;
                          return (
                            <td key={i} className="mono" style={{
                              textAlign: "right",
                              color: v.alcanza ? "var(--text-primary)" : "var(--negative)",
                              fontWeight: v.alcanza ? 400 : 600,
                            }}>
                              {pct(v.d)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
