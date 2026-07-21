import { useEffect, useMemo, useRef, useState } from "react"
import type { LatLon, RouteResponse } from "@/api/types"
import { errorText, postRoute } from "@/api/client"

/**
 * Long enough that dragging a waypoint does not hammer Valhalla, short enough
 * that the polyline feels attached to the cursor. The route cache makes most
 * repeat edits free anyway.
 */
export const ROUTE_DEBOUNCE_MS = 300

export interface RoutePreviewOptions {
  delayMs: number
  fetchRoute(waypoints: LatLon[], costing: string, signal: AbortSignal): Promise<RouteResponse>
  onResult(result: RouteResponse | null): void
  onError(message: string | null): void
  onPending(pending: boolean): void
}

export interface RoutePreviewRunner {
  request(waypoints: LatLon[], costing: string): void
  cancel(): void
}

/**
 * Debounce + abort + last-write-wins, with no React in it, so the behaviour that
 * actually matters is testable in milliseconds.
 */
export function createRoutePreviewRunner(options: RoutePreviewOptions): RoutePreviewRunner {
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | null = null
  let generation = 0

  const cancel = () => {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
    controller?.abort()
    controller = null
  }

  return {
    cancel,
    request(waypoints, costing) {
      cancel()
      if (waypoints.length < 2) {
        // One point is not a route. Clear rather than show a stale line.
        options.onResult(null)
        options.onError(null)
        options.onPending(false)
        return
      }
      const mine = ++generation
      options.onPending(true)
      timer = setTimeout(() => {
        const local = new AbortController()
        controller = local
        options
          .fetchRoute(waypoints, costing, local.signal)
          .then((result) => {
            if (mine !== generation) return // superseded; drop it
            options.onResult(result)
            options.onError(null)
            options.onPending(false)
          })
          .catch((error: unknown) => {
            if (mine !== generation) return
            if (error instanceof DOMException && error.name === "AbortError") return
            options.onResult(null)
            options.onError(errorText(error))
            options.onPending(false)
          })
      }, options.delayMs)
    },
  }
}

export interface RoutePreview {
  route: LatLon[]
  lengthM: number | null
  error: string | null
  pending: boolean
}

export function useRoutePreview(
  waypoints: LatLon[],
  costing: string,
  enabled: boolean,
): RoutePreview {
  const [route, setRoute] = useState<LatLon[]>([])
  const [lengthM, setLengthM] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const runner = useMemo(
    () =>
      createRoutePreviewRunner({
        delayMs: ROUTE_DEBOUNCE_MS,
        fetchRoute: (points, c, signal) => postRoute({ waypoints: points, costing: c }, signal),
        onResult: (result) => {
          setRoute((result?.coords ?? []) as LatLon[])
          setLengthM(result?.length_m ?? null)
        },
        onError: setError,
        onPending: setPending,
      }),
    [],
  )

  // Compared by value: `waypoints` is a fresh array on every App render, so an
  // identity-keyed effect would re-request on every unrelated state change.
  const key = JSON.stringify(waypoints)
  const runnerRef = useRef(runner)
  runnerRef.current = runner

  useEffect(() => {
    if (!enabled) {
      runnerRef.current.cancel()
      setRoute([])
      setLengthM(null)
      setError(null)
      setPending(false)
      return
    }
    runnerRef.current.request(JSON.parse(key) as LatLon[], costing)
    return () => runnerRef.current.cancel()
  }, [key, costing, enabled])

  return { route, lengthM, error, pending }
}
