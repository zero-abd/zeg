"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./ui";

const stages = [
    { label: "Speech in and out", detail: "Full-duplex audio-to-audio model, resident in GPU memory" },
    { label: "Interview logic", detail: "Prompt, plan, wall clock, memory, prohibited-question check" },
    { label: "Transcript", detail: "Written to local disk, under your retention policy" },
    { label: "Assessment", detail: "1-10 with quoted evidence, scored on the same machine" },
];

const points = [
    {
        title: "No third-party processor",
        body: "Nothing in the pipeline is a vendor you have to add to a data-processing agreement. That is not a smaller compliance review. For this pipeline it is the absence of one.",
        icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="M9 12l2 2 4-4" />
            </svg>
        ),
    },
    {
        title: "Residency is physical, not contractual",
        body: "Where the audio lives is a question about which rack it is in, answerable by pointing at it. No region flags, no sub-processor list, no transfer mechanism.",
        icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="20" height="8" rx="2" />
                <rect x="2" y="13" width="20" height="8" rx="2" />
                <path d="M6 7h.01M6 17h.01" />
            </svg>
        ),
    },
    {
        title: "Pinned weights, no silent swaps",
        body: "The model is a file on your disk at a version you chose. It does not change underneath a calibrated rubric because a vendor shipped an update on a Tuesday.",
        icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v6M12 8l4 4v9H8v-9l4-4z" />
                <path d="M9 2h6" />
            </svg>
        ),
    },
    {
        title: "No voiceprints",
        body: "The agent and the candidate are already on separate audio channels, so the two speakers are told apart by channel. Nothing derives a speaker embedding, which keeps biometric statutes out of scope by design.",
        icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 10v4M8 6v12M12 8v8M16 5v14M20 10v4" />
            </svg>
        ),
    },
];

function Boundary() {
    return (
        <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="mb-16"
        >
            <div className="flex flex-col lg:flex-row items-stretch gap-4">
                {/* Candidate */}
                <div className="glass-card rounded-2xl p-6 lg:w-[230px] shrink-0 flex flex-col justify-center text-center lg:text-left">
                    <div className="w-11 h-11 mx-auto lg:mx-0 flex items-center justify-center rounded-xl bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] mb-4 text-[rgba(255,255,255,0.7)]">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <rect x="9" y="2" width="6" height="11" rx="3" />
                            <path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8" />
                        </svg>
                    </div>
                    <h3 className="text-[15px] font-bold mb-1.5">Candidate&apos;s browser</h3>
                    <p className="text-[13px] text-[rgba(255,255,255,0.5)] leading-relaxed">
                        A link, a microphone, nothing to install.
                    </p>
                </div>

                {/* The one connection */}
                <div className="flex lg:flex-col items-center justify-center gap-2 py-2 lg:py-0 lg:w-[150px] shrink-0">
                    <svg viewBox="0 0 120 24" className="w-[90px] lg:w-[120px] h-6 max-lg:rotate-90" fill="none" aria-hidden="true">
                        <path d="M2 12h110M106 6l6 6-6 6" stroke="url(#connGrad)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        <defs>
                            <linearGradient id="connGrad" x1="0" y1="12" x2="120" y2="12">
                                <stop offset="0%" stopColor="rgba(45,212,191,0.25)" />
                                <stop offset="100%" stopColor="#2dd4bf" />
                            </linearGradient>
                        </defs>
                    </svg>
                    <span className="text-[11px] text-center text-[rgba(255,255,255,0.45)] leading-tight max-lg:max-w-[120px]">
                        Encrypted audio,
                        <br className="hidden lg:inline" /> straight to your box
                    </span>
                </div>

                {/* Premises */}
                <div className="relative flex-1 rounded-2xl border border-dashed border-[rgba(45,212,191,0.4)] bg-[rgba(20,184,166,0.04)] p-6 pt-8">
                    <span className="absolute -top-2.5 left-6 px-2.5 py-0.5 rounded-full bg-black border border-[rgba(45,212,191,0.4)] text-[11px] font-semibold uppercase tracking-[0.08em] text-[#2dd4bf]">
                        Your premises
                    </span>
                    <div className="grid sm:grid-cols-2 gap-3">
                        {stages.map((s) => (
                            <div key={s.label} className="rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-4 py-3">
                                <p className="text-[14px] font-semibold mb-1">{s.label}</p>
                                <p className="text-[12.5px] text-[rgba(255,255,255,0.5)] leading-relaxed">{s.detail}</p>
                            </div>
                        ))}
                    </div>
                    <p className="mt-4 text-[12.5px] text-[rgba(255,255,255,0.45)]">
                        One machine. Pull its network cable after the call connects and the interview still finishes.
                    </p>
                </div>
            </div>

            {/* What is absent */}
            <div className="mt-4 flex items-center gap-3 rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.015)] px-5 py-3.5">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="1.5" className="shrink-0" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M6 6l12 12" strokeLinecap="round" />
                </svg>
                <p className="text-[13px] text-[rgba(255,255,255,0.45)]">
                    <span className="line-through decoration-[rgba(255,255,255,0.3)]">Hosted speech API</span>
                    <span className="mx-2 text-[rgba(255,255,255,0.25)]">·</span>
                    <span className="line-through decoration-[rgba(255,255,255,0.3)]">Frontier model provider</span>
                    <span className="mx-2 text-[rgba(255,255,255,0.25)]">·</span>
                    <span className="line-through decoration-[rgba(255,255,255,0.3)]">Transcription vendor</span>
                    <span className="ml-2 text-[rgba(255,255,255,0.6)]">— none of these are in the diagram.</span>
                </p>
            </div>
        </motion.div>
    );
}

export default function OnDevice() {
    return (
        <section id="on-device" className="py-24 px-6 border-t border-[rgba(255,255,255,0.08)] relative">
            <div className="max-w-[1100px] mx-auto">
                <SectionHeading
                    eyebrow="On-device"
                    title="The audio has nowhere"
                    accent="else to go."
                    lede="Speech recognition, the reasoning, the voice, the transcript and the score all run on a single workstation you own. This is the part that is hard to copy and the part that closes deals."
                />
                <Boundary />

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    {points.map((p, i) => (
                        <motion.div
                            key={p.title}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-40px" }}
                            transition={{ duration: 0.5, delay: (i % 2) * 0.1, ease: "easeOut" }}
                            whileHover={{ y: -6, transition: { duration: 0.25 } }}
                            className="glass-card rounded-2xl p-8 relative overflow-hidden group"
                        >
                            <div className="absolute inset-0 rounded-2xl bg-[radial-gradient(ellipse_at_top_left,rgba(20,184,166,0.07),transparent_60%)] opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                            <div className="relative z-10">
                                <div className="w-11 h-11 flex items-center justify-center rounded-xl bg-[rgba(20,184,166,0.15)] border border-[rgba(45,212,191,0.2)] mb-5">
                                    <div className="w-[22px] h-[22px] text-[#2dd4bf]" aria-hidden="true">{p.icon}</div>
                                </div>
                                <h3 className="text-[17px] font-bold mb-2.5 tracking-tight">{p.title}</h3>
                                <p className="text-sm text-[rgba(255,255,255,0.6)] leading-relaxed">{p.body}</p>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
