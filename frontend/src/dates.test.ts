import { describe, expect, it } from "vitest";
import { formatDate, isoWeek, periodDays } from "./dates";

describe("dates", () => {
  it("formate en JJ/MM/AAAA", () => expect(formatDate("2026-11-03")).toBe("03/11/2026"));
  it("calcule la semaine ISO", () => {
    expect(isoWeek("2026-11-03")).toBe(45);
    expect(isoWeek("2027-01-01")).toBe(53);
    expect(isoWeek("2026-01-01")).toBe(1);
  });
  it("compte les jours d'une période incluse", () => {
    expect(periodDays("2026-11-03", "2026-11-03")).toBe(1);
    expect(periodDays("2026-10-24", "2026-10-26")).toBe(3); // passage à l'heure d'hiver
  });
});
