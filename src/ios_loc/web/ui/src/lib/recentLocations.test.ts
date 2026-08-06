import { describe, expect, it } from "vitest"
import { addRecent, loadRecents, removeRecent } from "./recentLocations"

function fakeStore() {
  const data = new Map<string, string>()
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value),
  }
}

describe("recentLocations", () => {
  it("starts empty", () => {
    expect(loadRecents(fakeStore())).toEqual([])
  })

  it("adds a point to the front", () => {
    const store = fakeStore()
    addRecent([48.858666, 2.293991], 1000, store)
    expect(loadRecents(store)).toEqual([{ point: [48.858666, 2.293991], ts: 1000 }])
  })

  it("puts the newest point first", () => {
    const store = fakeStore()
    addRecent([1, 1], 1000, store)
    addRecent([2, 2], 2000, store)
    expect(loadRecents(store)).toEqual([
      { point: [2, 2], ts: 2000 },
      { point: [1, 1], ts: 1000 },
    ])
  })

  it("moves a re-pinned point to the front instead of duplicating it", () => {
    const store = fakeStore()
    addRecent([1, 1], 1000, store)
    addRecent([2, 2], 2000, store)
    addRecent([1, 1], 3000, store)
    expect(loadRecents(store)).toEqual([
      { point: [1, 1], ts: 3000 },
      { point: [2, 2], ts: 2000 },
    ])
  })

  it("caps the history at 8 entries", () => {
    const store = fakeStore()
    for (let i = 0; i < 10; i++) addRecent([i, i], i, store)
    const recents = loadRecents(store)
    expect(recents).toHaveLength(8)
    expect(recents[0]).toEqual({ point: [9, 9], ts: 9 })
  })

  it("removes an entry", () => {
    const store = fakeStore()
    addRecent([1, 1], 1000, store)
    addRecent([2, 2], 2000, store)
    expect(removeRecent([1, 1], store)).toEqual([{ point: [2, 2], ts: 2000 }])
    expect(loadRecents(store)).toEqual([{ point: [2, 2], ts: 2000 }])
  })

  it("ignores a corrupt stored value", () => {
    const store = fakeStore()
    store.setItem("ios-loc:recent-locations", "not json")
    expect(loadRecents(store)).toEqual([])
  })
})
