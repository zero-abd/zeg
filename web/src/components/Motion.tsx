"use client";

import { MotionConfig } from "framer-motion";

/**
 * Honours the OS "reduce motion" setting for every framer-motion animation on
 * the page. The CSS keyframes are handled separately, in globals.css.
 */
export default function Motion({ children }: { children: React.ReactNode }) {
    return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
