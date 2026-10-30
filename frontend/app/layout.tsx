import type { Metadata } from "next";
import "./globals.css";
import {AutoRefreshProvider} from "./AutoRefresh";

export const metadata: Metadata = { title: "Bermúdez Profesional", description: "Portal B2B para instaladores" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body><AutoRefreshProvider>{children}</AutoRefreshProvider></body></html>;
}

