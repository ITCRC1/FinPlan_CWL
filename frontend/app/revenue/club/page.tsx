"use client";
import { useCallback, useEffect, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import ClubMembershipEditor from "@/components/ClubMembershipEditor";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getClubFee, saveClubFee,
  type Scenario, type ClubFee,
} from "@/lib/api";

/**
 * Club Madresal — membresías y sus tres ingresos.
 *
 * Tab propio, con la misma forma que Spa (capture rate): arriba el dato
 * operativo que se lleva mes a mes, abajo el precio que se presupuesta, y la
 * cuota sale sola.
 *
 *     4500  Ingreso Madresal Club   ← socios(base) × precio
 *     4501  Actividad fin de año    ← se digita
 *     4502  Visitantes              ← se digita
 *
 * **Por qué no vive en Room Stats.** Ese tab va para los dueños de CWL y las
 * membresías son de Amarena. Acá, además, está donde se planea el ingreso.
 *
 * **Las otras dos no son un «otros» anónimo.** El catálogo las lleva con nombre
 * y cuenta propia, así que acá también: los rótulos y los números de cuenta
 * vienen del backend (`fee.lineas`), que los toma del mapeo — la pantalla no se
 * inventa nombres que después no calcen con los del mayor.
 *
 * Cada una se persiste en SU línea del checkbook de ingresos, que es de donde
 * el P&L lee. Las tres caen en REV_CLUB, así que separarlas no cambia el total.
 */
const HOTEL = HOTEL_ID;
const GOLD = "#c8a24a";
const MESES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 11, textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.05em", background: "var(--bg-elevated)" };
const thNum: CSSProperties = { ...th, textAlign: "right", textTransform: "none", letterSpacing: 0 };
const tdNum: CSSProperties = { padding: "5px 10px", textAlign: "right", fontSize: 12.5, fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--border-subtle)" };

const money = (v: number) => (v ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "");
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version))
    ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

export default function ClubPage() {
  const hotel = useHotel();
  const t = useTranslations("club");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [fee, setFee] = useState<ClubFee | null>(null);
  const [precio, setPrecio] = useState<string[]>(Array(12).fill(""));
  // Las dos fuentes que se digitan, cada una su cuenta del catálogo.
  const [actividad, setActividad] = useState<string[]>(Array(12).fill(""));   // 4501
  const [visitantes, setVisitantes] = useState<string[]>(Array(12).fill("")); // 4502
  const [base, setBase] = useState("pagando");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL);
        if (!all.length) { setError(tc("noScenarios", { hotel: hotel.id })); return; }
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const bud = elegir(all, "budget") ?? all[0];
        setScenarioId(sharedScenarioOr(bud.id));
      } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    })();
  }, [setScenarioId, tc]);

  const cargar = useCallback(async (id: string) => {
    if (!id) return;
    setError(""); setMsg("");
    try {
      const d = await getClubFee(id);
      setFee(d); setBase(d.base);
      setPrecio(d.filas.map(f => (f.precio ? String(f.precio) : "")));
      setActividad(d.filas.map(f => (f.actividad ? String(f.actividad) : "")));
      setVisitantes(d.filas.map(f => (f.visitantes ? String(f.visitantes) : "")));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); setFee(null); }
  }, []);

  useEffect(() => { cargar(scenarioId); }, [scenarioId, cargar]);

  const num = (s: string) => { const n = parseFloat((s || "").replace(/[^\d.-]/g, "")); return isNaN(n) ? 0 : n; };
  const socios = (m: number) => fee?.filas[m]?.socios ?? 0;
  const cuotas = (m: number) => socios(m) * num(precio[m]);
  const ingreso = (m: number) => cuotas(m) + num(actividad[m]) + num(visitantes[m]);
  const total = Array.from({ length: 12 }, (_, m) => ingreso(m)).reduce((a, b) => a + b, 0);

  /** Las dos filas que se digitan, con su estado. El rótulo y el número de
   *  cuenta NO están acá: vienen del backend (`fee.lineas`), que los toma del
   *  catálogo. */
  const editar = (set: React.Dispatch<React.SetStateAction<string[]>>) =>
    (m: number, v: string) =>
      set(prev => { const n = [...prev]; n[m] = v.replace(/[^\d.-]/g, ""); return n; });
  const MANUALES = [
    { linea: "CLUB_ACTIVIDAD", valores: actividad, poner: editar(setActividad) },
    { linea: "CLUB_VISITANTES", valores: visitantes, poner: editar(setVisitantes) },
  ];

  /** Un precio en una casilla se copia a los meses siguientes que estén vacíos:
   *  la cuota casi nunca cambia mes a mes y tipearla doce veces es trabajo tonto. */
  function ponerPrecio(m: number, v: string) {
    setPrecio(prev => {
      const nv = [...prev];
      nv[m] = v.replace(/[^\d.-]/g, "");
      for (let i = m + 1; i < 12; i++) { if (!nv[i]) nv[i] = nv[m]; else break; }
      return nv;
    });
  }

  /** Baja el cuadro de la cuota — el mismo que está en pantalla, con lo digitado.
   *  El conteo de socios detallado vive en su propio componente; acá va la base
   *  que alimenta la cuota, que es la fila que este cuadro muestra. */
  async function bajarExcel() {
    if (!fee) return;
    const meses = Array.from({ length: 12 }, (_, m) => m);
    const linea = (id: string, fallback: string) => {
      const meta = fee.lineas.find(l => l.linea === id);
      return meta ? `${meta.cuenta} · ${meta.nombre}` : fallback;
    };
    const filas: FilaCuadro[] = [
      { label: t("membersBase"), formato: "num", valores: [...meses.map(m => socios(m) || null), null] },
      { label: t("feePerMember"), formato: "usd2",
        valores: [...meses.map(m => (precio[m] || "").trim() === "" ? null : num(precio[m])), null] },
      {
        label: linea("CLUB", t("feeRevenue")), nivel: 1,
        valores: [...meses.map(m => cuotas(m)), meses.reduce((a, m) => a + cuotas(m), 0)],
      },
      ...MANUALES.map(({ linea: id, valores }) => ({
        label: linea(id, id),
        valores: [...meses.map(m => num(valores[m])), meses.reduce((a, m) => a + num(valores[m]), 0)],
      })),
      { label: t("clubRevenue"), es_total: true, valores: [...meses.map(m => ingreso(m)), total] },
    ];
    try {
      await bajarCuadros("Club_Madresal", [{
        titulo: t("title"),
        subtitulo: [scenarios.find(s => s.id === scenarioId)?.year ? scnLabel(scenarios.find(s => s.id === scenarioId)!) : "",
          fee.etiquetas_base[base] ?? base].filter(Boolean).join(" · "),
        hoja: "Club Madresal",
        columnas: [
          { label: tc("concept"), ancho: 34, formato: "texto" },
          ...MESES.map(m => ({ label: m, ancho: 12, formato: "usd" as const })),
          { label: t("yearTotal"), ancho: 15, formato: "usd" as const },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  async function guardar() {
    setBusy(true); setMsg(""); setError("");
    try {
      const d = await saveClubFee(scenarioId, base,
        Array.from({ length: 12 }, (_, m) => ({
          month: m + 1, precio: num(precio[m]),
          actividad: num(actividad[m]), visitantes: num(visitantes[m]),
        })));
      setFee(d);
      setMsg(t("saved"));
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setBusy(false); }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: "24px 20px 60px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} disabled={!fee} title={t("excelHint")}
          style={{ padding: "5px 14px", fontSize: 12.5, fontWeight: 700, borderRadius: 6,
            cursor: fee ? "pointer" : "not-allowed", background: "transparent",
            color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6, maxWidth: "80ch" }}>
        {t("intro")}
      </p>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginTop: 12 }}>{error}</div>}

      {fee && !fee.visible && (
        <div style={{ marginTop: 16, padding: "12px 16px", borderRadius: 8, fontSize: 12.5,
          background: "rgba(200,162,74,0.08)", border: `1px solid ${GOLD}` }}>
          {t("notEnabled")}
        </div>
      )}

      {/* Un escenario en modo drivers arma los ingresos con tarifas y ocupación y
          NO lee las líneas del checkbook: acá uno guardaría y el P&L seguiría en
          cero, sin decir nada. Se avisa en vez de dejarlo pasar callado. */}
      {fee && fee.visible && fee.llega_al_pl === false && (
        <div style={{ marginTop: 16, padding: "12px 16px", borderRadius: 8, fontSize: 12.5,
          background: "rgba(200,162,74,0.08)", border: `1px solid ${GOLD}` }}>
          {t("notCheckbook")}
        </div>
      )}

      {fee && fee.visible && <>
        {/* 1 · el conteo de socios */}
        <ClubMembershipEditor scenarioId={scenarioId} meses={MESES} />

        {/* 2 · la cuota, y el ingreso que sale de las dos cosas */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginTop: 30, flexWrap: "wrap" }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{t("feeTitle")}</h2>
          <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}
            title={t("baseHint")}>
            {t("base")}
            <select value={base} onChange={e => setBase(e.target.value)}
              style={{ padding: "4px 8px", fontSize: 12, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
              {fee.bases.map(b => <option key={b} value={b}>{fee.etiquetas_base[b] ?? b}</option>)}
            </select>
          </label>
        </div>

        <div className="fin-sticky" style={{ marginTop: 8, background: "var(--bg-elevated)",
          border: "1px solid var(--border-medium)", borderRadius: 10, overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1080 }}>
            <thead>
              <tr>
                <th style={{ ...th, minWidth: 220 }}>{tc("concept")}</th>
                {MESES.map(m => <th key={m} style={{ ...thNum, minWidth: 78 }}>{m}</th>)}
                <th style={{ ...thNum, minWidth: 96, borderLeft: "1px solid var(--border-medium)" }}>
                  {t("yearTotal")}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: "5px 12px", fontSize: 12.5, borderBottom: "1px solid var(--border-subtle)" }}>
                  {t("membersBase")}
                </td>
                {Array.from({ length: 12 }, (_, m) => (
                  <td key={m} style={{ ...tdNum, color: "var(--text-secondary)" }}>{socios(m) || ""}</td>
                ))}
                <td style={{ ...tdNum, borderLeft: "1px solid var(--border-medium)" }} />
              </tr>
              <tr>
                <td style={{ padding: "5px 12px", fontSize: 12.5, borderBottom: "1px solid var(--border-subtle)" }}>
                  {t("feePerMember")}
                </td>
                {Array.from({ length: 12 }, (_, m) => (
                  <td key={m} style={{ padding: 2, borderBottom: "1px solid var(--border-subtle)" }}>
                    <input className="fin-input mono" value={precio[m]}
                      onChange={e => ponerPrecio(m, e.target.value)}
                      style={{ width: "100%", textAlign: "right", fontSize: 12, padding: "3px 6px" }} />
                  </td>
                ))}
                <td style={{ ...tdNum, borderLeft: "1px solid var(--border-medium)" }} />
              </tr>
              <tr style={{ color: "var(--text-secondary)" }}>
                <td style={{ padding: "5px 12px", fontSize: 12.5, borderBottom: "1px solid var(--border-subtle)", paddingLeft: 26 }}>
                  <span className="mono" style={{ color: "var(--text-disabled)", marginRight: 8 }}>
                    {fee.lineas.find(l => l.linea === "CLUB")?.cuenta}
                  </span>
                  {fee.lineas.find(l => l.linea === "CLUB")?.nombre ?? t("feeRevenue")}
                </td>
                {Array.from({ length: 12 }, (_, m) => <td key={m} style={tdNum}>{money(cuotas(m))}</td>)}
                <td style={{ ...tdNum, borderLeft: "1px solid var(--border-medium)" }}>
                  {money(Array.from({ length: 12 }, (_, m) => cuotas(m)).reduce((a, b) => a + b, 0))}
                </td>
              </tr>
              {/* Las otras dos fuentes: se digitan, pero NO son un «otros»
                  anónimo — cada una es su cuenta del catálogo. El rótulo y el
                  número de cuenta vienen del backend para que la pantalla no se
                  invente nombres que después no cuadran con la contabilidad. */}
              {MANUALES.map(({ linea, valores, poner }) => {
                const meta = fee.lineas.find(l => l.linea === linea);
                return (
                  <tr key={linea}>
                    <td style={{ padding: "5px 12px", fontSize: 12.5, borderBottom: "1px solid var(--border-subtle)" }}>
                      <span className="mono" style={{ color: "var(--text-disabled)", marginRight: 8 }}>
                        {meta?.cuenta}
                      </span>
                      {meta?.nombre ?? linea}
                    </td>
                    {Array.from({ length: 12 }, (_, m) => (
                      <td key={m} style={{ padding: 2, borderBottom: "1px solid var(--border-subtle)" }}>
                        <input className="fin-input mono" value={valores[m]}
                          onChange={e => poner(m, e.target.value)}
                          style={{ width: "100%", textAlign: "right", fontSize: 12, padding: "3px 6px" }} />
                      </td>
                    ))}
                    <td style={{ ...tdNum, borderLeft: "1px solid var(--border-medium)" }}>
                      {money(Array.from({ length: 12 }, (_, m) => num(valores[m])).reduce((a, b) => a + b, 0))}
                    </td>
                  </tr>
                );
              })}
              <tr style={{ fontWeight: 700, background: "rgba(200,162,74,0.07)" }}>
                <td style={{ padding: "6px 12px", fontSize: 12.5, borderTop: "1px solid var(--border-medium)" }}>
                  {t("clubRevenue")}
                </td>
                {Array.from({ length: 12 }, (_, m) => (
                  <td key={m} style={{ ...tdNum, borderTop: "1px solid var(--border-medium)" }}>{money(ingreso(m))}</td>
                ))}
                <td style={{ ...tdNum, fontWeight: 700, borderLeft: "1px solid var(--border-medium)", borderTop: "1px solid var(--border-medium)" }}>
                  {money(total)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 10, flexWrap: "wrap" }}>
          <button onClick={guardar} disabled={busy}
            style={{ padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 6,
              cursor: busy ? "default" : "pointer", background: "var(--positive)", color: "#fff", border: "none" }}>
            {busy ? tc("saving") : t("saveAndPush")}
          </button>
          {msg && <span style={{ fontSize: 12.5, color: "var(--positive)" }}>{msg}</span>}
        </div>
        <p style={{ fontSize: 11.5, color: GOLD, marginTop: 8, maxWidth: "80ch" }}>{t("pushNote")}</p>
      </>}
    </div>
  );
}
