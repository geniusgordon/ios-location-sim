import { MapPin, RefreshCw } from "lucide-react"
import type { Preset } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Spinner } from "@/components/ui/spinner"

export interface RouteLibraryProps {
  open: boolean
  onOpenChange(open: boolean): void
  presets: Preset[]
  selectedName: string | null
  loading: boolean
  loadError: string | null
  onReload(): void
  onSelect(preset: Preset): void
}

export default function RouteLibrary(props: RouteLibraryProps) {
  return (
    // Non-modal, no overlay, no outside-press dismissal, and cleared off the
    // h-14 dock. A modal Sheet renders a backdrop over the map and swallows
    // every map click -- and clicking the map with this open is the whole point.
    // The `data-[side=left]:` prefixes are load-bearing: unprefixed classes lose
    // to sheet.tsx's own variant-prefixed inset-y-0/h-full under tailwind-merge.
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
          <SheetTitle>Saved routes</SheetTitle>
          <SheetDescription>
            Pick one to load it onto the map. Editing it afterwards makes it a new, unnamed route.
          </SheetDescription>
          {/* Surfaced here as well as on the dock: a failed /api/presets also
              empties the Profile select in the options popover, and an empty
              select with no explanation reads as a bug in the app. */}
          {props.loadError ? (
            <Alert variant="destructive" className="mt-2">
              <AlertTitle>Could not read the config</AlertTitle>
              <AlertDescription className="flex flex-col items-start gap-2">
                <span>{props.loadError}</span>
                <Button variant="outline" size="sm" onClick={props.onReload}>
                  <RefreshCw className="size-4" /> Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {props.loading ? (
            <div className="flex items-center gap-2 p-4 text-sm">
              <Spinner className="size-4" /> Loading routes…
            </div>
          ) : props.loadError ? null : props.presets.length === 0 ? (
            <p className="text-muted-foreground p-4 text-sm">
              No saved routes yet. Draw one on the map and save it from Options — it lands in
              <code className="mx-1">~/.config/ios-loc/config.toml</code>, so
              <code className="mx-1">ios-loc walk &lt;name&gt;</code> works on it too.
            </p>
          ) : (
            <ul className="divide-border divide-y">
              {props.presets.map((preset) => (
                <li key={preset.name}>
                  <button
                    type="button"
                    onClick={() => props.onSelect(preset)}
                    className={`hover:bg-accent flex w-full items-center gap-3 px-4 py-3 text-left ${
                      props.selectedName === preset.name ? "bg-accent" : ""
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
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
