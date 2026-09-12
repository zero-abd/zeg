"use client";

import { motion } from "framer-motion";
import { GitHubIcon, Logo, REPO_URL } from "./ui";

export default function Footer() {
    return (
        <footer className="border-t border-[rgba(255,255,255,0.08)] pt-14 pb-10 px-6 bg-[#05090a]">
            <div className="max-w-[1100px] mx-auto">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="text-center mb-9"
                >
                    <div className="flex items-center justify-center gap-2.5 mb-4">
                        <Logo className="w-7 h-7" id="footGrad" />
                        <span className="font-bold text-lg tracking-tight">zeg</span>
                    </div>
                    <p className="text-sm text-[rgba(255,255,255,0.6)] max-w-[520px] mx-auto mb-5 leading-relaxed">
                        A local AI interview agent. It runs a technical screening call on hardware you own, probes what
                        the candidate actually did, and hands a person the evidence to decide on.
                    </p>
                    <p className="text-xs text-[rgba(255,255,255,0.4)] tracking-wider font-medium">
                        Full-duplex speech · WebRTC · runs on one box you own
                    </p>
                </motion.div>

                <div className="h-px bg-[rgba(255,255,255,0.08)] mb-6" />

                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
                    className="text-center"
                >
                    <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-[rgba(45,212,191,0.2)] bg-[rgba(20,184,166,0.05)] text-sm text-[rgba(255,255,255,0.6)] mb-6">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2dd4bf" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M20 6L9 17l-5-5" />
                        </svg>
                        zeg recommends. <strong className="text-[#2dd4bf] font-semibold">A human decides.</strong>
                    </div>

                    <div className="flex items-center justify-center gap-5 mb-6">
                        <a
                            href={REPO_URL}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 text-sm text-[rgba(255,255,255,0.6)] hover:text-white transition-colors"
                        >
                            <GitHubIcon size={16} />
                            zero-abd/zeg
                        </a>
                    </div>

                    <p className="text-xs text-[rgba(255,255,255,0.4)]">
                        © {new Date().getFullYear()} zeg · Built in the open at a hackathon
                    </p>
                </motion.div>
            </div>
        </footer>
    );
}
