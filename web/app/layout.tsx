import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import { StoreProvider } from "@/lib/store";

export const metadata: Metadata = {
  title: "Proofly prototype",
  description: "Check a sublet before you pay. Usability prototype, not a live service.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <div className="proto-banner" role="note">
          Prototype for usability testing. Data stays in this browser; nothing is checked for real.
        </div>
        <header className="site-header">
          <Link href="/" className="brand">Proofly</Link>
        </header>
        <StoreProvider>
          <main id="main" className="container">{children}</main>
        </StoreProvider>
      </body>
    </html>
  );
}