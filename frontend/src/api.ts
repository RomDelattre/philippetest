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
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* corps non JSON */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
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
