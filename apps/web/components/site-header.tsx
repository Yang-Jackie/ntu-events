import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link className="brand" href="/" aria-label="NTU Events home">
        <span className="brand__mark" aria-hidden="true">
          <span>N</span>
        </span>
        <span>NTU Events</span>
      </Link>
      <p className="site-header__context">Campus discovery · Singapore time</p>
    </header>
  );
}
