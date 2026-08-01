import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Describe your idea. We'll build the app.",
  description:
    "Describe your idea in plain words and a full team of AI agents builds, tests, secures, and launches your app. Free to try, no signup required.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
