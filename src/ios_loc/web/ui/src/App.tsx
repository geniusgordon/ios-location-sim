import { useCallback, useEffect, useRef, useState } from "react"
import type { LatLon, Preset } from "@/api/types"
import { errorText, getPresets } from "@/api/client"
import MapView from "@/components/MapView"
import Sidebar, { type SidebarMode } from "@/components/Sidebar"
import StatusBar from "@/components/StatusBar"
import { useRoutePreview } from "@/hooks/useRoutePreview"
import { useWalkStream, useWalkMeta } from "@/hooks/useWalkStream"
import { isRunning } from "@/state/walkReducer"

export default function App() {
  useWalkStream()

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mode, setMode] = useState<SidebarMode>("presets")

  const [presets, setPresets] = useState<Preset[]>([])
  const [profiles, setProfiles] = useState<string[]>([])
  const [offline, setOffline] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedPreset, setSelectedPreset] = useState<string | null>(null)
  const [draftWaypoints, setDraftWaypoints] = useState<LatLon[]>([])

  // Only the newest load may write state. Two overlapping fetches (StrictMode
  // double-invokes the mount effect in dev) would otherwise let whichever
  // RESOLVES last win, stranding a stale error beside freshly loaded presets.
  const loadId = useRef(0)

  const reloadPresets = useCallback(() => {
    const mine = ++loadId.current
    setLoading(true)
    setLoadError(null)
    getPresets()
      .then((data) => {
        if (mine !== loadId.current) return
        setPresets(data.presets)
        setProfiles(data.profiles)
        setOffline(data.offline)
      })
      .catch((error: unknown) => {
        if (mine !== loadId.current) return
        setLoadError(errorText(error))
      })
      .finally(() => {
        if (mine === loadId.current) setLoading(false)
      })
  }, [])

  useEffect(() => {
    reloadPresets()
  }, [reloadPresets])

  const meta = useWalkMeta()
  // Map-first: editable whenever no walk holds the device, sidebar or not.
  const editing = !isRunning(meta.state)

  // The moment the draft stops being the preset, it is an ad-hoc route -- keeping
  // the name would start the OLD route on the phone while the map shows the new one.
  const editDraft = useCallback((next: (w: LatLon[]) => LatLon[]) => {
    setSelectedPreset(null)
    setDraftWaypoints(next)
  }, [])

  const [costing, setCosting] = useState("pedestrian")
  // Gated on the device being free, not on the sidebar: a map-first route
  // must draw as a line, not disconnected dots, whether or not the sidebar
  // is open. One debounced, server-cached Valhalla call.
  const preview = useRoutePreview(draftWaypoints, costing, !offline && !isRunning(meta.state))

  return (
    <div className="flex h-full w-full flex-col">
      <div className="min-h-0 flex-1">
        <MapView
          draftWaypoints={draftWaypoints}
          draftRoute={preview.route}
          editing={editing}
          onMapClick={(point) => editDraft((w) => [...w, point])}
          onWaypointDrag={(index, point) =>
            editDraft((w) => w.map((p, i) => (i === index ? point : p)))
          }
          onWaypointClick={(index) => editDraft((w) => w.filter((_, i) => i !== index))}
          lengthM={preview.lengthM}
          costing={costing}
          onRemoveLast={() => editDraft((w) => w.slice(0, -1))}
          onClearWaypoints={() => editDraft(() => [])}
          onStarted={() => setSidebarOpen(false)}
        />
      </div>
      <StatusBar onOpenSidebar={() => setSidebarOpen(true)} />
      <Sidebar
        open={sidebarOpen}
        onOpenChange={setSidebarOpen}
        mode={mode}
        onModeChange={setMode}
        presets={presets}
        profiles={profiles}
        offline={offline}
        loading={loading}
        loadError={loadError}
        onReloadPresets={reloadPresets}
        selectedPreset={selectedPreset}
        onSelectPreset={(preset) => {
          setSelectedPreset(preset.name)
          setDraftWaypoints(preset.waypoints as LatLon[])
          setMode("start")
        }}
        draftWaypoints={draftWaypoints}
        onClearWaypoints={() => editDraft(() => [])}
        onRemoveLast={() => editDraft((w) => w.slice(0, -1))}
        presetLoop={presets.find((p) => p.name === selectedPreset)?.loop ?? false}
        lengthM={preview.lengthM}
        routeError={preview.error}
        routePending={preview.pending}
        costing={costing}
        onCostingChange={setCosting}
        onPresetSaved={(name) => {
          setSelectedPreset(name)
          reloadPresets()
          setMode("start")
        }}
        onStarted={() => setSidebarOpen(false)}
      />
    </div>
  )
}
