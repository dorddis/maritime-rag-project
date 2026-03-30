/**
 * Demo mode utilities
 *
 * When NEXT_PUBLIC_DEMO_MODE=true, the dashboard uses mock data
 * instead of connecting to a real backend.
 */

export function isDemoMode(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_MODE === "true";
}
