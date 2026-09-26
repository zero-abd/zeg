"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./ui";

export default function Demo() {
    return (
        <section id="demo" className="py-24 px-6 border-t border-[rgba(255,255,255,0.08)]">
            <div className="max-w-[1100px] mx-auto">
                <SectionHeading
                    eyebrow="Demo"
                    title="See a call,"
                    accent="then read the report."
                    lede="The model needs the GB10 box, so it cannot run on this website. Here is a recording of a real screening call, and the candidate page with prepared sample data."
                />

                <div className="grid lg:grid-cols-5 gap-5">
                    <motion.div
                        initial={{ opacity: 0, y: 30 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-40px" }}
                        transition={{ duration: 0.6, ease: "easeOut" }}
                        className="lg:col-span-3 rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[rgba(5,12,14,0.7)] overflow-hidden"
                    >
                        <div className="flex items-center gap-3 px-5 py-3 border-b border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)]">
                            <span className="text-xs font-medium text-[rgba(255,255,255,0.6)]">Two-minute demo video</span>
                            <span className="ml-auto text-[11px] font-mono text-[rgba(255,255,255,0.35)]">mp4, 3.3 MB</span>
                        </div>
                        <video
                            className="w-full aspect-video bg-black"
                            src="/zeg-demo.mp4"
                            poster="/demo-poster.png"
                            controls
                            preload="none"
                            playsInline
                        >
                            <a href="/zeg-demo.mp4">Download the demo video</a>
                        </video>
                        <p className="px-5 py-3.5 text-[12.5px] text-[rgba(255,255,255,0.45)] border-t border-[rgba(255,255,255,0.08)]">
                            The problem, a screening call end to end, and the report it produces.
                        </p>
                    </motion.div>

                    <motion.div
                        initial={{ opacity: 0, y: 30 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-40px" }}
                        transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
                        className="lg:col-span-2 rounded-2xl border border-dashed border-[rgba(245,165,36,0.45)] bg-[rgba(245,165,36,0.04)] p-6 flex flex-col"
                    >
                        <span className="self-start inline-flex items-center px-2.5 py-1 rounded-full border border-dashed border-[rgba(245,165,36,0.55)] text-[11px] font-semibold uppercase tracking-[0.07em] text-[#f3c583] mb-4">
                            Read-only demo
                        </span>
                        <h3 className="text-[19px] font-bold tracking-tight mb-2">The candidate page, with sample data</h3>
                        <p className="text-[14px] text-[rgba(255,255,255,0.6)] leading-relaxed mb-4">
                            The candidate page from the gateway, playing seven pre-recorded interviewer clips. Answer out
                            loud if you like; press space to move on, or it moves on by itself after nine seconds. At the
                            end it shows the scorecard view.
                        </p>
                        <ul className="text-[13px] text-[rgba(255,255,255,0.55)] leading-relaxed space-y-1.5 mb-6">
                            <li>No microphone is opened and nothing is recorded.</li>
                            <li>The interviewer lines are fixed clips, not a live model.</li>
                            <li>The 7/10 scorecard is written copy, labelled as such.</li>
                        </ul>
                        <a
                            href="/demo"
                            className="mt-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-[15px] font-semibold bg-gradient-to-br from-[#0f9c8d] to-[#2dd4bf] text-[#04110f] hover:-translate-y-0.5 transition-all duration-300"
                        >
                            Open the prepared demo
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <path d="M5 12h14M13 6l6 6-6 6" />
                            </svg>
                        </a>
                    </motion.div>
                </div>
            </div>
        </section>
    );
}
