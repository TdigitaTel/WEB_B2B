import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Bermúdez Profesional", description: "Portal B2B para instaladores" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}

