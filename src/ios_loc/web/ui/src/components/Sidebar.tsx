import { PanelLeftClose } from "lucide-react"
import type { LatLon, Pace, Place, Preset } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsPanel, TabsTab } from "@/components/ui/tabs"
import DeviceChip from "@/components/DeviceChip"
import LocationPanel from "@/components/LocationPanel"
import WalkPanel from "@/components/WalkPanel"
import type { DraftRoute, DraftSettings } from "@/lib/draft"
import type { DeviceIndicator } from "@/lib/deviceIndicator"
import type { RecentLocation } from "@/lib/recentLocations"

export type SidebarTab = "location" | "walk"

/** The selected-tab look, applied at the call site from the controlled value. */
function activeTabClass(active: boolean): string {
  return active ? "bg-background text-foreground shadow-sm" : ""
}

export interface SidebarProps {
  tab: SidebarTab
  onTabChange(tab: SidebarTab): void
  onCollapse(): void
  /** Renders as an overlay drawer (with a scrim) instead of an inline column. */
  overlay: boolean
  deviceIndicator: DeviceIndicator

  // Set-location tab
  locationDisabled: boolean
  deviceConnected: boolean
  lastPin: LatLon | null
  onPinned(point: LatLon, opts?: { recenter?: boolean }): void
  onPlaceSaved(): void
  held: boolean
  onClearPin(): Promise<void>
  pinError: string | null
  places: Place[]
  placesLoading: boolean
  onSelectPlace(place: Place): void
  onDeletePlace(name: string): Promise<void>
  recents: RecentLocation[]
  onSelectRecent(point: LatLon): void
  onRemoveRecent(point: LatLon): void

  // Walk tab
  route: DraftRoute
  settings: DraftSettings
  onSettingsChange(next: DraftSettings): void
  lengthM: number | null
  routePending: boolean
  routeError: string | null
  loadError: string | null
  /** Waypoints appended ahead of a running walk, not yet applied. */
  pendingReroute: LatLon[]
  onApplyReroute(): Promise<void>
  onUndoRerouteWaypoint(): void
  paces: Pace[]
  offline: boolean
  onRemoveLast(): void
  onClear(): void
  onPaste(route: DraftRoute): void
  onSaved(name: string): void
  onStarted(): void
  showSummary: boolean
  onDismissSummary(): void
  presets: Preset[]
  loading: boolean
  onReloadPresets(): void
  onSelectPreset(preset: Preset): void
  onDeletePreset(name: string): Promise<void>
}

export default function Sidebar(props: SidebarProps) {
  const panel = (
    <div
      className={
        props.overlay
          ? "bg-background fixed inset-y-0 left-0 z-30 flex w-[85vw] max-w-sm flex-col border-r shadow-xl"
          : "bg-background flex h-full w-[360px] shrink-0 flex-col border-r"
      }
    >
      <div className="flex items-center gap-2 border-b px-4 py-2">
        <DeviceChip indicator={props.deviceIndicator} />
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto"
          aria-label="Collapse sidebar"
          onClick={props.onCollapse}
        >
          <PanelLeftClose className="size-4" />
        </Button>
      </div>

      <Tabs
        value={props.tab}
        onValueChange={(value) => props.onTabChange(value as SidebarTab)}
        className="min-h-0 flex-1 gap-0"
      >
        {/* The active-tab styling is applied here rather than in the ui/ tabs
            primitive: the sidebar owns the controlled `tab` value, so it knows
            which tab is active without depending on the primitive's internal
            data attribute. */}
        <TabsList className="m-3 mb-0 w-auto">
          <TabsTab value="location" className={activeTabClass(props.tab === "location")}>
            Set location
          </TabsTab>
          <TabsTab value="walk" className={activeTabClass(props.tab === "walk")}>
            Walk
          </TabsTab>
        </TabsList>

        <TabsPanel value="location" className="min-h-0 flex-1 overflow-hidden">
          <LocationPanel
            disabled={props.locationDisabled}
            deviceConnected={props.deviceConnected}
            lastPin={props.lastPin}
            onPinned={props.onPinned}
            onPlaceSaved={props.onPlaceSaved}
            held={props.held}
            onClear={props.onClearPin}
            pinError={props.pinError}
            places={props.places}
            placesLoading={props.placesLoading}
            onSelectPlace={props.onSelectPlace}
            onDeletePlace={props.onDeletePlace}
            recents={props.recents}
            onSelectRecent={props.onSelectRecent}
            onRemoveRecent={props.onRemoveRecent}
          />
        </TabsPanel>

        <TabsPanel value="walk" className="min-h-0 flex-1 overflow-hidden">
          <WalkPanel
            route={props.route}
            settings={props.settings}
            onSettingsChange={props.onSettingsChange}
            lengthM={props.lengthM}
            routePending={props.routePending}
            routeError={props.routeError}
            loadError={props.loadError}
            pendingReroute={props.pendingReroute}
            onApplyReroute={props.onApplyReroute}
            onUndoRerouteWaypoint={props.onUndoRerouteWaypoint}
            paces={props.paces}
            offline={props.offline}
            onRemoveLast={props.onRemoveLast}
            onClear={props.onClear}
            onPaste={props.onPaste}
            onSaved={props.onSaved}
            onStarted={props.onStarted}
            showSummary={props.showSummary}
            onDismissSummary={props.onDismissSummary}
            presets={props.presets}
            loading={props.loading}
            onReloadPresets={props.onReloadPresets}
            onSelectPreset={props.onSelectPreset}
            onDeletePreset={props.onDeletePreset}
          />
        </TabsPanel>
      </Tabs>
    </div>
  )

  if (!props.overlay) return panel

  // Mobile: a scrim closes the drawer on outside tap. It sits under the panel
  // (z-20 vs z-30) so the sidebar's own controls stay clickable.
  return (
    <>
      <div
        className="fixed inset-0 z-20 bg-black/30"
        aria-hidden
        onClick={props.onCollapse}
      />
      {panel}
    </>
  )
}
