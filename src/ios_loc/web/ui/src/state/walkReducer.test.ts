import { describe, expect, it } from "vitest"
import type { Fix, Stats, WalkStatus } from "@/api/types"
import {
  TRAIL_LIMIT,
  applyMessage,
  fromStatus,
  initialModel,
  isRunning,
  metaEquals,
  metaOf,
  showsLiveDock,
} from "./walkReducer"

function fix(n: number): Fix {
  return { elapsed_s: n, lat: 25 + n / 1000, lon: 121, distance_m: n * 1.3, speed_mps: 1.3, paused: false }
}

const stats: Stats = { elapsed_s: 1, distance_m: 1.3, laps: 0, reconnects: 0, ticks: 1 }

const status: WalkStatus = {
  state: "walking",
  error: null,
  fix: fix(3),
  stats,
  route: [[25, 121], [25.01, 121]],
  trail: [fix(1), fix(2), fix(3)],
  preset_name: "park",
  pace: "walk",
  loop: true,
  length_m: 1200,
}

describe("fromStatus", () => {
  it("adopts every field of the connect snapshot", () => {
    const model = fromStatus(status)
    expect(model.state).toBe("walking")
    expect(model.route).toEqual([[25, 121], [25.01, 121]])
    expect(model.trail).toHaveLength(3)
    expect(model.preset_name).toBe("park")
    expect(model.length_m).toBe(1200)
  })

  it("caps an oversized snapshot trail", () => {
    const long = { ...status, trail: Array.from({ length: 500 }, (_, i) => fix(i)) }
    expect(fromStatus(long).trail).toHaveLength(TRAIL_LIMIT)
    expect(fromStatus(long).trail[TRAIL_LIMIT - 1].elapsed_s).toBe(499)
  })

  it("drops the trail for a pinned snapshot (no orange line on reconnect)", () => {
    const pinned = { ...status, state: "pinned" as const }
    expect(fromStatus(pinned).trail).toEqual([])
  })
})

describe("applyMessage: fix", () => {
  it("appends to the trail and replaces fix/stats/state", () => {
    const model = applyMessage(fromStatus(status), { type: "fix", fix: fix(4), stats, state: "walking" })
    expect(model.trail).toHaveLength(4)
    expect(model.fix?.elapsed_s).toBe(4)
    expect(model.stats).toBe(stats)
  })

  it("caps the trail at TRAIL_LIMIT, dropping the oldest", () => {
    let model = initialModel
    for (let i = 0; i < TRAIL_LIMIT + 40; i++) {
      model = applyMessage(model, { type: "fix", fix: fix(i), stats, state: "walking" })
    }
    expect(model.trail).toHaveLength(TRAIL_LIMIT)
    expect(model.trail[0].elapsed_s).toBe(40)
    expect(model.trail[TRAIL_LIMIT - 1].elapsed_s).toBe(TRAIL_LIMIT + 39)
  })

  it("pins the live trail cap value to 120 via hardcoded bounds", () => {
    let model = initialModel
    for (let i = 0; i < 400; i++) {
      model = applyMessage(model, { type: "fix", fix: fix(i), stats, state: "walking" })
    }
    // Hardcoded assertions that fail if TRAIL_LIMIT changes from 120
    expect(model.trail).toHaveLength(120)
    expect(model.trail[0].elapsed_s).toBe(280)
    expect(model.trail[119].elapsed_s).toBe(399)
  })

  it("never mutates the model it was given", () => {
    const before = fromStatus(status)
    const trailBefore = before.trail
    applyMessage(before, { type: "fix", fix: fix(9), stats, state: "walking" })
    expect(before.trail).toBe(trailBefore)
    expect(before.trail).toHaveLength(3)
  })

  it("leaves meta unchanged, so the map and sidebar need not re-render", () => {
    const before = fromStatus(status)
    const after = applyMessage(before, { type: "fix", fix: fix(4), stats, state: "walking" })
    expect(metaEquals(metaOf(before), metaOf(after))).toBe(true)
  })

  it("does change meta when the fix message carries a new state", () => {
    const before = fromStatus(status)
    const after = applyMessage(before, { type: "fix", fix: fix(4), stats, state: "reconnecting" })
    expect(after.state).toBe("reconnecting")
    expect(metaEquals(metaOf(before), metaOf(after))).toBe(false)
  })
})

describe("applyMessage: fix (pinned)", () => {
  it("does not append a pinned fix to the trail", () => {
    // A set location is a single point, not a walked path: no orange trail line.
    const model = applyMessage(fromStatus(status), { type: "fix", fix: fix(4), stats, state: "pinned" })
    expect(model.trail).toEqual([])
    expect(model.fix?.elapsed_s).toBe(4)
    expect(model.state).toBe("pinned")
  })

  it("still appends a walking fix to the trail", () => {
    const model = applyMessage(fromStatus(status), { type: "fix", fix: fix(4), stats, state: "walking" })
    expect(model.trail).toHaveLength(4)
  })
})

describe("showsLiveDock", () => {
  it("is false for a bare pinned location (edited in place, no dock takeover)", () => {
    expect(showsLiveDock("pinned", false)).toBe(false)
  })
  it("is true while a walk holds the device", () => {
    expect(showsLiveDock("walking", false)).toBe(true)
    expect(showsLiveDock("starting", false)).toBe(true)
    expect(showsLiveDock("reconnecting", false)).toBe(true)
  })
  it("is true while a finished/lost run's summary is pinned on screen", () => {
    expect(showsLiveDock("finished", true)).toBe(true)
    expect(showsLiveDock("idle", true)).toBe(true)
  })
  it("is false when idle with no summary", () => {
    expect(showsLiveDock("idle", false)).toBe(false)
  })
})

describe("applyMessage: state", () => {
  it("updates state and error without touching the trail or route", () => {
    const before = fromStatus(status)
    const after = applyMessage(before, { type: "state", state: "error", error: "device lost" })
    expect(after.state).toBe("error")
    expect(after.error).toBe("device lost")
    expect(after.trail).toBe(before.trail)
    expect(after.route).toBe(before.route)
  })

  it("clears a stale error when a clean state arrives", () => {
    const errored = applyMessage(initialModel, { type: "state", state: "error", error: "boom" })
    const cleared = applyMessage(errored, { type: "state", state: "idle", error: null })
    expect(cleared.error).toBeNull()
  })

  it("adopts the authoritative stats a terminal state carries", () => {
    const walking = applyMessage(fromStatus(status), { type: "fix", fix: fix(4), stats, state: "walking" })
    // One tick ahead of the last fix: the run ended on a set() that never
    // reached on_fix, so this count is the only place it is reported.
    const final: Stats = { elapsed_s: 5, distance_m: 6.5, laps: 1, reconnects: 2, ticks: 5 }
    const after = applyMessage(walking, { type: "state", state: "finished", error: null, stats: final })
    expect(after.stats).toEqual(final)
    // The last fix stays: it is what the map's dot and the trail are drawn from.
    expect(after.fix?.elapsed_s).toBe(4)
  })

  it("keeps the stats on screen when a state message carries none", () => {
    const walking = applyMessage(fromStatus(status), { type: "fix", fix: fix(4), stats, state: "walking" })
    const reconnecting = applyMessage(walking, { type: "state", state: "reconnecting", error: null })
    expect(reconnecting.stats).toEqual(stats)
    // An explicit null is the same case -- a run that never produced stats.
    const nulled = applyMessage(walking, { type: "state", state: "finished", error: null, stats: null })
    expect(nulled.stats).toEqual(stats)
  })
})

describe("applyMessage: snapshot", () => {
  it("replaces the whole model, so a reconnecting socket resyncs rather than merges", () => {
    const drifted = applyMessage(fromStatus(status), { type: "fix", fix: fix(99), stats, state: "walking" })
    const resynced = applyMessage(drifted, { type: "snapshot", status: { ...status, trail: [fix(1)] } })
    expect(resynced.trail).toHaveLength(1)
    expect(resynced.fix?.elapsed_s).toBe(3)
  })
})

describe("metaEquals", () => {
  it("compares route contents, not identity", () => {
    const a = metaOf(fromStatus(status))
    const b = metaOf(fromStatus({ ...status, route: [[25, 121], [25.01, 121]] }))
    expect(metaEquals(a, b)).toBe(true)
  })

  it("notices a route of the same length with different coordinates", () => {
    const a = metaOf(fromStatus(status))
    const b = metaOf(fromStatus({ ...status, route: [[25, 121], [99, 121]] }))
    expect(metaEquals(a, b)).toBe(false)
  })
})

describe("isRunning", () => {
  it("covers every state in which the device is ours", () => {
    expect(isRunning("starting")).toBe(true)
    expect(isRunning("walking")).toBe(true)
    expect(isRunning("reconnecting")).toBe(true)
    expect(isRunning("idle")).toBe(false)
    expect(isRunning("finished")).toBe(false)
    expect(isRunning("error")).toBe(false)
  })
})
