"use client";
import { PacingShell } from "@/components/pacing/comun";
import { AnalisisMes } from "@/components/pacing/mes";

export default function PacingPage() {
  return <PacingShell tab="diciembre-2026"><AnalisisMes year={2026} month={12} /></PacingShell>;
}
