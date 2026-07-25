/** Display helpers for the status bar. Pure; no locale dependence. */

export function formatDistance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres)} m`
  return `${(metres / 1000).toFixed(2)} km`
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const s = total % 60
  const m = Math.floor(total / 60) % 60
  const h = Math.floor(total / 3600)
  const pad = (n: number) => String(n).padStart(2, "0")
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

/** The 20 km/h speed ceiling is stated in km/h, so show km/h. */
export function formatSpeed(metresPerSecond: number): string {
  return `${(metresPerSecond * 3.6).toFixed(1)} km/h`
}

/**
 * A pace's speed, both ways round: km/h is how the ceiling is stated and how
 * people read walking speed, m/s is what config.toml and `--speed` take, so
 * showing only one leaves the user converting by hand to edit their config.
 */
export function formatPaceSpeed(metresPerSecond: number): string {
  return `${(metresPerSecond * 3.6).toFixed(1)} km/h · ${metresPerSecond.toFixed(2)} m/s`
}
