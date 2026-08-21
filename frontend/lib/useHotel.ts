"use client";
import { useEffect, useState } from "react";
import { HOTEL_ID, hotelName, hotelShort, cargarHotel, refrescarHotel } from "./hotel";

/**
 * El nombre visible de la propiedad, para las pantallas.
 *
 * Va en un archivo aparte de `lib/hotel.ts` a propósito: ese lo importa
 * `app/layout.tsx`, que es un componente de SERVIDOR, y meterle un hook de React
 * lo rompería.
 *
 * Devuelve el valor de arranque en el primer render y se actualiza cuando llega
 * la respuesta del backend. `cargarHotel()` se pide una vez por sesión de
 * navegador, así que montar este hook en veinte pantallas no son veinte
 * llamadas.
 */

// Quién está montado y quiere enterarse de un cambio de nombre. Sin esto, el
// nombre nuevo no aparece en la barra hasta recargar la página — y eso se lee
// como «no guardó», que fue exactamente lo que pasó al probarlo.
const suscriptores = new Set<() => void>();

function avisar() { suscriptores.forEach(f => f()); }

/** Guarda y avisa. La usa Provisionamiento después de un guardado exitoso. */
export async function recargarNombreHotel(): Promise<void> {
  await refrescarHotel();
  avisar();
}

export function useHotel() {
  const [, setTick] = useState(0);
  const [nombre, setNombre] = useState(hotelName());
  const [corto, setCorto] = useState(hotelShort());

  useEffect(() => {
    let vivo = true;
    const sincronizar = () => {
      if (!vivo) return;
      setNombre(hotelName());
      setCorto(hotelShort());
      setTick(t => t + 1);
    };
    suscriptores.add(sincronizar);
    cargarHotel().then(sincronizar);
    return () => { vivo = false; suscriptores.delete(sincronizar); };
  }, []);

  return { id: HOTEL_ID, nombre, corto };
}
