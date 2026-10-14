import type { Membership } from "./api";

// Keep a just-created server membership visible while subsequent pages load.
// Later server results replace stale roles without duplicating selector options.
export function mergeMemberships(
  current: Membership[],
  incoming: Membership[],
): Membership[] {
  return [
    ...new Map(
      [...current, ...incoming].map((membership) => [
        membership.id,
        membership,
      ]),
    ).values(),
  ];
}
