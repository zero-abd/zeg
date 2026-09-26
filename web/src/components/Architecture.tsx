"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./ui";

/* Every number here comes from services/agent/zeg/runtime/protocol.py and docs/11-runtime.md. */
const stages = [
    {
        name: "Candidate browser",
        where: "any laptop",
        lines: ["Mic and speaker over WebRTC", "No account, no install"],
    },
    {
        name: "Gateway",
        where: "aiohttp + aiortc",
        lines: ["Signaling and media", "Resamples caller audio to 16 kHz", "Playback queue, flushed on barge-in"],
    },
    {
        name: "Agent",
        where: "call process, Python stdlib",
        lines: ["Interview engine: a state machine", "Voice gate owns turn boundaries", "Wall clock, rubric coverage, legal follow-ups"],
    },
    {
        name: "Model process",
        where: "PyTorch on the GB10",
        lines: ["Full-duplex speech-to-speech model", "One step per 80 ms, in lockstep", "Binds 127.0.0.1 only"],
    },
];

const links = ["WebRTC, 20 ms RTP frames", "20 ms transport frames", "Loopback WebSocket, 80 ms frames"];

const facts = [
    {
        title: "Full duplex, not turn-taking",
        body: "Both channels are open for the whole call. When the candidate talks over the agent, the call process drops its playout queue at once and then tells the model to close its response cleanly, so the model never believes it is still mid-sentence.",
    },
    {
        title: "The 80 ms frame is the clock",
        body: "One model step takes 80 ms of caller audio (1,280 samples at 16 kHz) and returns one text token plus 80 ms of agent audio (1,764 samples at 22.05 kHz). That is exactly four 20 ms transport frames each way, so nothing drifts over a 15-minute call. Over-budget frames are counted, never hidden in a queue.",
    },
    {
        title: "Scorecards cite the transcript",
        body: "After the call a separate pass scores each rubric dimension from 1 to 4 and quotes the timestamped line behind it. A dimension with nothing to quote is marked insufficient evidence, not scored low. The overall 1-10 is a recommendation for a human.",
    },
];

function Arrow({ label }: { label: string }) {
    return (
        <div className="flex lg:flex-col items-center justify-center gap-2 py-2 lg:py-0 lg:px-1 lg:w-[92px] shrink-0" aria-hidden="true">
            <svg viewBox="0 0 24 24" className="w-5 h-5 text-[#2dd4bf] rotate-90 lg:rotate-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 12h15M14 6l6 6-6 6" />
            </svg>
            <span className="font-mono text-[10.5px] leading-tight text-[rgba(255,255,255,0.45)] lg:text-center">{label}</span>
        </div>
    );
}

export default function Architecture() {
    return (
        <section id="architecture" className="py-24 px-6 border-t border-[rgba(255,255,255,0.08)]">
            <div className="max-w-[1100px] mx-auto">
                <SectionHeading
                    eyebrow="Architecture"
                    title="Four processes,"
                    accent="one box."
                    lede="The candidate's audio goes from the browser to a gateway, an agent and a speech model, all on the same machine. The report is written there too."
                />

                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="rounded-2xl border border-[rgba(45,212,191,0.2)] bg-[rgba(5,12,14,0.6)] p-5 sm:p-6 mb-5"
                >
                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(255,255,255,0.4)] mb-4">
                        Live call path
                    </p>
                    <div className="flex flex-col lg:flex-row lg:items-stretch">
                        {stages.map((s, i) => (
                            <div key={s.name} className="contents">
                                <div className="glass-card rounded-xl p-4 lg:flex-1 min-w-0">
                                    <p className="text-[15px] font-bold tracking-tight">{s.name}</p>
                                    <p className="font-mono text-[11px] text-[#2dd4bf] mb-2.5">{s.where}</p>
                                    <ul className="space-y-1">
                                        {s.lines.map((l) => (
                                            <li key={l} className="text-[12.5px] text-[rgba(255,255,255,0.6)] leading-snug">
                                                {l}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                                {i < stages.length - 1 && <Arrow label={links[i]} />}
                            </div>
                        ))}
                    </div>

                    <div className="mt-5 pt-5 border-t border-[rgba(255,255,255,0.08)] flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(255,255,255,0.4)] shrink-0">
                            After the call
                        </p>
                        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 text-[13px] text-[rgba(255,255,255,0.65)]">
                            <span className="glass-card rounded-lg px-3 py-1.5">Transcript on local disk</span>
                            <span className="text-[#2dd4bf] hidden sm:inline" aria-hidden="true">→</span>
                            <span className="glass-card rounded-lg px-3 py-1.5">Scorer: rubric, quotes, flags</span>
                            <span className="text-[#2dd4bf] hidden sm:inline" aria-hidden="true">→</span>
                            <span className="glass-card rounded-lg px-3 py-1.5">Recruiter report</span>
                        </div>
                    </div>
                </motion.div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    {facts.map((f, i) => (
                        <motion.div
                            key={f.title}
                            initial={{ opacity: 0, y: 24 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-40px" }}
                            transition={{ duration: 0.5, delay: i * 0.1, ease: "easeOut" }}
                            className="glass-card rounded-2xl p-6"
                        >
                            <h3 className="text-[16px] font-bold mb-2 tracking-tight">{f.title}</h3>
                            <p className="text-[13.5px] text-[rgba(255,255,255,0.6)] leading-relaxed">{f.body}</p>
                        </motion.div>
                    ))}
                </div>

                <p className="mt-6 text-center text-[13px] text-[rgba(255,255,255,0.4)]">
                    The model sits behind one contract,{" "}
                    <code className="font-mono text-[12px] text-[rgba(255,255,255,0.6)]">backends/base.py</code>. A mock
                    backend implements it with no model, so everything above the model runs and is tested on a laptop.
                </p>
            </div>
        </section>
    );
}
