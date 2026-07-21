import { useCallback, useEffect, useState } from "react"
import type { LatLon, Preset } from "@/api/types"
import { ApiError, getPresets } from "@/api/client"
import MapView from "@/components/MapView"
import Sidebar, { type SidebarMode } from "@/components/Sidebar"
import StatusBar from "@/components/StatusBar"
import { useWalkStream } from "@/hooks/useWalkStream"

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
  const [draftRoute] = useState<LatLon[]>([])

  const reloadPresets = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    getPresets()
      .then((data) => {
        setPresets(data.presets)
        setProfiles(data.profiles)
        setOffline(data.offline)
      })
      .catch((error: unknown) => {
        setLoadError(error instanceof ApiError ? error.detail : String(error))
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    reloadPresets()
  }, [reloadPresets])

  const editing = mode === "editor" && sidebarOpen

  return (
    <div className="flex h-full w-full flex-col">
      <div className="min-h-0 flex-1">
        <MapView
          draftWaypoints={draftWaypoints}
          draftRoute={draftRoute}
          editing={editing}
          onMapClick={(point) => setDraftWaypoints((w) => [...w, point])}
          onWaypointDrag={(index, point) =>
            setDraftWaypoints((w) => w.map((p, i) => (i === index ? point : p)))
          }
          onWaypointClick={(index) => setDraftWaypoints((w) => w.filter((_, i) => i !== index))}
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
      />
    </div>
  )
}
