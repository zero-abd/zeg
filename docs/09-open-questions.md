# Open questions

Decisions owed before or during Phase 0. Each one blocks something.

## Product

1. **Inbound or outbound calls?** Does the candidate dial a number at a scheduled time, or
   does the agent call them? Outbound is a better experience and carries telemarketing-rule
   exposure. Inbound is simpler. This changes the telephony design.
2. **Who is the buyer?** In-house recruiting teams and staffing agencies want very
   different products. Agencies have volume and less tolerance for compliance overhead.
3. **Is 15 minutes fixed or per-role?** Affects the state machine and the rubric.
4. **What happens on "insufficient signal"?** Automatic human screen, or back to the queue?
   This has a real cost implication for the customer.

## Technical

5. **Which Dell box?** Blocked on Phase 0 benchmarks.
6. **Vendor serving layer, or drive the checkpoints ourselves?** The serving layer is
   faster to a working system. Driving the checkpoints directly gives control over
   endpointing and streaming behaviour. Probably the serving layer first, but confirm it
   exposes the barge-in control we need before committing.
7. **How many concurrent calls per box?** Drives the unit economics and the sales pitch.
8. **Is a shared code pad in scope?** A read-only snippet the candidate discusses would
   deepen the technical probe considerably. It also adds a web surface, a second
   synchronization problem, and accessibility questions. Leaning no for v1.
9. **Does anything derive a speaker embedding?** If yes, biometric law applies. Confirm
   that channel separation is sufficient for diarization before any component that might
   embed voice is added.
10. **What is the update mechanism?** An appliance in someone else's rack still needs
    security patches and model updates. Pull or push, and who authorizes.

## Compliance

11. **US only, or EU from the start?** The largest single scope decision in the project.
12. **Which states in scope for v1?** Determines which notice and audit regimes apply.
13. **Who is the independent bias auditor, and what do they cost?** Get a quote in Phase 0.
14. **Who carries liability?** The customer makes the hiring decision, but the tool shapes
    it. Contract question, needs counsel.

## Team and process

15. **Who owns what?** Three people, roughly three surfaces: media and latency, interview
    engine and scoring, ops and console. Assign before Phase 0 starts.
16. **Where does hardware come from, and when?** Phase 0 cannot begin without a box, and
    lead times on these configurations are not short. This is likely the critical path
    right now.
17. **Who recruits the 50-call seed set, and the volunteers for Phase 1?** Both need
    calendar time from people who are not on this team.
