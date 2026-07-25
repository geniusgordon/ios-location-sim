import { useEffect, useState } from "react"
import { MapPin, Pin, Save, X } from "lucide-react"
import type { LatLon, Place } from "@/api/types"
import { errorText, pinLocation, savePlace } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import LibraryRow from "@/components/LibraryRow"
import { formatLatLon, parseLatLon } from "@/lib/coords"

export interface LocationPanelProps {
  /** A walk owns the device -- setting mid-walk 409s. Disables the controls. */
  disabled: boolean
  /** Whether a device is currently reachable. When false, Set/tap/place-select
   *  still picks (marker + save form) but never pushes to a phone. */
  deviceConnected: boolean
  /** The currently set/target coordinate, shown in the form and saved by Save. */
  lastPin: LatLon | null
  /** Called after a coordinate-typed set. `recenter` asks the map to fly there. */
  onPinned(point: LatLon, opts?: { recenter?: boolean }): void
  onPlaceSaved(): void
  /** True while a location is currently held (meta.state === "pinned"). */
  held: boolean
  /** Releases the held location (DELETE /api/walk). */
  onClear(): Promise<void>
  /** A failed set-location map tap, surfaced from App. */
  pinError: string | null
  places: Place[]
  placesLoading: boolean
  onSelectPlace(place: Place): void
  onDeletePlace(name: string): Promise<void>
}

export default function LocationPanel(props: LocationPanelProps) {
  const [text, setText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pinning, setPinning] = useState(false)
  const [placeName, setPlaceName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [clearing, setClearing] = useState(false)

  // The coordinate input is the single source of truth for both Set and Save.
  // Syncing it from lastPin (a map tap or a selected place) is what makes "what
  // you save" always equal "what you see": no separate last-pin/input split.
  useEffect(() => {
    if (props.lastPin) setText(formatLatLon(props.lastPin))
  }, [props.lastPin])

  const shown = parseLatLon(text)
  const shownValid = "point" in shown

  const onSubmit = async () => {
    if (!shownValid) {
      setError(shown.error)
      return
    }
    setError(null)
    props.onPinned(shown.point, { recenter: true }) // pick: marker + fills save form
    if (!props.deviceConnected) return // no device: picked for saving only
    setPinning(true)
    try {
      await pinLocation(shown.point[0], shown.point[1])
    } catch (err) {
      setError(errorText(err))
    } finally {
      setPinning(false)
    }
  }

  const onSave = async () => {
    if (!shownValid || placeName.trim() === "") return
    setSaving(true)
    setSaveError(null)
    try {
      await savePlace({ name: placeName.trim(), point: shown.point })
      setPlaceName("")
      props.onPlaceSaved()
    } catch (err) {
      setSaveError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  const onClear = async () => {
    setClearing(true)
    try {
      await props.onClear()
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-3 border-b p-4">
        {props.held && props.lastPin ? (
          <div className="bg-accent flex items-center justify-between gap-2 rounded-md px-3 py-2 text-xs">
            <span className="font-mono tabular-nums">Location set {formatLatLon(props.lastPin)}</span>
            <Button
              variant="ghost"
              size="icon"
              className="size-6 shrink-0"
              aria-label="Clear the set location"
              disabled={clearing}
              onClick={onClear}
            >
              {clearing ? <Spinner className="size-3" /> : <X className="size-3" />}
            </Button>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            {props.disabled
              ? "Stop the walk before setting a location."
              : "Tap the map to set the device location, or enter coordinates below."}
          </p>
        )}

        <Input
          aria-label="Coordinates to set the device to"
          placeholder="48.858666,2.293991"
          value={text}
          onChange={(event) => setText(event.target.value)}
          disabled={props.disabled}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !pinning && !props.disabled) onSubmit()
          }}
        />
        <Button size="sm" disabled={pinning || props.disabled} onClick={onSubmit}>
          {pinning ? <Spinner className="size-4" /> : <MapPin className="size-4" />} Set to coordinates
        </Button>

        {!props.deviceConnected && !props.disabled ? (
          <p className="text-muted-foreground text-xs">
            No device connected — the coordinate is saved as a place, not pushed to a phone.
          </p>
        ) : null}
        {error ? (
          <p className="text-destructive text-xs" title={error}>
            {error}
          </p>
        ) : null}
        {props.pinError ? (
          <p className="text-destructive text-xs" title={props.pinError}>
            {props.pinError}
          </p>
        ) : null}

        {/* Always shown so saving is discoverable -- disabled until the shown
            coordinate is a valid lat,lon. */}
        <div className="mt-1 flex flex-col gap-2 border-t pt-3">
          <p className="text-muted-foreground text-xs">
            {shownValid
              ? "Name this coordinate to save it to your saved places."
              : "Set or type a valid coordinate above, then name it to save it here."}
          </p>
          <Input
            aria-label="Name for this place"
            placeholder="home"
            value={placeName}
            onChange={(event) => setPlaceName(event.target.value)}
            disabled={props.disabled || !shownValid}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !saving && shownValid) onSave()
            }}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={saving || !shownValid || placeName.trim() === ""}
            onClick={onSave}
          >
            {saving ? <Spinner className="size-4" /> : <Save className="size-4" />} Save place
          </Button>
          {saveError ? (
            <p className="text-destructive text-xs" title={saveError}>
              {saveError}
            </p>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <h3 className="text-muted-foreground px-4 pt-4 pb-1 text-xs font-medium tracking-wide uppercase">
          Saved places
        </h3>
        {props.disabled && props.places.length > 0 ? (
          <p className="text-muted-foreground px-4 pb-2 text-xs">
            Stop the walk to set the device to a saved place.
          </p>
        ) : null}
        {props.placesLoading ? (
          <div className="flex items-center gap-2 px-4 pb-3 text-sm">
            <Spinner className="size-4" /> Loading places…
          </div>
        ) : props.places.length === 0 ? (
          <p className="text-muted-foreground px-4 pb-3 text-sm">
            No saved places yet. Set a location above, then name it to save it here.
          </p>
        ) : (
          <ul className="divide-border divide-y border-y">
            {props.places.map((place) => (
              <LibraryRow
                key={place.name}
                icon={<Pin className="text-muted-foreground size-4 shrink-0" />}
                title={place.name}
                subtitle={`${place.point[0].toFixed(5)}, ${place.point[1].toFixed(5)}`}
                selected={false}
                selectDisabled={props.disabled}
                onSelect={() => props.onSelectPlace(place)}
                onDelete={() => props.onDeletePlace(place.name)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
