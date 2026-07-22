import { afterEach, describe, expect, it, vi } from "vitest"
import {
  ApiError,
  deletePlace,
  deletePreset,
  getPresets,
  postRoute,
  savePlace,
  setFetch,
  startWalk,
  stopWalk,
} from "./client"

function stub(status: number, body: unknown, contentType = "application/json") {
  const f = vi.fn(async () =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: { "content-type": contentType },
    }),
  )
  setFetch(f as unknown as typeof fetch)
  return f
}

afterEach(() => {
  setFetch(globalThis.fetch)
})

describe("request shaping", () => {
  it("GETs /api/presets and returns the parsed body", async () => {
    const f = stub(200, { presets: [], profiles: ["walk"], offline: false })
    await expect(getPresets()).resolves.toEqual({
      presets: [],
      profiles: ["walk"],
      offline: false,
    })
    expect((f.mock.calls[0] as unknown[])[0]).toBe("/api/presets")
  })

  it("POSTs JSON with a content-type header", async () => {
    const f = stub(200, { coords: [], length_m: 0, is_closed_loop: false })
    await postRoute({ waypoints: [[25, 121], [25.1, 121.1]], costing: "pedestrian" })
    const init = (f.mock.calls[0] as unknown[])[1] as RequestInit
    expect(init.method).toBe("POST")
    expect(new Headers(init.headers).get("content-type")).toBe("application/json")
    expect(JSON.parse(init.body as string)).toEqual({
      waypoints: [[25, 121], [25.1, 121.1]],
      costing: "pedestrian",
    })
  })

  it("DELETEs /api/walk to stop", async () => {
    const f = stub(200, { state: "idle", route: [], trail: [], loop: false })
    await stopWalk()
    expect((f.mock.calls[0] as unknown[])[0]).toBe("/api/walk")
    expect(((f.mock.calls[0] as unknown[])[1] as RequestInit).method).toBe("DELETE")
  })
})

describe("error mapping", () => {
  it("turns a FastAPI string detail into ApiError.detail", async () => {
    stub(409, { detail: "a walk is already running" })
    const err = await startWalk({ preset: "loop" } as never).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.detail).toBe("a walk is already running")
  })

  it("flattens a 422 validation-error array into one readable line", async () => {
    stub(422, {
      detail: [
        { loc: ["body", "waypoints", 0], msg: "Input should be a valid number", type: "float_parsing" },
        { loc: ["body", "duration_s"], msg: "Input should be greater than 0", type: "greater_than" },
      ],
    })
    const err = await postRoute({ waypoints: [] } as never).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(err.detail).toBe(
      "waypoints.0: Input should be a valid number; duration_s: Input should be greater than 0",
    )
  })

  it("falls back to the status text when the body is not JSON", async () => {
    stub(500, "Internal Server Error", "text/plain")
    const err = await getPresets().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(500)
    expect(err.detail).toContain("500")
  })

  it("lets an AbortError through untouched, so callers can ignore supersessions", async () => {
    setFetch(
      vi.fn(async () => {
        throw new DOMException("aborted", "AbortError")
      }) as unknown as typeof fetch,
    )
    const err = await postRoute({ waypoints: [] } as never).catch((e) => e)
    expect(err).not.toBeInstanceOf(ApiError)
    expect((err as DOMException).name).toBe("AbortError")
  })
})

describe("places and deletion", () => {
  it("percent-encodes a name with a space", async () => {
    let seen = ""
    setFetch(async (path) => {
      seen = String(path)
      return new Response(null, { status: 204 })
    })
    await deletePreset("my route")
    expect(seen).toBe("/api/presets/my%20route")
  })

  it("resolves a 204 delete without a body", async () => {
    setFetch(async () => new Response(null, { status: 204 }))
    await expect(deletePlace("home")).resolves.toBeUndefined()
  })

  it("surfaces the server detail on a failed save", async () => {
    setFetch(
      async () =>
        new Response(JSON.stringify({ detail: "could not write config: disk full" }), {
          status: 500,
        }),
    )
    await expect(savePlace({ name: "home", point: [1, 2] })).rejects.toThrow(ApiError)
  })
})
