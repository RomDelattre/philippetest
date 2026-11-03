// Conventions : dates JJ/MM/AAAA, semaine commençant le lundi, fuseau Europe/Brussels (section 5).
// Les dates métier circulent en chaînes ISO « AAAA-MM-JJ » (journées entières, P4).

export function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

/** Numéro de semaine ISO 8601. */
export function isoWeek(iso: string): number {
  const date = parseIsoDate(iso);
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = Date.UTC(date.getUTCFullYear(), 0, 1);
  return Math.ceil(((date.getTime() - yearStart) / 86400000 + 1) / 7);
}

/** Nombre de jours d'une période incluse (calculé, jamais stocké : R-03). */
export function periodDays(startIso: string, endIso: string): number {
  return Math.round((parseIsoDate(endIso).getTime() - parseIsoDate(startIso).getTime()) / 86400000) + 1;
}

const DAY_MS = 86400000;

export function toIso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function addDays(iso: string, n: number): string {
  return toIso(new Date(parseIsoDate(iso).getTime() + n * DAY_MS));
}

/** b - a en jours. */
export function diffDays(a: string, b: string): number {
  return Math.round((parseIsoDate(b).getTime() - parseIsoDate(a).getTime()) / DAY_MS);
}

export function mondayOf(iso: string): string {
  const day = parseIsoDate(iso).getUTCDay() || 7;
  return addDays(iso, 1 - day);
}

/** 0 = lundi … 6 = dimanche */
export function weekdayIndex(iso: string): number {
  return (parseIsoDate(iso).getUTCDay() + 6) % 7;
}

export function isWeekend(iso: string): boolean {
  return weekdayIndex(iso) >= 5;
}

export function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Brussels" }).format(new Date());
}

const MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
  "octobre", "novembre", "décembre"];
export function monthLabel(iso: string): string {
  const [y, m] = iso.split("-");
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

export const WEEKDAY_INITIALS = ["L", "M", "M", "J", "V", "S", "D"];
