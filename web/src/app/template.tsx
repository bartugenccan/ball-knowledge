/**
 * Route transition. A template re-mounts on every navigation, so this CSS animation
 * replays per page. It is CSS (not JS) on purpose: content is visible even before hydration.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
