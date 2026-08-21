"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { getToken } from "@/lib/api";

// Si no hay sesión y no estás en /login, redirige a /login.
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("common");
  const [ok, setOk] = useState(false);

  useEffect(() => {
    const isLogin = pathname?.startsWith("/login");
    const hasToken = !!getToken();
    if (!hasToken && !isLogin) {
      router.replace("/login");
      setOk(false);
    } else {
      setOk(true);
    }
  }, [pathname, router]);

  if (!ok && !pathname?.startsWith("/login")) {
    return <div style={{ padding: 40, color: "var(--text-secondary)" }}>{t("redirecting")}</div>;
  }
  return <>{children}</>;
}
