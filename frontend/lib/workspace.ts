import type { Membership } from "./api";

export const sections = [
  { path: "dashboard", label: "Overview" },
  { path: "products", label: "Products" },
  { path: "imports", label: "Imports and review" },
  { path: "equipment", label: "Equipment and rules" },
  { path: "assessments", label: "Assessments" },
  { path: "commercial", label: "Plan and usage", manager: true },
  { path: "billing", label: "Billing history", manager: true },
  { path: "integrations", label: "Integrations", manager: true },
  { path: "settings", label: "Organization settings" },
] as const;

export function organizationPath(org: string, section = "dashboard") {
  return `/organizations/${encodeURIComponent(org)}/${section}`;
}

export function visibleSections(role: Membership["role"]) {
  return sections.filter((item) => !("manager" in item) || role !== "member");
}

export function currentSection(pathname: string) {
  const segment = pathname.split("/")[3];
  return sections.find((item) => item.path === segment) ?? sections[0];
}
