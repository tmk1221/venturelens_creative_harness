/** T22: tiny localStorage-backed feature flags. Post is audio-only now -- picture/angle
 * judgement happens in Resolve, so "Set angle" is hidden by default; flip it on with
 * `localStorage.setItem('post:showSetAngle', '1')` for the rare case it's still useful. */
export function isFlagEnabled(name: string): boolean {
  try {
    return localStorage.getItem(name) === '1'
  } catch {
    return false
  }
}
