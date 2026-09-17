import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Github } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Micro Integration Factory",
  description: "Capture Solace events, chat with an AI builder, and generate MDK micro-integrations."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-frame">
          <div className="shell">
            <header className="topbar">
              <div className="brand-row">
                <Image
                  className="solace-logo"
                  src="/solace-logo.svg"
                  alt="Solace"
                  width={410}
                  height={123}
                  priority
                />
                <div className="brand">
                  <span className="brand-title">Micro Integration Factory</span>
                </div>
              </div>
              <nav className="topbar-nav" aria-label="Primary">
                <Link href="/">Builder</Link>
                <Link href="/schema-library">Schema Library</Link>
                <Link href="/settings">Settings</Link>
                <a
                  className="source-link"
                  href="https://github.com/solacese/micro-integration-factory"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Github size={16} aria-hidden="true" />
                  <span>GitHub repo</span>
                </a>
              </nav>
            </header>
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
