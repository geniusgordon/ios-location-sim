import { useEffect, useState } from "react"
import { Keyboard, MapPin, Save, X } from "lucide-react"
import type { LatLon } from "@/api/types"
import { errorText, pinLocation, savePlace } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Spinner } from "@/components/ui/spinner"
import { formatLatLon, parseLatLon } from "@/lib/coords"

export interface PinControlProps {
  armed: boolean
  onArmedChange(armed: boolean): void
  /** A walk owns the device -- setting mid-walk 409s. Disables the control. */
  disabled: boolean
  /** The currently set/target coordinate, shown in the control and saved by Save. */
  lastPin: LatLon | null
  /** Called after a coordinate-typed set. `recenter` asks the map to fly there. */
  onPinned(point: LatLon, opts?: { recenter?: boolean }): void
  onPlaceSaved(): void
  /** True while a location is currently held (meta.state === "pinned"). */
  held: boolean
  /** Releases the held location (DELETE /api/walk). */
  onClear(): Promise<void>
}

export default function PinControl(props: PinControlProps) {
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
    setPinning(true)
    setError(null)
    try {
      await pinLocation(shown.point[0], shown.point[1])
      props.onPinned(shown.point, { recenter: true })
      // Deliberately does NOT disarm: consecutive sets are the point.
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
    <div className="flex items-center gap-1">
      {props.held && props.lastPin ? (
        <span className="text-muted-foreground flex items-center gap-1 text-xs">
          <span className="font-mono tabular-nums">Location set {formatLatLon(props.lastPin)}</span>
          <Button
            variant="ghost"
            size="icon"
            className="size-6"
            aria-label="Clear the set location"
            disabled={clearing}
            onClick={onClear}
          >
            {clearing ? <Spinner className="size-3" /> : <X className="size-3" />}
          </Button>
        </span>
      ) : null}
      {/* A toggle, not a button: while armed, the next (and every subsequent)
          map tap sets the location instead of drawing a waypoint. */}
      <Button
        variant={props.armed ? "secondary" : "ghost"}
        size="sm"
        aria-label="Set a location by tapping the map"
        aria-pressed={props.armed}
        disabled={props.disabled}
        onClick={() => props.onArmedChange(!props.armed)}
      >
        <MapPin className="size-4" /> Set location
      </Button>
      <Popover>
        <PopoverTrigger
          render={
            <Button variant="ghost" size="sm" aria-label="Set location by coordinates" disabled={props.disabled}>
              <Keyboard className="size-4" />
            </Button>
          }
        />
        <PopoverContent align="end" side="top" className="w-80">
          <div className="flex flex-col gap-2">
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
              {pinning ? <Spinner className="size-4" /> : <MapPin className="size-4" />} Set location
            </Button>
            {error ? (
              <p className="text-destructive text-xs" title={error}>
                {error}
              </p>
            ) : null}
            {props.disabled ? (
              <p className="text-muted-foreground text-xs">Stop the walk before setting a location.</p>
            ) : null}
            {shownValid ? (
              <div className="mt-2 flex flex-col gap-2 border-t pt-2">
                <p className="text-muted-foreground text-xs">
                  Name this coordinate to save it to your saved places.
                </p>
                <Input
                  aria-label="Name for this place"
                  placeholder="home"
                  value={placeName}
                  onChange={(event) => setPlaceName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !saving) onSave()
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  disabled={saving || placeName.trim() === ""}
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
            ) : null}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
