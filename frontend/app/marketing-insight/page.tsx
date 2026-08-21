"use client";
import { useTranslations } from "next-intl";
import { useHotel } from "@/lib/useHotel";

export default function MarketingInsightPage() {
  const hotel = useHotel();
  const t = useTranslations("mkt");
  return (
    <div className="pag pag-lectura" style={{ padding: "28px 32px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Marketing <span style={{ color: "var(--brand)" }}>Insight</span></h1>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 28 }}>{t("subtitle", { hotel: hotel.nombre })}</p>

      <div style={{ background: "var(--bg-elevated)", border: "1px dashed var(--border-medium)", borderRadius: 8, padding: "40px 28px", textAlign: "center" }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8 }}>{t("wip")}</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", maxWidth: 620, margin: "0 auto", lineHeight: 1.6 }}>
          Decime qué querés ver acá (canales de venta, mix de reservas, costo de adquisición, comisiones OTA,
          conversión, ingresos por segmento, etc.) y lo armo.
        </div>
      </div>
    </div>
  );
}
