import type { LatLon, Preset } from "@/api/types"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import PresetList from "@/components/PresetList"

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
}

export default function Sidebar(props: SidebarProps) {
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent side="left" className="flex w-100 flex-col gap-0 p-0 sm:max-w-100">
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
              >
                {TITLE[mode]}
              </Button>
            ))}
          </div>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {props.mode === "presets" ? (
            <PresetList
              presets={props.presets}
              selectedPreset={props.selectedPreset}
              loading={props.loading}
              loadError={props.loadError}
              onSelect={props.onSelectPreset}
              onReload={props.onReloadPresets}
            />
          ) : null}
          {props.mode === "editor" ? (
            <p className="text-muted-foreground p-4 text-sm">
              {props.draftWaypoints.length} waypoints. The editor lands in the next task.
            </p>
          ) : null}
          {props.mode === "start" ? (
            <p className="text-muted-foreground p-4 text-sm">
              Profiles: {props.profiles.join(", ") || "—"}. The start form lands in the next task.
            </p>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}
