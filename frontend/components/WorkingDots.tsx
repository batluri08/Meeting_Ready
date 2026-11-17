/** Three animated dots meaning "agents are working on this". */
export function WorkingDots({ className = "" }: { className?: string }) {
  return (
    <span className={`working-dots ${className}`} role="status" aria-label="Working">
      <span /><span /><span />
    </span>
  );
}
