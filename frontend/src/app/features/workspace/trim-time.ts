/** Longitud mínima del fragmento recortado (igual que el backend). */
export const MIN_TRIM_SECONDS = 0.5;

/** "1:05.5", "0:01:05.5" o "65.5" → segundos; null si no es un tiempo válido. */
export function parseTrimTime(value: string): number | null {
  const parts = value.trim().replace(',', '.').split(':');
  if (!parts.length || parts.length > 3 || parts.some((part) => !/^\d+(\.\d+)?$/.test(part))) {
    return null;
  }
  return parts.reduce((total, part) => total * 60 + Number(part), 0);
}

/** Segundos → "m:ss.s" (o "h:mm:ss.s"). */
export function formatTrimTime(seconds: number): string {
  const tenths = Math.round(Math.max(seconds, 0) * 10);
  const hours = Math.floor(tenths / 36000);
  const minutes = Math.floor((tenths % 36000) / 600);
  const secs = ((tenths % 600) / 10).toFixed(1).padStart(4, '0');
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${secs}` : `${minutes}:${secs}`;
}

/** Ajusta el rango al video: inicio dentro, fin tras el inicio y al menos MIN_TRIM_SECONDS. */
export function clampTrim(
  start: number,
  end: number,
  duration: number,
): { start: number; end: number } {
  const limit = duration > 0 ? duration : Math.max(end, start + MIN_TRIM_SECONDS);
  const safeStart = Math.min(Math.max(start, 0), Math.max(limit - MIN_TRIM_SECONDS, 0));
  const safeEnd = Math.min(Math.max(end, safeStart + MIN_TRIM_SECONDS), limit);
  return { start: round(safeStart), end: round(safeEnd) };
}

function round(value: number): number {
  return Math.round(value * 1000) / 1000;
}
