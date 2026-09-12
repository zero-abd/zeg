"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./ui";

const steps = [
    {
        num: "01",
        title: "Send a link",
        desc: "The recruiter creates a call for an open role. The candidate opens it in a browser. No account, no download, no app.",
    },
    {
        num: "02",
        title: "It discloses, then asks",
        desc: "In the first twenty seconds it says it is an AI and asks permission to record. If the answer is no, the call ends and routes to a human.",
    },
    {
        num: "03",
        title: "It talks, and it probes",
        desc: "One question at a time, under twenty seconds a turn, following each claim down until the answer gets specific. Interrupt it and it yields.",
    },
    {
        num: "04",
        title: "A human reads the report",
        desc: "Each rubric dimension gets a score and a quoted span with a timestamp. No evidence means insufficient evidence, never a low score.",
    },
];

function Connector() {
    return (
        <div className="shrink-0 w-[44px] flex items-center justify-center max-xl:w-full max-xl:h-[44px]" aria-hidden="true">
            <svg viewBox="0 0 44 24" fill="none" className="w-[44px] h-6 max-xl:rotate-90">
                <path d="M0 12h38M33 6l6 6-6 6" stroke="url(#stepGrad)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <defs>
                    <linearGradient id="stepGrad" x1="0" y1="12" x2="44" y2="12">
                        <stop offset="0%" stopColor="#0f9c8d" />
                        <stop offset="100%" stopColor="#2dd4bf" />
                    </linearGradient>
                </defs>
            </svg>
        </div>
    );
}

export default function HowItWorks() {
    return (
        <section id="how-it-works" className="py-24 px-6 border-t border-[rgba(255,255,255,0.08)]">
            <div className="max-w-[1100px] mx-auto">
                <SectionHeading
                    eyebrow="Workflow"
                    title="Four steps, about"
                    accent="fifteen minutes."
                    lede="One candidate at a time per box, which is also the unit you buy more of."
                />

                <div className="flex flex-col xl:flex-row items-center justify-center">
                    {steps.map((step, i) => (
                        <div key={step.num} className="contents">
                            <motion.div
                                initial={{ opacity: 0, y: 30 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true, margin: "-40px" }}
                                transition={{ duration: 0.5, delay: i * 0.12, ease: "easeOut" }}
                                whileHover={{ y: -6, transition: { duration: 0.25 } }}
                                className="glass-card rounded-2xl p-8 flex-1 max-w-[320px] w-full"
                            >
                                <div className="text-5xl font-[900] gradient-text opacity-30 mb-4 leading-none">
                                    {step.num}
                                </div>
                                <h3 className="text-[17px] font-bold mb-2.5 tracking-tight">{step.title}</h3>
                                <p className="text-sm text-[rgba(255,255,255,0.6)] leading-relaxed">{step.desc}</p>
                            </motion.div>
                            {i < steps.length - 1 && <Connector />}
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
