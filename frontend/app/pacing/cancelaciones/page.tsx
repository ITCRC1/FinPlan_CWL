"use client";
import { PacingShell } from "@/components/pacing/comun";
import { Cancelaciones } from "@/components/pacing/vistas";

export default function PacingPage() {
  return <PacingShell tab="cancelaciones"><Cancelaciones /></PacingShell>;
}
