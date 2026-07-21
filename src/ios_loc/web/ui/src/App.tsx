import { useState } from "react"
import type { LatLon } from "@/api/types"
import MapView from "@/components/MapView"
import { useWalkStream } from "@/hooks/useWalkStream"

export default function App() {
  useWalkStream()
  // Draft state lives here because Task 7's sidebar and Task 5's map both need
  // it; it is the only cross-component state on the page.
  const [draftWaypoints, setDraftWaypoints] = useState<LatLon[]>([])
  const [draftRoute] = useState<LatLon[]>([])
  const editing = false

  return (
    <div className="h-full w-full">
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
  )
}
