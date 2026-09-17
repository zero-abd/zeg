"""Run a conversation against a backend and print what happened."""

import argparse
import sys

from .backends import build_backend
from .config import AudioConfig, BackendConfig, CallConfig
from .conversation import ConversationRunner, InterviewRunner
from .prompts import GREETING, SYSTEM_PROMPT


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="zeg-converse")
    p.add_argument(
        "--backend",
        default="mock",
        choices=["mock", "tts", "gb10"],
        help="mock runs anywhere and is silent; tts speaks real words on this "
             "machine; gb10 needs the box and the weights",
    )
    p.add_argument("--checkpoint", default=BackendConfig.checkpoint_dir)
    p.add_argument("--quiet", action="store_true", help="summary only")
    p.add_argument("--no-score", action="store_true", help="skip the post-call report")
    p.add_argument("--raw", action="store_true",
                   help="bypass the interview engine and measure the backend alone")
    args = p.parse_args(argv)

    backend = build_backend(
        BackendConfig(
            kind=args.backend,
            checkpoint_dir=args.checkpoint,
            audio=AudioConfig(),
        )
    )
    backend.warmup()

    if args.raw:
        return _raw(backend, args)

    result = InterviewRunner(backend).run()

    if not args.quiet:
        print(result.render())
        print()

    print("backend            %s" % backend.name)
    print("call duration      %.1f s" % result.duration_s)
    print("consent            %s" % ("granted" if result.consent else "declined"))
    print("interruptions      %d" % result.interruptions)
    print("briefings sent     %d" % len(result.steers))
    print("probes issued      %d" % len(result.probes))
    print("session rollovers  %d" % result.rollovers)
    if result.ended:
        print("ended              %s" % result.ended)
    for f in result.flags:
        print("flag               %s" % f)

    if not args.no_score:
        # Offline, so it can afford judgement the live path cannot. Without a model
        # behind it this is the heuristic judge, which is shallow by design; the report
        # shape and the evidence discipline are what it demonstrates.
        print()
        # Only the interview itself. The consent answer and anything said after the
        # wrap-up used to be scored as if they answered interview questions.
        print(report_for(result).render())

    return 0


def report_for(result):
    """The report for a finished call.

    The interview's flags travel with it: a candidate who talked over the recording
    disclosure, a prohibited question that was blocked. They were printed beside the
    report and left out of it, so the report itself — the thing a recruiter reads, and
    the thing anything other than this console would keep — did not mention them.

    Only the interview is scored. The consent answer and anything said after the
    wrap-up are outside the window.

    A call that was cut short says so. Every failure path ends the call with whatever
    was gathered, which is right, but a score from four minutes of a fifteen-minute
    interview reads exactly like a score from the whole thing unless the report says
    otherwise.
    """
    from .report import assemble_report

    return assemble_report(
        result.transcript,
        flags=result.flags,
        consent=result.consent,
        interview_started_s=result.interview_started_s,
        wrapped_up_s=result.wrapped_up_s,
        ended=result.ended,
        errors=result.errors,
    )


def _raw(backend, args) -> int:
    """The backend on its own, with no engine in the loop. For latency work."""
    result = ConversationRunner(backend, call=CallConfig()).run(SYSTEM_PROMPT, GREETING)
    if not args.quiet:
        print(result.render())
        print()
    print("backend            %s" % backend.name)
    print("call duration      %.1f s" % result.duration_s)
    print("agent speech       %.1f s" % result.agent_audio_s)
    print("interruptions      %d" % result.interruptions)
    if result.median_latency_ms is not None:
        print("reply latency      median %.0f ms, p95 %.0f ms"
              % (result.median_latency_ms, result.p95_latency_ms))
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
