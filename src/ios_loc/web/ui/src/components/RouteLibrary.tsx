import { useState, type ReactNode } from "react"
import { MapPin, Pin, RefreshCw, Trash2 } from "lucide-react"
import type { Place, Preset } from "@/api/types"
import { errorText } from "@/api/client"
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
  places: Place[]
  selectedName: string | null
  loading: boolean
  loadError: string | null
  onReload(): void
  onSelect(preset: Preset): void
  /** Pins the device at this place and closes the sheet. */
  onSelectPlace(place: Place): void
  /** Rejects with an ApiError whose message is shown on the row. */
  onDeletePreset(name: string): Promise<void>
  onDeletePlace(name: string): Promise<void>
}

interface LibraryRowProps {
  icon: ReactNode
  title: string
  subtitle: string
  selected: boolean
  onSelect(): void
  onDelete(): Promise<void>
}

function LibraryRow(props: LibraryRowProps) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onConfirm = async () => {
    setDeleting(true)
    setError(null)
    try {
      await props.onDelete()
      // No setConfirming(false): a successful delete unmounts this row.
    } catch (err) {
      // Stay in the confirming state so the action can simply be retried.
      setError(errorText(err))
    } finally {
      setDeleting(false)
    }
  }

  if (confirming) {
    return (
      <li className="px-4 py-3">
        <p className="text-sm">
          Delete <span className="font-medium">{props.title}</span>?
        </p>
        <p className="text-muted-foreground text-xs">This rewrites your config file.</p>
        <div className="mt-2 flex gap-2">
          <Button variant="outline" size="sm" disabled={deleting} onClick={() => setConfirming(false)}>
            Cancel
          </Button>
          <Button variant="destructive" size="sm" disabled={deleting} onClick={onConfirm}>
            {deleting ? <Spinner className="size-4" /> : <Trash2 className="size-4" />} Delete
          </Button>
        </div>
        {error ? (
          <p className="text-destructive mt-2 text-xs" title={error}>
            {error}
          </p>
        ) : null}
      </li>
    )
  }

  return (
    <li className="flex items-center">
      <button
        type="button"
        onClick={props.onSelect}
        className={`hover:bg-accent flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left ${
          props.selected ? "bg-accent" : ""
        }`}
      >
        {props.icon}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{props.title}</span>
          <span className="text-muted-foreground block text-xs">{props.subtitle}</span>
        </span>
      </button>
      <Button
        variant="ghost"
        size="sm"
        className="mr-2 shrink-0"
        aria-label={`Delete ${props.title}`}
        onClick={() => setConfirming(true)}
      >
        <Trash2 className="size-4" />
      </Button>
    </li>
  )
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
            Pick a route to load it onto the map, or a place to set the device there. Editing a
            route afterwards makes it a new, unnamed route.
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
          ) : props.loadError ? null : (
            <>
              <h3 className="text-muted-foreground px-4 pt-4 pb-1 text-xs font-medium tracking-wide uppercase">
                Routes
              </h3>
              {props.presets.length === 0 ? (
                <p className="text-muted-foreground px-4 pb-3 text-sm">
                  No saved routes yet. Draw one on the map and save it from Options — it lands in
                  <code className="mx-1">~/.config/ios-loc/config.toml</code>, so
                  <code className="mx-1">ios-loc walk &lt;name&gt;</code> works on it too.
                </p>
              ) : (
                <ul className="divide-border divide-y border-b">
                  {props.presets.map((preset) => (
                    <LibraryRow
                      key={preset.name}
                      icon={<MapPin className="text-muted-foreground size-4 shrink-0" />}
                      title={preset.name}
                      subtitle={`${preset.waypoints.length} waypoints · ${preset.profile}${
                        preset.loop ? " · loop" : ""
                      }`}
                      selected={props.selectedName === preset.name}
                      onSelect={() => props.onSelect(preset)}
                      onDelete={() => props.onDeletePreset(preset.name)}
                    />
                  ))}
                </ul>
              )}

              <h3 className="text-muted-foreground px-4 pt-4 pb-1 text-xs font-medium tracking-wide uppercase">
                Places
              </h3>
              {props.places.length === 0 ? (
                <p className="text-muted-foreground px-4 pb-3 text-sm">
                  No saved places yet. Set a location with the Pin button, then name it to save it
                  here.
                </p>
              ) : (
                <ul className="divide-border divide-y border-b">
                  {props.places.map((place) => (
                    <LibraryRow
                      key={place.name}
                      icon={<Pin className="text-muted-foreground size-4 shrink-0" />}
                      title={place.name}
                      subtitle={`${place.point[0].toFixed(5)}, ${place.point[1].toFixed(5)}`}
                      selected={false}
                      onSelect={() => props.onSelectPlace(place)}
                      onDelete={() => props.onDeletePlace(place.name)}
                    />
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
