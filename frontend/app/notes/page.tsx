"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";
import {
  getScenarios, getAssignments, getAnnotations, addAnnotation, resolveAnnotation, deleteAnnotation,
  getStoredUser, type Scenario, type SectionRow, type Annotation,
} from "@/lib/api";

const MONTHS_FALLBACK = ["General/Anual","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

const btn = (enabled: boolean): React.CSSProperties => ({
  padding: "8px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
  cursor: enabled ? "pointer" : "not-allowed",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

export default function NotesPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  // El indice 0 no es un mes ("General/Anual"): solo se traducen los 12 meses.
  const MONTHS = [MONTHS_FALLBACK[0], ...((tm.raw("short") as string[]) ?? MONTHS_FALLBACK.slice(1))];
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Las notas son de UN escenario: si el selector se mueve solo, el comentario
  // se escribe sobre el presupuesto equivocado. Se acuerda de lo ultimo elegido
  // aca y, si nunca se eligio, abre con el preferido del owner (el ano estaba
  // clavado en 2026).
  const [scenarioId, setScenarioId] = useEscenarioDe("notes:budget", scenarios, "budget", undefined, true);
  const [sections, setSections] = useState<SectionRow[]>([]);
  const [kind, setKind] = useState<"comment" | "question">("comment");
  const [items, setItems] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const me = typeof window !== "undefined" ? getStoredUser() : null;

  // form
  const [fSection, setFSection] = useState("revenue");
  const [fRef, setFRef] = useState("");
  const [fMonth, setFMonth] = useState(0);
  const [fBody, setFBody] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string, k: string) => {
    setLoading(true); setError(null);
    try {
      const [a, asg] = await Promise.all([getAnnotations(sid, { kind: k }), getAssignments(sid)]);
      setItems(a.annotations);
      setSections(asg.sections);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId, kind); }, [scenarioId, kind, load]);

  async function submit() {
    if (!scenarioId || !fBody.trim()) return;
    setBusy(true); setError(null);
    try {
      await addAnnotation(scenarioId, { section: fSection, ref: fRef, month: fMonth, kind, body: fBody.trim() });
      setFRef(""); setFBody("");
      await load(scenarioId, kind);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setBusy(false); }
  }
  async function act(fn: () => Promise<unknown>) {
    try { await fn(); await load(scenarioId, kind); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
  }

  // agrupar por sección (para la narrativa)
  const bySection: Record<string, Annotation[]> = {};
  for (const a of items) (bySection[a.label] ??= []).push(a);

  const input: React.CSSProperties = {
    padding: "8px 10px", fontSize: 13, background: "var(--bg-input, var(--bg-surface))",
    color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6,
  };

  return (
    <div className="pag pag-lectura" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Comentarios &amp; Q&amp;A</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>)}
        </select>
        <div style={{ display: "inline-flex", border: "1px solid var(--border-medium)", borderRadius: 6, overflow: "hidden" }}>
          {(["comment", "question"] as const).map(k => (
            <button key={k} onClick={() => setKind(k)} style={{
              padding: "6px 14px", fontSize: 13, border: "none", cursor: "pointer",
              background: kind === k ? "var(--brand)" : "transparent",
              color: kind === k ? "#fff" : "var(--text-secondary)",
            }}>{k === "comment" ? "Comentarios (narrativa)" : "Q&A"}</button>
          ))}
        </div>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {kind === "comment"
          ? "Explicaciones por línea que se agregan en la narrativa para los dueños (ej. “Abril 2026 tuvo el grupo NH → ingreso alto; 2027 sin grupo → baja”)."
          : "Preguntas en contexto (abierta/resuelta) para el equipo."}
      </p>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {/* Form */}
      <div style={{ border: "1px solid var(--border-medium)", borderRadius: 8, padding: 14, marginBottom: 20, background: "var(--bg-surface)", display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          Sección
          <select style={input} value={fSection} onChange={e => setFSection(e.target.value)}>
            {sections.map(s => <option key={s.section} value={s.section}>{s.label}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          Línea / ref<input style={{ ...input, width: 160 }} value={fRef} onChange={e => setFRef(e.target.value)} placeholder="ej. Tours" />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          {tc("month")}
          <select style={input} value={fMonth} onChange={e => setFMonth(parseInt(e.target.value))}>
            {MONTHS.map((m, i) => <option key={i} value={i}>{m}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)", flex: 1, minWidth: 220 }}>
          {kind === "comment" ? "Explicación" : "Pregunta"}
          <input style={input} value={fBody} onChange={e => setFBody(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") submit(); }}
            placeholder={kind === "comment" ? "por qué la variación…" : "tu pregunta…"} />
        </label>
        <button onClick={submit} disabled={busy || !fBody.trim()} style={btn(!busy && !!fBody.trim())}>
          {busy ? "…" : "Agregar"}
        </button>
      </div>

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : items.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", padding: 12 }}>Sin {kind === "comment" ? "comentarios" : "preguntas"} todavía.</div>
      ) : (
        Object.entries(bySection).map(([label, list]) => (
          <div key={label} style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--brand)", marginBottom: 6 }}>{label}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {list.map(a => {
                const canEdit = me?.role === "admin" || a.author === (me?.name || me?.email);
                return (
                  <div key={a.id} style={{ display: "flex", gap: 10, alignItems: "flex-start",
                    background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "9px 12px",
                    opacity: a.resolved ? 0.6 : 1 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 2 }}>
                        {a.ref && <b style={{ color: "var(--text-primary)" }}>{a.ref}</b>}
                        {a.ref && a.month > 0 && " · "}
                        {a.month > 0 && MONTHS[a.month]}
                        {a.resolved && <span style={{ color: "var(--accent-green, #1A7F4B)", marginLeft: 6 }}>✓ resuelta</span>}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.5 }}>{a.body}</div>
                      <div style={{ fontSize: 11, color: "var(--text-disabled)", marginTop: 3 }}>
                        {a.author ?? "—"}{a.created_at ? " · " + new Date(a.created_at).toLocaleDateString("es-CR") : ""}
                      </div>
                    </div>
                    {canEdit && (
                      <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                        <button onClick={() => act(() => resolveAnnotation(a.id, !a.resolved))}
                          style={{ fontSize: 11, padding: "3px 8px", borderRadius: 4, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
                          {a.resolved ? "Reabrir" : (kind === "question" ? "Resolver" : "Marcar")}
                        </button>
                        <button onClick={() => act(() => deleteAnnotation(a.id))}
                          style={{ fontSize: 11, padding: "3px 8px", borderRadius: 4, cursor: "pointer", background: "none", color: "var(--text-disabled)", border: "1px solid var(--border-medium)" }}>✕</button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
