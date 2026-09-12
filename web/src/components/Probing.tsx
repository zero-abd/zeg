"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./ui";

type Turn = { who: "candidate" | "agent"; at: string; text: string; note?: string };

const exchange: Turn[] = [
    { who: "agent", at: "04:02", text: "Tell me about the hardest bug you shipped a fix for this year." },
    { who: "candidate", at: "04:09", text: "A race condition in our payment reconciler. We fixed it and it\u2019s been solid since." },
    {
        who: "agent",
        at: "04:21",
        text: "What did you personally do there, as opposed to the rest of the team?",
        note: "claim → ownership",
    },
    { who: "candidate", at: "04:26", text: "I wrote the repro harness and the advisory-lock fix." },
    { who: "agent", at: "04:38", text: "Roughly how often was it firing before the fix?", note: "ownership → a number" },
    { who: "candidate", at: "04:44", text: "Eleven double-settlements over about six weeks." },
    { who: "agent", at: "04:55", text: "What did the lock cost you?", note: "number → tradeoff" },
    { who: "candidate", at: "05:01", text: "Reconciliation went from parallel to serial. Batch time roughly doubled." },
];

const rules = [
    { k: "What did you personally do?", v: "Separates the claim from the team it belongs to." },
    { k: "What is the number?", v: "A rehearsed story survives one follow-up. It rarely survives a quantity." },
    { k: "What did you give up?", v: "Every real engineering decision cost something. Naming it is the tell." },
    { k: "What broke afterwards?", v: "The people who shipped it remember. The people who heard about it do not." },
];

function Transcript() {
    return (
        <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[rgba(5,12,14,0.7)] overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-3 border-b border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)]">
                <span className="text-xs font-medium text-[rgba(255,255,255,0.5)]">Transcript excerpt</span>
                <span className="ml-auto text-[11px] font-mono text-[rgba(255,255,255,0.35)]">local disk only</span>
            </div>
            <div className="px-5 py-5 space-y-3.5">
                {exchange.map((t, i) => (
                    <div key={i} className="flex gap-3 text-[13.5px] leading-relaxed">
                        <span className="font-mono text-[11px] text-[rgba(255,255,255,0.28)] pt-[3px] w-[38px] shrink-0">
                            {t.at}
                        </span>
                        <div className="min-w-0">
                            <span
                                className={`font-mono text-[11px] uppercase tracking-[0.06em] mr-2 ${
                                    t.who === "agent" ? "text-[#2dd4bf]" : "text-[rgba(255,255,255,0.35)]"
                                }`}
                            >
                                {t.who}
                            </span>
                            <span className={t.who === "agent" ? "text-[#eef4f3]" : "text-[rgba(255,255,255,0.55)]"}>
                                {t.text}
                            </span>
                            {t.note ? (
                                <span className="ml-2 inline-block align-middle rounded-full border border-[rgba(45,212,191,0.25)] bg-[rgba(20,184,166,0.1)] px-2 py-[1px] text-[10.5px] font-medium text-[#2dd4bf] whitespace-nowrap">
                                    {t.note}
                                </span>
                            ) : null}
                        </div>
                    </div>
                ))}
            </div>
            <div className="px-5 py-3.5 border-t border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] text-[12.5px] text-[rgba(255,255,255,0.45)]">
                It stops descending when the answer gets specific, or when two answers in a row stay general.
            </div>
        </div>
    );
}

function ReportCard() {
    return (
        <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] overflow-hidden h-full flex flex-col">
            <div className="px-5 py-3 border-b border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] flex items-center gap-3">
                <span className="text-xs font-medium text-[rgba(255,255,255,0.5)]">What the recruiter sees</span>
            </div>

            <div className="px-5 py-5 border-b border-[rgba(255,255,255,0.08)]">
                <div className="flex items-end gap-3 mb-1">
                    <span className="text-5xl font-[900] gradient-text leading-none">7</span>
                    <span className="text-[rgba(255,255,255,0.35)] text-lg font-semibold pb-1">/ 10</span>
                </div>
                <p className="text-[13px] font-semibold text-[#2dd4bf] uppercase tracking-[0.08em] mt-2">
                    Advance with reservations
                </p>
                <p className="text-[13px] text-[rgba(255,255,255,0.55)] leading-relaxed mt-2">
                    Concrete on debugging and on the tradeoff they accepted. Thin on system design; the topic was
                    raised twice and not covered.
                </p>
            </div>

            <div className="px-5 py-5 space-y-4 flex-1">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(255,255,255,0.35)]">
                    Evidence
                </p>
                <blockquote className="border-l-2 border-[rgba(45,212,191,0.5)] pl-3">
                    <p className="text-[13px] text-[rgba(255,255,255,0.75)] italic leading-relaxed">
                        &ldquo;Reconciliation went from parallel to serial. Batch time roughly doubled.&rdquo;
                    </p>
                    <footer className="text-[11px] font-mono text-[rgba(255,255,255,0.3)] mt-1.5">
                        05:01 · debugging depth
                    </footer>
                </blockquote>
                <div className="rounded-lg border border-[rgba(255,255,255,0.07)] bg-[rgba(255,255,255,0.02)] px-3.5 py-3">
                    <p className="text-[12.5px] text-[rgba(255,255,255,0.5)] leading-relaxed">
                        <span className="text-[rgba(255,255,255,0.7)] font-medium">System design — insufficient evidence.</span>{" "}
                        A dimension with nothing to quote is recorded as unevidenced, not scored low.
                    </p>
                </div>
            </div>

            <div className="px-5 py-3.5 border-t border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] text-[12.5px] text-[rgba(255,255,255,0.45)]">
                A recommendation, for a person to act on. Not a decision.
            </div>
        </div>
    );
}

export default function Probing() {
    return (
        <section id="probing" className="py-24 px-6 border-t border-[rgba(255,255,255,0.08)]">
            <div className="max-w-[1100px] mx-auto">
                <SectionHeading
                    eyebrow="The interview"
                    title="It does not accept"
                    accent="the first answer."
                    lede="Anyone can rehearse a project story. Almost nobody rehearses the third follow-up. zeg keeps descending until the answer is specific enough to quote."
                />

                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="grid lg:grid-cols-5 gap-5 mb-5"
                >
                    <div className="lg:col-span-3">
                        <Transcript />
                    </div>
                    <div className="lg:col-span-2">
                        <ReportCard />
                    </div>
                </motion.div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                    {rules.map((r, i) => (
                        <motion.div
                            key={r.k}
                            initial={{ opacity: 0, y: 24 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-40px" }}
                            transition={{ duration: 0.5, delay: i * 0.1, ease: "easeOut" }}
                            whileHover={{ y: -6, transition: { duration: 0.25 } }}
                            className="glass-card rounded-2xl p-6"
                        >
                            <p className="text-[15px] font-bold mb-2 tracking-tight text-[#eef4f3]">{r.k}</p>
                            <p className="text-[13px] text-[rgba(255,255,255,0.55)] leading-relaxed">{r.v}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
