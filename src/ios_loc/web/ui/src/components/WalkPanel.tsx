import { useState } from "react"
import { MapPin, Play, RefreshCw, Save, Square, Trash2, Undo2 } from "lucide-react"
import type { Pace, Preset, WalkStateName } from "@/api/types"
import { errorText, savePreset, startWalk, stopWalk } from "@/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import LibraryRow from "@/components/LibraryRow"
import { COSTINGS } from "@/lib/costings"
import type { DraftRoute, DraftSettings } from "@/lib/draft"
import { formatDistance, formatDuration, formatPaceSpeed, formatSpeed } from "@/lib/format"
import { canStart, startBody } from "@/lib/startBody"
import { canStop, showsLiveDock } from "@/state/walkReducer"
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
 * the walker's random rest stops). Shown because a stationary dot with no
 * explanation reads as a hang.
 */
function chipLabel(state: WalkStateName, paused: boolean): string {
  return state === "walking" && paused ? "paused" : LABEL[state]
}

function Stat(props: { label: string; value: string }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-muted-foreground text-[10px] uppercase tracking-wide">{props.label}</span>
      <span className="font-mono text-sm tabular-nums">{props.value}</span>
    </div>
  )
}

/**
 * THE ONLY telemetry subscriber in the app. Every fix re-renders this component
 * and nothing else -- it is a leaf inside the sidebar, so a 1 Hz fix never
 * reaches the map (a sibling of the sidebar) or any editor control.
 */
function LiveWalkPanel() {
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
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-4 p-4">
        <div className="flex items-center gap-2">
          <Badge variant={tone(state)}>{chipLabel(state, fix?.paused ?? false)}</Badge>
          {meta.preset_name ? (
            <span className="min-w-0 truncate text-sm font-medium" title={meta.preset_name}>
              {meta.preset_name}
            </span>
          ) : null}
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          <Stat label="elapsed" value={formatDuration(stats?.elapsed_s ?? 0)} />
          <Stat label="distance" value={formatDistance(stats?.distance_m ?? 0)} />
          <Stat label="speed" value={formatSpeed(fix?.speed_mps ?? 0)} />
          <Stat label="laps" value={String(stats?.laps ?? 0)} />
          <Stat label="reconnects" value={String(stats?.reconnects ?? 0)} />
        </div>

        {/* The server's own words, never paraphrased. */}
        {meta.error ? (
          <p className="text-destructive text-xs" title={meta.error}>
            {meta.error}
          </p>
        ) : null}
        {stopError ? <p className="text-destructive text-xs">{stopError}</p> : null}

        <Button
          variant="destructive"
          className="w-full"
          disabled={!canStop(state) || stopping}
          onClick={onStop}
        >
          {stopping ? <Spinner className="size-4" /> : <Square className="size-4" />} Stop
        </Button>
      </div>
    </div>
  )
}

export interface WalkPanelProps {
  route: DraftRoute
  settings: DraftSettings
  onSettingsChange(next: DraftSettings): void
  lengthM: number | null
  routePending: boolean
  /** The route preview's failure — a Valhalla problem. */
  routeError: string | null
  /** A failed /api/presets — a config problem, kept separate from routeError. */
  loadError: string | null
  paces: Pace[]
  offline: boolean
  onRemoveLast(): void
  onClear(): void
  onSaved(name: string): void
  onStarted(): void
  /** True while a finished/lost run's summary should stay on screen even
   *  though the draft route (still on the map) is non-empty. */
  showSummary: boolean
  presets: Preset[]
  loading: boolean
  onReloadPresets(): void
  onSelectPreset(preset: Preset): void
  onDeletePreset(name: string): Promise<void>
}

export default function WalkPanel(props: WalkPanelProps) {
  const meta = useWalkMeta()
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // A walk (or a finished/lost run's still-pinned summary) shows the live view.
  // A bare pinned location does NOT -- it stays editable so the next location
  // can be set from the Set-location tab without stopping first.
  if (showsLiveDock(meta.state, props.showSummary)) {
    return <LiveWalkPanel />
  }

  const set = <K extends keyof DraftSettings>(key: K, value: DraftSettings[K]) => {
    props.onSettingsChange({ ...props.settings, [key]: value })
  }

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

  const onSave = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      await savePreset({
        name: saveName.trim(),
        waypoints: props.route.waypoints,
        // A saved route owns a concrete pace; the start-time "inherit the
        // default" null has no meaning in the config file.
        pace: props.settings.pace ?? "walk",
        loop: props.settings.loop,
        // Saved with the route because it describes the geometry: reloading it
        // under a different Routing mode would draw a different polyline.
        costing: props.settings.costing,
      })
      setSaveOpen(false)
      props.onSaved(saveName.trim())
    } catch (error) {
      setSaveError(errorText(error))
    } finally {
      setSaving(false)
    }
  }

  const empty = props.route.waypoints.length === 0

  // `pace: null` means "inherit the default", which the backend resolves to
  // `walk` -- so show walk's speed rather than nothing, matching the
  // placeholder the closed select already displays. Falls back to null only if
  // the config failed to load and the list is empty.
  const selectedPace = props.paces.find((p) => p.name === (props.settings.pace ?? "walk")) ?? null

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-4 border-b p-4">
        {/* Route summary */}
        <div className="flex items-center gap-2">
          <span className="min-w-0 flex-1 truncate text-sm">
            {props.route.name ? <span className="mr-2 font-medium">{props.route.name}</span> : null}
            {empty ? (
              <span className="text-muted-foreground">Tap the map to draw a route</span>
            ) : (
              <>
                <span className="font-medium">{props.route.waypoints.length}</span>{" "}
                <span className="text-muted-foreground">pts</span>
                {props.lengthM !== null ? (
                  <span className="text-muted-foreground"> · {formatDistance(props.lengthM)}</span>
                ) : null}
              </>
            )}
          </span>
          {props.routePending ? <Spinner className="size-4 shrink-0" /> : null}
          <Button
            variant="ghost"
            size="icon"
            aria-label="Undo last point"
            disabled={empty}
            onClick={props.onRemoveLast}
          >
            <Undo2 className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Clear points"
            disabled={empty}
            onClick={props.onClear}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>

        {props.offline ? (
          <Alert>
            <AlertTitle>Offline mode</AlertTitle>
            <AlertDescription>
              The server was started with <code>--offline</code>, so routing is disabled. Waypoints
              still save; the preview needs Valhalla.
            </AlertDescription>
          </Alert>
        ) : null}

        {/* The server's own words, verbatim -- a blank map with no explanation
            is the failure mode the spec calls out by name. */}
        {props.routeError ? (
          <Alert variant="destructive">
            <AlertTitle>Routing failed</AlertTitle>
            <AlertDescription>{props.routeError}</AlertDescription>
          </Alert>
        ) : null}
        {props.loadError ? (
          <Alert variant="destructive">
            <AlertTitle>Could not read the config</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              <span>{props.loadError}</span>
              <Button variant="outline" size="sm" onClick={props.onReloadPresets}>
                <RefreshCw className="size-4" /> Retry
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        {/* Settings */}
        <div className="grid gap-2">
          <Label htmlFor="opt-pace">Pace</Label>
          <Select
            value={props.settings.pace ?? ""}
            onValueChange={(value) => set("pace", value === "" ? null : value)}
          >
            <SelectTrigger id="opt-pace">
              <SelectValue placeholder="walk" />
            </SelectTrigger>
            <SelectContent>
              {props.paces.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  <span className="flex w-full items-baseline justify-between gap-3">
                    <span>{p.name}</span>
                    <span className="text-muted-foreground font-mono text-xs tabular-nums">
                      {formatSpeed(p.speed_mps)}
                    </span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {/* The selected pace's speed, spelled out under the closed select --
              the value inside a collapsed SelectValue is the name alone, so
              without this the speed is only visible while the menu is open. */}
          <p className="text-muted-foreground text-xs">
            {selectedPace
              ? formatPaceSpeed(selectedPace.speed_mps)
              : "Speed only — it does not affect how the route is planned."}
          </p>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="opt-costing">Routing mode</Label>
          <Select
            value={props.settings.costing}
            onValueChange={(value) => {
              if (value !== null) set("costing", value)
            }}
          >
            <SelectTrigger id="opt-costing" disabled={props.offline}>
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
          <p className="text-muted-foreground text-xs">
            Which paths the route follows. Independent of the pace.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Switch
            id="opt-loop"
            checked={props.settings.loop}
            onCheckedChange={(checked) => set("loop", checked)}
          />
          <Label htmlFor="opt-loop">Loop the route</Label>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="opt-duration">Duration (min, blank = until the route ends)</Label>
          <Input
            id="opt-duration"
            inputMode="decimal"
            placeholder="60"
            value={props.settings.durationMin}
            onChange={(event) => set("durationMin", event.target.value)}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="opt-scatter">GPS scatter (metres, 0–100)</Label>
          <Input
            id="opt-scatter"
            type="number"
            min={0}
            max={100}
            step={1}
            inputMode="decimal"
            value={props.settings.scatterM}
            onChange={(event) => set("scatterM", event.target.value)}
          />
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            className="flex-1"
            disabled={props.route.waypoints.length < 2}
            onClick={() => {
              setSaveName(props.route.name ?? "")
              setSaveError(null)
              setSaveOpen(true)
            }}
          >
            <Save className="size-4" /> Save as…
          </Button>
          <Button className="flex-1" disabled={!canStart(props.route) || starting} onClick={onStart}>
            {starting ? <Spinner className="size-4" /> : <Play className="size-4" />} Start
          </Button>
        </div>
        {startError ? (
          <p className="text-destructive text-xs" title={startError}>
            {startError}
          </p>
        ) : null}
      </div>

      {/* Saved routes */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <h3 className="text-muted-foreground px-4 pt-4 pb-1 text-xs font-medium tracking-wide uppercase">
          Saved routes
        </h3>
        {props.loading ? (
          <div className="flex items-center gap-2 px-4 pb-3 text-sm">
            <Spinner className="size-4" /> Loading routes…
          </div>
        ) : props.loadError ? null : props.presets.length === 0 ? (
          <p className="text-muted-foreground px-4 pb-3 text-sm">
            No saved routes yet. Draw one on the map and save it — it lands in
            <code className="mx-1">~/.config/ios-loc/config.toml</code>, so
            <code className="mx-1">ios-loc walk &lt;name&gt;</code> works on it too.
          </p>
        ) : (
          <ul className="divide-border divide-y border-y">
            {props.presets.map((preset) => (
              <LibraryRow
                key={preset.name}
                icon={<MapPin className="text-muted-foreground size-4 shrink-0" />}
                title={preset.name}
                subtitle={`${preset.waypoints.length} waypoints · ${preset.pace} · ${
                  preset.costing
                }${preset.loop ? " · loop" : ""}`}
                selected={props.route.name === preset.name}
                onSelect={() => props.onSelectPreset(preset)}
                onDelete={() => props.onDeletePreset(preset.name)}
              />
            ))}
          </ul>
        )}
      </div>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save this route</DialogTitle>
            <DialogDescription>
              Saving rewrites the <code>[presets.*]</code> tables in your config. Comments and hand
              formatting inside those tables are lost; everything else is preserved byte for byte.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="save-name">Name</Label>
            <Input
              id="save-name"
              value={saveName}
              placeholder="riverside-loop"
              onChange={(event) => setSaveName(event.target.value)}
            />
          </div>
          {saveError ? (
            <Alert variant="destructive">
              <AlertTitle>Could not save</AlertTitle>
              <AlertDescription>{saveError}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button disabled={saveName.trim().length === 0 || saving} onClick={onSave}>
              {saving ? <Spinner className="size-4" /> : <Save className="size-4" />} Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
