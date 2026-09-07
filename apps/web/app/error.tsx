"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="error-shell">
      <p className="eyebrow">Connection interrupted</p>
      <h1>We couldn’t load the events.</h1>
      <p>Check that the local backend is running, then try again.</p>
      <button className="button button--primary" type="button" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
