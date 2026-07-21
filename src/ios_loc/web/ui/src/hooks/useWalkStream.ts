import { useEffect, useSyncExternalStore } from "react"
import type { Fix, ServerMessage, Stats, WalkStateName } from "@/api/types"
import { createWalkStore, nextReconnectDelay } from "@/state/walkStore"
import type { WalkMeta } from "@/state/walkReducer"

/** One page, one socket, one store. */
export const walkStore = createWalkStore()

function socketUrl(): string {
  const url = new URL("/ws", window.location.href)
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.toString()
}

/**
 * Owns the single WebSocket. Mount from `App` exactly once.
 *
 * The server sends a full snapshot on every connect, so a reconnect resyncs by
 * itself — there is no catch-up protocol and nothing to replay.
 */
export function useWalkStream(): void {
  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let closed = false

    const connect = () => {
      if (closed) return
      socket = new WebSocket(socketUrl())
      socket.onopen = () => {
        attempt = 0
      }
      socket.onmessage = (event) => {
        let msg: ServerMessage
        try {
          msg = JSON.parse(event.data as string) as ServerMessage
        } catch {
          // A malformed frame is a server bug, not a reason to tear down a
          // healthy socket. Drop it and keep listening.
          return
        }
        walkStore.dispatch(msg)
      }
      socket.onclose = () => {
        if (closed) return
        timer = setTimeout(connect, nextReconnectDelay(attempt))
        attempt += 1
      }
      // `onerror` is always followed by `onclose`, so reconnection is handled
      // there and this handler only exists to stop the console noise.
      socket.onerror = () => {}
    }

    connect()
    return () => {
      closed = true
      if (timer !== undefined) clearTimeout(timer)
      socket?.close()
    }
  }, [])
}

export function useWalkMeta(): WalkMeta {
  return useSyncExternalStore(
    (l) => walkStore.subscribeMeta(l),
    () => walkStore.getMeta(),
  )
}

export interface Telemetry {
  fix: Fix | null
  stats: Stats | null
  state: WalkStateName
}

/**
 * Subscribe ONLY from the status bar. Every fix re-renders whatever calls this.
 */
export function useWalkTelemetry(): Telemetry {
  const model = useSyncExternalStore(
    (l) => walkStore.subscribeTelemetry(l),
    () => walkStore.getModel(),
  )
  return { fix: model.fix, stats: model.stats, state: model.state }
}
