import { MapPin } from "lucide-react"
import type { Preset } from "@/api/types"
import { Spinner } from "@/components/ui/spinner"

export interface PresetListProps {
  presets: Preset[]
  selectedPreset: string | null
  loading: boolean
  loadError: string | null
  onSelect(preset: Preset): void
}

export default function PresetList(props: PresetListProps) {
  if (props.loading) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm">
        <Spinner className="size-4" /> Loading presets…
      </div>
    )
  }

  // The sidebar header owns the error and its Retry, so every mode sees it.
  // Bail out here anyway: "no presets yet" is a lie when the load failed.
  if (props.loadError) return null

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
