// Grille de planning : techniciens en lignes, jours en colonnes (F-01 à F-04).
// Le contexte de glisser-déposer (F-07, R-03) est fourni par PlanningPage via dnd.ts.
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { memo, type CSSProperties, type MouseEvent } from "react";
import type { Absence, Assignment, MissionType, RequestSummary, Technician } from "../api";
import { formatDate, WEEKDAY_INITIALS, weekdayIndex } from "../dates";
import {
  ABSENCE_LABELS,
  ASSIGNMENT_STATUS_LABELS,
  type DayInfo,
  type DragKind,
  type Filters,
  filtersActive,
  matchesFilters,
  monthSpans,
  NAME_WIDTH,
  type Period,
  placement,
  readableText,
  weekSpans,
} from "./layout";

const ROW_HEIGHT = 32;

export interface GridProps {
  days: DayInfo[];
  dayWidth: number;
  mechanics: Technician[];
  electronicians: Technician[];
  assignments: Assignment[];
  requests: Map<string, RequestSummary>;
  absences: Absence[];
  missionTypes: Map<string, MissionType>;
  filters: Filters;
  selectedId: string | null;
  onSelect: (assignmentId: string) => void;
  onAbsenceClick: (absence: Absence) => void;
  onEmptyClick: (technicianId: string, iso: string) => void;
  /** Aperçu du glisser-déposer en cours (déplacement d'une barre ou dépose d'une vignette). */
  drag: GridDrag | null;
}

export interface GridDrag {
  sourceAssignmentId: string | null;
  preview: Period;
}

export function techName(t: Technician): string {
  return [t.first_name, t.last_name].filter(Boolean).join(" ");
}

export default function Grid(props: GridProps) {
  const { days, dayWidth } = props;
  const windowStart = days[0].iso;
  const totalWidth = NAME_WIDTH + days.length * dayWidth;
  const columns = `repeat(${days.length}, ${dayWidth}px)`;

  return (
    <>
      <div className="relative" style={{ width: totalWidth }}>
        <Header days={days} dayWidth={dayWidth} columns={columns} />
        <div className="relative">
          <DayBackground days={days} columns={columns} />
          {props.mechanics.length === 0 && (
            <p className="sticky left-0 p-3 text-sm text-slate-500" style={{ width: NAME_WIDTH * 3 }}>
              Aucun technicien à afficher.
            </p>
          )}
          {props.mechanics.map((t) => (
            <Row key={t.id} tech={t} droppable {...props} windowStart={windowStart} columns={columns} />
          ))}
          {props.electronicians.length > 0 && (
            <>
              <div
                className="sticky left-0 z-20 border-y border-slate-300 bg-slate-100 px-2 py-1 text-xs font-semibold tracking-wide text-slate-600 uppercase"
                style={{ width: NAME_WIDTH }}
              >
                Électroniciens
              </div>
              {props.electronicians.map((t) => (
                <Row
                  key={t.id}
                  tech={t}
                  droppable={false}
                  {...props}
                  windowStart={windowStart}
                  columns={columns}
                />
              ))}
            </>
          )}
        </div>
      </div>
    </>
  );
}

// --------------------------------------------------------------------------- en-têtes

const Header = memo(function Header({ days, dayWidth, columns }: { days: DayInfo[]; dayWidth: number; columns: string }) {
  const months = monthSpans(days);
  const weeks = weekSpans(days);
  const showDays = dayWidth >= 20;
  const cell = "border-r border-slate-200 overflow-hidden whitespace-nowrap text-center";
  const corner = "sticky left-0 z-40 bg-white border-r border-slate-300";
  return (
    <div className="sticky top-0 z-30 border-b border-slate-300 bg-white text-xs select-none">
      <div className="flex">
        <div className={corner} style={{ width: NAME_WIDTH }} />
        <div className="grid" style={{ gridTemplateColumns: columns }}>
          {months.map((m) => (
            <div key={m.label} className={`${cell} px-1 py-0.5 text-left font-semibold capitalize`} style={{ gridColumn: `${m.start + 1} / span ${m.span}` }}>
              {m.label}
            </div>
          ))}
        </div>
      </div>
      <div className="flex border-t border-slate-100">
        <div className={`${corner} px-2 text-slate-500`} style={{ width: NAME_WIDTH }}>
          Technicien
        </div>
        <div className="grid" style={{ gridTemplateColumns: columns }}>
          {weeks.map((w) => (
            <div key={`${w.label}-${w.start}`} className={`${cell} text-slate-600`} style={{ gridColumn: `${w.start + 1} / span ${w.span}` }}>
              {w.span * dayWidth >= 26 ? w.label : ""}
            </div>
          ))}
        </div>
      </div>
      {showDays && (
        <div className="flex border-t border-slate-100">
          <div className={corner} style={{ width: NAME_WIDTH }} />
          <div className="grid" style={{ gridTemplateColumns: columns }}>
            {days.map((d) => (
              <div
                key={d.iso}
                title={d.holiday ? `${formatDate(d.iso)} – ${d.holiday}` : formatDate(d.iso)}
                className={`${cell} leading-tight tabular-nums ${d.today ? "bg-amber-200 font-bold" : d.weekend || d.holiday ? "bg-slate-200 text-slate-500" : ""}`}
              >
                {dayWidth >= 28 && <div className="text-[10px] text-slate-500">{WEEKDAY_INITIALS[weekdayIndex(d.iso)]}</div>}
                <div>{Number(d.iso.slice(8))}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

/** Fonds grisés des week-ends et fériés, surlignage du jour (F-04) : une seule couche pour toutes les lignes. */
const DayBackground = memo(function DayBackground({ days, columns }: { days: DayInfo[]; columns: string }) {
  return (
    <div className="pointer-events-none absolute inset-y-0 grid" style={{ left: NAME_WIDTH, gridTemplateColumns: columns }} aria-hidden>
      {days
        .filter((d) => d.weekend || d.holiday || d.today)
        .map((d) => (
          <div
            key={d.iso}
            style={{ gridColumn: d.index + 1, gridRow: 1 }}
            className={d.today ? "border-x border-amber-400 bg-amber-100/60" : d.holiday ? "bg-slate-300/50" : "bg-slate-200/60"}
          />
        ))}
    </div>
  );
});

// --------------------------------------------------------------------------- lignes

interface RowProps extends GridProps {
  tech: Technician;
  droppable: boolean;
  windowStart: string;
  columns: string;
}

function Row(p: RowProps) {
  const { tech, days, dayWidth, windowStart, columns, drag } = p;
  const { setNodeRef, isOver } = useDroppable({ id: `lane:${tech.id}`, disabled: !p.droppable });
  const n = days.length;
  const hasFilter = filtersActive(p.filters);

  const onLaneClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const index = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - rect.left) / dayWidth)));
    p.onEmptyClick(tech.id, days[index].iso);
  };

  const absences = p.absences.filter((a) => a.technician_id === tech.id);
  const own = p.assignments.filter((a) => a.technician_id === tech.id);
  const partnerOf = p.droppable ? [] : p.assignments.filter((a) => a.partner_electronician_id === tech.id);
  const ghost = drag && drag.preview.technicianId === tech.id ? placement(drag.preview.start, drag.preview.end, windowStart, n) : null;

  return (
    <div className="flex border-b border-slate-200" style={{ height: ROW_HEIGHT }}>
      <div
        className="sticky left-0 z-20 flex items-center truncate border-r border-slate-300 bg-white px-2 text-sm"
        style={{ width: NAME_WIDTH, minWidth: NAME_WIDTH }}
        title={techName(tech)}
      >
        {techName(tech)}
      </div>
      <div
        ref={setNodeRef}
        onClick={onLaneClick}
        data-testid={`lane-${tech.id}`}
        data-lane={tech.id}
        className={`relative grid cursor-cell ${isOver ? "bg-sky-50/70" : ""}`}
        style={{ gridTemplateColumns: columns, gridTemplateRows: "1fr" }}
      >
        {absences.map((ab) => {
          const pos = placement(ab.start_date, ab.end_date, windowStart, n);
          if (!pos) return null;
          return (
            <button
              key={ab.id}
              type="button"
              onClick={() => p.onAbsenceClick(ab)}
              title={`Absence – ${ABSENCE_LABELS[ab.category]} – du ${formatDate(ab.start_date)} au ${formatDate(ab.end_date)}`}
              className="z-[5] my-1 flex items-center overflow-hidden rounded-sm border border-slate-500 bg-slate-400 px-1 text-left text-xs whitespace-nowrap text-white"
              style={{ gridColumn: `${pos.column} / span ${pos.span}`, gridRow: 1 }}
            >
              AB · {ABSENCE_LABELS[ab.category]}
            </button>
          );
        })}
        {own.map((a) => {
          const pos = placement(a.start_date, a.end_date, windowStart, n);
          if (!pos) return null;
          const req = p.requests.get(a.request_id);
          return (
            <Bar
              key={a.id}
              assignment={a}
              request={req}
              pos={pos}
              type={req?.type_code ? p.missionTypes.get(req.type_code) : undefined}
              dimmed={hasFilter && !matchesFilters(a, req, p.filters)}
              selected={p.selectedId === a.id}
              dragging={drag?.sourceAssignmentId === a.id}
              onSelect={p.onSelect}
            />
          );
        })}
        {partnerOf.map((a) => {
          const pos = placement(a.start_date, a.end_date, windowStart, n);
          const req = p.requests.get(a.request_id);
          if (!pos) return null;
          return (
            <button
              key={`partner-${a.id}`}
              type="button"
              onClick={() => p.onSelect(a.id)}
              title="Binôme (information seulement, R-11)"
              className="z-[6] my-1.5 overflow-hidden rounded-sm border border-dashed border-slate-500 bg-white/80 px-1 text-left text-xs whitespace-nowrap text-slate-700"
              style={{ gridColumn: `${pos.column} / span ${pos.span}`, gridRow: 1 }}
            >
              Binôme · {req?.ref ?? ""}
            </button>
          );
        })}
        {ghost && (
          <div
            data-testid="drag-preview"
            className="pointer-events-none z-[15] my-0.5 rounded border-2 border-dashed border-sky-600 bg-sky-200/50"
            style={{ gridColumn: `${ghost.column} / span ${ghost.span}`, gridRow: 1 }}
          />
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- barres (F-03)

interface BarProps {
  assignment: Assignment;
  request: RequestSummary | undefined;
  pos: { column: number; span: number; clippedStart: boolean; clippedEnd: boolean };
  type: MissionType | undefined;
  dimmed: boolean;
  selected: boolean;
  dragging: boolean;
  onSelect: (id: string) => void;
}

function barStyle(a: Assignment, color: string): CSSProperties {
  const text = readableText(color);
  if (a.status === "accepted") return { backgroundColor: color, color: text, borderColor: color };
  if (a.status === "pending_response")
    // hachures : la couleur n'est pas le seul porteur d'information (section 11)
    return {
      backgroundImage: `repeating-linear-gradient(135deg, ${color} 0 6px, ${color}99 6px 12px)`,
      color: text,
      borderColor: color,
    };
  return { backgroundColor: "#ffffff", color: "#111827", borderColor: color, borderStyle: "dashed" };
}

function Handle({ id, side, assignmentId }: { id: string; side: "start" | "end"; assignmentId: string }) {
  const kind: DragKind = side === "start" ? "resize-start" : "resize-end";
  // Poignée souris uniquement : l'alternative clavier est le formulaire du panneau latéral (F-05).
  const { setNodeRef, listeners } = useDraggable({ id: `${kind}:${id}`, data: { kind, assignmentId } });
  return (
    <span
      ref={setNodeRef}
      {...listeners}
      aria-hidden
      title={side === "start" ? "Modifier la date de début" : "Modifier la date de fin"}
      className={`absolute inset-y-0 z-10 w-1.5 cursor-ew-resize hover:bg-black/20 ${side === "start" ? "left-0" : "right-0"}`}
    />
  );
}

function Bar({ assignment: a, request, pos, type, dimmed, selected, dragging, onSelect }: BarProps) {
  const { setNodeRef, listeners, attributes } = useDraggable({ id: `move:${a.id}`, data: { kind: "move", assignmentId: a.id } });
  const color = type?.color ?? "#64748b";
  const code = request?.type_code ?? "?";
  const label = [code, request?.title, request?.location].filter(Boolean).join(" · ");
  const tooltip = [
    `${request?.ref ?? ""} – ${label}`,
    `Du ${formatDate(a.start_date)} au ${formatDate(a.end_date)}`,
    ASSIGNMENT_STATUS_LABELS[a.status],
  ].join("\n");
  return (
    <div
      data-testid={`bar-${a.id}`}
      className={`relative z-10 my-1 rounded-sm border text-xs ${dimmed ? "opacity-25" : ""} ${dragging ? "opacity-50" : ""} ${selected ? "ring-2 ring-sky-600 ring-offset-1" : ""} ${pos.clippedStart ? "rounded-l-none" : ""} ${pos.clippedEnd ? "rounded-r-none" : ""}`}
      style={{ gridColumn: `${pos.column} / span ${pos.span}`, gridRow: 1, ...barStyle(a, color) }}
      title={tooltip}
    >
      {!pos.clippedStart && <Handle id={a.id} side="start" assignmentId={a.id} />}
      <button
        ref={setNodeRef}
        type="button"
        {...listeners}
        {...attributes}
        onClick={() => onSelect(a.id)}
        aria-label={`${request?.ref ?? "Activité"} : ${label}, ${ASSIGNMENT_STATUS_LABELS[a.status]}`}
        className="block h-full w-full cursor-grab overflow-hidden px-1.5 text-left font-medium whitespace-nowrap active:cursor-grabbing"
      >
        {a.status === "draft" && "✎ "}
        {label}
      </button>
      {!pos.clippedEnd && <Handle id={a.id} side="end" assignmentId={a.id} />}
    </div>
  );
}
