import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Motion from "@/components/Motion";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "zeg — technical screening that never leaves the building",
  description:
    "A local AI interview agent. It runs a technical screening call on one on-premises box, probes what the candidate actually did, and hands the recruiter a 1-10 assessment with quoted evidence. Candidate audio never leaves the device.",
  keywords: [
    "zeg",
    "AI interview",
    "technical screening",
    "on-premises",
    "local AI",
    "full-duplex voice",
    "recruiting",
  ],
  openGraph: {
    title: "zeg — technical screening that never leaves the building",
    description:
      "A local AI interview agent. One on-premises box runs the whole interview; candidate audio never leaves the device.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased`}>
        <Motion>{children}</Motion>
      </body>
    </html>
  );
}
