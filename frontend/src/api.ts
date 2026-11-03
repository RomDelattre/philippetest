export const DEV_USER_KEY = "planning-ats.dev-user";
export const DEV_USER_HEADER = "X-Dev-User";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function devUser(): string | null {
  try {
    return localStorage.getItem(DEV_USER_KEY);
  } catch {
    return null;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const user = devUser();
  if (user) headers.set(DEV_USER_HEADER, user); // ignoré par l'API hors mode dev
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail: string = res.statusText;
    try {
      const raw = (await res.json()).detail;
      if (Array.isArray(raw)) detail = raw.map((d) => String(d.msg ?? d)).join(" ; ");
      else if (raw) detail = String(raw);
    } catch {
      /* corps non JSON */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function sendJson<T>(method: "POST" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  return api<T>(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export type Role = "admin" | "planner";
export interface Me {
  id: string;
  email: string;
  display_name: string;
  role: Role;
}
export interface Health {
  status: string;
  database: string;
  auth_mode: "dev" | "proxy" | "oidc";
}
export interface Technician {
  id: string;
  last_name: string;
  first_name: string;
  email: string | null;
  role: "mechanic" | "electronician";
  active: boolean;
  sort_order: number;
  version: number;
}
export interface MissionType {
  code: string;
  label: string;
  color: string;
  sort_order: number;
}
export interface Holiday {
  date: string;
  label: string;
}

export type AssignmentStatus = "draft" | "pending_response" | "accepted" | "refused" | "cancelled";
export type RequestStatus = "to_assign" | "partially_assigned" | "pending" | "confirmed" | "cancelled";
export type AbsenceCategory = "leave" | "sick" | "recovery" | "other";

export interface RequestSummary {
  id: string;
  ref: string;
  type_code: string | null;
  title: string;
  requester_name: string | null;
  cf: string | null;
  client: string | null;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  technicians_needed: number;
  status: RequestStatus;
}
export interface Assignment {
  id: string;
  request_id: string;
  technician_id: string;
  start_date: string;
  end_date: string;
  status: AssignmentStatus;
  partner_electronician_id: string | null;
  version: number;
}
export interface Absence {
  id: string;
  technician_id: string;
  start_date: string;
  end_date: string;
  category: AbsenceCategory;
  version: number;
}
export interface Planning {
  window_start: string;
  window_end: string;
  technicians: Technician[];
  assignments: Assignment[];
  requests: RequestSummary[];
  absences: Absence[];
  holidays: Holiday[];
}

export type ChangeKind = "modification" | "cancellation";

export interface Vignette {
  id: string;
  ref: string;
  type_code: string | null;
  title: string;
  requester_name: string | null;
  client: string | null;
  cf: string | null;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  technicians_needed: number;
  remaining: number;
  status: RequestStatus;
  needs_review: boolean;
  missing_fields: string[];
  badges: string[];
  pending_changes: ChangeKind[];
  origin: "mail" | "teams" | "sharepoint" | "manual";
  date_flexible: boolean;
  version: number;
}

export interface ProductLine {
  product: string;
  ammunition: string | null;
  comment: string | null;
}

/** Champs éditables d'une demande (F-12, F-14). */
export interface RequestFields {
  type_code: string | null;
  title: string;
  requester_name: string | null;
  requester_email: string | null;
  cf: string | null;
  client: string | null;
  location: string | null;
  objective: string | null;
  technicians_needed: number;
  start_date: string | null;
  end_date: string | null;
  date_flexible: boolean;
  flex_justification: string | null;
  comments: string | null;
  products: ProductLine[];
  needed_by: string | null;
  attachment_url: string | null;
}

export interface RequestDetail extends RequestFields {
  id: string;
  ref: string;
  status: RequestStatus;
  needs_review: boolean;
  missing_fields: string[];
  badges: string[];
  origin: Vignette["origin"];
  confidence: number | null;
  requested_at: string | null;
  cancelled_at: string | null;
  merged_into_ref: string | null;
  remaining: number;
  version: number;
  assignments: (Assignment & { technician_name: string; created_at: string })[];
  sources: {
    id: string;
    source: "mail" | "teams" | "sharepoint";
    received_at: string;
    sender: string | null;
    subject: string | null;
    body_excerpt: string | null;
    web_link: string | null;
  }[];
  pending_changes: { id: string; kind: ChangeKind; proposed_changes: Record<string, unknown>; created_at: string }[];
  history: {
    created_at: string;
    actor: string;
    action: string;
    entity_type: string;
    before: Record<string, unknown> | null;
    after: Record<string, unknown> | null;
  }[];
}
