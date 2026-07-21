import { RefreshCw } from "lucide-react"
import type { LatLon, Preset } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import PresetList from "@/components/PresetList"
import RouteEditor from "@/components/RouteEditor"
import StartForm from "@/components/StartForm"
import { isRunning } from "@/state/walkReducer"
import { useWalkMeta } from "@/hooks/useWalkStream"

export type SidebarMode = "presets" | "editor" | "start"

const TITLE: Record<SidebarMode, string> = {
  presets: "Presets",
  editor: "Route editor",
  start: "Start a walk",
}

export interface SidebarProps {
  open: boolean
  onOpenChange(open: boolean): void
  mode: SidebarMode
  onModeChange(mode: SidebarMode): void
  presets: Preset[]
  profiles: string[]
  offline: boolean
  loading: boolean
  loadError: string | null
  onReloadPresets(): void
  selectedPreset: string | null
  onSelectPreset(preset: Preset): void
  draftWaypoints: LatLon[]
  onClearWaypoints(): void
  onRemoveLast(): void
  presetLoop: boolean
  lengthM: number | null
  routeError: string | null
  routePending: boolean
  costing: string
  onCostingChange(costing: string): void
  onPresetSaved(name: string): void
  onStarted(): void
}

export default function Sidebar(props: SidebarProps) {
  const meta = useWalkMeta()
  const locked = isRunning(meta.state)

  return (
    <Sheet
      open={props.open}
      onOpenChange={props.onOpenChange}
      modal={false}
      disablePointerDismissal
    >
      <SheetContent
        side="left"
        showOverlay={false}
        className="data-[side=left]:bottom-14 data-[side=left]:h-auto flex w-100 flex-col gap-0 p-0 sm:max-w-100"
      >
        <SheetHeader className="border-b">
          <SheetTitle>{TITLE[props.mode]}</SheetTitle>
          <SheetDescription>
            {props.offline
              ? "Offline mode: routing is disabled, saved presets still work."
              : "Pick a preset, draw a route, or start a walk."}
          </SheetDescription>
          <div className="flex gap-2 pt-2">
            {(["presets", "editor", "start"] as const).map((mode) => (
              <Button
                key={mode}
                size="sm"
                variant={props.mode === mode ? "default" : "outline"}
                onClick={() => props.onModeChange(mode)}
                disabled={mode === "editor" && locked}
                title={mode === "editor" && locked ? "Stop the walk to edit a route" : undefined}
              >
                {TITLE[mode]}
              </Button>
            ))}
          </div>
          {/* Surfaced here, not inside PresetList: a failed /api/presets also
              empties the Profile selects in the editor and the start form, and
              an empty select with no explanation reads as a bug in the app. */}
          {props.loadError ? (
            <Alert variant="destructive" className="mt-2">
              <AlertTitle>Could not read the config</AlertTitle>
              <AlertDescription className="flex flex-col items-start gap-2">
                <span>{props.loadError}</span>
                <Button variant="outline" size="sm" onClick={props.onReloadPresets}>
                  <RefreshCw className="size-4" /> Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {props.mode === "presets" ? (
            <PresetList
              presets={props.presets}
              selectedPreset={props.selectedPreset}
              loading={props.loading}
              loadError={props.loadError}
              onSelect={props.onSelectPreset}
            />
          ) : null}
          {props.mode === "editor" ? (
            <RouteEditor
              waypoints={props.draftWaypoints}
              onClearWaypoints={props.onClearWaypoints}
              onRemoveLast={props.onRemoveLast}
              profiles={props.profiles}
              offline={props.offline}
              lengthM={props.lengthM}
              routeError={props.routeError}
              pending={props.routePending}
              costing={props.costing}
              onCostingChange={props.onCostingChange}
              onSaved={props.onPresetSaved}
            />
          ) : null}
          {props.mode === "start" ? (
            <StartForm
              presetName={props.selectedPreset}
              presetLoop={props.presetLoop}
              waypoints={props.draftWaypoints}
              profiles={props.profiles}
              costing={props.costing}
              offline={props.offline}
              onStarted={props.onStarted}
            />
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}
