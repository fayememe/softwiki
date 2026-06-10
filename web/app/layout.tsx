import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Softwiki — Research Intelligence Hub",
  description: "AI-powered generic research assistant with hybrid RAG search, automated ingestion, and wiki generation.",
  keywords: ["research", "intelligence", "RAG", "knowledge management", "wiki"],
  openGraph: {
    title: "Softwiki — Research Intelligence Hub",
    description: "AI-powered generic research with hybrid semantic search and source-grounded analysis.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        {children}
      </body>
    </html>
  );
}
