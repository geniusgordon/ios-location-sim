import { useEffect, useState } from "react"
import type { DeviceStatus } from "@/api/types"
import { getDeviceStatus } from "@/api/client"

/** Polls /api/device every 8s (+ on window focus). `paused` stops polling
 *  while the service already holds the device (a walk/pin) -- the walk state
 *  is the truth then, and a probe would open a second tunnel. */
export function useDeviceStatus(paused: boolean): DeviceStatus | null {
  const [status, setStatus] = useState<DeviceStatus | null>(null)
  useEffect(() => {
    if (paused) return
    let cancelled = false
    const controller = new AbortController()
    const poll = () => {
      getDeviceStatus(controller.signal)
        .then((s) => {
          if (!cancelled) setStatus(s)
        })
        .catch(() => {
          // Transient; keep the last known value.
        })
    }
    poll()
    const id = setInterval(poll, 8000)
    const onFocus = () => poll()
    window.addEventListener("focus", onFocus)
    return () => {
      cancelled = true
      controller.abort()
      clearInterval(id)
      window.removeEventListener("focus", onFocus)
    }
  }, [paused])
  return status
}
