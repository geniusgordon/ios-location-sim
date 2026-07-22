import type { DeviceIndicator } from "@/lib/deviceIndicator"

const DOT: Record<DeviceIndicator["tone"], string> = {
  ok: "bg-green-500",
  warn: "bg-amber-500",
  error: "bg-red-500",
  muted: "bg-muted-foreground",
}

/** A compact device-connectivity chip -- a colored dot plus a label, with the
 *  full detail in `title` for hover. Prop-driven only: it never calls
 *  telemetry or device hooks itself. */
export default function DeviceChip({ indicator }: { indicator: DeviceIndicator }) {
  return (
    <span
      className="text-muted-foreground flex shrink-0 items-center gap-1.5 text-xs"
      title={indicator.detail}
    >
      <span className={`size-2 shrink-0 rounded-full ${DOT[indicator.tone]}`} />
      {indicator.label}
    </span>
  )
}
