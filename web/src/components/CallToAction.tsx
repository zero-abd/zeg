"use client";

import { motion } from "framer-motion";
import { CodeBlock, GitHubIcon, PrimaryButton, REPO_URL, SecondaryButton } from "./ui";

const RUN = `git clone https://github.com/zero-abd/zeg.git && cd zeg
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m zeg.cli`;

export default function CallToAction() {
    return (
        <section id="run-it" className="relative py-28 px-6 border-t border-[rgba(255,255,255,0.08)] overflow-hidden">
            <div className="dot-bg opacity-60" />
            <div className="hero-glow" style={{ top: "-40%" }} />

            <div className="relative z-10 max-w-[760px] mx-auto text-center">
                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                >
                    <span className="inline-block text-[13px] font-semibold uppercase tracking-[0.1em] text-[#2dd4bf] mb-4">
                        Try it
                    </span>
                    <h2 className="text-[clamp(2rem,4.5vw,3rem)] font-[800] tracking-[-0.025em] leading-[1.12] mb-5 text-balance">
                        Hear the shape of a call <span className="gradient-text">without the hardware.</span>
                    </h2>
                    <p className="text-[17px] text-[rgba(255,255,255,0.6)] leading-relaxed mb-10 max-w-[600px] mx-auto text-pretty">
                        A mock backend replays a scripted interview through the real conversation harness — full
                        duplex, barge-in, timestamped transcript, latency accounting. No GPU, no weights, no
                        dependencies past pytest. It runs on a laptop in about a minute.
                    </p>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
                    className="mb-8"
                >
                    <CodeBlock filename="Terminal" code={RUN} />
                    <p className="mt-3 text-[12.5px] text-[rgba(255,255,255,0.4)]">
                        The replies come from a fixed script and the audio is a test tone, not speech. The real voice
                        needs the box.
                    </p>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
                    className="flex flex-col sm:flex-row items-center justify-center gap-4"
                >
                    <PrimaryButton href={REPO_URL} external>
                        <GitHubIcon />
                        Open the repo
                    </PrimaryButton>
                    <SecondaryButton href="#on-device">Read it again from the top</SecondaryButton>
                </motion.div>

                <motion.p
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: 0.3 }}
                    className="mt-8 text-[13px] text-[rgba(255,255,255,0.4)] max-w-[520px] mx-auto leading-relaxed"
                >
                    There is no signup here, because there is nothing to sign up to yet. zeg is a hackathon build in
                    the open. The repository is the front door.
                </motion.p>
            </div>
        </section>
    );
}
