"""Run a conversation against a backend and print what happened."""

import argparse
import sys

from .backends import build_backend
from .config import AudioConfig, BackendConfig, CallConfig
from .conversation import ConversationRunner
from .scoring import score_call
from .prompts import GREETING, SYSTEM_PROMPT


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="zeg-converse")
    p.add_argument(
        "--backend",
        default="mock",
        choices=["mock", "gb10"],
        help="mock runs anywhere; gb10 needs the real box and weights",
    )
    p.add_argument("--checkpoint", default=BackendConfig.checkpoint_dir)
    p.add_argument("--quiet", action="store_true", help="summary only")
    p.add_argument("--no-score", action="store_true", help="skip the post-call report")
    args = p.parse_args(argv)

    backend = build_backend(
        BackendConfig(
            kind=args.backend,
            checkpoint_dir=args.checkpoint,
            audio=AudioConfig(),
        )
    )
    backend.warmup()

    runner = ConversationRunner(backend, call=CallConfig())
    result = runner.run(SYSTEM_PROMPT, GREETING)

    if not args.quiet:
        print(result.render())
        print()

    print("backend            %s" % backend.name)
    print("call duration      %.1f s" % result.duration_s)
    print("agent speech       %.1f s" % result.agent_audio_s)
    print("agent audio frames %d" % result.agent_audio_frames)
    print("interruptions      %d" % result.interruptions)
    if result.median_latency_ms is not None:
        print("reply latency      median %.0f ms, p95 %.0f ms"
              % (result.median_latency_ms, result.p95_latency_ms))
    if result.hit_time_limit:
        print("note               call hit the 15 minute wall clock")
    for e in result.errors:
        print("error              %s" % e)

    if not args.no_score:
        # The post-call pass. Offline, so it can afford judgement the live path cannot.
        # Without a model behind it this is the heuristic judge, which is shallow by
        # design; the report shape and the evidence discipline are what it demonstrates.
        print()
        print(score_call(result.transcript).render())

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
