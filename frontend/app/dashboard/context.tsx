"use client";

import { createContext, useContext } from "react";
import type { Membership } from "../../lib/api";

export const TenantContext = createContext<Membership | null>(null);
export const WorkspaceContext = createContext<{ org: string } | null>(null);

export function useTenant() {
  const value = useContext(TenantContext);
  if (!value) throw new Error("Organization context is missing");
  return value;
}
