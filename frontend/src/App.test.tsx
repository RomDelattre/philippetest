import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const responses: Record<string, unknown> = {
  "/api/health": { status: "ok", database: "ok", auth_mode: "dev" },
  "/api/me": { id: "1", email: "olivier@example.local", display_name: "Olivier", role: "planner" },
  "/api/technicians": [
    { id: "t1", last_name: "Technicien A", first_name: "", email: null, role: "mechanic", active: true, sort_order: 0, version: 1 },
    { id: "t2", last_name: "Électronicien A", first_name: "", email: null, role: "electronician", active: true, sort_order: 0, version: 1 },
  ],
  "/api/mission-types": [{ code: "MI", label: "Mission", color: "#2563eb", sort_order: 0 }],
  "/api/holidays": [{ date: "2026-11-11", label: "Armistice" }],
};

function mockFetch(status = 200) {
  return vi.fn(async (url: string) => {
    const key = url.split("?")[0];
    return new Response(JSON.stringify(status === 200 ? responses[key] : { detail: "refusé" }), { status });
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("affiche l'utilisateur, les référentiels et les dates au format JJ/MM/AAAA", async () => {
    vi.stubGlobal("fetch", mockFetch());
    render(<App />);
    expect(await screen.findByTestId("current-user")).toHaveTextContent("Olivier · Planificateur");
    expect(screen.getByText("Technicien A")).toBeInTheDocument();
    expect(screen.getByText("Mécaniciens (1)")).toBeInTheDocument();
    expect(screen.getByText("11/11/2026")).toBeInTheDocument();
  });

  it("affiche un message clair si l'utilisateur n'est pas autorisé", async () => {
    vi.stubGlobal("fetch", mockFetch(403));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("pas autorisé");
  });
});
