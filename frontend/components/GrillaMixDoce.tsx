"use client";
/**
 * El mix de canales, los doce meses en una sola grilla.
 *
 * Owner, 2026-10-05, con la captura del mix de un mes: *«me gustaría que esto
 * esté lineal por mes para hacer un copy paste desde el Excel»* · *«que sea más
 * sencillo de lo que hoy es»*.
 *
 * ## Qué reemplaza
 *
 * La pantalla editaba **un mes a la vez** con un desplegable de trece opciones.
 * Para cargar el año había que entrar trece veces y guardar trece veces, y el
 * Excel del que sale el dato ya tiene los doce meses uno al lado del otro. Acá
 * se pega el bloque entero y se guarda una vez.
 *
 * ## ⚠️ Las celdas guardan el NÚMERO del porcentaje
 *
 * `55` es 55%, no 5500% ni 0,55. Por eso el pegado usa `numeroDePorcentaje` y
 * no `numeroDeExcel`: el primero deja `52`, `52%` y `52,0` los tres en 52; el
 * segundo divide el que trae `%` entre cien y devolvería 0,52. Las dos
 * funciones existen porque lo que decide es qué guarda la celda, y acá guarda
 * el número.
 *
 * ## ⚠️ El resumen de abajo NO es una segunda cuenta
 *
 * Suma el mix de los sub-canales que ruedan a cada cubo y promedia su comisión
 * **ponderada por mix** — la misma regla del motor. Se calcula acá para que se
 * vea mientras se escribe, y lo que se guarda son los sub-canales: el cubo
 * nunca se escribe.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { getMixerDoce, guardarMixer, type MixerDoce } from "@/lib/api";
import { manejarPegado, numeroDePorcentaje, repartirPegado } from "@/lib/pegarGrilla";

const DOCE = Array.from({ length: 12 }, (_, i) => i);
/** Debajo de esto, la suma del mix se considera cerrada en 100. */
const TOL = 0.05;

type Celdas = Record<string, number[]>;

export default function GrillaMixDoce({
  scenarioId, puedeEditar, onGuardado,
}: {
  scenarioId: string;
  puedeEditar: boolean;
  onGuardado?: () => void;
}) {
  const t = useTranslations("channels.mixer");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES = tm.raw("short") as string[];

  const [datos, setDatos] = useState<MixerDoce | null>(null);
  const [mix, setMix] = useState<Celdas>({});
  const [com, setCom] = useState<Celdas>({});
  const [sucio, setSucio] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async (sid: string) => {
    if (!sid) return;
    try {
      const d = await getMixerDoce(sid);
      setDatos(d);
      const m: Celdas = {}, c: Celdas = {};
      for (const s of d.subcanales) {
        m[s.code] = DOCE.map(i => (d.meses[i]?.filas[s.code]?.mix_pct ?? 0) * 100);
        c[s.code] = DOCE.map(i => (d.meses[i]?.filas[s.code]?.comision_pct ?? 0) * 100);
      }
      setMix(m); setCom(c); setSucio(false); setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    }
  }, [tc]);

  useEffect(() => { void cargar(scenarioId); }, [scenarioId, cargar]);

  const subs = useMemo(() => datos?.subcanales ?? [], [datos]);

  /** El cubo de cada mes: suma del mix y comisión ponderada. */
  const resumen = useMemo(() => (datos?.canales ?? []).map(k => {
    const mios = subs.filter(s => s.destino === k.code);
    const mixes = DOCE.map(i => mios.reduce((a, s) => a + (mix[s.code]?.[i] ?? 0), 0));
    const pond = DOCE.map(i => mios.reduce(
      (a, s) => a + (mix[s.code]?.[i] ?? 0) * (com[s.code]?.[i] ?? 0), 0));
    return {
      code: k.code, nombre: k.nombre, n: mios.length, mix: mixes,
      com: DOCE.map(i => (mixes[i] ? pond[i] / mixes[i] : 0)),
    };
  }), [datos, subs, mix, com]);

  const sumaMix = DOCE.map(i => subs.reduce((a, s) => a + (mix[s.code]?.[i] ?? 0), 0));
  /** Net Factor = 1 − Σ(mix × comisión), en fracción: como lo usa el motor. */
  const netFactor = DOCE.map(i =>
    1 - subs.reduce((a, s) =>
      a + (mix[s.code]?.[i] ?? 0) / 100 * (com[s.code]?.[i] ?? 0) / 100, 0));
  const todosCierran = sumaMix.every(v => Math.abs(v - 100) <= TOL);

  function poner(cual: "mix" | "com", code: string, i: number, valor: number) {
    const set = cual === "mix" ? setMix : setCom;
    set(prev => ({ ...prev, [code]: DOCE.map(j => (j === i ? valor : prev[code]?.[j] ?? 0)) }));
    setSucio(true);
  }

  /** Un bloque pegado desde Excel: cada celda cae en SU fila y SU mes. */
  function pegar(cual: "mix" | "com", fila: number, mesIdx: number, bloque: string[][]) {
    const set = cual === "mix" ? setMix : setCom;
    set(prev => {
      const copia: Celdas = {};
      for (const s of subs) copia[s.code] = [...(prev[s.code] ?? DOCE.map(() => 0))];
      repartirPegado(bloque, fila, mesIdx, subs.length, 12, (f, c, v) => {
        copia[subs[f].code][c] = numeroDePorcentaje(v);
      });
      return copia;
    });
    setSucio(true);
  }

  async function guardar() {
    if (!scenarioId) return;
    setGuardando(true); setAviso(null); setError(null);
    try {
      const filas = subs.flatMap(s => DOCE.map(i => ({
        code: s.code, month: i + 1,
        mix_pct: (mix[s.code]?.[i] ?? 0) / 100,
        comision_pct: (com[s.code]?.[i] ?? 0) / 100,
      })));
      await guardarMixer(scenarioId, filas);
      setSucio(false);
      setAviso(t("twelveSaved", { n: filas.length }));
      await cargar(scenarioId);
      onGuardado?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setGuardando(false); }
  }

  const TH: React.CSSProperties = {
    textAlign: "right", padding: "6px 8px", fontSize: 11, fontWeight: 600,
    color: "var(--text-secondary)", borderBottom: "1px solid var(--border-subtle)",
    whiteSpace: "nowrap",
  };
  const TD: React.CSSProperties = {
    padding: "3px 4px", borderBottom: "1px solid var(--border-subtle)", textAlign: "right",
  };
  const ROT: React.CSSProperties = {
    ...TD, textAlign: "left", fontSize: 13, whiteSpace: "nowrap",
  };
  const INP: React.CSSProperties = {
    width: 56, textAlign: "right", padding: "3px 5px", fontSize: 13,
    fontVariantNumeric: "tabular-nums",
  };

  if (error) return <p style={{ color: "#C0392B", fontSize: 13 }}>{error}</p>;
  if (!datos) {
    return <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tc("loading")}</p>;
  }

  const grilla = (cual: "mix" | "com", valores: Celdas, titulo: string) => (
    <div style={{ marginBottom: 18 }}>
      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{titulo}</div>
      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", minWidth: 820 }}>
          <thead>
            <tr>
              <th style={{ ...TH, textAlign: "left", minWidth: 230 }}>{t("colSub")}</th>
              {MESES.map(m => <th key={m} style={TH}>{m}</th>)}
            </tr>
          </thead>
          <tbody>
            {subs.map((s, fi) => (
              <tr key={s.code}>
                <td style={ROT}>
                  {s.nombre}
                  <span style={{ color: "var(--text-secondary)", fontSize: 11 }}>
                    {" "}· {s.destino}
                  </span>
                </td>
                {DOCE.map(i => (
                  <td key={i} style={TD}>
                    <input className="fin-input" style={INP} type="text" inputMode="decimal"
                      disabled={!puedeEditar}
                      value={String(valores[s.code]?.[i] ?? 0)}
                      onChange={e => poner(cual, s.code, i, numeroDePorcentaje(e.target.value))}
                      onPaste={e => manejarPegado(e, b => pegar(cual, fi, i, b))} />
                  </td>
                ))}
              </tr>
            ))}
            {cual === "mix" && (
              <tr>
                <td style={{ ...ROT, fontWeight: 700 }}>{t("mixSum")}</td>
                {DOCE.map(i => (
                  <td key={i} style={{ ...TD, fontWeight: 700, paddingRight: 9,
                    color: Math.abs(sumaMix[i] - 100) <= TOL ? "inherit" : "#C0392B" }}>
                    {sumaMix[i].toFixed(1)}
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
        marginBottom: 10 }}>
        <p style={{ fontSize: 12.5, color: "var(--text-secondary)", margin: 0, flex: 1 }}>
          {t("twelveHelp")}
        </p>
        <button onClick={() => void guardar()}
          disabled={!puedeEditar || !sucio || guardando}
          style={{ padding: "7px 14px", fontSize: 13, fontWeight: 600, borderRadius: 6,
            border: "1px solid var(--border-medium)", cursor: "pointer",
            opacity: puedeEditar && sucio && !guardando ? 1 : .45 }}>
          {guardando ? tc("saving") : t("twelveSave")}
        </button>
      </div>
      {aviso && <p style={{ fontSize: 13, color: "#26A69A" }}>{aviso}</p>}
      {/* ⚠️ Un mes cuyo mix no cierra en 100 deja el Net Factor sobre una base
          que no es el total. El aviso va acá arriba y no al guardar, porque el
          endpoint de excepción por escenario no lo valida: sólo lo hace el del
          mix base. */}
      {!todosCierran && (
        <p style={{ fontSize: 13, color: "#C0392B" }}>{t("mixMustBe100")}</p>
      )}

      {grilla("mix", mix, t("twelveMix"))}
      {grilla("com", com, t("twelveCommission"))}

      <div style={{ marginTop: 6 }}>
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{t("rollupTitle")}</div>
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", minWidth: 820 }}>
            <thead>
              <tr>
                <th style={{ ...TH, textAlign: "left", minWidth: 230 }}>{t("colChannel")}</th>
                {MESES.map(m => <th key={m} style={TH}>{m}</th>)}
              </tr>
            </thead>
            <tbody>
              {resumen.map(r => (
                <tr key={r.code}>
                  <td style={ROT}>
                    <strong>{r.nombre || r.code}</strong>
                    <span style={{ color: "var(--text-secondary)", fontSize: 11 }}>
                      {" "}· {t("rollupFrom", { n: r.n })}
                    </span>
                  </td>
                  {DOCE.map(i => (
                    <td key={i} style={{ ...TD, paddingRight: 9, fontSize: 12.5 }}>
                      {r.mix[i].toFixed(1)}
                      <span style={{ color: "var(--text-secondary)" }}>
                        {" / "}{r.com[i].toFixed(1)}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
              <tr>
                <td style={{ ...ROT, fontWeight: 700 }}>Net Factor</td>
                {DOCE.map(i => (
                  <td key={i} style={{ ...TD, fontWeight: 700, paddingRight: 9, fontSize: 12.5 }}>
                    {netFactor[i].toFixed(4)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 5 }}>
          {t("rollupHelp")}
        </p>
      </div>
    </div>
  );
}
