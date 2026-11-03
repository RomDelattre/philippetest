// Glisser-déposer du planning : déplacement / redimensionnement d'une barre (F-07)
// et dépose d'une vignette du tampon sur un technicien (R-03).
import {
  type CollisionDetection,
  type DragEndEvent,
  type DragMoveEvent,
  type DragStartEvent,
  PointerSensor,
  pointerWithin,
  rectIntersection,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Assignment, Vignette } from "../api";
import type { GridDrag } from "./Grid";
import { type DayInfo, type DragKind, dragResult, type Period, placementForDrop } from "./layout";

export const collision: CollisionDetection = (args) => {
  const hits = pointerWithin(args);
  return hits.length ? hits : rectIntersection(args);
};

type DragData = { kind: DragKind; assignmentId: string } | { kind: "new"; requestId: string };

export interface DropOfVignette {
  vignette: Vignette;
  technicianId: string;
  start: string;
  end: string;
  differsFromRequest: boolean;
  requestDatesIncomplete: boolean;
}

function laneTechnician(e: DragMoveEvent | DragEndEvent): string | undefined {
  const id = e.over?.id ? String(e.over.id) : "";
  return id.startsWith("lane:") ? id.slice(5) : undefined;
}

/** Jour sous le pointeur dans la ligne survolée. On lit la position réelle du pointeur et de la
 * ligne : les rectangles mémorisés par dnd-kit se décalent quand une zone défile pendant le glisser. */
function dayUnderPointer(
  e: DragMoveEvent | DragEndEvent,
  pointerX: number | null,
  technicianId: string,
  days: DayInfo[],
  dayWidth: number,
): string | undefined {
  const lane = document.querySelector<HTMLElement>(`[data-lane="${technicianId}"]`);
  const start = e.activatorEvent as PointerEvent | undefined;
  const x = pointerX ?? (start && typeof start.clientX === "number" ? start.clientX + e.delta.x : null);
  if (!lane || x === null) return undefined;
  const index = Math.floor((x - lane.getBoundingClientRect().left) / dayWidth);
  return days[Math.min(days.length - 1, Math.max(0, index))]?.iso;
}

export function usePlanningDnd(opts: {
  days: DayInfo[];
  dayWidth: number;
  assignments: Assignment[];
  vignettes: Vignette[];
  onMove: (assignment: Assignment, period: Period) => void;
  onDropVignette: (drop: DropOfVignette) => void;
}) {
  const { days, dayWidth } = opts;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));
  const [drag, setDrag] = useState<GridDrag | null>(null);
  const [activeVignette, setActiveVignette] = useState<Vignette | null>(null);
  const assignments = useMemo(() => new Map(opts.assignments.map((a) => [a.id, a])), [opts.assignments]);
  const vignettes = useMemo(() => new Map(opts.vignettes.map((v) => [v.id, v])), [opts.vignettes]);
  const pointerX = useRef<number | null>(null);
  useEffect(() => {
    const track = (ev: PointerEvent) => {
      pointerX.current = ev.clientX;
    };
    window.addEventListener("pointermove", track, { passive: true });
    return () => window.removeEventListener("pointermove", track);
  }, []);

  const compute = (e: DragMoveEvent | DragEndEvent) => {
    const data = e.active.data.current as DragData | undefined;
    if (!data) return null;
    if (data.kind === "new") {
      const v = vignettes.get(data.requestId);
      const tech = laneTechnician(e);
      const day = tech ? dayUnderPointer(e, pointerX.current, tech, days, dayWidth) : undefined;
      if (!v || !tech || !day) return null;
      const p = placementForDrop(v.start_date, v.end_date, day);
      return { kind: "new" as const, vignette: v, drop: { vignette: v, technicianId: tech, ...p } };
    }
    const a = assignments.get(data.assignmentId);
    if (!a) return null;
    const base = { technicianId: a.technician_id, start: a.start_date, end: a.end_date };
    const period = dragResult(data.kind, base, Math.round(e.delta.x / dayWidth), laneTechnician(e));
    return { kind: "existing" as const, assignment: a, period };
  };

  const handlers = {
    onDragStart: (e: DragStartEvent) => {
      const data = e.active.data.current as DragData | undefined;
      setActiveVignette(data?.kind === "new" ? (vignettes.get(data.requestId) ?? null) : null);
    },
    onDragMove: (e: DragMoveEvent) => {
      const r = compute(e);
      if (!r) return setDrag(null);
      setDrag(
        r.kind === "new"
          ? { sourceAssignmentId: null, preview: { technicianId: r.drop.technicianId, start: r.drop.start, end: r.drop.end } }
          : { sourceAssignmentId: r.assignment.id, preview: r.period },
      );
    },
    onDragCancel: () => {
      setDrag(null);
      setActiveVignette(null);
    },
    onDragEnd: (e: DragEndEvent) => {
      const r = compute(e);
      setDrag(null);
      setActiveVignette(null);
      if (!r) return;
      if (r.kind === "new") opts.onDropVignette(r.drop);
      else opts.onMove(r.assignment, r.period);
    },
  };

  return { sensors, handlers, drag, activeVignette };
}
