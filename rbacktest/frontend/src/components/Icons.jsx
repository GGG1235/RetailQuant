/**
 * Inline SVG icons — no external dependencies.
 */

export function MenuIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </svg>
  );
}

export function CloseIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export function GripIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" opacity="0.4">
      <circle cx="9"  cy="5"  r="2" />
      <circle cx="15" cy="5"  r="2" />
      <circle cx="9"  cy="12" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="9"  cy="19" r="2" />
      <circle cx="15" cy="19" r="2" />
    </svg>
  );
}
