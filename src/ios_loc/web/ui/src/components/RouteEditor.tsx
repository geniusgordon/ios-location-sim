import { useState } from "react"
import { Save, Trash2, Undo2 } from "lucide-react"
import { ApiError, savePreset } from "@/api/client"
import type { LatLon } from "@/api/types"
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
import { formatDistance } from "@/lib/format"

const COSTINGS = ["pedestrian", "bicycle", "auto"]

export interface RouteEditorProps {
  waypoints: LatLon[]
  onClearWaypoints(): void
  onRemoveLast(): void
  profiles: string[]
  offline: boolean
  route: LatLon[]
  lengthM: number | null
  routeError: string | null
  pending: boolean
  costing: string
  onCostingChange(costing: string): void
  onSaved(name: string): void
}

export default function RouteEditor(props: RouteEditorProps) {
  const [name, setName] = useState("")
  const [profile, setProfile] = useState("walk")
  const [loop, setLoop] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const canSave = name.trim().length > 0 && props.waypoints.length >= 2 && !saving

  const onSave = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      await savePreset({
        name: name.trim(),
        waypoints: props.waypoints,
        profile,
        loop,
      })
      props.onSaved(name.trim())
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.detail : String(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-muted-foreground text-sm">
        Click the map to add a waypoint, drag one to move it, click one to remove it.
      </p>

      {props.offline ? (
        <Alert>
          <AlertTitle>Offline mode</AlertTitle>
          <AlertDescription>
            The server was started with <code>--offline</code>, so routing is disabled. Waypoints
            still save; the preview needs Valhalla.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">{props.waypoints.length}</span>
        <span className="text-muted-foreground">waypoints</span>
        {props.pending ? <Spinner className="size-4" /> : null}
        {props.lengthM !== null ? (
          <span className="text-muted-foreground ml-auto">
            route {formatDistance(props.lengthM)}
          </span>
        ) : null}
      </div>

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={props.waypoints.length === 0}
          onClick={props.onRemoveLast}
        >
          <Undo2 className="size-4" /> Undo point
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={props.waypoints.length === 0}
          onClick={props.onClearWaypoints}
        >
          <Trash2 className="size-4" /> Clear
        </Button>
      </div>

      {/* The server's own words, verbatim -- a blank map with no explanation is
          the failure mode the spec calls out by name. */}
      {props.routeError ? (
        <Alert variant="destructive">
          <AlertTitle>Routing failed</AlertTitle>
          <AlertDescription>{props.routeError}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-2">
        <Label htmlFor="costing">Routing mode</Label>
        <Select
          value={props.costing}
          onValueChange={(value) => {
            if (value !== null) props.onCostingChange(value)
          }}
        >
          <SelectTrigger id="costing" disabled={props.offline}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {COSTINGS.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="border-t pt-4">
        <div className="grid gap-2">
          <Label htmlFor="preset-name">Save as preset</Label>
          <Input
            id="preset-name"
            value={name}
            placeholder="riverside-loop"
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        <div className="mt-3 grid gap-2">
          <Label htmlFor="preset-profile">Profile</Label>
          <Select
            value={profile}
            onValueChange={(value) => {
              if (value !== null) setProfile(value)
            }}
          >
            <SelectTrigger id="preset-profile">
              <SelectValue />
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

        <div className="mt-3 flex items-center gap-2">
          <Switch id="preset-loop" checked={loop} onCheckedChange={setLoop} />
          <Label htmlFor="preset-loop">Loop</Label>
        </div>

        {saveError ? (
          <Alert variant="destructive" className="mt-3">
            <AlertTitle>Could not save</AlertTitle>
            <AlertDescription>{saveError}</AlertDescription>
          </Alert>
        ) : null}

        <p className="text-muted-foreground mt-3 text-xs">
          Saving rewrites the <code>[presets.*]</code> tables in your config. Comments and hand
          formatting inside those tables are lost; everything else is preserved byte for byte.
        </p>

        <Button className="mt-3 w-full" disabled={!canSave} onClick={onSave}>
          {saving ? <Spinner className="size-4" /> : <Save className="size-4" />} Save preset
        </Button>
      </div>
    </div>
  )
}
