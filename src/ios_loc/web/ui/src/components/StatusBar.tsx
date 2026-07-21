import { useState } from "react"
import { Menu, Square } from "lucide-react"
import type { WalkStateName } from "@/api/types"
import { errorText, stopWalk } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { formatDistance, formatDuration, formatSpeed } from "@/lib/format"
import { isRunning } from "@/state/walkReducer"
import { useWalkMeta, useWalkTelemetry } from "@/hooks/useWalkStream"

const LABEL: Record<WalkStateName, string> = {
  idle: "idle",
  starting: "starting",
  walking: "walking",
  reconnecting: "reconnecting",
  finished: "finished",
  error: "device lost",
}

// `destructive` for error, `secondary` for the quiet states, default for live.
function tone(state: WalkStateName): "default" | "secondary" | "destructive" {
  if (state === "error") return "destructive"
  if (state === "reconnecting") return "destructive"
  if (state === "walking" || state === "starting") return "default"
  return "secondary"
}

/**
 * `paused` is not a WalkState -- the server models it per-fix (`Fix.paused`,
 * the walker's random rest stops). The chip shows it because a stationary dot
 * with no explanation reads as a hang.
 */
function chipLabel(state: WalkStateName, paused: boolean): string {
  return state === "walking" && paused ? "paused" : LABEL[state]
}

function Stat(props: { label: string; value: string; truncate?: boolean }) {
  return (
    <div className={`flex min-w-0 flex-col leading-tight${props.truncate ? " max-w-50" : ""}`}>
      <span className="text-muted-foreground text-[10px] uppercase tracking-wide">
        {props.label}
      </span>
      <span
        className={`font-mono text-sm tabular-nums${props.truncate ? " truncate" : ""}`}
        title={props.truncate ? props.value : undefined}
      >
        {props.value}
      </span>
    </div>
  )
}

export default function StatusBar(props: { onOpenSidebar(): void }) {
  const { fix, stats, state } = useWalkTelemetry()
  const meta = useWalkMeta()
  const [stopping, setStopping] = useState(false)
  const [stopError, setStopError] = useState<string | null>(null)

  const onStop = async () => {
    setStopping(true)
    setStopError(null)
    try {
      await stopWalk()
    } catch (error) {
      setStopError(errorText(error))
    } finally {
      setStopping(false)
    }
  }

  return (
    <div className="bg-background/95 flex h-14 items-center gap-4 border-t px-4 py-2 backdrop-blur">
      <Button variant="ghost" size="icon" aria-label="Open sidebar" onClick={props.onOpenSidebar}>
        <Menu className="size-4" />
      </Button>

      <Badge variant={tone(state)}>{chipLabel(state, fix?.paused ?? false)}</Badge>

      <Stat label="elapsed" value={formatDuration(stats?.elapsed_s ?? 0)} />
      <Stat label="distance" value={formatDistance(stats?.distance_m ?? 0)} />
      <Stat label="speed" value={formatSpeed(fix?.speed_mps ?? 0)} />
      <Stat label="laps" value={String(stats?.laps ?? 0)} />
      <Stat label="reconnects" value={String(stats?.reconnects ?? 0)} />
      {/* Bounded like the error span: a long preset name must not push Stop off-screen. */}
      {meta.preset_name ? <Stat label="preset" value={meta.preset_name} truncate /> : null}

      <div className="ml-auto flex items-center gap-3">
        {/* The server's own words, never paraphrased -- an honest failure beats
            a pretty one (see the spec's failure-handling section). */}
        {meta.error ? (
          <span className="text-destructive max-w-100 truncate text-xs" title={meta.error}>
            {meta.error}
          </span>
        ) : null}
        {stopError ? <span className="text-destructive text-xs">{stopError}</span> : null}
        <Button
          variant="destructive"
          size="sm"
          disabled={!isRunning(state) || stopping}
          onClick={onStop}
        >
          {stopping ? <Spinner className="size-4" /> : <Square className="size-4" />}
          Stop
        </Button>
      </div>
    </div>
  )
}
