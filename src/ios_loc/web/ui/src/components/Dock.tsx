import { useState } from "react"
import { Menu, Play, Square, Trash2, Undo2 } from "lucide-react"
import type { LatLon, WalkStateName } from "@/api/types"
import { errorText, startWalk, stopWalk } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import PinControl from "@/components/PinControl"
import RouteOptions from "@/components/RouteOptions"
import { formatDistance, formatDuration, formatSpeed } from "@/lib/format"
import type { DraftRoute, DraftSettings } from "@/lib/draft"
import { canStart, startBody } from "@/lib/startBody"
import { canStop, isRunning, showsLiveDock } from "@/state/walkReducer"
import { useWalkMeta, useWalkTelemetry } from "@/hooks/useWalkStream"

const LABEL: Record<WalkStateName, string> = {
  idle: "idle",
  starting: "starting",
  walking: "walking",
  reconnecting: "reconnecting",
  finished: "finished",
  error: "device lost",
  pinned: "pinned",
}

function tone(state: WalkStateName): "default" | "secondary" | "destructive" {
  if (state === "error" || state === "reconnecting") return "destructive"
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

/**
 * THE ONLY telemetry subscriber in the app. Every fix re-renders this component
 * and nothing else -- pulling `useWalkTelemetry` up into `Dock` would re-render
 * the map's siblings once a second.
 */
function LiveDock() {
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
    <>
      <Badge variant={tone(state)}>{chipLabel(state, fix?.paused ?? false)}</Badge>
      <Stat label="elapsed" value={formatDuration(stats?.elapsed_s ?? 0)} />
      <Stat label="distance" value={formatDistance(stats?.distance_m ?? 0)} />
      <Stat label="speed" value={formatSpeed(fix?.speed_mps ?? 0)} />
      <Stat label="laps" value={String(stats?.laps ?? 0)} />
      <Stat label="reconnects" value={String(stats?.reconnects ?? 0)} />
      {meta.preset_name ? <Stat label="route" value={meta.preset_name} truncate /> : null}

      <div className="ml-auto flex items-center gap-3">
        {/* The server's own words, never paraphrased. */}
        {meta.error ? (
          <span className="text-destructive max-w-100 truncate text-xs" title={meta.error}>
            {meta.error}
          </span>
        ) : null}
        {stopError ? <span className="text-destructive text-xs">{stopError}</span> : null}
        <Button
          variant="destructive"
          size="sm"
          disabled={!canStop(state) || stopping}
          onClick={onStop}
        >
          {stopping ? <Spinner className="size-4" /> : <Square className="size-4" />}
          Stop
        </Button>
      </div>
    </>
  )
}

export interface DockProps {
  route: DraftRoute
  settings: DraftSettings
  onSettingsChange(next: DraftSettings): void
  lengthM: number | null
  routePending: boolean
  /** The route preview's failure — a Valhalla problem. */
  routeError: string | null
  /** A failed /api/presets — a config problem. Kept separate so the options
   *  popover does not label a config error "Routing failed". */
  loadError: string | null
  profiles: string[]
  offline: boolean
  pinArmed: boolean
  onPinArmedChange(armed: boolean): void
  /** The last pinned point, or null. Gates the save-place form. */
  lastPin: LatLon | null
  onPinned(point: LatLon, opts?: { recenter?: boolean }): void
  onPlaceSaved(): void
  /** True while a location is currently held (meta.state === "pinned"). */
  held: boolean
  /** Releases the held location (DELETE /api/walk). */
  onClear(): Promise<void>
  /** A failed set-location pin (map-tap while armed). LiveDock never mounts
   *  for this failure -- pin errors leave the dock in one of the other two
   *  branches -- so it is rendered here instead of via `meta.error`. */
  pinError: string | null
  onRemoveLast(): void
  onClear(): void
  onOpenLibrary(): void
  onSaved(name: string): void
  onStarted(): void
  /** True while a finished/lost run's summary should stay on screen even
   *  though the draft route (still on the map) is non-empty. Cleared by
   *  App.tsx on the next route edit, load, or walk start. */
  showSummary: boolean
}

export default function Dock(props: DockProps) {
  const meta = useWalkMeta()
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  // Telemetry while the device is held, and afterwards while the last run's
  // summary is still the most useful thing on screen -- `showSummary` is an
  // explicit user-visible flag App.tsx sets on `finished`/`error` and clears
  // on the next route edit, load, or walk start, so a completed run does not
  // vanish the instant the dock re-evaluates against an unchanged route.
  // A walk (or a finished/lost run's still-pinned summary) shows the live dock.
  // A bare pinned location does NOT -- it stays editable in the dock below so
  // the next location can be set without stopping first.
  const live = showsLiveDock(meta.state, props.showSummary)

  const onStart = async () => {
    setStarting(true)
    setStartError(null)
    try {
      await startWalk(startBody(props.route, props.settings))
      props.onStarted()
    } catch (error) {
      setStartError(errorText(error))
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="bg-background/95 flex h-14 items-center gap-4 border-t px-4 py-2 backdrop-blur">
      {live ? (
        <LiveDock />
      ) : props.route.waypoints.length === 0 ? (
        <>
          <Button variant="ghost" size="icon" aria-label="Saved routes" onClick={props.onOpenLibrary}>
            <Menu className="size-4" />
          </Button>
          <span className="text-muted-foreground text-sm">Tap the map to draw a route</span>
          {/* A failed /api/presets also empties the Profile select, and an empty
              select with no explanation reads as a bug in the app. */}
          {props.loadError ? (
            <span className="text-destructive max-w-80 truncate text-xs" title={props.loadError}>
              {props.loadError}
            </span>
          ) : null}
          {props.pinError ? (
            <span className="text-destructive max-w-80 truncate text-xs" title={props.pinError}>
              {props.pinError}
            </span>
          ) : null}
          <div className="ml-auto">
            <PinControl
              armed={props.pinArmed}
              onArmedChange={props.onPinArmedChange}
              disabled={isRunning(meta.state)}
              lastPin={props.lastPin}
              onPinned={props.onPinned}
              onPlaceSaved={props.onPlaceSaved}
              held={props.held}
              onClear={props.onClear}
            />
          </div>
        </>
      ) : (
        <>
          <Button variant="ghost" size="icon" aria-label="Saved routes" onClick={props.onOpenLibrary}>
            <Menu className="size-4" />
          </Button>
          <span className="min-w-0 truncate text-sm">
            {props.route.name ? (
              <span className="mr-2 font-medium">{props.route.name}</span>
            ) : null}
            <span className="font-medium">{props.route.waypoints.length}</span>{" "}
            <span className="text-muted-foreground">pts</span>
            {props.lengthM !== null ? (
              <span className="text-muted-foreground"> · {formatDistance(props.lengthM)}</span>
            ) : null}
          </span>
          {props.routePending ? <Spinner className="size-4" /> : null}
          <Button variant="ghost" size="icon" aria-label="Undo last point" onClick={props.onRemoveLast}>
            <Undo2 className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Clear points" onClick={props.onClear}>
            <Trash2 className="size-4" />
          </Button>

          <div className="ml-auto flex items-center gap-3">
            {/* Short here, full text in the popover: a user who never opens
                Options would otherwise see disconnected dots and no reason. */}
            {(props.routeError ?? props.loadError) ? (
              <span
                className="text-destructive max-w-60 truncate text-xs"
                title={props.routeError ?? props.loadError ?? ""}
              >
                {props.routeError ?? props.loadError}
              </span>
            ) : null}
            {startError ? (
              <span className="text-destructive max-w-60 truncate text-xs" title={startError}>
                {startError}
              </span>
            ) : null}
            {props.pinError ? (
              <span className="text-destructive max-w-60 truncate text-xs" title={props.pinError}>
                {props.pinError}
              </span>
            ) : null}
            <PinControl
              armed={props.pinArmed}
              onArmedChange={props.onPinArmedChange}
              disabled={isRunning(meta.state)}
              lastPin={props.lastPin}
              onPinned={props.onPinned}
              onPlaceSaved={props.onPlaceSaved}
              held={props.held}
              onClear={props.onClear}
            />
            <RouteOptions
              route={props.route}
              settings={props.settings}
              onSettingsChange={props.onSettingsChange}
              profiles={props.profiles}
              offline={props.offline}
              routeError={props.routeError}
              onSaved={props.onSaved}
            />
            <Button size="sm" disabled={!canStart(props.route) || starting} onClick={onStart}>
              {starting ? <Spinner className="size-4" /> : <Play className="size-4" />} Start
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
