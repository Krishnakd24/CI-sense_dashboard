import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "CI-Sense | Evidence workspace", description: "Inspect failed-test evidence from XML, commit changes and source code." };
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>) {
 return <html lang="en"><body>{children}</body></html>;
}
