/**
 * Whether the map chases the live dot.
 *
 * A user pan detaches permanently until the recenter button reattaches it.
 * Deliberately NOT time-based: a map that silently re-grabs the viewport a few
 * seconds after you let go is worse than one you have to click to reattach.
 */
export interface FollowState {
  following: boolean
}

export const initialFollow: FollowState = { following: true }

export function onUserPan(_state: FollowState): FollowState {
  return { following: false }
}

export function onRecenter(_state: FollowState): FollowState {
  return { following: true }
}

/** Our own easeTo/fitBounds. Must not count as a user pan. */
export function onProgrammaticMove(state: FollowState): FollowState {
  return state
}

export function shouldCenter(state: FollowState, hasFix: boolean): boolean {
  return state.following && hasFix
}
