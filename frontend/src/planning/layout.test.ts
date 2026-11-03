import { describe, expect, it } from "vitest";
import type { Assignment, RequestSummary } from "../api";
import {
  buildDays,
  dragResult,
  EMPTY_FILTERS,
  matchesFilters,
  monthSpans,
  needsConfirmation,
  placement,
  readableText,
  weekSpans,
  windowFor,
} from "./layout";

describe("fenêtre (F-02)", () => {
  it("8 semaines démarrant le lundi, 2 semaines avant aujourd'hui", () => {
    expect(windowFor("2026-11-04", "8w")).toEqual({ start: "2026-10-19", end: "2026-12-13", days: 56 });
  });
  it("6 mois = 26 semaines", () => {
    expect(windowFor("2026-11-04", "6m").days).toBe(182);
  });
});

describe("en-têtes (F-01)", () => {
  const days = buildDays("2026-10-26", 14, [{ date: "2026-11-01", label: "Toussaint" }], "2026-10-28");
  it("marque week-ends, fériés et aujourd'hui (F-04)", () => {
    expect(days[5].weekend).toBe(true);
    expect(days[6].holiday).toBe("Toussaint");
    expect(days[2].today).toBe(true);
  });
  it("regroupe les mois et les semaines ISO", () => {
    expect(monthSpans(days)).toEqual([
      { label: "octobre 2026", start: 0, span: 6 },
      { label: "novembre 2026", start: 6, span: 8 },
    ]);
    expect(weekSpans(days).map((w) => w.label)).toEqual(["S44", "S45"]);
  });
});

describe("placement", () => {
  it("place une période entière", () => {
    expect(placement("2026-11-02", "2026-11-04", "2026-11-02", 28)).toEqual({
      column: 1,
      span: 3,
      clippedStart: false,
      clippedEnd: false,
    });
  });
  it("coupe aux bords de la fenêtre", () => {
    expect(placement("2026-10-30", "2026-11-03", "2026-11-02", 28)).toMatchObject({
      column: 1,
      span: 2,
      clippedStart: true,
    });
    expect(placement("2026-11-28", "2026-12-05", "2026-11-02", 28)).toMatchObject({
      column: 27,
      span: 2,
      clippedEnd: true,
    });
  });
  it("ignore une période hors fenêtre", () => {
    expect(placement("2026-12-01", "2026-12-02", "2026-11-02", 28)).toBeNull();
  });
});

describe("glisser-déposer (F-07)", () => {
  const p = { technicianId: "a", start: "2026-11-09", end: "2026-11-11" };
  it("déplace en gardant la durée, éventuellement sur un autre technicien", () => {
    expect(dragResult("move", p, 7, "b")).toEqual({ technicianId: "b", start: "2026-11-16", end: "2026-11-18" });
  });
  it("redimensionne sans jamais inverser la période", () => {
    expect(dragResult("resize-end", p, 2).end).toBe("2026-11-13");
    expect(dragResult("resize-end", p, -5)).toMatchObject({ start: "2026-11-09", end: "2026-11-09" });
    expect(dragResult("resize-start", p, -1).start).toBe("2026-11-08");
    expect(dragResult("resize-start", p, 9)).toMatchObject({ start: "2026-11-11", end: "2026-11-11" });
  });
  it("demande confirmation pour une activité déjà envoyée", () => {
    expect(needsConfirmation("accepted")).toBe(true);
    expect(needsConfirmation("pending_response")).toBe(true);
    expect(needsConfirmation("draft")).toBe(false);
  });
});

describe("filtres (F-06)", () => {
  const a = { id: "1", request_id: "r", status: "accepted" } as Assignment;
  const r = { id: "r", type_code: "MI", client: "Société Générale", cf: "CF123", requester_name: "Chef A" } as RequestSummary;
  it("filtre par type, statut, demande et texte (sans accents)", () => {
    expect(matchesFilters(a, r, EMPTY_FILTERS)).toBe(true);
    expect(matchesFilters(a, r, { ...EMPTY_FILTERS, typeCode: "SD" })).toBe(false);
    expect(matchesFilters(a, r, { ...EMPTY_FILTERS, status: "pending_response" })).toBe(false);
    expect(matchesFilters(a, r, { ...EMPTY_FILTERS, requestId: "x" })).toBe(false);
    expect(matchesFilters(a, r, { ...EMPTY_FILTERS, text: "generale" })).toBe(true);
    expect(matchesFilters(a, r, { ...EMPTY_FILTERS, text: "cf123" })).toBe(true);
    expect(matchesFilters(a, r, { ...EMPTY_FILTERS, text: "inconnu" })).toBe(false);
  });
});

describe("contraste", () => {
  it("texte blanc sur fond foncé, sombre sur fond clair", () => {
    expect(readableText("#2563eb")).toBe("#ffffff");
    expect(readableText("#fde68a")).toBe("#111827");
  });
});

import { placementForDrop } from "./layout";

describe("dépose d'une vignette (R-03)", () => {
  it("colle aux dates de la demande quand on dépose dans sa période", () => {
    expect(placementForDrop("2026-11-09", "2026-11-13", "2026-11-11")).toEqual({
      start: "2026-11-09", end: "2026-11-13", differsFromRequest: false, requestDatesIncomplete: false,
    });
  });
  it("décale en gardant la durée hors période", () => {
    expect(placementForDrop("2026-11-09", "2026-11-13", "2026-11-23")).toMatchObject({
      start: "2026-11-23", end: "2026-11-27", differsFromRequest: true,
    });
  });
  it("crée un jour unique pour une demande sans dates", () => {
    expect(placementForDrop(null, null, "2026-11-23")).toMatchObject({
      start: "2026-11-23", end: "2026-11-23", requestDatesIncomplete: true,
    });
  });
});
