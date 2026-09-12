"""zeg gateway.

Bridges a candidate's live WebRTC media to the interview agent's VoiceSession
(services/agent/zeg/backends/base.py): inbound mic audio becomes 16 kHz mono
AudioFrames pushed into the session, and the agent's 22.05 kHz replies are
played back to the candidate. See services/gateway/README.md.

The agent package (`zeg`) lives in the sibling services/agent tree and is not
pip-installed in the hackathon setup, it is used via PYTHONPATH. This shim makes
`import zeg` work even when that env is not set, so `python -m gateway` from the
repo root just works.
"""

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))          # services/gateway/gateway
_services = os.path.dirname(os.path.dirname(_here))         # services
_agent = os.path.join(_services, "agent")                   # services/agent
if os.path.isdir(os.path.join(_agent, "zeg")) and _agent not in sys.path:
    sys.path.insert(0, _agent)
