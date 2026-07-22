import { useState } from "react"
import { Keyboard, MapPin } from "lucide-react"
import { errorText, pinLocation } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Spinner } from "@/components/ui/spinner"
import { parseLatLon } from "@/lib/coords"

export interface PinControlProps {
  /** Armed: the next map tap pins instead of adding a waypoint. */
  armed: boolean
  onArmedChange(armed: boolean): void
  /** A walk owns the device -- pinning mid-walk 409s and would cost distance. */
  disabled: boolean
}

export default function PinControl(props: PinControlProps) {
  const [text, setText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pinning, setPinning] = useState(false)

  const onSubmit = async () => {
    const parsed = parseLatLon(text)
    if ("error" in parsed) {
      setError(parsed.error)
      return
    }
    setPinning(true)
    setError(null)
    try {
      await pinLocation(parsed.point[0], parsed.point[1])
      props.onArmedChange(false)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setPinning(false)
    }
  }

  return (
    <div className="flex items-center gap-1">
      {/* A toggle, not a button: aria-pressed plus the filled variant is what
          tells you the next map tap will pin rather than draw. */}
      <Button
        variant={props.armed ? "secondary" : "ghost"}
        size="sm"
        aria-label="Pin a location by tapping the map"
        aria-pressed={props.armed}
        disabled={props.disabled}
        onClick={() => props.onArmedChange(!props.armed)}
      >
        <MapPin className="size-4" /> Pin
      </Button>
      <Popover>
        <PopoverTrigger
          render={
            <Button variant="ghost" size="sm" aria-label="Pin by coordinates" disabled={props.disabled}>
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
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
