import type {
  DeviceStatus,
  LatLon,
  PinRequest,
  Place,
  PlaceIn,
  PlacesList,
  PresetIn,
  Preset,
  PresetsList,
  RerouteRequest,
  RouteRequest,
  RouteResponse,
  StartRequest,
  WalkStatus,
} from "./types"

/**
 * A non-2xx response. `detail` is always a human-readable single line, whether
 * FastAPI sent a plain string (HTTPException) or the 422 validation array.
 */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

/** The message to show a user for any thrown value, server text preferred. */
export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.detail : String(error)
}

// Injectable seam, matching the clock/poster/opener style used on the Python
// side. Production code never calls setFetch.
let doFetch: typeof fetch = (...args) => globalThis.fetch(...args)

export function setFetch(f: typeof fetch): void {
  doFetch = f
}

interface ValidationItem {
  loc?: (string | number)[]
  msg?: string
}

function describe(status: number, body: unknown): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      // 422 from pydantic. `loc` starts with "body"; drop it, it is noise.
      const lines = (detail as ValidationItem[]).map((item) => {
        const where = (item.loc ?? []).filter((p) => p !== "body").join(".")
        const msg = item.msg ?? "invalid value"
        return where ? `${where}: ${msg}` : msg
      })
      if (lines.length > 0) return lines.join("; ")
    }
  }
  return `HTTP ${status}`
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  // An AbortError from here propagates untouched: a superseded route preview is
  // not a failure the user should ever see.
  const response = await doFetch(path, init)
  const text = await response.text()
  let parsed: unknown = undefined
  try {
    parsed = text.length > 0 ? JSON.parse(text) : undefined
  } catch {
    parsed = undefined
  }
  if (!response.ok) throw new ApiError(response.status, describe(response.status, parsed))
  return parsed as T
}

function json(method: string, body: unknown, signal?: AbortSignal): RequestInit {
  return {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }
}

export function getPresets(signal?: AbortSignal): Promise<PresetsList> {
  return request<PresetsList>("/api/presets", { method: "GET", signal })
}

export function savePreset(body: PresetIn, signal?: AbortSignal): Promise<Preset> {
  return request<Preset>("/api/presets", json("POST", body, signal))
}

export function deletePreset(name: string, signal?: AbortSignal): Promise<void> {
  // encodeURIComponent, not raw interpolation: a saved name may contain a
  // space or a slash, and the server matches the decoded path segment.
  return request<void>(`/api/presets/${encodeURIComponent(name)}`, { method: "DELETE", signal })
}

export function getPlaces(signal?: AbortSignal): Promise<PlacesList> {
  return request<PlacesList>("/api/places", { method: "GET", signal })
}

export function savePlace(body: PlaceIn, signal?: AbortSignal): Promise<Place> {
  return request<Place>("/api/places", json("POST", body, signal))
}

export function deletePlace(name: string, signal?: AbortSignal): Promise<void> {
  return request<void>(`/api/places/${encodeURIComponent(name)}`, { method: "DELETE", signal })
}

export function postRoute(body: RouteRequest, signal?: AbortSignal): Promise<RouteResponse> {
  return request<RouteResponse>("/api/route", json("POST", body, signal))
}

export function getWalk(signal?: AbortSignal): Promise<WalkStatus> {
  return request<WalkStatus>("/api/walk", { method: "GET", signal })
}

export function startWalk(body: StartRequest, signal?: AbortSignal): Promise<WalkStatus> {
  return request<WalkStatus>("/api/walk", json("POST", body, signal))
}

export function stopWalk(signal?: AbortSignal): Promise<WalkStatus> {
  return request<WalkStatus>("/api/walk", { method: "DELETE", signal })
}

export function getDeviceStatus(signal?: AbortSignal): Promise<DeviceStatus> {
  return request<DeviceStatus>("/api/device", { method: "GET", signal })
}

export function patchReroute(waypoints: LatLon[], signal?: AbortSignal): Promise<WalkStatus> {
  const body: RerouteRequest = { waypoints }
  return request<WalkStatus>("/api/walk/route", json("PATCH", body, signal))
}

export function pinLocation(
  lat: number,
  lon: number,
  signal?: AbortSignal,
): Promise<WalkStatus> {
  const body: PinRequest = { lat, lon }
  return request<WalkStatus>("/api/pin", json("POST", body, signal))
}
