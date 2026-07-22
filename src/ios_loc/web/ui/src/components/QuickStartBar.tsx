import { useState } from "react"
import { Play, Trash2, Undo2 } from "lucide-react"
import { errorText, startWalk } from "@/api/client"
import type { LatLon, StartRequest } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { formatDistance } from "@/lib/format"
import { isRunning } from "@/state/walkReducer"
import { useWalkMeta } from "@/hooks/useWalkStream"

export interface QuickStartBarProps {
  waypoints: LatLon[]
  lengthM: number | null
  costing: string
  onRemoveLast(): void
  onClear(): void
  onStarted(): void
}

export default function QuickStartBar(props: QuickStartBarProps) {
  const meta = useWalkMeta()
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Hidden while the device is busy (a walk or a pin -- the status bar owns
  // those) and when there is nothing to start.
  if (isRunning(meta.state) || meta.state === "pinned" || props.waypoints.length === 0) {
    return null
  }

  const onStart = async () => {
    setStarting(true)
    setError(null)
    // Exactly the ad-hoc defaults StartForm sends, so the two paths cannot drift.
    const body: StartRequest = {
      preset: null,
      waypoints: props.waypoints,
      profile: null,
      speed: null,
      costing: props.costing,
      loop: false,
      duration_s: null,
      scatter_m: 3,
    }
    try {
      await startWalk(body)
      props.onStarted()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setStarting(false)
    }
  }

  const canStart = props.waypoints.length >= 2 && !starting

  return (
    <div className="absolute bottom-6 left-1/2 z-10 -translate-x-1/2">
      <div className="bg-background/95 flex items-center gap-3 rounded-full border px-4 py-2 shadow-md backdrop-blur">
        <span className="text-sm">
          <span className="font-medium">{props.waypoints.length}</span>{" "}
          <span className="text-muted-foreground">pts</span>
          {props.lengthM !== null ? (
            <span className="text-muted-foreground"> · {formatDistance(props.lengthM)}</span>
          ) : null}
        </span>
        <Button variant="ghost" size="icon" aria-label="Undo last point" onClick={props.onRemoveLast}>
          <Undo2 className="size-4" />
        </Button>
        <Button variant="ghost" size="icon" aria-label="Clear points" onClick={props.onClear}>
          <Trash2 className="size-4" />
        </Button>
        <Button size="sm" disabled={!canStart} onClick={onStart}>
          {starting ? <Spinner className="size-4" /> : <Play className="size-4" />} Start
        </Button>
      </div>
      {error ? (
        <p className="text-destructive mt-1 text-center text-xs" title={error}>
          {error}
        </p>
      ) : null}
    </div>
  )
}
