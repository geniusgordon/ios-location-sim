import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { LatLon, RouteResponse } from "@/api/types"
import { ROUTE_DEBOUNCE_MS, createRoutePreviewRunner } from "./useRoutePreview"

const A: LatLon[] = [[25, 121], [25.1, 121.1]]
const B: LatLon[] = [[25, 121], [25.2, 121.2]]

function response(lengthM: number): RouteResponse {
  return { coords: [[25, 121]], length_m: lengthM, is_closed_loop: false }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe("debounce", () => {
  it("does not call the server before the delay elapses", () => {
    const fetchRoute = vi.fn(async () => response(1))
    const runner = createRoutePreviewRunner({
      delayMs: ROUTE_DEBOUNCE_MS,
      fetchRoute,
      onResult: () => {},
      onError: () => {},
      onPending: () => {},
    })
    runner.request(A, "pedestrian")
    vi.advanceTimersByTime(ROUTE_DEBOUNCE_MS - 1)
    expect(fetchRoute).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(fetchRoute).toHaveBeenCalledTimes(1)
  })

  it("collapses a burst of edits into one request", () => {
    const fetchRoute = vi.fn(async () => response(1))
    const runner = createRoutePreviewRunner({
      delayMs: ROUTE_DEBOUNCE_MS,
      fetchRoute,
      onResult: () => {},
      onError: () => {},
      onPending: () => {},
    })
    for (let i = 0; i < 10; i++) {
      runner.request(A, "pedestrian")
      vi.advanceTimersByTime(50)
    }
    vi.advanceTimersByTime(ROUTE_DEBOUNCE_MS)
    expect(fetchRoute).toHaveBeenCalledTimes(1)
  })
})

describe("supersession", () => {
  it("aborts the in-flight request when a newer edit lands", async () => {
    const signals: AbortSignal[] = []
    const fetchRoute = vi.fn(
      (_w: LatLon[], _c: string, signal: AbortSignal) =>
        new Promise<RouteResponse>((_resolve, reject) => {
          signals.push(signal)
          signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))
        }),
    )
    const runner = createRoutePreviewRunner({
      delayMs: ROUTE_DEBOUNCE_MS,
      fetchRoute,
      onResult: () => {},
      onError: () => {},
      onPending: () => {},
    })
    runner.request(A, "pedestrian")
    await vi.advanceTimersByTimeAsync(ROUTE_DEBOUNCE_MS)
    runner.request(B, "pedestrian")
    await vi.advanceTimersByTimeAsync(ROUTE_DEBOUNCE_MS)
    expect(signals[0].aborted).toBe(true)
    expect(signals[1].aborted).toBe(false)
  })

  it("never lets a stale response overwrite a newer one", async () => {
    const results: (RouteResponse | null)[] = []
    let resolveFirst: ((r: RouteResponse) => void) | null = null
    const fetchRoute = vi.fn((waypoints: LatLon[]) => {
      if (waypoints === A) return new Promise<RouteResponse>((r) => (resolveFirst = r))
      return Promise.resolve(response(222))
    })
    const runner = createRoutePreviewRunner({
      delayMs: ROUTE_DEBOUNCE_MS,
      fetchRoute: fetchRoute as never,
      onResult: (r) => results.push(r),
      onError: () => {},
      onPending: () => {},
    })
    runner.request(A, "pedestrian")
    await vi.advanceTimersByTimeAsync(ROUTE_DEBOUNCE_MS)
    runner.request(B, "pedestrian")
    await vi.advanceTimersByTimeAsync(ROUTE_DEBOUNCE_MS)
    // Cast works around a tsc 6.0 CFA quirk: reassigning a closured `let` from
    // inside a nested callback narrows its declared type to `never` at this
    // read site even though the assignment demonstrably happens first at runtime.
    ;(resolveFirst as ((r: RouteResponse) => void) | null)?.(response(111)) // the slow first request finally answers
    await vi.advanceTimersByTimeAsync(0)
    expect(results.map((r) => r?.length_m)).toEqual([222])
  })
})

describe("edge cases", () => {
  it("clears the route and asks for nothing when there are fewer than two waypoints", async () => {
    const fetchRoute = vi.fn(async () => response(1))
    const results: (RouteResponse | null)[] = []
    const runner = createRoutePreviewRunner({
      delayMs: ROUTE_DEBOUNCE_MS,
      fetchRoute,
      onResult: (r) => results.push(r),
      onError: () => {},
      onPending: () => {},
    })
    runner.request([[25, 121]], "pedestrian")
    await vi.advanceTimersByTimeAsync(ROUTE_DEBOUNCE_MS * 2)
    expect(fetchRoute).not.toHaveBeenCalled()
    expect(results).toEqual([null])
  })

  it("surfaces the Valhalla error text rather than leaving a blank map", async () => {
    const errors: (string | null)[] = []
    const runner = createRoutePreviewRunner({
      delayMs: ROUTE_DEBOUNCE_MS,
      fetchRoute: async () => {
        throw new Error("No suitable edges near location")
      },
      onResult: () => {},
      onError: (m) => errors.push(m),
      onPending: () => {},
    })
    runner.request(A, "pedestrian")
    await vi.advanceTimersByTimeAsync(ROUTE_DEBOUNCE_MS)
    expect(errors.at(-1)).toContain("No suitable edges")
  })

  it("cancel() stops a pending request from ever firing", () => {
    const fetchRoute = vi.fn(async () => response(1))
    const runner = createRoutePreviewRunner({
      delayMs: ROUTE_DEBOUNCE_MS,
      fetchRoute,
      onResult: () => {},
      onError: () => {},
      onPending: () => {},
    })
    runner.request(A, "pedestrian")
    runner.cancel()
    vi.advanceTimersByTime(ROUTE_DEBOUNCE_MS * 2)
    expect(fetchRoute).not.toHaveBeenCalled()
  })
})
