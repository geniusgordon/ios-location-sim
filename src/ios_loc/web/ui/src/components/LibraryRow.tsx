import { useState, type ReactNode } from "react"
import { Trash2 } from "lucide-react"
import { errorText } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

export interface LibraryRowProps {
  icon: ReactNode
  title: string
  subtitle: string
  selected: boolean
  onSelect(): void
  /** Greys out the select button when selecting cannot succeed (e.g. a walk
   *  owns the device, so setting a location would 409). Delete stays live. */
  selectDisabled?: boolean
  /** Rejects with an ApiError whose message is shown inline on the row. */
  onDelete(): Promise<void>
}

/**
 * One selectable saved-thing row (a route or a place) with inline delete
 * confirmation. Delete confirms with local row state rather than an
 * AlertDialog on purpose: a modal dialog would render a backdrop over the map,
 * and drawing/tapping the map while the sidebar is open is a supported flow.
 */
export default function LibraryRow(props: LibraryRowProps) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onConfirm = async () => {
    setDeleting(true)
    setError(null)
    try {
      await props.onDelete()
      // No setConfirming(false): a successful delete unmounts this row.
    } catch (err) {
      // Stay in the confirming state so the action can simply be retried.
      setError(errorText(err))
    } finally {
      setDeleting(false)
    }
  }

  if (confirming) {
    return (
      <li className="px-4 py-3">
        <p className="text-sm">
          Delete <span className="font-medium">{props.title}</span>?
        </p>
        <p className="text-muted-foreground text-xs">This rewrites your config file.</p>
        <div className="mt-2 flex gap-2">
          <Button variant="outline" size="sm" disabled={deleting} onClick={() => setConfirming(false)}>
            Cancel
          </Button>
          <Button variant="destructive" size="sm" disabled={deleting} onClick={onConfirm}>
            {deleting ? <Spinner className="size-4" /> : <Trash2 className="size-4" />} Delete
          </Button>
        </div>
        {error ? (
          <p className="text-destructive mt-2 text-xs" title={error}>
            {error}
          </p>
        ) : null}
      </li>
    )
  }

  return (
    <li className="flex items-center">
      <button
        type="button"
        onClick={props.onSelect}
        disabled={props.selectDisabled}
        className={`flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left ${
          props.selectDisabled ? "cursor-not-allowed opacity-50" : "hover:bg-accent"
        } ${props.selected ? "bg-accent" : ""}`}
      >
        {props.icon}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{props.title}</span>
          <span className="text-muted-foreground block text-xs">{props.subtitle}</span>
        </span>
      </button>
      <Button
        variant="ghost"
        size="sm"
        className="mr-2 shrink-0"
        aria-label={`Delete ${props.title}`}
        onClick={() => setConfirming(true)}
      >
        <Trash2 className="size-4" />
      </Button>
    </li>
  )
}
