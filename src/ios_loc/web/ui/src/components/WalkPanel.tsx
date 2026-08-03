import { useRef, useState } from "react"
import {
  Check,
  ClipboardPaste,
  MapPin,
  Play,
  RefreshCw,
  Save,
  Square,
  Trash2,
  Undo2,
  Upload,
} from "lucide-react"
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
import { Tabs, TabsList, TabsPanel, TabsTab } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import LibraryRow from "@/components/LibraryRow"
import { COSTINGS } from "@/lib/costings"
import { pasteRoute, type DraftRoute, type DraftSettings } from "@/lib/draft"
import { gpxToRoute, type GpxPointType } from "@/lib/gpx"
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

/**
 * The heading over a summary. The badge alone reads as a live panel that has
 * stalled; a title says the run is over and the numbers are final.
 */
function summaryTitle(state: WalkStateName): string {
  if (state === "error") return "Device lost"
  if (state === "finished") return "Walk finished"
  return "Walk ended"
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
function LiveWalkPanel(props: {
  /** Drop the summary and go back to the editor. */
  onDismiss(): void
  /** Re-run the same route; null when the draft is no longer startable. */
  onRestart: (() => Promise<void>) | null
}) {
  const { fix, stats, state } = useWalkTelemetry()
  const meta = useWalkMeta()
  // Which footer action is in flight, so the spinner lands on the button that
  // was actually clicked rather than on both.
  const [busy, setBusy] = useState<"stop" | "done" | "restart" | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // The device is held -> Stop. The run is over and the session is already
  // torn down -> there is nothing to stop, so the footer must offer a way out
  // instead. A disabled Stop as the panel's only control is a dead end.
  const held = canStop(state)

  const run = async (which: "stop" | "done" | "restart", action: () => Promise<unknown>) => {
    setBusy(which)
    setActionError(null)
    try {
      await action()
    } catch (error) {
      setActionError(errorText(error))
    } finally {
      setBusy(null)
    }
  }

  const onStop = () => run("stop", () => stopWalk())

  const onDone = () =>
    run("done", async () => {
      // Not just a local dismiss: the service keeps reporting `finished` with
      // this run's route and trail until something clears it, so a reload
      // would resurrect the summary. DELETE returns it to idle.
      await stopWalk()
      props.onDismiss()
    })

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-4 p-4">
        {/* Live: the badge is the state. Terminal: the title says it in words,
            so the badge would only repeat itself ("Device lost" / "device
            lost") -- the route's name is the useful thing to keep beside it. */}
        {held ? (
          <div className="flex items-center gap-2">
            <Badge variant={tone(state)}>{chipLabel(state, fix?.paused ?? false)}</Badge>
            {meta.preset_name ? (
              <span className="min-w-0 truncate text-sm font-medium" title={meta.preset_name}>
                {meta.preset_name}
              </span>
            ) : null}
          </div>
        ) : (
          <div className="flex min-w-0 flex-col">
            <h3 className={`text-sm font-semibold ${state === "error" ? "text-destructive" : ""}`}>
              {summaryTitle(state)}
            </h3>
            {meta.preset_name ? (
              <span className="text-muted-foreground truncate text-xs" title={meta.preset_name}>
                {meta.preset_name}
              </span>
            ) : null}
          </div>
        )}

        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          <Stat label="elapsed" value={formatDuration(stats?.elapsed_s ?? 0)} />
          <Stat label="distance" value={formatDistance(stats?.distance_m ?? 0)} />
          {/* Live only: `speed` comes from the last fix, so on a finished run
              it is a frozen instantaneous reading that looks like a hang. */}
          {held ? <Stat label="speed" value={formatSpeed(fix?.speed_mps ?? 0)} /> : null}
          <Stat label="laps" value={String(stats?.laps ?? 0)} />
          <Stat label="reconnects" value={String(stats?.reconnects ?? 0)} />
        </div>

        {/* The server's own words, never paraphrased. */}
        {meta.error ? (
          <p className="text-destructive text-xs" title={meta.error}>
            {meta.error}
          </p>
        ) : null}
        {actionError ? <p className="text-destructive text-xs">{actionError}</p> : null}

        {held ? (
          <Button
            variant="destructive"
            className="w-full"
            disabled={busy !== null}
            onClick={onStop}
          >
            {busy === "stop" ? <Spinner className="size-4" /> : <Square className="size-4" />} Stop
          </Button>
        ) : (
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              disabled={busy !== null}
              onClick={onDone}
            >
              {busy === "done" ? <Spinner className="size-4" /> : <Check className="size-4" />} Done
            </Button>
            {props.onRestart ? (
              <Button
                className="flex-1"
                disabled={busy !== null}
                onClick={() => run("restart", props.onRestart!)}
              >
                {busy === "restart" ? <Spinner className="size-4" /> : <Play className="size-4" />}{" "}
                Walk again
              </Button>
            ) : null}
          </div>
        )}
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
  onPaste(route: DraftRoute): void
  onSaved(name: string): void
  onStarted(): void
  /** True while a finished/lost run's summary should stay on screen even
   *  though the draft route (still on the map) is non-empty. */
  showSummary: boolean
  /** Take the summary down — the explicit exit from a terminal state. */
  onDismissSummary(): void
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
  const [importOpen, setImportOpen] = useState(false)
  const [importTab, setImportTab] = useState<"coords" | "gpx">("coords")
  const [pasteText, setPasteText] = useState("")
  const [gpxText, setGpxText] = useState("")
  const [gpxPointType, setGpxPointType] = useState<GpxPointType>("auto")
  const [importError, setImportError] = useState<string | null>(null)
  // Defaults to literal (today's behavior) every time the dialog opens, rather
  // than remembering the last choice. Shared by both tabs -- it means the same
  // thing for a pasted coordinate list and a GPX track.
  const [pasteLiteral, setPasteLiteral] = useState(true)
  const gpxInputRef = useRef<HTMLInputElement>(null)

  const set = <K extends keyof DraftSettings>(key: K, value: DraftSettings[K]) => {
    props.onSettingsChange({ ...props.settings, [key]: value })
  }

  // Throws, unlike onStart: the summary's "Walk again" reports a failed start
  // through its own footer, not through this panel's startError (which is only
  // rendered in the editor branch below and would be invisible there).
  const beginWalk = async () => {
    await startWalk(startBody(props.route, props.settings))
    props.onStarted()
  }

  const onStart = async () => {
    setStarting(true)
    setStartError(null)
    try {
      await beginWalk()
    } catch (error) {
      setStartError(errorText(error))
    } finally {
      setStarting(false)
    }
  }

  // A walk (or a finished/lost run's still-pinned summary) shows the live view.
  // A bare pinned location does NOT -- it stays editable so the next location
  // can be set from the Set-location tab without stopping first.
  if (showsLiveDock(meta.state, props.showSummary)) {
    return (
      <LiveWalkPanel
        onDismiss={props.onDismissSummary}
        // The draft route survives a run, so re-running it is one click. Absent
        // when there is nothing to re-run -- e.g. a walk this tab did not start.
        onRestart={canStart(props.route) ? beginWalk : null}
      />
    )
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

  const onImportSubmit = () => {
    const result =
      importTab === "coords"
        ? pasteRoute(pasteText, pasteLiteral)
        : gpxToRoute(gpxText, pasteLiteral, gpxPointType)
    if ("error" in result) {
      setImportError(result.error)
      return
    }
    setImportError(null)
    setImportOpen(false)
    setPasteText("")
    setGpxText("")
    // "Route between these points" is about turning an imported list into a
    // walkable route, not about picking a travel mode -- always plan it on
    // foot regardless of whatever Routing mode the select last showed.
    if (!pasteLiteral) props.onSettingsChange({ ...props.settings, costing: "pedestrian" })
    props.onPaste(result)
  }

  // Loads a file's text into the GPX tab's textarea rather than importing it
  // straight away -- same submit path as pasted GPX text, so a file pick is
  // just a way to fill the textarea instead of typing into it.
  const onGpxFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ""
    if (!file) return
    setGpxText(await file.text())
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
            aria-label="Import route"
            onClick={() => {
              setImportError(null)
              setPasteText("")
              setGpxText("")
              setGpxPointType("auto")
              setPasteLiteral(true)
              setImportTab("coords")
              setImportOpen(true)
            }}
          >
            <ClipboardPaste className="size-4" />
          </Button>
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
            <SelectTrigger id="opt-costing" disabled={props.offline || props.route.literal}>
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
            {props.route.literal
              ? "No effect on a pasted route — it is walked exactly as given."
              : "Which paths the route follows. Independent of the pace."}
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
            disabled={props.route.waypoints.length < 2 || props.route.literal}
            title={props.route.literal ? "Pasted routes can't be saved as a preset yet" : undefined}
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

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Import a route</DialogTitle>
            <DialogDescription>Replaces the current route.</DialogDescription>
          </DialogHeader>

          <Tabs value={importTab} onValueChange={(value) => setImportTab(value as "coords" | "gpx")}>
            <TabsList>
              <TabsTab value="coords">Coordinates</TabsTab>
              <TabsTab value="gpx">GPX</TabsTab>
            </TabsList>
            <TabsPanel value="coords" className="grid gap-2">
              <Label htmlFor="paste-coords">Coordinates</Label>
              <Textarea
                id="paste-coords"
                rows={10}
                className="min-h-40 font-mono text-xs"
                placeholder={"19.0370900, 78.6447320\n19.0381340, 78.6466280"}
                value={pasteText}
                onChange={(event) => setPasteText(event.target.value)}
              />
              <p className="text-muted-foreground text-xs">
                One <code>latitude, longitude</code> pair per line.
              </p>
            </TabsPanel>
            <TabsPanel value="gpx" className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="paste-gpx">GPX</Label>
                <input
                  ref={gpxInputRef}
                  type="file"
                  accept=".gpx,application/gpx+xml"
                  className="hidden"
                  onChange={onGpxFile}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => gpxInputRef.current?.click()}
                >
                  <Upload className="size-4" /> Choose file…
                </Button>
              </div>
              <Textarea
                id="paste-gpx"
                rows={10}
                className="min-h-40 font-mono text-xs"
                placeholder={'<gpx>\n  <trk><trkseg>\n    <trkpt lat="..." lon="..."/>\n  </trkseg></trk>\n</gpx>'}
                value={gpxText}
                onChange={(event) => setGpxText(event.target.value)}
              />
              <div className="grid gap-2">
                <Label htmlFor="gpx-point-type">Read points from</Label>
                <Select
                  value={gpxPointType}
                  onValueChange={(value) => setGpxPointType(value as GpxPointType)}
                >
                  <SelectTrigger id="gpx-point-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto (track, then route, then waypoints)</SelectItem>
                    <SelectItem value="trkpt">Track points (trkpt)</SelectItem>
                    <SelectItem value="rtept">Route points (rtept)</SelectItem>
                    <SelectItem value="wpt">Waypoints (wpt)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </TabsPanel>
          </Tabs>

          <div className="flex items-center gap-2">
            <Switch
              id="import-route"
              checked={!pasteLiteral}
              onCheckedChange={(checked) => setPasteLiteral(!checked)}
            />
            <Label htmlFor="import-route">Route between these points</Label>
          </div>
          <p className="text-muted-foreground text-xs">
            {pasteLiteral
              ? "Walked exactly as given — no road-snapping."
              : "Planned as a pedestrian route connecting these points."}
          </p>

          {importError ? (
            <Alert variant="destructive">
              <AlertTitle>Could not parse</AlertTitle>
              <AlertDescription>{importError}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button
              disabled={(importTab === "coords" ? pasteText : gpxText).trim().length === 0}
              onClick={onImportSubmit}
            >
              <ClipboardPaste className="size-4" /> Use these points
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
