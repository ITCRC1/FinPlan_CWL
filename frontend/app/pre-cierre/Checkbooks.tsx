"use client";
/**
 * Pre-Cierre → Checkbooks: el mes que se cierra, cuenta por cuenta, contra el
 * Budget y el Forecast.
 *
 * Owner, 2026-10-06: *«lo que quiero es que jales los checkbooks con máximo
 * detalle del budget y forecast y que haga la comparación […] ya que se sube
 * máximo detalle del mes, se pueda hacer una máxima revisión a nivel de
 * checkbook»*.
 *
 * ## No es una pantalla nueva: es la de Planning, apuntada al espejo
 *
 * El cuadro lo arma `cuadroCheckbook` y lo dibuja `Tabla` — los MISMOS que usa
 * el Budget Package. Copiarlos habría dado dos pantallas que comparan lo mismo
 * y pueden decir cosas distintas, que es el defecto que este proyecto ya pagó
 * («el excel no baja lo que está viendo», 2026-08-27).
 *
 * Lo único propio de acá es de dónde sale la versión principal: **el espejo**,
 * el ACTUAL donde Pre-Cierre escribe el mes subido. No se elige en un selector
 * porque no hay nada que elegir — es el mes que se está cerrando.
 *
 * ⚠️ **El espejo no sale en la lista de escenarios por defecto** (migración
 * 140): es un ACTUAL del mismo año que el de verdad, y si apareciera en los
 * selectores cada pantalla ofrecería dos versiones del mismo mes. Acá se pide
 * `incluirPrecierre` a propósito, porque es justo el que se quiere mirar.
 *
 * ## Hasta la cuenta, no más abajo — por ahora
 *
 * La sub-línea (`800 · Coral`) sólo sale del auxiliar: el mayor trae la cuenta
 * y se acabó (ver `abrir` en `detalle_celda_api`). Abrirla en el actual es
 * posible —el Pre-Cierre guarda la cuenta de 7 segmentos y su `seg3` es el
 * mismo eje— pero no está hecho, y una comparación donde un lado se abre y el
 * otro no se lee como si al actual le faltara detalle. Owner, 2026-10-06:
 * primero por cuenta, el detalle después.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  espejoAlDia, getDetalleDeCelda, getScenarios,
  type DetalleCelda, type Scenario,
} from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { APERTURAS, cuadroCheckbook, type ClaseApertura } from "@/lib/planningReport";
import Tabla from "@/app/planning/report/Tabla";

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

export default function Checkbooks(
  { anio, mes }: { anio: number; mes: number },
) {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [espejo, setEspejo] = useState<string>("");
  // ⚠️ La regla COMPARTIDA, no una propia. Cada pantalla traía su «el año más
  // nuevo» copiado a mano, y el día que nacieron los Working 2028-2035 todos
  // los reportes se fueron a 2035 sin que nada fallara.
  //
  // Dos llaves distintas y SIN `?esc=`: con un solo parámetro en la dirección,
  // los dos selectores quedarían en el mismo escenario y la comparación sería
  // contra sí misma — variaciones de cero que se leen como «no cambió nada».
  const [budget, setBudget] = useEscenarioDe(
    "pre-cierre/checkbooks:budget", escenarios, "budget");
  const [forecast, setForecast] = useEscenarioDe(
    "pre-cierre/checkbooks:forecast", escenarios, "forecast");
  const otros = useMemo(() => [budget, forecast], [budget, forecast]);
  const ponerOtro = (i: number, v: string) =>
    (i === 0 ? setBudget : setForecast)(v);
  const [clase, setClase] = useState<ClaseApertura>("opex");
  const [compacto, setCompacto] = useState(true);
  const [datos, setDatos] = useState<DetalleCelda | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  // El espejo y la lista, una sola vez. `incluirPrecierre` es deliberado: ver
  // la nota de arriba.
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const [lista, esp] = await Promise.all([
          getScenarios(HOTEL_ID, true),
          espejoAlDia(anio, mes),
        ]);
        if (!vivo) return;
        setEscenarios(lista);
        setEspejo(esp.espejo?.id || "");
        // Con qué arranca cada selector lo decide `useEscenarioDe`, y lo que se
        // elija queda recordado por pantalla.
      } catch (e) {
        if (vivo) setError(e instanceof Error ? e.message : "no se pudo cargar");
      }
    })();
    return () => { vivo = false; };
  }, [anio, mes]);

  const ids = useMemo(() => [espejo, ...otros].filter(Boolean), [espejo, otros]);

  const cargar = useCallback(async () => {
    if (!espejo) return;
    setCargando(true); setError("");
    try {
      // `abrir=false`: hasta la cuenta. Ver la nota de arriba.
      setDatos(await getDetalleDeCelda(ids, clase, "", mes, false));
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo cargar");
      setDatos(null);
    } finally {
      setCargando(false);
    }
  }, [ids, clase, mes, espejo]);

  useEffect(() => { cargar(); }, [cargar]);

  const cuadro = useMemo(() => {
    if (!datos) return null;
    try {
      return cuadroCheckbook(datos, escenarios, {
        ambito: `${MESES[mes - 1]} ${anio}`, compacto,
      });
    } catch {
      return null;
    }
  }, [datos, escenarios, compacto, mes, anio]);

  if (!espejo && !error) {
    return (
      <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        Todavía no hay espejo de este mes. Subí el archivo del Pre-Cierre y
        volvé — el espejo se escribe al guardar.
      </p>
    );
  }

  const rotulo = (s: Scenario) => `${s.type} ${s.version} ${s.year}`;

  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 12px" }}>
        El mes subido, cuenta por cuenta, contra las versiones que elijas. Los
        doce meses salen del espejo; la columna de {MESES[mes - 1]} es la del
        cierre.
      </p>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap",
                    alignItems: "center", marginBottom: 12 }}>
        {APERTURAS.map(a => (
          <button key={a.clase} onClick={() => setClase(a.clase)} title={a.eje}
                  style={{ padding: "5px 11px", borderRadius: 6, fontSize: 12,
                           cursor: "pointer",
                           border: `1px solid ${clase === a.clase
                             ? "var(--brand)" : "var(--border-medium)"}`,
                           background: clase === a.clase ? "var(--brand)" : "transparent",
                           color: clase === a.clase ? "#fff" : "var(--text-primary)" }}>
            {a.rotulo}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap",
                    alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          Comparar contra
        </span>
        {otros.map((id, i) => (
          <select key={i} value={id}
                  onChange={e => ponerOtro(i, e.target.value)}
                  style={{ fontSize: 12, padding: "4px 8px", borderRadius: 5 }}>
            <option value="">— sin comparar —</option>
            {escenarios.filter(s => !s.es_precierre).map(s => (
              <option key={s.id} value={s.id}>{rotulo(s)}</option>
            ))}
          </select>
        ))}
        <label style={{ fontSize: 12, display: "flex", gap: 5,
                        alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={compacto}
                 onChange={e => setCompacto(e.target.checked)} />
          Esconder las líneas en cero
        </label>
      </div>

      {error && <p style={{ fontSize: 13, color: "var(--negative)" }}>{error}</p>}
      {cargando && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>Cargando…</p>
      )}
      {!cargando && cuadro && <Tabla cuadro={cuadro} />}
      {!cargando && !cuadro && !error && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          No hay movimiento en esta clase para este mes.
        </p>
      )}
    </div>
  );
}
