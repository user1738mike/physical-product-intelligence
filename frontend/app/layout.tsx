import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Physical Product Intelligence Cloud",
  description:
    "Engineering the foundation for traceable product and packaging assessments.",
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
