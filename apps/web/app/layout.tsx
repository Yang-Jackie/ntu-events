import type { Metadata } from "next";
import type { ReactNode } from "react";

import "leaflet/dist/leaflet.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "NTU Events",
    template: "%s · NTU Events",
  },
  description: "Find talks, workshops, activities, and gatherings around NTU.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
