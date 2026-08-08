import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Business Automation Platform",
  description: "V2 foundation for controlled accounting document operations.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
