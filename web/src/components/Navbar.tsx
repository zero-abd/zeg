"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { GitHubIcon, Logo, REPO_URL } from "./ui";

const links = [
    { href: "#on-device", label: "On-device" },
    { href: "#how-it-works", label: "How it works" },
    { href: "#cost", label: "Cost" },
    { href: "#limits", label: "Limits" },
];

export default function Navbar() {
    const [scrolled, setScrolled] = useState(false);

    useEffect(() => {
        const handler = () => setScrolled(window.scrollY > 50);
        handler();
        window.addEventListener("scroll", handler, { passive: true });
        return () => window.removeEventListener("scroll", handler);
    }, []);

    return (
        <>
            <a
                href="#main"
                className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[#0f9c8d] focus:text-black focus:font-semibold"
            >
                Skip to content
            </a>
            <motion.nav
                initial={{ y: -20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className={`fixed top-5 sm:top-8 left-1/2 -translate-x-1/2 z-50 backdrop-blur-xl border rounded-full transition-all duration-300 w-auto max-w-[calc(100vw-1.5rem)] ${
                    scrolled
                        ? "border-[rgba(45,212,191,0.45)] bg-black/80 shadow-[0_10px_50px_rgba(20,184,166,0.35)]"
                        : "border-[rgba(45,212,191,0.25)] bg-black/50 shadow-[0_0_30px_rgba(20,184,166,0.15)]"
                }`}
            >
                <div className="px-4 sm:px-6 h-14 flex items-center gap-5 sm:gap-10">
                    <a href="#" className="flex items-center gap-2.5 font-bold text-lg tracking-tight shrink-0">
                        <Logo className="w-6 h-6 sm:w-7 sm:h-7" id="navGrad" />
                        <span>zeg</span>
                    </a>

                    <div className="hidden md:flex items-center gap-6">
                        {links.map((l) => (
                            <a
                                key={l.href}
                                href={l.href}
                                className="text-sm text-[rgba(255,255,255,0.7)] hover:text-white transition-colors font-medium whitespace-nowrap"
                            >
                                {l.label}
                            </a>
                        ))}
                    </div>

                    <a
                        href={REPO_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 sm:px-4 sm:py-2 rounded-full border border-[rgba(255,255,255,0.15)] text-[13px] sm:text-sm font-medium hover:border-[rgba(45,212,191,0.5)] hover:bg-[rgba(20,184,166,0.15)] hover:text-white transition-all shrink-0"
                    >
                        <GitHubIcon size={16} className="sm:w-[18px] sm:h-[18px]" />
                        <span className="hidden sm:inline">GitHub</span>
                    </a>
                </div>
            </motion.nav>
        </>
    );
}
