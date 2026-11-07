/**
 * El Budget Package para el Excel en vivo.
 *
 * Owner, 2026-11-06: *«automatiza este [Budget Package] de una, así como
 * está… cada tab»*. El libro de Excel lo pide con Power Query cada vez que se
 * aprieta «Actualizar todo», y recibe la grilla de las veintitrés hojas —valor
 * y estilo por celda— para volver a pintarlas.
 *
 *   GET /api/paquete?listar=1
 *       → las versiones que se pueden elegir (para las listas del Excel)
 *   GET /api/paquete?principal=…&comparar=…,…&meses_de=0&compacto=1
 *       → la grilla del paquete
 *
 * Las versiones se piden por id o por rótulo («2027 · BUDGET Working», el mismo
 * que muestran los selectores de la pantalla).
 *
 * ⚠️ **Arma con `armarPaquete`, el MISMO armador del botón** «Budget Package»
 * de `app/planning/report`, y la grilla la hace el MISMO exportador del backend
 * (`/export/cuadros/grilla/` llama a `build_cuadros_workbook`). El Excel que se
 * refresca y el que se baja con el botón no pueden decir cosas distintas.
 *
 * ⚠️ **La llave (`x-paquete-key`) abre la plantilla con sueldos por posición.**
 * Es otra llave que la del consolidado, a propósito (ver `PAQUETE_API_KEY` en
 * `backend/app/auth.py`). Sin la variable de entorno la ruta no abre a nadie.
 */
import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

import { api, fijarCabecerasDeServidor, getScenarios, type Scenario } from "@/lib/api";
import { armarPaquete, extrasDe } from "@/lib/budgetPackage";
import { HOTEL_ID } from "@/lib/hotel";

export const dynamic = "force-dynamic";

const rotulo = (s: Scenario) => `${s.year} · ${s.type} ${s.version}`;

function llaveValida(recibida: string): boolean {
  const esperada = (process.env.PAQUETE_API_KEY ?? "").trim();
  const r = Buffer.from(recibida.trim());
  const e = Buffer.from(esperada);
  // Comparación en tiempo constante: con `===` se puede adivinar la llave
  // midiendo cuánto tarda en contestar.
  return esperada.length > 0 && r.length === e.length && timingSafeEqual(r, e);
}

function error(status: number, detail: string) {
  return NextResponse.json({ detail }, { status });
}

export async function GET(req: NextRequest) {
  const llave = req.headers.get("x-paquete-key") ?? "";
  if (!llaveValida(llave)) return error(401, "No autenticado");
  // El backend vuelve a comprobar la misma llave, ruta por ruta.
  fijarCabecerasDeServidor({ "x-paquete-key": llave.trim() });

  const p = req.nextUrl.searchParams;
  let escenarios: Scenario[];
  try {
    escenarios = await getScenarios(HOTEL_ID);
  } catch (e) {
    return error(502, `No se pudo leer la lista de versiones: ${(e as Error).message}`);
  }

  if (p.get("listar")) {
    return NextResponse.json({
      escenarios: escenarios.map(s => ({
        id: s.id, rotulo: rotulo(s), year: s.year, tipo: s.type,
        version: s.version, status: s.status,
      })),
    });
  }

  const buscar = (v: string | null): Scenario | undefined => {
    const t = (v ?? "").trim();
    return t ? escenarios.find(s => s.id === t || rotulo(s) === t) : undefined;
  };
  const principal = buscar(p.get("principal"));
  if (!principal) return error(404, `No existe la versión «${p.get("principal") ?? ""}»`);
  const pedidas = (p.get("comparar") ?? "").split(",").map(x => x.trim()).filter(Boolean);
  const otros: string[] = [];
  for (const x of pedidas) {
    const s = buscar(x);
    if (!s) return error(404, `No existe la versión «${x}»`);
    if (s.id !== principal.id && !otros.includes(s.id)) otros.push(s.id);
  }
  const ids = [principal.id, ...otros];
  const mesesDe = Math.min(Math.max(0, Number(p.get("meses_de") ?? 0) || 0), ids.length - 1);
  const compacto = p.get("compacto") !== "0";

  const fallas: string[] = [];
  const cuadros = await armarPaquete({
    principal: principal.id, otros, escenarios,
    op: { compacto, ambito: "consolidado", mesesDe, extras: extrasDe(ids, mesesDe) },
  }, r => fallas.push(r));
  if (!cuadros.length) return error(502, "No se pudo armar ninguna hoja del paquete");

  const grilla = await api.post<Record<string, unknown>>(
    "/export/cuadros/grilla/", { archivo: "Budget_Package", cuadros });
  return NextResponse.json({
    ...grilla,
    versiones: ids.map(id => rotulo(escenarios.find(s => s.id === id)!)),
    meses_de: mesesDe,
    fallas,
  });
}
