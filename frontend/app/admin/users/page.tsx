"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { listUsers, createUser, updateUser, getStoredUser, type AuthUser } from "@/lib/api";

const btn = (enabled: boolean): React.CSSProperties => ({
  padding: "8px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
  cursor: enabled ? "pointer" : "not-allowed",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

/**
 * Contraseña inicial, generada acá y no digitada por nadie.
 *
 * Antes el admin la escribía en un campo `type="text"`: quedaba a la vista de
 * quien estuviera al lado y terminaba siendo la misma para todo el equipo.
 *
 * Sin `I`/`l`/`1`/`O`/`0` — esta clave se dicta o se copia a mano, y esos
 * caracteres se confunden entre sí. `crypto.getRandomValues` y no `Math.random`,
 * que es predecible.
 */
function generarClave(largo = 14): string {
  const abc = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const bytes = new Uint32Array(largo);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, b => abc[b % abc.length]).join("");
}

export default function UsersPage() {
  const tc = useTranslations("common");
  const t = useTranslations("users");
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const me = typeof window !== "undefined" ? getStoredUser() : null;

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("collaborator");
  const [busy, setBusy] = useState(false);
  // Contraseña recién generada, para entregársela a la persona. Se muestra UNA
  // vez y no se puede volver a ver: en el servidor solo queda el hash.
  const [entrega, setEntrega] = useState<{ email: string; pw: string } | null>(null);
  const [copiado, setCopiado] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setUsers(await listUsers());
    } catch (e: unknown) {
      const m = e instanceof Error ? e.message : "Error";
      setError(/403/.test(m) ? t("forbidden") : m);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    const correo = email.trim().toLowerCase();
    setBusy(true); setError(null); setMsg(null); setEntrega(null); setCopiado(false);
    try {
      const pw = generarClave();
      await createUser(correo, pw, name, role);
      setEntrega({ email: correo, pw });
      setName(""); setEmail(""); setRole("collaborator");
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("createError"));
    } finally { setBusy(false); }
  }

  async function patch(id: string, p: { name?: string; role?: string; active?: boolean; password?: string }) {
    setError(null); setMsg(null);
    try { await updateUser(id, p); await load(); setMsg(t("updated")); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
  }
  async function resetPass(u: AuthUser) {
    if (!window.confirm(t("resetConfirm", { email: u.email }))) return;
    const pw = generarClave();
    setError(null); setMsg(null); setEntrega(null); setCopiado(false);
    try {
      await updateUser(u.id, { password: pw });
      setEntrega({ email: u.email, pw });
      await load();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  const rolePill = (r: string): React.CSSProperties => ({
    fontSize: 11, padding: "2px 8px", borderRadius: 5,
    color: r === "admin" ? "var(--brand)" : "var(--text-secondary)",
    background: r === "admin" ? "rgba(41,98,255,0.12)" : "var(--bg-surface)",
  });
  const input: React.CSSProperties = {
    padding: "8px 10px", fontSize: 13, background: "var(--bg-input, var(--bg-surface))",
    color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6,
  };
  const editBtn: React.CSSProperties = {
    padding: "3px 8px", fontSize: 11, borderRadius: 4, cursor: "pointer",
    background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)",
  };

  return (
    <div className="pag pag-lectura" style={{ padding: 24 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <div style={{ flex: 1 }} />
        {me?.role === "admin" && (
          <button onClick={() => setShowForm(v => !v)} style={btn(true)}>
            {showForm ? tc("cancel") : t("newUser")}
          </button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {showForm && me?.role === "admin" && (
        <div style={{ border: "1px solid var(--border-medium)", borderRadius: 8, padding: 16, marginBottom: 20, background: "var(--bg-surface)", display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            {tc("name")}<input style={input} value={name} onChange={e => setName(e.target.value)} placeholder={t("namePlaceholder")} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            Email<input style={input} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder={t("emailPlaceholder")} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            {t("role")}
            <select style={input} value={role} onChange={e => setRole(e.target.value)}>
              <option value="collaborator">{t("collaborator")}</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <button onClick={handleCreate} disabled={busy || !email.includes("@")} style={btn(!busy && email.includes("@"))}>
            {busy ? t("creating") : t("create")}
          </button>
          <span style={{ fontSize: 11, color: "var(--text-disabled)", maxWidth: 240, lineHeight: 1.4 }}>
            {t("passwordNote")}
          </span>
        </div>
      )}

      {/* Entrega de la contraseña. Se ve una sola vez: en el servidor solo queda
          el hash, así que no hay forma de volver a mostrarla — solo generar otra. */}
      {entrega && (
        <div style={{ border: "1px solid var(--positive)", borderRadius: 8, padding: 16, marginBottom: 20, background: "rgba(26,127,75,0.08)" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--positive)", marginBottom: 8 }}>
            {t("passwordFor", { email: entrega.email })}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <code className="mono" style={{ fontSize: 18, letterSpacing: 1.5, padding: "8px 14px", borderRadius: 6, background: "var(--bg-input)", border: "1px solid var(--border-medium)", color: "var(--text-primary)", userSelect: "all" }}>
              {entrega.pw}
            </code>
            <button onClick={() => { navigator.clipboard?.writeText(entrega.pw); setCopiado(true); }}
              style={{ ...btn(true), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
              {copiado ? t("copied") : t("copy")}
            </button>
            <button onClick={() => { setEntrega(null); setCopiado(false); }}
              style={{ ...btn(true), background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
              {t("done")}
            </button>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 10, lineHeight: 1.5 }}>
            {t.rich("handoffNote", { b: (c: React.ReactNode) => <b>{c}</b> })}
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <table className="fin-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>{tc("name")}</th>
              <th style={{ textAlign: "left" }}>Email</th>
              <th style={{ textAlign: "left" }}>{t("role")}</th>
              <th style={{ textAlign: "left" }}>{tc("status")}</th>
              {me?.role === "admin" && <th style={{ textAlign: "left" }}>{t("actions")}</th>}
            </tr>
          </thead>
          <tbody>
            {users.map(u => {
              const self = !!me && u.id === me.id;
              return (
              <tr key={u.id}>
                <td style={{ textAlign: "left", fontWeight: 500 }}>{u.name || "—"}{self && <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>{t("you")}</span>}</td>
                <td style={{ textAlign: "left" }}>{u.email}</td>
                <td style={{ textAlign: "left" }}><span style={rolePill(u.role)}>{u.role === "admin" ? "Admin" : t("collaborator")}</span></td>
                <td style={{ textAlign: "left", color: u.active ? "var(--accent-green, #1A7F4B)" : "var(--text-disabled)", fontSize: 12 }}>{u.active ? t("active") : t("inactive")}</td>
                {me?.role === "admin" && (
                  <td style={{ textAlign: "left" }}>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                      <select className="fin-input" value={u.role} disabled={self}
                        onChange={e => patch(u.id, { role: e.target.value })} style={{ fontSize: 11, padding: "2px 4px" }}>
                        <option value="collaborator">{t("collaborator")}</option>
                        <option value="admin">Admin</option>
                      </select>
                      <button onClick={() => patch(u.id, { active: !u.active })} disabled={self}
                        style={{ ...editBtn, opacity: self ? 0.4 : 1 }}>{u.active ? t("deactivate") : t("activate")}</button>
                      <button onClick={() => resetPass(u)} style={editBtn}>{t("resetPass")}</button>
                    </div>
                  </td>
                )}
              </tr>
            );})}
          </tbody>
        </table>
      )}
    </div>
  );
}
