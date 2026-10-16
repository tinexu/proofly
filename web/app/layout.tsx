import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { SiteHeader } from "@/components/header";

export const metadata: Metadata = {
  title: "Proofly",
  description: "Check a sublet before you pay. Early development version.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <div className="proto-banner" role="note">
          Early development version. Checks aren&apos;t complete yet; don&apos;t rely on Proofly for a real decision.
        </div>
        <AuthProvider>
          <SiteHeader />
          <main id="main" className="container">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}