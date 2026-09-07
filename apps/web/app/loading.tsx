export default function Loading() {
  return (
    <main
      className="loading-shell"
      aria-busy="true"
      aria-label="Loading events"
    >
      <div className="loading-line loading-line--short" />
      <div className="loading-line loading-line--title" />
      <div className="loading-grid">
        <div className="loading-panel" />
        <div className="loading-panel" />
      </div>
    </main>
  );
}
