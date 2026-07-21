import type { Fix, ServerMessage } from "@/api/types"
import {
  applyMessage,
  initialModel,
  metaEquals,
  metaOf,
  type WalkMeta,
  type WalkModel,
} from "./walkReducer"

type Unsubscribe = () => void

export interface WalkStore {
  getModel(): WalkModel
  /** Referentially stable while meta is unchanged — required by useSyncExternalStore. */
  getMeta(): WalkMeta
  subscribeMeta(listener: () => void): Unsubscribe
  subscribeTelemetry(listener: () => void): Unsubscribe
  subscribeFix(listener: (fix: Fix) => void): Unsubscribe
  dispatch(msg: ServerMessage): void
}

function channel<T extends (...args: never[]) => void>() {
  const listeners = new Set<T>()
  return {
    add(listener: T): Unsubscribe {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    emit(...args: Parameters<T>) {
      // Copied first: a listener that unsubscribes itself must not perturb the
      // iteration of the others.
      for (const listener of [...listeners]) listener(...args)
    },
  }
}

export function createWalkStore(): WalkStore {
  let model = initialModel
  let meta = metaOf(model)

  const metaChannel = channel<() => void>()
  const telemetryChannel = channel<() => void>()
  const fixChannel = channel<(fix: Fix) => void>()

  function commit(next: WalkModel, fix: Fix | null): void {
    model = next
    const nextMeta = metaOf(next)
    const metaChanged = !metaEquals(meta, nextMeta)
    // Only swap the object when it really changed, so getMeta() stays stable
    // and useSyncExternalStore bails out instead of re-rendering the map.
    if (metaChanged) meta = nextMeta
    telemetryChannel.emit()
    if (metaChanged) metaChannel.emit()
    if (fix) fixChannel.emit(fix)
  }

  return {
    getModel: () => model,
    getMeta: () => meta,
    subscribeMeta: (l) => metaChannel.add(l),
    subscribeTelemetry: (l) => telemetryChannel.add(l),
    subscribeFix: (l) => fixChannel.add(l),
    dispatch(msg) {
      commit(applyMessage(model, msg), msg.type === "fix" ? msg.fix : null)
    },
  }
}

/** 500 ms doubling to a 10 s ceiling. Reconnecting is cheap; the server is local. */
export function nextReconnectDelay(attempt: number): number {
  return Math.min(10000, 500 * 2 ** attempt)
}
