/** Bloom pages available through the Electron renderer hash router. */
export type AppRoute =
  | 'student-dashboard'
  | 'student-summary'
  | 'lecture-library'
  | 'educator-dashboard'
  | 'educator-summary'
  | 'account'
  | 'login';

export const DEFAULT_ROUTE: AppRoute = 'student-dashboard';

const VALID_ROUTES = new Set<AppRoute>([
  'student-dashboard',
  'student-summary',
  'lecture-library',
  'educator-dashboard',
  'educator-summary',
  'account',
  'login',
]);

/**
 * Resolves a location hash to a supported Bloom application route.
 *
 * @param locationHash - Browser location hash, with or without a leading hash.
 * @returns A supported route or the student dashboard fallback.
 */
export function resolveRoute(locationHash: string): AppRoute {
  const candidate = locationHash.replace(/^#\/?/, '').split('?')[0];

  if (VALID_ROUTES.has(candidate as AppRoute)) {
    return candidate as AppRoute;
  }

  return DEFAULT_ROUTE;
}

/**
 * Builds the canonical hash URL used by Bloom's in-app navigation.
 *
 * @param route - Supported application route.
 * @returns A hash URL suitable for anchor elements and location updates.
 */
export function buildRouteHash(route: AppRoute): string {
  return `#/${route}`;
}
