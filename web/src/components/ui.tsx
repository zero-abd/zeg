"use client";

import { motion } from "framer-motion";
import { useCallback, useState } from "react";

export const REPO_URL = "https://github.com/zero-abd/zeg";

/**
 * The mark: a rounded square holding four level bars, two rising and two
 * falling. Two voices at once, which is the whole point of a full-duplex model.
 */
export function Logo({ className = "w-7 h-7", id = "zegGrad" }: { className?: string; id?: string }) {
    return (
        <svg className={className} viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <rect x="2" y="2" width="24" height="24" rx="7" stroke={`url(#${id})`} strokeWidth="2" />
            <path
                d="M8.5 11.5v5M12.2 8.5v11M15.8 10.5v7M19.5 13v2"
                stroke={`url(#${id})`}
                strokeWidth="2"
                strokeLinecap="round"
            />
            <defs>
                <linearGradient id={id} x1="0" y1="0" x2="28" y2="28">
                    <stop offset="0%" stopColor="#14b8a6" />
                    <stop offset="100%" stopColor="#2dd4bf" />
                </linearGradient>
            </defs>
        </svg>
    );
}

export function GitHubIcon({ size = 18, className = "" }: { size?: number; className?: string }) {
    return (
        <svg width={size} height={size} className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
        </svg>
    );
}

/** Centred eyebrow / heading / lede block used at the top of every section. */
export function SectionHeading({
    eyebrow,
    title,
    accent,
    lede,
}: {
    eyebrow: string;
    title: string;
    accent?: string;
    lede?: string;
}) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="text-center mb-16"
        >
            <span className="inline-block text-[13px] font-semibold uppercase tracking-[0.1em] text-[#2dd4bf] mb-4">
                {eyebrow}
            </span>
            <h2 className="text-[clamp(2rem,4vw,2.75rem)] font-[800] tracking-[-0.02em] mb-4 text-balance">
                {title} {accent ? <span className="gradient-text">{accent}</span> : null}
            </h2>
            {lede ? (
                <p className="text-[17px] text-[rgba(255,255,255,0.6)] max-w-[580px] mx-auto leading-relaxed text-pretty">
                    {lede}
                </p>
            ) : null}
        </motion.div>
    );
}

export function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);

    const copy = useCallback(() => {
        navigator.clipboard?.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    }, [text]);

    return (
        <button
            type="button"
            onClick={copy}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors ${
                copied
                    ? "text-[#2dd4bf]"
                    : "text-[rgba(255,255,255,0.4)] hover:text-white hover:bg-[rgba(255,255,255,0.05)]"
            }`}
        >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            {copied ? "Copied" : "Copy"}
            <span className="sr-only"> the command</span>
        </button>
    );
}

export function CodeBlock({ filename, code }: { filename: string; code: string }) {
    return (
        <div className="rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(5,12,14,0.7)] overflow-hidden text-left">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)]">
                <span className="text-xs text-[rgba(255,255,255,0.4)] font-medium">{filename}</span>
                <CopyButton text={code} />
            </div>
            <pre className="px-5 py-4 overflow-x-auto">
                <code className="font-mono text-[13px] text-[#eef4f3] leading-relaxed whitespace-pre">{code}</code>
            </pre>
        </div>
    );
}

export function PrimaryButton({
    href,
    children,
    external = false,
}: {
    href: string;
    children: React.ReactNode;
    external?: boolean;
}) {
    return (
        <a
            href={href}
            {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-[15px] font-semibold bg-gradient-to-br from-[#0f9c8d] to-[#2dd4bf] text-[#04110f] shadow-[0_0_20px_rgba(20,184,166,0.3),inset_0_1px_0_rgba(255,255,255,0.25)] hover:-translate-y-0.5 hover:shadow-[0_0_30px_rgba(20,184,166,0.5)] transition-all duration-300 w-full sm:w-auto justify-center"
        >
            {children}
        </a>
    );
}

export function SecondaryButton({
    href,
    children,
    external = false,
}: {
    href: string;
    children: React.ReactNode;
    external?: boolean;
}) {
    return (
        <a
            href={href}
            {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-[15px] font-semibold bg-[rgba(255,255,255,0.03)] text-white border border-[rgba(255,255,255,0.08)] hover:border-[rgba(45,212,191,0.4)] hover:bg-[rgba(255,255,255,0.06)] hover:-translate-y-0.5 transition-all duration-300 w-full sm:w-auto justify-center"
        >
            {children}
        </a>
    );
}
