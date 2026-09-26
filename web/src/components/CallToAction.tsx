"use client";

import { motion } from "framer-motion";
import { CodeBlock, GitHubIcon, PrimaryButton, REPO_URL, SecondaryButton } from "./ui";
import { MAKE_DEMO_OUTPUT } from "./makeDemoOutput";

const steps = [
    {
        n: "1",
        title: "A scripted call on your laptop",
        need: "Python 3.9+ and make. No GPU, no weights, nothing past pytest.",
        code: `git clone https://github.com/zero-abd/zeg.git && cd zeg
make setup     # .venv with pytest
make demo      # a scripted interview through the mock backend
make test      # agent and gateway test suites`,
    },
    {
        n: "2",
        title: "A browser call against the mock",
        need: "Adds aiortc and aiohttp. The mock's voice is a 220 Hz tone, not speech.",
        code: `make gateway-setup
make gateway          # open http://localhost:8080, wear headphones`,
    },
    {
        n: "3",
        title: "The real interviewer, on the box",
        need: "A Dell Pro Max with an NVIDIA GB10, the speech model weights and the runtime process up.",
        code: `make gateway BACKEND=gb10     # http://<box>:8080`,
    },
];

export default function CallToAction() {
    return (
        <section id="run-it" className="relative py-28 px-6 border-t border-[rgba(255,255,255,0.08)] overflow-hidden">
            <div className="dot-bg opacity-60" />
            <div className="hero-glow" style={{ top: "-40%" }} />

            <div className="relative z-10 max-w-[900px] mx-auto">
                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="text-center"
                >
                    <span className="inline-block text-[13px] font-semibold uppercase tracking-[0.1em] text-[#2dd4bf] mb-4">
                        Run it locally
                    </span>
                    <h2 className="text-[clamp(2rem,4.5vw,3rem)] font-[800] tracking-[-0.025em] leading-[1.12] mb-5 text-balance">
                        Hear the shape of a call <span className="gradient-text">without the hardware.</span>
                    </h2>
                    <p className="text-[17px] text-[rgba(255,255,255,0.6)] leading-relaxed mb-12 max-w-[640px] mx-auto text-pretty">
                        A mock backend implements the same contract as the model, so the conversation harness, the
                        interview engine and the scorer all run on a laptop: full duplex, barge-in, a timestamped
                        transcript and the post-call report.
                    </p>
                </motion.div>

                <div className="space-y-6 mb-10">
                    {steps.map((s, i) => (
                        <motion.div
                            key={s.n}
                            initial={{ opacity: 0, y: 24 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-40px" }}
                            transition={{ duration: 0.5, delay: i * 0.08, ease: "easeOut" }}
                        >
                            <div className="flex items-baseline gap-3 mb-2.5">
                                <span className="font-mono text-[13px] text-[#2dd4bf]">{s.n}</span>
                                <div>
                                    <h3 className="text-[16px] font-bold tracking-tight">{s.title}</h3>
                                    <p className="text-[13px] text-[rgba(255,255,255,0.5)]">{s.need}</p>
                                </div>
                            </div>
                            <CodeBlock filename="Terminal" code={s.code} />
                        </motion.div>
                    ))}
                </div>

                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(5,12,14,0.7)] overflow-hidden mb-4"
                >
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 border-b border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)]">
                        <span className="text-xs text-[rgba(255,255,255,0.6)] font-medium">What step 1 prints</span>
                        <span className="text-[11px] text-[rgba(255,255,255,0.4)]">
                            verbatim output of <code className="font-mono">make demo</code>: mock backend, scripted caller,
                            heuristic judge
                        </span>
                    </div>
                    <pre className="px-5 py-4 overflow-x-auto max-h-[520px] overflow-y-auto">
                        <code className="font-mono text-[12.5px] text-[#dfe9e7] leading-relaxed whitespace-pre">
                            {MAKE_DEMO_OUTPUT}
                        </code>
                    </pre>
                </motion.div>
                <p className="text-[12.5px] text-[rgba(255,255,255,0.4)] mb-12 text-center max-w-[640px] mx-auto">
                    The replies come from a fixed script, the voice is a test tone and the clock is virtual, so the
                    durations are frame accounting, not measurements. The heuristic judge matches wording; the model
                    judge runs on the box.
                </p>

                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="flex flex-col sm:flex-row items-center justify-center gap-4"
                >
                    <PrimaryButton href={REPO_URL} external>
                        <GitHubIcon />
                        Open the repo
                    </PrimaryButton>
                    <SecondaryButton href="/demo">Try the read-only demo</SecondaryButton>
                </motion.div>

                <p className="mt-8 text-[13px] text-[rgba(255,255,255,0.4)] max-w-[520px] mx-auto leading-relaxed text-center">
                    There is no signup here, because there is nothing to sign up to yet. zeg is a hackathon build in
                    the open. The repository is the front door.
                </p>
            </div>
        </section>
    );
}
