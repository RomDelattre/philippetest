import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import PlanningPage from "./planning/PlanningPage";

const mech = (id: string, name: string, order: number) => ({
  id, last_name: name, first_name: "", email: null, role: "mechanic", active: true, sort_order: order, version: 1,
});

const planning = {
  window_start: "2026-10-19",
  window_end: "2026-12-13",
  technicians: [
    mech("t1", "Technicien A", 0),
    mech("t2", "Technicien B", 1),
    { ...mech("e1", "Électronicien A", 0), role: "electronician" },
  ],
  assignments: [
    { id: "a1", request_id: "r1", technician_id: "t1", start_date: "2026-11-09", end_date: "2026-11-11",
      status: "accepted", partner_electronician_id: "e1", version: 3 },
    { id: "a2", request_id: "r2", technician_id: "t2", start_date: "2026-11-02", end_date: "2026-11-03",
      status: "draft", partner_electronician_id: null, version: 1 },
  ],
  requests: [
    { id: "r1", ref: "D-2026-0001", type_code: "MI", title: "Visite délégation", requester_name: "Chef A", cf: "CF1",
      client: "Client Alpha", location: "Herstal", start_date: "2026-11-09", end_date: "2026-11-11",
      technicians_needed: 1, status: "confirmed" },
    { id: "r2", ref: "D-2026-0002", type_code: "AT", title: "Atelier", requester_name: "Chef B", cf: null,
      client: "Client Bravo", location: null, start_date: "2026-11-02", end_date: "2026-11-03",
      technicians_needed: 1, status: "pending" },
  ],
  absences: [{ id: "ab1", technician_id: "t2", start_date: "2026-11-16", end_date: "2026-11-18", category: "leave", version: 1 }],
  holidays: [{ date: "2026-11-11", label: "Armistice" }],
};

const base: Record<string, unknown> = {
  "/api/health": { status: "ok", database: "ok", auth_mode: "dev" },
  "/api/me": { id: "1", email: "olivier@example.local", display_name: "Olivier", role: "planner" },
  "/api/planning": planning,
  "/api/mission-types": [
    { code: "MI", label: "Mission", color: "#2563eb", sort_order: 0 },
    { code: "AT", label: "Atelier", color: "#059669", sort_order: 2 },
  ],
};

function mockFetch(overrides: Record<string, { status: number; body: unknown }> = {}) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url.split("?")[0]}`;
    if (overrides[key]) return new Response(JSON.stringify(overrides[key].body), { status: overrides[key].status });
    return new Response(JSON.stringify(base[url.split("?")[0]] ?? {}), { status: 200 });
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("affiche l'utilisateur et le planning", async () => {
    vi.stubGlobal("fetch", mockFetch());
    render(<App />);
    expect(await screen.findByTestId("current-user")).toHaveTextContent("Olivier · Planificateur");
    expect(await screen.findByTestId("lane-t1")).toBeInTheDocument();
  });

  it("affiche un message clair si l'utilisateur n'est pas autorisé", async () => {
    vi.stubGlobal("fetch", mockFetch({ "GET /api/me": { status: 403, body: { detail: "refusé" } } }));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("pas autorisé");
  });
});

describe("PlanningPage", () => {
  it("affiche lignes, en-têtes, barres, absences et binôme (F-01, F-03, F-04, R-11)", async () => {
    vi.stubGlobal("fetch", mockFetch());
    render(<PlanningPage today="2026-11-04" />);
    expect(await screen.findByText("Électroniciens")).toBeInTheDocument();
    expect(screen.getByText("novembre 2026")).toBeInTheDocument();
    expect(screen.getByText("S46")).toBeInTheDocument();
    expect(screen.getByTestId("bar-a1")).toHaveTextContent("MI · Visite délégation · Herstal");
    expect(screen.getByTestId("bar-a2")).toHaveTextContent("✎ AT · Atelier");
    expect(screen.getByText("AB · Congé")).toBeInTheDocument();
    expect(screen.getByText("Binôme · D-2026-0001")).toBeInTheDocument();
    expect(screen.getByText(/du 19\/10\/2026 au 13\/12\/2026/)).toBeInTheDocument();
  });

  it("ouvre le panneau latéral au clic sur une barre (F-05)", async () => {
    vi.stubGlobal("fetch", mockFetch());
    render(<PlanningPage today="2026-11-04" />);
    fireEvent.click(within(await screen.findByTestId("bar-a1")).getByRole("button"));
    const panel = screen.getByRole("complementary", { name: "Détail de l'activité" });
    expect(panel).toHaveTextContent("Visite délégation");
    expect(panel).toHaveTextContent("Client Alpha");
    expect(panel).toHaveTextContent("Électronicien A");
  });

  it("filtre par recherche texte en estompant les autres barres (F-06)", async () => {
    vi.stubGlobal("fetch", mockFetch());
    render(<PlanningPage today="2026-11-04" />);
    await screen.findByTestId("bar-a1");
    fireEvent.change(screen.getByLabelText("Rechercher client, CF ou demandeur"), { target: { value: "bravo" } });
    expect(screen.getByTestId("bar-a1").className).toContain("opacity-25");
    expect(screen.getByTestId("bar-a2").className).not.toContain("opacity-25");
  });

  it("demande confirmation avant de déplacer une activité acceptée (F-07)", async () => {
    const fetchMock = mockFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<PlanningPage today="2026-11-04" />);
    fireEvent.click(within(await screen.findByTestId("bar-a1")).getByRole("button"));
    fireEvent.change(screen.getByLabelText("Fin"), { target: { value: "2026-11-13" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("13/11/2026");
    fireEvent.click(within(dialog).getByRole("button", { name: "Déplacer" }));
    await screen.findByText(/remise en brouillon/);
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({ version: 3, end_date: "2026-11-13", confirm: true });
  });

  it("crée une absence au clic sur une case vide (F-31)", async () => {
    const fetchMock = mockFetch({ "POST /api/absences": { status: 201, body: {} } });
    vi.stubGlobal("fetch", fetchMock);
    render(<PlanningPage today="2026-11-04" />);
    const lane = await screen.findByTestId("lane-t1");
    lane.getBoundingClientRect = () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.click(lane, { clientX: 28 * 15 + 5 }); // 16e jour de la fenêtre = 03/11/2026
    const dialog = await screen.findByRole("dialog", { name: "Nouvelle absence" });
    expect(within(dialog).getByLabelText("Date de début")).toHaveValue("2026-11-03");
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    await screen.findByText("Absence créée.");
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      technician_id: "t1", start_date: "2026-11-03", end_date: "2026-11-03", category: "leave",
    });
  });
});
