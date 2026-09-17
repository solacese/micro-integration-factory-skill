import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Event Micro Integration Factory",
  description: "Upload OpenAPI, generate a Solace micro-integration, deploy it, and watch the event flow."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-frame">
          <div className="shell">
            <header className="topbar">
              <div className="brand">
                <span className="brand-title">Event Micro Integration Factory</span>
                <span className="brand-subtitle">Solace event flow</span>
              </div>
            </header>
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
