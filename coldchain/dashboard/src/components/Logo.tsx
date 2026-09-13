// Served from public/ -- BASE_URL picks up vite.config.ts's base ("/NRW/")
// automatically, in both dev and the built Pages deploy.
const LOGO_SRC = `${import.meta.env.BASE_URL}vallum-logo.png`;

export function Logo({ height = 32, onClick }: { height?: number; onClick?: () => void }) {
  return (
    <img
      src={LOGO_SRC}
      alt="Vallum"
      height={height}
      style={{ display: "block", cursor: onClick ? "pointer" : undefined }}
      onClick={onClick}
    />
  );
}
