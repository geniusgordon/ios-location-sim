import { describe, expect, it } from "vitest"
import { initialFollow, onRecenter, onUserPan, shouldCenter } from "./follow"

describe("follow mode", () => {
  it("follows the dot by default", () => {
    expect(shouldCenter(initialFollow, true)).toBe(true)
  })

  it("detaches the moment the user pans, and stays detached", () => {
    const panned = onUserPan(initialFollow)
    expect(shouldCenter(panned, true)).toBe(false)
    // Still detached several fixes later: the map must never yank itself back
    // out from under someone reading it.
    expect(shouldCenter(onUserPan(panned), true)).toBe(false)
  })

  it("reattaches when the recenter button is pressed", () => {
    expect(shouldCenter(onRecenter(onUserPan(initialFollow)), true)).toBe(true)
  })

  it("does not centre when there is no fix to centre on", () => {
    expect(shouldCenter(initialFollow, false)).toBe(false)
  })
})
