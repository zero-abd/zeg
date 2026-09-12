"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { GitHubIcon, PrimaryButton, REPO_URL, SecondaryButton } from "./ui";

/* Fixed, not random: the server and the client have to agree on the markup. */
const AGENT_BARS = [0.4, 0.75, 0.35, 0.9, 0.55, 0.7, 0.3, 0.85, 0.45, 0.65, 0.95, 0.4, 0.6, 0.8, 0.35, 0.7, 0.5, 0.9, 0.3, 0.6, 0.75, 0.45, 0.85, 0.4];
const CANDIDATE_BARS = [0.6, 0.3, 0.8, 0.45, 0.7, 0.35, 0.9, 0.5, 0.65, 0.4, 0.55, 0.85, 0.3, 0.75, 0.6, 0.4, 0.8, 0.35, 0.7, 0.5, 0.45, 0.9, 0.55, 0.65];

/* Every one of these is a line the interview prompt actually tells it to ask. */
const PROBES = [
    "What did you personally do there, as opposed to the rest of the team?",
    "Roughly what number are we talking about?",
    "What did you give up to get that?",
    "What broke afterwards?",
];

function Bars({ values, tone }: { values: number[]; tone: "agent" | "candidate" }) {
    const color = tone === "agent" ? "bg-[#2dd4bf]" : "bg-[rgba(255,255,255,0.45)]";
    return (
        <div className="flex items-center gap-[3px] h-9 flex-1" aria-hidden="true">
            {values.map((v, i) => (
                <span
                    key={i}
                    className={`bar-speak flex-1 min-w-[2px] rounded-full ${color}`}
                    style={{
                        height: `${Math.round(v * 100)}%`,
                        animationDelay: `${((i * (tone === "agent" ? 97 : 131)) % 1100) / 1000}s`,
                        animationDuration: tone === "agent" ? "1.1s" : "1.35s",
                    }}
                />
            ))}
        </div>
    );
}

function TypedProbe() {
    const [index, setIndex] = useState(0);
    const [chars, setChars] = useState(0);

    useEffect(() => {
        const full = PROBES[index];
        if (chars <= full.length) {
            const t = setTimeout(() => setChars((c) => c + 1), 28);
            return () => clearTimeout(t);
        }
        const t = setTimeout(() => {
            setChars(0);
            setIndex((i) => (i + 1) % PROBES.length);
        }, 2600);
        return () => clearTimeout(t);
    }, [chars, index]);

    return (
        <span>
            {PROBES[index].slice(0, chars)}
            <span className="text-[#2dd4bf] cursor-blink">|</span>
        </span>
    );
}

function CallPanel() {
    return (
        <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.6, ease: "easeOut" }}
            className="max-w-[600px] mx-auto rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[rgba(5,12,14,0.82)] backdrop-blur-md overflow-hidden shadow-[0_20px_60px_rgba(0,0,0,0.6)] text-left"
        >
            {/* Chrome */}
            <div className="flex items-center gap-3 px-4 py-3 bg-[rgba(255,255,255,0.03)] border-b border-[rgba(255,255,255,0.08)]">
                <span className="w-2 h-2 rounded-full bg-[#f59e0b] shadow-[0_0_8px_rgba(245,158,11,0.7)] pulse-dot" />
                <span className="text-xs font-medium text-[rgba(255,255,255,0.6)]">Screening call</span>
                <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-[rgba(255,255,255,0.4)]">
                    <span className="hidden sm:inline">host 127.0.0.1</span>
                    <span>04:12</span>
                </span>
            </div>

            {/* Two channels, both open */}
            <div className="px-5 pt-5 pb-4 space-y-3">
                <div className="flex items-center gap-4">
                    <span className="w-[74px] shrink-0 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#2dd4bf]">
                        Agent
                    </span>
                    <Bars values={AGENT_BARS} tone="agent" />
                </div>
                <div className="flex items-center gap-4">
                    <span className="w-[74px] shrink-0 text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(255,255,255,0.45)]">
                        Candidate
                    </span>
                    <Bars values={CANDIDATE_BARS} tone="candidate" />
                </div>
                <p className="text-[11px] text-[rgba(255,255,255,0.35)] pl-[90px]">
                    Both channels open at once. Interrupt it and it stops talking.
                </p>
            </div>

            {/* Transcript */}
            <div className="px-5 py-4 border-t border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] font-mono text-[13px] leading-relaxed space-y-2">
                <p className="text-[rgba(255,255,255,0.5)]">
                    <span className="text-[rgba(255,255,255,0.3)]">candidate&nbsp;&nbsp;</span>
                    we cut p99 latency on the checkout path
                </p>
                <p className="text-[#eef4f3] min-h-[3.2em] sm:min-h-[2.1em]">
                    <span className="text-[#2dd4bf]">agent&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>
                    <TypedProbe />
                </p>
            </div>
        </motion.div>
    );
}

export default function Hero() {
    return (
        <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-[132px] pb-24 px-6">
            <div className="dot-bg" />
            <div className="hero-glow" />

            <div className="relative z-10 text-center max-w-[860px] mx-auto">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-[13px] font-medium text-[rgba(255,255,255,0.6)] mb-8"
                >
                    <span className="w-1.5 h-1.5 rounded-full bg-[#f59e0b] shadow-[0_0_8px_rgba(245,158,11,0.6)] pulse-dot" />
                    Runs on one box, on your premises
                </motion.div>

                <h1 className="text-[clamp(2.4rem,6vw,4rem)] font-[800] leading-[1.08] tracking-[-0.03em] mb-6 text-balance">
                    <motion.span
                        className="block"
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
                    >
                        Screening interviews
                    </motion.span>
                    <motion.span
                        className="block gradient-text"
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
                    >
                        that never leave the building.
                    </motion.span>
                </h1>

                <motion.p
                    initial={{ opacity: 0, y: 24 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.3, ease: "easeOut" }}
                    className="text-lg text-[rgba(255,255,255,0.6)] max-w-[640px] mx-auto mb-10 leading-relaxed text-pretty"
                >
                    zeg is a voice agent that runs a technical screen for a software engineering role.
                    A candidate opens a link and talks. It probes what they actually did rather than
                    taking the first answer. Your recruiter gets a 1-10 assessment with the quotes
                    behind it — and the audio never left your hardware.
                </motion.p>

                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.4, ease: "easeOut" }}
                    className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-14"
                >
                    <PrimaryButton href="#on-device">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <rect x="2" y="4" width="20" height="12" rx="2" />
                            <path d="M7 20h10M12 16v4M6 10h.01M9.5 10h5" />
                        </svg>
                        Why on-device
                    </PrimaryButton>
                    <SecondaryButton href={REPO_URL} external>
                        <GitHubIcon />
                        Read the source
                    </SecondaryButton>
                </motion.div>

                <CallPanel />
            </div>
        </section>
    );
}
