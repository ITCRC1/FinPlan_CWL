"use client";
/**
 * Donde la persona invitada se pone SU contraseña.
 *
 * **El pedido (owner, 2026-10-25):** *«yo mando la invitación y ellos generan
 * sus claves»*.
 *
 * Es pública a propósito: quien la abre todavía no tiene cuenta utilizable. Lo
 * único que la protege es el token del enlace — 32 bytes aleatorios, de un solo
 * uso, que vencen a los 7 días.
 *
 * ⚠️ **La contraseña no sale de este navegador hasta que se envía, y el
 * servidor sólo guarda su hash.** Esa es toda la diferencia con lo que había
 * antes, donde la clave la generaba el admin y viajaba por un chat.
 */
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { canjearInvitacion, verInvitacion, type InvitacionAbierta } from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";

export default function InvitacionPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const token = String(params?.token ?? "");
  const t = useTranslations("invitacion");
  const tc = useTranslations("common");

  const [estado, setEstado] = useState<"cargando" | "lista" | "invalida">("cargando");
  const [inv, setInv] = useState<InvitacionAbierta | null>(null);
  const [clave, setClave] = useState("");
  const [repetida, setRepetida] = useState("");
  const [ver, setVer] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) { setEstado("invalida"); return; }
    verInvitacion(token)
      .then(d => { setInv(d); setEstado("lista"); })
      .catch(() => setEstado("invalida"));
  }, [token]);

  const minimo = inv?.largo_minimo ?? 8;
  const corta = clave.length > 0 && clave.length < minimo;
  // Se avisa al escribir, no al enviar: enterarse de que no coinciden después
  // de apretar el botón obliga a reescribir las dos.
  const distintas = repetida.length > 0 && clave !== repetida;
  const puede = clave.length >= minimo && clave === repetida && !busy;

  const enviar = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!puede) return;
    setBusy(true); setError(null);
    try {
      await canjearInvitacion(token, clave);
      // Queda adentro: ya demostró que tiene el enlace y acaba de elegir la
      // clave. Pedirle que la escriba otra vez en el login no prueba nada.
      router.push("/scenarios");
    } catch (err: unknown) {
      const m = err instanceof Error ? err.message : tc("error");
      // Si el enlace murió mientras llenaba el formulario —se reenvió otro, o
      // venció— hay que decirlo acá y no dejarlo reintentando.
      if (/404/.test(m)) { setEstado("invalida"); return; }
      setError(/422/.test(m) ? t("corta", { n: minimo }) : m);
    } finally { setBusy(false); }
  }, [puede, token, clave, router, t, tc, minimo]);

  const input: React.CSSProperties = {
    width: "100%", padding: "9px 11px", fontSize: 14, marginTop: 4,
    background: "var(--bg-input, var(--bg-surface))", color: "var(--text-primary)",
    border: "1px solid var(--border-medium)", borderRadius: 6,
  };
  const marco: React.CSSProperties = {
    width: "100%", maxWidth: 420, border: "1px solid var(--border-medium)",
    borderRadius: 12, padding: 28, background: "var(--bg-surface)",
  };

  return (
    <div style={{ minHeight: "70vh", display: "flex", alignItems: "center",
                  justifyContent: "center", padding: 24 }}>
      <div style={marco}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          {t("appName", { hotel: HOTEL_ID })}
        </h1>

        {estado === "cargando" && (
          <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 14 }}>
            {tc("loading")}
          </p>
        )}

        {/* ⚠️ El backend no dice SI el enlace no existe, ya se usó o venció —
          * distinguirlo le contaría a quien prueba tokens cuál acertó a
          * medias. Acá se ofrece la salida real: pedirle otro al admin. */}
        {estado === "invalida" && (
          <>
            <p style={{ color: "var(--accent-red, #C0392B)", fontSize: 14,
                        marginTop: 14, fontWeight: 600 }}>
              {t("invalidaTitulo")}
            </p>
            <p style={{ color: "var(--text-secondary)", fontSize: 13,
                        marginTop: 8, lineHeight: 1.55 }}>
              {t("invalidaDetalle")}
            </p>
            <button onClick={() => router.push("/login")}
              style={{ marginTop: 18, width: "100%", padding: 10, fontSize: 14,
                       fontWeight: 600, borderRadius: 6, border: "1px solid var(--border-medium)",
                       cursor: "pointer", background: "transparent",
                       color: "var(--text-primary)" }}>
              {t("irALogin")}
            </button>
          </>
        )}

        {estado === "lista" && inv && (
          <>
            <p style={{ color: "var(--text-secondary)", fontSize: 13,
                        marginTop: 6, marginBottom: 4, lineHeight: 1.55 }}>
              {inv.es_alta ? t("introAlta") : t("introCambio")}
            </p>
            {/* A qué cuenta le está poniendo clave. Sin esto, alguien con dos
              * correos no sabe cuál está configurando. */}
            <p style={{ fontSize: 13.5, fontWeight: 700, color: "var(--text-primary)",
                        marginBottom: 18 }}>
              {inv.email}
            </p>

            <form onSubmit={enviar}>
              <label style={{ display: "block", fontSize: 12,
                              color: "var(--text-secondary)", marginBottom: 12 }}>
                {t("clave")}
                <input style={input} type={ver ? "text" : "password"} value={clave}
                  onChange={e => setClave(e.target.value)} autoComplete="new-password"
                  autoFocus required minLength={minimo} />
              </label>
              <label style={{ display: "block", fontSize: 12,
                              color: "var(--text-secondary)", marginBottom: 6 }}>
                {t("repetir")}
                <input style={input} type={ver ? "text" : "password"} value={repetida}
                  onChange={e => setRepetida(e.target.value)} autoComplete="new-password"
                  required />
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: 7,
                              fontSize: 12, color: "var(--text-secondary)",
                              margin: "10px 0 14px", cursor: "pointer" }}>
                <input type="checkbox" checked={ver} onChange={e => setVer(e.target.checked)} />
                {t("verClave")}
              </label>

              <div style={{ fontSize: 11.5, lineHeight: 1.5, marginBottom: 12,
                            color: corta || distintas
                              ? "var(--accent-red, #C0392B)" : "var(--text-disabled)" }}>
                {distintas ? t("noCoinciden") : t("minimo", { n: minimo })}
              </div>

              {error && (
                <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13,
                              marginBottom: 12 }}>{error}</div>
              )}

              <button type="submit" disabled={!puede}
                style={{ width: "100%", padding: 10, fontSize: 14, fontWeight: 600,
                         borderRadius: 6, border: "none",
                         cursor: puede ? "pointer" : "default",
                         background: puede ? "var(--brand)" : "var(--bg-elevated)",
                         color: puede ? "#fff" : "var(--text-disabled)" }}>
                {busy ? "…" : t("guardar")}
              </button>
            </form>

            <p style={{ fontSize: 11, color: "var(--text-disabled)", marginTop: 14,
                        lineHeight: 1.5 }}>
              {t("privacidad")}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
