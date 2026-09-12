"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./ui";

const PER_INTERVIEW = 10;
const BOX = 5000;

const volumes = [250, 500, 1000, 2500];
const MAX = Math.max(...volumes) * PER_INTERVIEW;

const money = (n: number) => "$" + n.toLocaleString("en-US");

function Bars() {
    return (
        <div className="space-y-6">
            {volumes.map((v, i) => {
                const saas = v * PER_INTERVIEW;
                return (
                    <motion.div
                        key={v}
                        initial={{ opacity: 0, y: 16 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-40px" }}
                        transition={{ duration: 0.5, delay: i * 0.08, ease: "easeOut" }}
                    >
                        <div className="flex items-baseline justify-between mb-2.5">
                            <span className="text-[13px] font-semibold text-[rgba(255,255,255,0.7)]">
                                {v.toLocaleString("en-US")} interviews
                            </span>
                            <span className="text-[12px] font-mono text-[rgba(255,255,255,0.35)]">
                                {saas > BOX
                                    ? money(saas - BOX) + " more"
                                    : saas === BOX
                                      ? "break even"
                                      : money(BOX - saas) + " less"}
                            </span>
                        </div>

                        <div className="flex items-center gap-3 mb-2">
                            <span className="w-[72px] shrink-0 text-[11px] uppercase tracking-[0.06em] text-[rgba(255,255,255,0.35)]">
                                Per seat
                            </span>
                            <div className="flex-1 h-6 rounded-md bg-[rgba(255,255,255,0.04)] overflow-hidden">
                                <motion.div
                                    initial={{ width: 0 }}
                                    whileInView={{ width: `${(saas / MAX) * 100}%` }}
                                    viewport={{ once: true, margin: "-40px" }}
                                    transition={{ duration: 0.8, delay: 0.15 + i * 0.08, ease: "easeOut" }}
                                    className="h-full rounded-md bg-[rgba(255,255,255,0.18)]"
                                />
                            </div>
                            <span className="w-[64px] shrink-0 text-right text-[12.5px] font-mono text-[rgba(255,255,255,0.55)]">
                                {money(saas)}
                            </span>
                        </div>

                        <div className="flex items-center gap-3">
                            <span className="w-[72px] shrink-0 text-[11px] uppercase tracking-[0.06em] text-[#2dd4bf]">
                                zeg
                            </span>
                            <div className="flex-1 h-6 rounded-md bg-[rgba(255,255,255,0.04)] overflow-hidden">
                                <motion.div
                                    initial={{ width: 0 }}
                                    whileInView={{ width: `${(BOX / MAX) * 100}%` }}
                                    viewport={{ once: true, margin: "-40px" }}
                                    transition={{ duration: 0.8, delay: 0.15 + i * 0.08, ease: "easeOut" }}
                                    className="h-full rounded-md bg-gradient-to-r from-[#0f9c8d] to-[#2dd4bf]"
                                />
                            </div>
                            <span className="w-[64px] shrink-0 text-right text-[12.5px] font-mono text-[#2dd4bf]">
                                {money(BOX)}
                            </span>
                        </div>
                    </motion.div>
                );
            })}
        </div>
    );
}

const facts = [
    { k: "~$10", v: "roughly what a hosted screening interview costs, per interview, every interview" },
    { k: "~$5,000", v: "one workstation, once, and it is still yours next year" },
    { k: "500", v: "interviews to break even; after that the marginal cost is electricity" },
];

export default function Cost() {
    return (
        <section id="cost" className="py-24 px-6 border-t border-[rgba(255,255,255,0.08)]">
            <div className="max-w-[1100px] mx-auto">
                <SectionHeading
                    eyebrow="Cost"
                    title="A meter that never stops, versus"
                    accent="a thing you own."
                    lede="Hosted screening is priced per interview, so the bill grows with every hire you try to make. A box is bought once. That is the whole argument, and it is the reason this is aimed at teams without a recruiting budget to burn."
                />

                <div className="grid lg:grid-cols-5 gap-5">
                    <motion.div
                        initial={{ opacity: 0, y: 24 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-40px" }}
                        transition={{ duration: 0.6, ease: "easeOut" }}
                        className="lg:col-span-3 glass-card rounded-2xl p-7 sm:p-8"
                    >
                        <Bars />
                    </motion.div>

                    <div className="lg:col-span-2 flex flex-col gap-5">
                        {facts.map((f, i) => (
                            <motion.div
                                key={f.k}
                                initial={{ opacity: 0, y: 24 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true, margin: "-40px" }}
                                transition={{ duration: 0.5, delay: i * 0.1, ease: "easeOut" }}
                                className="glass-card rounded-2xl p-6 flex-1"
                            >
                                <p className="text-[28px] font-[800] gradient-text leading-none mb-2.5 tracking-tight">
                                    {f.k}
                                </p>
                                <p className="text-[13.5px] text-[rgba(255,255,255,0.55)] leading-relaxed">{f.v}</p>
                            </motion.div>
                        ))}
                    </div>
                </div>

                <motion.p
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: 0.2 }}
                    className="mt-6 text-[12.5px] text-[rgba(255,255,255,0.4)] leading-relaxed max-w-[760px]"
                >
                    Our own arithmetic, not a quote from anyone. It assumes ten dollars an interview and a
                    five-thousand-dollar machine, and it ignores the electricity and the hours someone on your side
                    spends running it. Put your own two numbers in; the crossover moves, the shape does not.
                </motion.p>
            </div>
        </section>
    );
}
