"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./ui";

const notDoing = [
    {
        title: "It does not decide",
        body: "zeg produces evidence and a recommendation band. A person reads the report and makes every call about a candidate. There is no autopilot setting and there will not be one.",
    },
    {
        title: "It does not read personality",
        body: "No culture fit, no confidence score, no inference from accent, affect or hesitation. It scores technical dimensions against a rubric and quotes the span it scored.",
    },
    {
        title: "It does not hide",
        body: "It says it is an AI in the first twenty seconds and asks before recording. Ask it directly and it confirms immediately and offers a human instead. Decline and the call routes to a person.",
    },
    {
        title: "It is not an accessibility substitute",
        body: "A voice-only screen excludes some candidates. A path to a human screen has to exist, be advertised ahead of the call, and be requestable without anyone explaining why.",
    },
];

const limits = [
    ["One interview at a time", "Single client, single GPU. More throughput means more boxes, which is also the pricing model."],
    ["Sessions cap near 16 minutes", "A hard runtime limit. The wall clock wraps the interview up before it, so it never cuts off mid-sentence."],
    ["The model's own memory is short", "It is trained on short audio context. Our layer holds the state and re-injects a compact summary, which is why the interview is a state machine and not a prompt."],
    ["The speech checkpoint is research-grade", "It can skip a tool, loop, or drop a transcript word. Anything that has to be reliable — the prohibited-question check, the clock, the rubric — lives in our code, not the model's."],
];

export default function Honesty() {
    return (
        <section id="limits" className="py-24 px-6 border-t border-[rgba(255,255,255,0.08)]">
            <div className="max-w-[1100px] mx-auto">
                <SectionHeading
                    eyebrow="Limits"
                    title="What it will not do, and"
                    accent="where it is weak."
                    lede="Hiring is one of the most regulated places to put a model, and overclaiming here costs someone a job. So here is the honest version."
                />

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-5">
                    {notDoing.map((n, i) => (
                        <motion.div
                            key={n.title}
                            initial={{ opacity: 0, y: 24 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-40px" }}
                            transition={{ duration: 0.5, delay: (i % 2) * 0.1, ease: "easeOut" }}
                            whileHover={{ y: -6, transition: { duration: 0.25 } }}
                            className="glass-card rounded-2xl p-7"
                        >
                            <div className="flex items-start gap-3">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2dd4bf" strokeWidth="1.5" strokeLinecap="round" className="mt-0.5 shrink-0" aria-hidden="true">
                                    <circle cx="12" cy="12" r="9" />
                                    <path d="M8.5 8.5l7 7M15.5 8.5l-7 7" />
                                </svg>
                                <div>
                                    <h3 className="text-[16px] font-bold mb-2 tracking-tight">{n.title}</h3>
                                    <p className="text-[13.5px] text-[rgba(255,255,255,0.6)] leading-relaxed">{n.body}</p>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>

                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] overflow-hidden"
                >
                    <div className="px-6 py-4 border-b border-[rgba(255,255,255,0.08)]">
                        <h3 className="text-[15px] font-bold tracking-tight">Known technical limits</h3>
                        <p className="text-[12.5px] text-[rgba(255,255,255,0.45)] mt-1">
                            Measured in the runtime we build on, not guessed at.
                        </p>
                    </div>
                    <dl className="divide-y divide-[rgba(255,255,255,0.06)]">
                        {limits.map(([k, v]) => (
                            <div key={k} className="px-6 py-4 sm:flex sm:gap-6">
                                <dt className="text-[13.5px] font-semibold text-[#eef4f3] sm:w-[280px] shrink-0 mb-1 sm:mb-0">
                                    {k}
                                </dt>
                                <dd className="text-[13.5px] text-[rgba(255,255,255,0.55)] leading-relaxed">{v}</dd>
                            </div>
                        ))}
                    </dl>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: 0.2 }}
                    className="mt-5 flex items-start gap-3 rounded-2xl border border-[rgba(245,158,11,0.25)] bg-[rgba(245,158,11,0.05)] px-6 py-5"
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0" aria-hidden="true">
                        <path d="M12 9v4M12 17h.01" />
                        <path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
                    </svg>
                    <p className="text-[13.5px] text-[rgba(255,255,255,0.6)] leading-relaxed">
                        <span className="font-semibold text-[#eef4f3]">Before a real candidate is ever screened:</span>{" "}
                        automated employment decision tools carry bias-audit, advance-notice and impact-assessment
                        duties that vary by where the <em>candidate</em> sits, not where you do. Running locally
                        removes a processor from the diagram. It does not remove any of that. None of this page is
                        legal advice, and every deployment needs counsel.
                    </p>
                </motion.div>
            </div>
        </section>
    );
}
