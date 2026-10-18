import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CycleScope · Market cycle research",
  description:
    "Investigate historical cycles, inspect exploratory forecasts, and compare walk-forward evidence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
