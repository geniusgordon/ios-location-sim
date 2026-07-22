import { useState } from "react"
import { Save, Settings2 } from "lucide-react"
import { errorText, savePreset } from "@/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { COSTINGS } from "@/lib/costings"
import type { DraftRoute, DraftSettings } from "@/lib/draft"

export interface RouteOptionsProps {
  route: DraftRoute
  settings: DraftSettings
  onSettingsChange(next: DraftSettings): void
  profiles: string[]
  offline: boolean
  /** The route preview's failure, shown next to the control that causes it. */
  routeError: string | null
  onSaved(name: string): void
}

export default function RouteOptions(props: RouteOptionsProps) {
  const [saveOpen, setSaveOpen] = useState(false)
  const [name, setName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const set = <K extends keyof DraftSettings>(key: K, value: DraftSettings[K]) => {
    props.onSettingsChange({ ...props.settings, [key]: value })
  }

  const onSave = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      await savePreset({
        name: name.trim(),
        waypoints: props.route.waypoints,
        // A saved route owns a concrete profile; the start-time "inherit the
        // default" null has no meaning in the config file.
        profile: props.settings.profile ?? "walk",
        loop: props.settings.loop,
      })
      setSaveOpen(false)
      props.onSaved(name.trim())
    } catch (error) {
      setSaveError(errorText(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Popover>
        <PopoverTrigger
          render={
            <Button variant="ghost" size="sm" aria-label="Route options">
              <Settings2 className="size-4" /> Options
            </Button>
          }
        />
        <PopoverContent align="end" side="top" className="w-80">
          <div className="flex flex-col gap-4">
            {props.offline ? (
              <Alert>
                <AlertTitle>Offline mode</AlertTitle>
                <AlertDescription>
                  The server was started with <code>--offline</code>, so routing is disabled.
                  Waypoints still save; the preview needs Valhalla.
                </AlertDescription>
              </Alert>
            ) : null}

            {/* The server's own words, verbatim -- a blank map with no
                explanation is the failure mode the spec calls out by name. */}
            {props.routeError ? (
              <Alert variant="destructive">
                <AlertTitle>Routing failed</AlertTitle>
                <AlertDescription>{props.routeError}</AlertDescription>
              </Alert>
            ) : null}

            <div className="grid gap-2">
              <Label htmlFor="opt-profile">Profile</Label>
              <Select
                value={props.settings.profile ?? ""}
                onValueChange={(value) => set("profile", value === "" ? null : (value ?? null))}
              >
                <SelectTrigger id="opt-profile">
                  <SelectValue placeholder="walk" />
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

            <div className="grid gap-2">
              <Label htmlFor="opt-costing">Routing mode</Label>
              <Select
                value={props.settings.costing}
                onValueChange={(value) => {
                  if (value !== null) set("costing", value)
                }}
              >
                <SelectTrigger id="opt-costing" disabled={props.offline}>
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

            <div className="flex items-center gap-2">
              <Switch
                id="opt-loop"
                checked={props.settings.loop}
                onCheckedChange={(checked) => set("loop", checked)}
              />
              <Label htmlFor="opt-loop">Loop the route</Label>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="opt-duration">Duration (min, blank = until the route ends)</Label>
              <Input
                id="opt-duration"
                inputMode="decimal"
                placeholder="60"
                value={props.settings.durationMin}
                onChange={(event) => set("durationMin", event.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="opt-scatter">GPS scatter (metres, 0–100)</Label>
              <Input
                id="opt-scatter"
                type="number"
                min={0}
                max={100}
                step={1}
                inputMode="decimal"
                value={props.settings.scatterM}
                onChange={(event) => set("scatterM", event.target.value)}
              />
            </div>

            <Button
              variant="outline"
              className="w-full"
              disabled={props.route.waypoints.length < 2}
              onClick={() => {
                setName(props.route.name ?? "")
                setSaveError(null)
                setSaveOpen(true)
              }}
            >
              <Save className="size-4" /> Save as…
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save this route</DialogTitle>
            <DialogDescription>
              Saving rewrites the <code>[presets.*]</code> tables in your config. Comments and hand
              formatting inside those tables are lost; everything else is preserved byte for byte.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="save-name">Name</Label>
            <Input
              id="save-name"
              value={name}
              placeholder="riverside-loop"
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {saveError ? (
            <Alert variant="destructive">
              <AlertTitle>Could not save</AlertTitle>
              <AlertDescription>{saveError}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button disabled={name.trim().length === 0 || saving} onClick={onSave}>
              {saving ? <Spinner className="size-4" /> : <Save className="size-4" />} Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
