import { useState } from "react"
import { Play, Repeat, Trash2, Undo2 } from "lucide-react"
import { errorText, startWalk } from "@/api/client"
import type { LatLon, StartRequest } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { COSTINGS } from "@/lib/costings"
import { formatDistance } from "@/lib/format"
import { isRunning } from "@/state/walkReducer"
import { useWalkMeta } from "@/hooks/useWalkStream"

export interface QuickStartBarProps {
  waypoints: LatLon[]
  lengthM: number | null
  /** Shared with the sidebar's editor: changing it re-previews the route. */
  costing: string
  onCostingChange(costing: string): void
  profiles: string[]
  offline: boolean
  onRemoveLast(): void
  onClear(): void
  onStarted(): void
}

export default function QuickStartBar(props: QuickStartBarProps) {
  const meta = useWalkMeta()
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Always sent as a boolean, exactly like StartForm's switch -- this toggle is
  // authoritative in both directions. An open path loops by bouncing back and
  // forth; a closed one wraps.
  const [loop, setLoop] = useState(false)
  // Empty means "inherit the profile default", which the backend models as
  // null -- so an empty box must send null, never 0. Same rule as StartForm.
  const [profile, setProfile] = useState("")

  // Hidden while the device is busy (a walk or a pin -- the status bar owns
  // those) and when there is nothing to start.
  if (isRunning(meta.state) || meta.state === "pinned" || props.waypoints.length === 0) {
    return null
  }

  const onStart = async () => {
    setStarting(true)
    setError(null)
    // The same ad-hoc body StartForm sends, so the two paths cannot drift. Only
    // duration and scatter stay at their defaults here -- the sidebar is still
    // where those get overridden.
    const body: StartRequest = {
      preset: null,
      waypoints: props.waypoints,
      profile: profile === "" ? null : profile,
      speed: null,
      costing: props.costing,
      loop,
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

  // rounded-2xl rather than a pill: with the selects in it the bar wraps to two
  // rows on a narrow window, and a wrapped pill reads as a mistake.
  return (
    <div className="absolute bottom-6 left-1/2 z-10 w-max max-w-[min(96vw,48rem)] -translate-x-1/2">
      <div className="bg-background/95 flex flex-wrap items-center justify-center gap-2 rounded-2xl border px-3 py-2 shadow-md backdrop-blur">
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
        {/* Writes the same `costing` the sidebar's editor does, so switching
            here re-previews the route instead of only changing what Start
            sends. Disabled offline, matching the editor's own select. */}
        <Select
          value={props.costing}
          onValueChange={(value) => {
            if (value !== null) props.onCostingChange(value)
          }}
        >
          <SelectTrigger size="sm" aria-label="Routing mode" disabled={props.offline}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {COSTINGS.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={profile} onValueChange={(value) => setProfile(value ?? "")}>
          <SelectTrigger size="sm" aria-label="Profile">
            <SelectValue placeholder="walk" />
          </SelectTrigger>
          <SelectContent>
            {props.profiles.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* A toggle, not a switch: the pill has no room for a label, so the
            filled variant plus aria-pressed carries the on/off state. */}
        <Button
          variant={loop ? "secondary" : "ghost"}
          size="icon"
          aria-label="Loop the route"
          aria-pressed={loop}
          title={loop ? "Looping: on" : "Looping: off"}
          onClick={() => setLoop(!loop)}
        >
          <Repeat className={loop ? "size-4" : "size-4 opacity-50"} />
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
