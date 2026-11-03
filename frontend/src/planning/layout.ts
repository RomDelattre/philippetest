// Calculs purs de la grille de planning (F-01 à F-04, F-06, F-07). Aucune dépendance React.

import type { Absence, Assignment, AssignmentStatus, Holiday, RequestSummary } from "../api";
import { addDays, diffDays, isoWeek, isWeekend, mondayOf, monthLabel } from "../dates";

export type Zoom = "4w" | "8w" | "12w" | "6m";

export const ZOOMS: Record<Zoom, { label: string; weeks: number; dayWidth: number }> = {
  "4w": { label: "4 semaines", weeks: 4, dayWidth: 40 },
  "8w": { label: "8 semaines", weeks: 8, dayWidth: 28 },
  "12w": { label: "12 semaines", weeks: 12, dayWidth: 20 },
  "6m": { label: "6 mois", weeks: 26, dayWidth: 10 },
};

export const NAME_WIDTH = 170;

/** F-02 : fenêtre glissante autour de la date d'ancrage (par défaut aujourd'hui). */
export function windowFor(anchor: string, zoom: Zoom): { start: string; end: string; days: number } {
  const weeks = ZOOMS[zoom].weeks;
  const start = addDays(mondayOf(anchor), -7 * Math.floor(weeks / 4));
  const days = weeks * 7;
  return { start, end: addDays(start, days - 1), days };
}

export interface DayInfo {
  iso: string;
  index: number;
  weekend: boolean;
  holiday: string | null;
  today: boolean;
}

export function buildDays(start: string, days: number, holidays: Holiday[], today: string): DayInfo[] {
  const hol = new Map(holidays.map((h) => [h.date, h.label]));
  return Array.from({ length: days }, (_, index) => {
    const iso = addDays(start, index);
    return { iso, index, weekend: isWeekend(iso), holiday: hol.get(iso) ?? null, today: iso === today };
  });
}

export interface HeaderSpan {
  label: string;
  start: number; // index du premier jour
  span: number;
}

function spans(days: DayInfo[], key: (iso: string) => string): HeaderSpan[] {
  const out: HeaderSpan[] = [];
  for (const d of days) {
    const label = key(d.iso);
    const last = out[out.length - 1];
    if (last && last.label === label) last.span += 1;
    else out.push({ label, start: d.index, span: 1 });
  }
  return out;
}

export const monthSpans = (days: DayInfo[]) => spans(days, monthLabel);
export const weekSpans = (days: DayInfo[]) => spans(days, (iso) => `S${isoWeek(iso)}`);

/** Position d'une période dans la fenêtre, ou null si elle est hors fenêtre. Colonnes à partir de 1. */
export function placement(
  start: string,
  end: string,
  windowStart: string,
  days: number,
): { column: number; span: number; clippedStart: boolean; clippedEnd: boolean } | null {
  const first = diffDays(windowStart, start);
  const last = diffDays(windowStart, end);
  if (last < 0 || first > days - 1) return null;
  const from = Math.max(first, 0);
  const to = Math.min(last, days - 1);
  return { column: from + 1, span: to - from + 1, clippedStart: first < 0, clippedEnd: last > days - 1 };
}

// --------------------------------------------------------------------------- glisser-déposer (F-07)

export type DragKind = "move" | "resize-start" | "resize-end";

export interface Period {
  technicianId: string;
  start: string;
  end: string;
}

/** Période résultant d'un glissement de `dayDelta` jours. Une période garde toujours fin ≥ début. */
export function dragResult(kind: DragKind, a: Period, dayDelta: number, targetTechnicianId?: string): Period {
  if (kind === "move") {
    return {
      technicianId: targetTechnicianId ?? a.technicianId,
      start: addDays(a.start, dayDelta),
      end: addDays(a.end, dayDelta),
    };
  }
  if (kind === "resize-start") {
    const start = addDays(a.start, dayDelta);
    return { ...a, start: diffDays(start, a.end) < 0 ? a.end : start };
  }
  const end = addDays(a.end, dayDelta);
  return { ...a, end: diffDays(a.start, end) < 0 ? a.start : end };
}

export function samePeriod(a: Period, b: Period): boolean {
  return a.technicianId === b.technicianId && a.start === b.start && a.end === b.end;
}

/** F-07 : un déplacement d'activité déjà envoyée au technicien demande une confirmation. */
export function needsConfirmation(status: AssignmentStatus): boolean {
  return status === "pending_response" || status === "accepted";
}

// --------------------------------------------------------------------------- filtres (F-06)

export interface Filters {
  technicianId: string;
  typeCode: string;
  status: "" | AssignmentStatus;
  requestId: string;
  text: string;
}

export const EMPTY_FILTERS: Filters = { technicianId: "", typeCode: "", status: "", requestId: "", text: "" };

function norm(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function matchesFilters(a: Assignment, req: RequestSummary | undefined, f: Filters): boolean {
  if (f.typeCode && (req?.type_code ?? "") !== f.typeCode) return false;
  if (f.status && a.status !== f.status) return false;
  if (f.requestId && a.request_id !== f.requestId) return false;
  if (f.text.trim()) {
    const hay = norm([req?.client, req?.cf, req?.requester_name].filter(Boolean).join(" "));
    if (!hay.includes(norm(f.text.trim()))) return false;
  }
  return true;
}

export function filtersActive(f: Filters): boolean {
  return Boolean(f.typeCode || f.status || f.requestId || f.text.trim());
}

// --------------------------------------------------------------------------- affichage

/** Couleur de texte lisible sur un fond donné (contraste, section 11). */
export function readableText(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return "#111827";
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.4 ? "#111827" : "#ffffff";
}

export const ABSENCE_LABELS: Record<Absence["category"], string> = {
  leave: "Congé",
  sick: "Maladie",
  recovery: "Récupération",
  other: "Autre",
};

export const ASSIGNMENT_STATUS_LABELS: Record<AssignmentStatus, string> = {
  draft: "Brouillon",
  pending_response: "En attente de réponse",
  accepted: "Accepté",
  refused: "Refusé",
  cancelled: "Annulé",
};
