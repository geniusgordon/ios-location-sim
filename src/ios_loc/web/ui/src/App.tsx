import { useState } from "react"
import type { LatLon } from "@/api/types"
import MapView from "@/components/MapView"
import StatusBar from "@/components/StatusBar"
import { useWalkStream } from "@/hooks/useWalkStream"

export default function App() {
  useWalkStream()
  const [draftWaypoints, setDraftWaypoints] = useState<LatLon[]>([])
  const [draftRoute] = useState<LatLon[]>([])
  const [, setSidebarOpen] = useState(false)
  const editing = false

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
    </div>
  )
}
