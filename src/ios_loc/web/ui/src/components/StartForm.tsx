import { useEffect, useState } from "react"
import { Play } from "lucide-react"
import { errorText, startWalk } from "@/api/client"
import type { LatLon, StartRequest } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { isRunning } from "@/state/walkReducer"
import { useWalkMeta } from "@/hooks/useWalkStream"

export interface StartFormProps {
  presetName: string | null
  /** The selected preset's own `loop`, so the switch can show the truth. */
  presetLoop: boolean
  waypoints: LatLon[]
  profiles: string[]
  costing: string
  offline: boolean
  onStarted(): void
}

export default function StartForm(props: StartFormProps) {
  const meta = useWalkMeta()
  const running = isRunning(meta.state)

  // Empty means "inherit the preset / profile default" -- the backend already
  // treats null that way, so an empty box must send null, never 0.
  const [profile, setProfile] = useState("")
  // `loop` is the exception: it is always sent as a boolean, so the switch is
  // authoritative in both directions. Sending null for an unchecked switch would
  // let a preset saved with loop = true loop forever while the UI showed it off.
  const [loop, setLoop] = useState(props.presetLoop)
  const [durationMin, setDurationMin] = useState("")
  const [scatter, setScatter] = useState("3")
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const usingPreset = props.presetName !== null

  // Re-sync when the selection changes: switching presets must not carry the
  // previous one's loop setting over.
  const presetLoop = props.presetLoop
  const presetName = props.presetName
  useEffect(() => {
    setLoop(presetLoop)
  }, [presetLoop, presetName])

  const canStart = !running && !starting && (usingPreset || props.waypoints.length >= 2)

  const onStart = async () => {
    setStarting(true)
    setError(null)
    const minutes = Number.parseFloat(durationMin)
    const scatterM = Number.parseFloat(scatter)
    const body: StartRequest = {
      // Exactly one of these -- the API rejects both and neither.
      preset: usingPreset ? props.presetName : null,
      waypoints: usingPreset ? null : props.waypoints,
      profile: profile === "" ? null : profile,
      speed: null,
      costing: usingPreset ? null : props.costing,
      loop,
      duration_s: Number.isFinite(minutes) && minutes > 0 ? minutes * 60 : null,
      // Clamped client-side: the server bounds this 0..100 and would 422 on
      // anything outside, which is a pointless round trip for a slider-ish
      // value the user can only have fat-fingered.
      scatter_m: Number.isFinite(scatterM) ? Math.min(100, Math.max(0, scatterM)) : 3,
    }
    try {
      await startWalk(body)
      props.onStarted()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {running ? (
        <Alert>
          <AlertTitle>A walk is running</AlertTitle>
          <AlertDescription>
            Stop it from the status bar before starting another. This server owns one device
            session at a time.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="text-sm">
        {usingPreset ? (
          <>
            Starting preset <span className="font-medium">{props.presetName}</span>
          </>
        ) : (
          <>
            Starting an ad-hoc route of{" "}
            <span className="font-medium">{props.waypoints.length}</span> waypoints
          </>
        )}
      </div>

      <div className="grid gap-2">
        <Label htmlFor="start-profile">Profile</Label>
        <Select
          value={profile}
          onValueChange={(value) => setProfile(value ?? "")}
        >
          <SelectTrigger id="start-profile">
            <SelectValue placeholder={usingPreset ? "preset default" : "walk"} />
          </SelectTrigger>
          <SelectContent>
            {props.profiles.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Switch id="start-loop" checked={loop} onCheckedChange={setLoop} />
        <Label htmlFor="start-loop">Loop the route</Label>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="start-duration">Duration (minutes, blank = until the route ends)</Label>
        <Input
          id="start-duration"
          inputMode="decimal"
          placeholder="60"
          value={durationMin}
          onChange={(event) => setDurationMin(event.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="start-scatter">GPS scatter (metres, 0–100)</Label>
        <Input
          id="start-scatter"
          type="number"
          min={0}
          max={100}
          step={1}
          inputMode="decimal"
          value={scatter}
          onChange={(event) => setScatter(event.target.value)}
        />
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not start</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Button disabled={!canStart} onClick={onStart}>
        {starting ? <Spinner className="size-4" /> : <Play className="size-4" />} Start walk
      </Button>

      <p className="text-muted-foreground text-xs">
        The run lives inside this server process. Quitting <code>ios-loc gui</code> ends it.
      </p>
    </div>
  )
}
