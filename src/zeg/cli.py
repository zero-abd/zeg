"""Run a conversation against a backend and print what happened."""

import argparse
import sys

from .backends import build_backend
from .config import AudioConfig, BackendConfig, CallConfig
from .conversation import ConversationRunner
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

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
