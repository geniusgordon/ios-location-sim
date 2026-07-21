import { MapPin, RefreshCw } from "lucide-react"
import type { Preset } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

export interface PresetListProps {
  presets: Preset[]
  selectedPreset: string | null
  loading: boolean
  loadError: string | null
  onSelect(preset: Preset): void
  onReload(): void
}

export default function PresetList(props: PresetListProps) {
  if (props.loading) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm">
        <Spinner className="size-4" /> Loading presets…
      </div>
    )
  }

  if (props.loadError) {
    return (
      <div className="p-4">
        <Alert variant="destructive">
          <AlertTitle>Could not read the config</AlertTitle>
          <AlertDescription>{props.loadError}</AlertDescription>
        </Alert>
        <Button variant="outline" size="sm" className="mt-3" onClick={props.onReload}>
          <RefreshCw className="size-4" /> Retry
        </Button>
      </div>
    )
  }

  if (props.presets.length === 0) {
    return (
      <p className="text-muted-foreground p-4 text-sm">
        No presets in the config yet. Draw a route in the editor and save it — it lands in
        <code className="mx-1">~/.config/ios-loc/config.toml</code>, so
        <code className="mx-1">ios-loc walk &lt;name&gt;</code> works on it too.
      </p>
    )
  }

  return (
    <ul className="divide-border divide-y">
      {props.presets.map((preset) => (
        <li key={preset.name}>
          <button
            type="button"
            onClick={() => props.onSelect(preset)}
            className={`hover:bg-accent flex w-full items-center gap-3 px-4 py-3 text-left ${
              props.selectedPreset === preset.name ? "bg-accent" : ""
            }`}
          >
            <MapPin className="text-muted-foreground size-4 shrink-0" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{preset.name}</span>
              <span className="text-muted-foreground block text-xs">
                {preset.waypoints.length} waypoints · {preset.profile}
                {preset.loop ? " · loop" : ""}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
