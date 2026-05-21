import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Providers } from "../src/components/providers";

export const metadata: Metadata = {
  title: "QGate KPI Dashboard",
  description: "Standalone QGate KPI workbench for PreAnalysis.",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}