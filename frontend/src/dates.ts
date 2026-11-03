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
