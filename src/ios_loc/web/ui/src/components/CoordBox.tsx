import { useState } from "react"
import { MapPin } from "lucide-react"
import { errorText, pinLocation } from "@/api/client"
import { parseLatLon } from "@/lib/coords"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { isRunning } from "@/state/walkReducer"
import { useWalkMeta } from "@/hooks/useWalkStream"

export default function CoordBox() {
  const meta = useWalkMeta()
  // A walk owns the device; setting a location mid-walk would 409 and destroy
  // the run's distance. A pin does not lock this out -- re-pinning is allowed.
  const walking = isRunning(meta.state)

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
    } catch (err) {
      setError(errorText(err))
    } finally {
      setPinning(false)
    }
  }

  return (
    <div className="absolute left-1/2 top-3 z-10 w-[min(92vw,26rem)] -translate-x-1/2">
      <div className="bg-background/95 flex items-center gap-2 rounded-lg border p-2 shadow-md backdrop-blur">
        <Input
          aria-label="Coordinates to set the device to"
          placeholder="48.858666,2.293991"
          value={text}
          disabled={walking}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !walking) onSubmit()
          }}
        />
        <Button size="sm" disabled={walking || pinning} onClick={onSubmit}>
          <MapPin className="size-4" /> Set
        </Button>
      </div>
      {walking ? (
        <p className="text-muted-foreground mt-1 px-1 text-xs">
          Stop the walk before setting a location.
        </p>
      ) : null}
      {error ? (
        <p className="text-destructive mt-1 px-1 text-xs" title={error}>
          {error}
        </p>
      ) : null}
    </div>
  )
}
