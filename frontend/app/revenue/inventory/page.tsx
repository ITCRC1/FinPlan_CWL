"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getRoomTypes, createRoomType, updateRoomType, deleteRoomType, rtLabel,
  type RoomType,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const HOTEL = HOTEL_ID;

const btnStyle = (enabled: boolean): React.CSSProperties => ({
  padding: "7px 14px", fontSize: 13, borderRadius: 5, fontWeight: 500,
  cursor: enabled ? "pointer" : "not-allowed", border: "none",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

// Inline-editable text/number cell that saves on blur.
function EditCell({
  value, onSave, type = "text", align = "left", width,
}: {
  value: string | number;
  onSave: (v: string) => void;
  type?: "text" | "number";
  align?: "left" | "right";
  width?: number;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => { setDraft(String(value)); }, [value]);
  return (
    <input
      className="fin-input mono"
      value={draft}
      inputMode={type === "number" ? "numeric" : undefined}
      onChange={e => setDraft(e.target.value)}
      onBlur={() => { if (draft !== String(value)) onSave(draft); }}
      onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      style={{ width: width ?? "100%", textAlign: align, padding: "4px 6px" }}
    />
  );
}

export default function InventoryPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("inventory");
  const [rows, setRows] = useState<RoomType[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await getRoomTypes(HOTEL);
      setRows(res.room_types);
      setTotal(res.total_units);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save(id: string, patch: Partial<RoomType>) {
    setBusy(true); setError(null);
    try {
      await updateRoomType(HOTEL, id, patch);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally {
      setBusy(false);
    }
  }

  async function addRow() {
    setBusy(true); setError(null);
    try {
      await createRoomType(HOTEL, { name: t("newCategory"), units: 0 });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string, name: string) {
    // No se borra: se OCULTA. El código queda reservado para siempre, así que
    // un SH08 de hoy no puede terminar apuntando a otra categoría mañana.
    if (!confirm(t("confirmHide", { name }))) return;
    setBusy(true); setError(null);
    try {
      await deleteRoomType(HOTEL, id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setBusy(false);
    }
  }

  // Live total reflects edits in flight too.
  const liveTotal = rows.reduce((s, r) => s + (Number(r.units) || 0), 0) || total;

  // ── Excel: la misma tabla, con units y pax como número ────────────────────
  async function bajarExcel() {
    const filas: FilaCuadro[] = rows.map(r => ({
      label: rtLabel(r.code, r.name), nivel: 1,
      valores: [Number(r.pax_min) || 0, Number(r.pax_max) || 0, Number(r.units) || 0],
    }));
    // Pax min/max no se suman: el total solo aplica a unidades.
    filas.push({ label: tc("total"), es_total: true, valores: [null, null, liveTotal] });
    try {
      await bajarCuadros("Inventario", [{
        titulo: t("title"),
        subtitulo: t("xlsSubtitle", { hotel: hotel.nombre }),
        hoja: t("sheet"),
        columnas: [
          { label: tc("category"), ancho: 40, formato: "texto" },
          { label: "Pax min", ancho: 12, formato: "num" },
          { label: "Pax max", ancho: 12, formato: "num" },
          { label: t("units"), ancho: 12, formato: "num" },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  return (
    <div className="pag pag-lectura" style={{ padding: 24 }}>
      <IrA />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          {t("title")}
        </h1>
        <button onClick={bajarExcel} title={t("excelHint")}
          style={{ ...btnStyle(true), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {t("intro", { hotel: hotel.nombre })} {busy && `· ${tc("saving")}`}
      </p>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <>
          <table className="fin-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 40 }}>#</th>
                <th style={{ textAlign: "left" }}>{tc("category")}</th>
                <th style={{ textAlign: "right", width: 90 }}>Pax min</th>
                <th style={{ textAlign: "right", width: 90 }}>Pax max</th>
                <th style={{ textAlign: "right", width: 100 }}>{t("units")}</th>
                <th style={{ width: 40 }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id}>
                  <td className="mono" style={{ color: "var(--text-disabled)" }}>{i + 1}</td>
                  {/* El nombre se edita ACÁ. Antes era texto muerto con un
                      tooltip que mandaba a Master Data, pero esa pantalla nunca
                      se construyó: la regla no protegía nada, solo dejaba el
                      campo inalcanzable — una categoría nueva se quedaba
                      llamándose «Nueva categoría» para siempre. El CÓDIGO sí
                      queda fijo: es lo que liga el tipo con el revenue, las
                      tarifas y los actuals, y no depende del nombre. */}
                  <td style={{ fontWeight: 500 }}>
                    <span className="mono" style={{ color: "var(--text-disabled)", marginRight: 6 }}
                      title={t("fixedCode")}>
                      {r.code}
                    </span>
                    <EditCell value={r.name} onSave={v => save(r.id, { name: v.trim() || r.name })} />
                  </td>
                  <td><EditCell value={r.pax_min} type="number" align="right" onSave={v => save(r.id, { pax_min: parseInt(v) || 0 })} /></td>
                  <td><EditCell value={r.pax_max} type="number" align="right" onSave={v => save(r.id, { pax_max: parseInt(v) || 0 })} /></td>
                  <td><EditCell value={r.units} type="number" align="right" onSave={v => save(r.id, { units: parseInt(v) || 0 })} /></td>
                  <td style={{ textAlign: "center" }}>
                    <button
                      onClick={() => remove(r.id, r.name)}
                      aria-label={t("hideCategory")}
                      title={t("hideCategoryHint")}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-disabled)", fontSize: 15 }}
                    >×</button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td></td>
                <td style={{ textAlign: "left" }}>{tc("total")}</td>
                <td></td><td></td>
                <td className="mono" style={{ textAlign: "right" }}>{liveTotal}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>

          <div style={{ marginTop: 14 }}>
            <button onClick={addRow} disabled={busy} style={btnStyle(!busy)}>{t("addCategory")}</button>
          </div>
        </>
      )}
    </div>
  );
}
