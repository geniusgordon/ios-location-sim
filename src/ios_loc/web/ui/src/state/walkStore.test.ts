import { describe, expect, it, vi } from "vitest"
import type { Fix, Stats } from "@/api/types"
import { createWalkStore, nextReconnectDelay } from "./walkStore"
import { initialModel } from "./walkReducer"

function fix(n: number): Fix {
  return { elapsed_s: n, lat: 25, lon: 121, distance_m: n, speed_mps: 1.3, paused: false }
}
const stats: Stats = { elapsed_s: 1, distance_m: 1, laps: 0, reconnects: 0, ticks: 1 }

describe("notification channels", () => {
  it("does NOT notify meta subscribers when only a fix arrives", () => {
    const store = createWalkStore()
    const meta = vi.fn()
    const telemetry = vi.fn()
    store.subscribeMeta(meta)
    store.subscribeTelemetry(telemetry)

    store.dispatch({ type: "fix", fix: fix(1), stats, state: "walking" })
    store.dispatch({ type: "fix", fix: fix(2), stats, state: "walking" })

    // The whole point: 1 Hz telemetry must not re-render the map or sidebar.
    expect(meta).toHaveBeenCalledTimes(0)
    expect(telemetry).toHaveBeenCalledTimes(2)
  })

  it("notifies meta subscribers when the state changes", () => {
    const store = createWalkStore()
    const meta = vi.fn()
    store.subscribeMeta(meta)
    store.dispatch({ type: "state", state: "walking", error: null })
    expect(meta).toHaveBeenCalledTimes(1)
  })

  it("notifies meta when a fix message also carries a new state", () => {
    const store = createWalkStore()
    const meta = vi.fn()
    store.subscribeMeta(meta)
    store.dispatch({ type: "fix", fix: fix(1), stats, state: "walking" })
    store.dispatch({ type: "fix", fix: fix(2), stats, state: "reconnecting" })
    expect(meta).toHaveBeenCalledTimes(1)
  })

  it("hands fixes to fix subscribers, and only fixes", () => {
    const store = createWalkStore()
    const seen: number[] = []
    store.subscribeFix((f) => seen.push(f.elapsed_s))
    store.dispatch({ type: "state", state: "walking", error: null })
    store.dispatch({ type: "fix", fix: fix(7), stats, state: "walking" })
    expect(seen).toEqual([7])
  })

  it("stops calling a listener after it unsubscribes", () => {
    const store = createWalkStore()
    const telemetry = vi.fn()
    const off = store.subscribeTelemetry(telemetry)
    store.dispatch({ type: "fix", fix: fix(1), stats, state: "walking" })
    off()
    store.dispatch({ type: "fix", fix: fix(2), stats, state: "walking" })
    expect(telemetry).toHaveBeenCalledTimes(1)
  })
})

describe("snapshot identity", () => {
  it("keeps getMeta() referentially stable across fixes, so useSyncExternalStore bails out", () => {
    const store = createWalkStore()
    const before = store.getMeta()
    store.dispatch({ type: "fix", fix: fix(1), stats, state: "walking" })
    expect(store.getMeta()).toBe(before)
  })

  it("returns a new meta object once meta genuinely changes", () => {
    const store = createWalkStore()
    const before = store.getMeta()
    store.dispatch({ type: "state", state: "walking", error: null })
    expect(store.getMeta()).not.toBe(before)
  })

  it("keeps getModel() in sync regardless of which channel fired", () => {
    const store = createWalkStore()
    store.dispatch({ type: "fix", fix: fix(5), stats, state: "walking" })
    expect(store.getModel().fix?.elapsed_s).toBe(5)
    expect(store.getModel().trail).toHaveLength(1)
  })

  it("reset() replaces the model and notifies both channels", () => {
    const store = createWalkStore()
    const meta = vi.fn()
    const telemetry = vi.fn()
    store.dispatch({ type: "state", state: "walking", error: null })
    store.subscribeMeta(meta)
    store.subscribeTelemetry(telemetry)
    store.reset(initialModel)
    expect(store.getModel().state).toBe("idle")
    expect(meta).toHaveBeenCalledTimes(1)
    expect(telemetry).toHaveBeenCalledTimes(1)
  })
})

describe("nextReconnectDelay", () => {
  it("backs off exponentially from half a second", () => {
    expect(nextReconnectDelay(0)).toBe(500)
    expect(nextReconnectDelay(1)).toBe(1000)
    expect(nextReconnectDelay(3)).toBe(4000)
  })

  it("caps at ten seconds so an overnight server restart is still noticed promptly", () => {
    expect(nextReconnectDelay(20)).toBe(10000)
  })
})
