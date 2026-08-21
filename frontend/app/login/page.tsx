"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { authStatus, login, bootstrapAdmin } from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";

export default function LoginPage() {
  const router = useRouter();
  const t = useTranslations("auth");
  const tc = useTranslations("common");
  const [mode, setMode] = useState<"login" | "bootstrap" | "loading">("loading");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await authStatus();
        setMode(s.has_users ? "login" : "bootstrap");
      } catch {
        setMode("login");
      }
    })();
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (mode === "bootstrap") await bootstrapAdmin(email.trim().toLowerCase(), password, name);
      else await login(email.trim().toLowerCase(), password);
      router.push("/scenarios");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : tc("error");
      setError(mode === "login" && /401/.test(msg) ? t("invalidCredentials") : msg);
    } finally {
      setBusy(false);
    }
  }

  const input: React.CSSProperties = {
    width: "100%", padding: "9px 11px", fontSize: 14, marginTop: 4,
    background: "var(--bg-input, var(--bg-surface))", color: "var(--text-primary)",
    border: "1px solid var(--border-medium)", borderRadius: 6,
  };

  return (
    <div style={{ minHeight: "70vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ width: "100%", maxWidth: 360, border: "1px solid var(--border-medium)", borderRadius: 12, padding: 28, background: "var(--bg-surface)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{t("appName", { hotel: HOTEL_ID })}</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 20 }}>
          {mode === "bootstrap" ? t("bootstrapIntro") : t("loginIntro")}
        </p>

        {mode === "loading" ? (
          <div style={{ color: "var(--text-secondary)" }}>{tc("loading")}</div>
        ) : (
          <form onSubmit={submit}>
            {mode === "bootstrap" && (
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
                {t("name")}
                <input style={input} value={name} onChange={e => setName(e.target.value)} placeholder={t("namePlaceholder")} />
              </label>
            )}
            <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
              {t("email")}
              <input style={input} type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" required />
            </label>
            <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 16 }}>
              {t("password")}
              <input style={input} type="password" value={password} onChange={e => setPassword(e.target.value)}
                autoComplete={mode === "bootstrap" ? "new-password" : "current-password"} required
                placeholder={mode === "bootstrap" ? t("passwordHint") : ""} />
            </label>

            {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

            <button type="submit" disabled={busy}
              style={{ width: "100%", padding: "10px", fontSize: 14, fontWeight: 600, borderRadius: 6, border: "none",
                cursor: busy ? "default" : "pointer", background: busy ? "var(--bg-elevated)" : "var(--brand)", color: "#fff" }}>
              {busy ? "…" : mode === "bootstrap" ? t("createAdmin") : tc("login")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
