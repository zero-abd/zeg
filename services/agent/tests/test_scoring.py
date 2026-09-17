import pytest

from zeg.conversation import TranscriptEntry as T
from zeg.engine import DIMENSIONS
from zeg.scoring import (
    Assessment,
    DimensionScore,
    HeuristicJudge,
    Judge,
    RolePack,
    band_for,
    score_call,
    to_qa_units,
)


def strong():
    """A candidate who answers specifically across every dimension."""
    return [
        T(0, "agent", "Tell me about the hardest bug you shipped a fix for."),
        T(10, "caller", "A race in our reconciler. I wrote the repro harness and bisected it."),
        T(20, "agent", "What did you personally do?"),
        T(30, "caller", "I wrote the advisory-lock fix because the root cause was a double read."),
        T(40, "agent", "Any numbers?"),
        T(50, "caller", "11 double-settlements over 6 weeks, down to 0 after."),
        T(60, "agent", "What did it cost?"),
        T(70, "caller", "We gave up parallel reconciliation. Batch time roughly doubled."),
        T(80, "agent", "How did you find it?"),
        T(90, "caller", "I suspected a lock ordering issue and reproduced it under load."),
    ]


def thin():
    return [
        T(0, "agent", "Tell me about a recent project."),
        T(10, "caller", "we basically did various things you know"),
        T(20, "agent", "Anything specific?"),
        T(30, "caller", "pretty much just stuff"),
    ]


# --- segmentation ------------------------------------------------------------


def test_questions_pair_with_the_answer_that_followed():
    units = to_qa_units(strong())
    assert len(units) == 5
    assert units[0].question.startswith("Tell me")
    assert "repro harness" in units[0].answer
    assert units[0].asked_at_s == 0 and units[0].answered_at_s == 10


def test_an_unanswered_final_question_is_dropped():
    units = to_qa_units([T(0, "agent", "q"), T(10, "caller", "a"), T(20, "agent", "unanswered")])
    assert len(units) == 1


def test_an_empty_transcript_yields_nothing():
    assert to_qa_units([]) == []


def test_a_caller_turn_before_any_question_is_ignored():
    assert to_qa_units([T(0, "caller", "hello?")]) == []


# --- evidence discipline -----------------------------------------------------


def test_a_dimension_with_no_evidence_is_insufficient_not_low():
    a = score_call(thin())
    for d in a.dimensions:
        if d.insufficient:
            assert d.score is None
            assert "Not a low score" in d.note


def test_every_score_carries_a_quote():
    a = score_call(strong())
    for d in a.dimensions:
        if not d.insufficient:
            assert d.evidence, "%s scored with no evidence" % d.dimension
            assert d.evidence[0].quote


def test_evidence_keeps_its_timestamp():
    a = score_call(strong())
    scored = [d for d in a.dimensions if not d.insufficient]
    assert all(e.at_s > 0 for d in scored for e in d.evidence)


# --- bands -------------------------------------------------------------------


def test_a_thin_call_is_insufficient_signal_not_a_rejection():
    a = score_call(thin())
    assert a.band == "insufficient signal"
    assert a.overall is None
    assert any("human screen" in f for f in a.flags)


def test_a_strong_call_scores_and_lands_in_a_band():
    a = score_call(strong())
    assert a.overall is not None
    assert 1 <= a.overall <= 10
    assert a.band != "insufficient signal"


def test_advance_requires_every_dimension_to_have_evidence():
    """A high mean over a thin rubric is not an advance."""
    thin_rubric = [DimensionScore(d, 4, [], "") for d in DIMENSIONS[:3]]
    thin_rubric += [DimensionScore(d, None, [], "") for d in DIMENSIONS[3:]]
    assert band_for(10, thin_rubric) == "advance with reservations"


def test_reservations_band_is_reachable():
    full = [DimensionScore(d, 3, [], "") for d in DIMENSIONS]
    assert band_for(7, full) == "advance with reservations"


# --- independence and weighting ----------------------------------------------


def test_dimensions_are_judged_one_at_a_time():
    """No halo: a judge must never see another dimension's verdict."""
    seen = []

    class Spy(Judge):
        def score_dimension(self, dimension, units):
            seen.append(dimension)
            return DimensionScore(dimension, 3, [])

    score_call(strong(), judge=Spy())
    assert seen == list(DIMENSIONS)


def test_role_weighting_moves_the_headline():
    class Split(Judge):
        def score_dimension(self, dimension, units):
            return DimensionScore(dimension, 4 if dimension == "ownership" else 1, [])

    heavy = RolePack("ownership-heavy", {d: (9.0 if d == "ownership" else 1.0) for d in DIMENSIONS})
    assert score_call(strong(), judge=Split(), role=heavy).overall > \
           score_call(strong(), judge=Split()).overall


def test_scores_stay_inside_the_rubric():
    a = score_call(strong())
    for d in a.dimensions:
        assert d.score is None or 1 <= d.score <= 4


# --- report ------------------------------------------------------------------


def test_report_leads_with_the_headline_and_the_band():
    first = score_call(strong()).render().splitlines()[0]
    assert "/10" in first


def test_a_heuristic_report_says_it_is_not_for_a_hiring_decision():
    """The heuristic judge's own documentation says its reports must never reach a
    hiring manager, and "9/10 — advance" from it looked exactly like a real one."""
    lines = score_call(strong()).render().splitlines()
    assert "/10" in lines[0], "the headline still leads"
    assert "heuristic judge" in lines[1]
    assert "not for a hiring decision" in lines[1]


def test_a_thin_heuristic_report_carries_the_warning_too():
    rendered = score_call(thin()).render()
    assert "not for a hiring decision" in rendered


def test_a_model_judged_report_names_its_judge_without_the_warning():
    import json

    from zeg.scoring import ModelJudge

    def complete(prompt):
        return json.dumps({"score": 3, "quote": "I wrote the advisory-lock fix",
                           "reason": "first person"})

    report = score_call(strong(), judge=ModelJudge(complete))
    assert report.judge == "model"
    rendered = report.render()
    assert "Scored by the model judge." in rendered
    assert "not for a hiring decision" not in rendered


def test_report_says_a_human_decides():
    assert "does not decide" in score_call(strong()).render()


def test_report_shows_insufficient_rather_than_a_number():
    assert "insufficient evidence" in score_call(thin()).render()


def test_report_quotes_with_a_timestamp():
    assert "[00:" in score_call(strong()).render()


def test_a_no_score_report_still_renders():
    r = score_call(thin()).render()
    assert "no score" in r and "insufficient signal" in r


def test_the_heuristic_judge_is_deterministic():
    assert score_call(strong()).overall == score_call(strong()).overall


def test_judge_names_itself():
    assert HeuristicJudge().name == "heuristic"


def test_ownership_is_found_in_a_lowercased_transcript():
    """Recognised speech is often lowercased; a capital-I rule loses every claim."""
    lower = [
        T(0, "agent", "What did you do?"),
        T(10, "caller", "i wrote the fix and the repro harness"),
    ]
    own = next(d for d in score_call(lower).dimensions if d.dimension == "ownership")
    assert not own.insufficient


# --- a candidate who pauses and keeps going -----------------------------------


def test_a_second_consecutive_answer_is_not_dropped():
    """Real candidates pause and then continue. The second half used to be discarded,
    and it is often the specific half, because they have had a moment to remember the
    number."""
    paused = [
        T(0, "agent", "What did you do?"),
        T(10, "caller", "I rewrote the retry logic."),
        T(18, "caller", "Retry volume dropped by ninety percent, because of the jitter."),
    ]
    units = to_qa_units(paused)
    assert len(units) == 1
    assert "ninety percent" in units[0].answer


def test_the_merged_answer_keeps_the_later_timestamp():
    paused = [
        T(0, "agent", "What did you do?"),
        T(10, "caller", "I rewrote it."),
        T(18, "caller", "Volume dropped ninety percent."),
    ]
    assert to_qa_units(paused)[0].answered_at_s == 18


def test_a_dropped_continuation_used_to_cost_the_whole_score():
    """The regression: with the continuation discarded there was no citable evidence
    left and the call came out as insufficient signal."""
    paused = [
        T(0, "agent", "What did you do?"),
        T(10, "caller", "It was the reconciler."),
        T(18, "caller", "I wrote the advisory-lock fix because two workers raced."),
        T(30, "agent", "What did it cost?"),
        T(40, "caller", "We gave up parallelism. Batch time roughly doubled."),
        T(50, "agent", "How did you find it?"),
        T(60, "caller", "I reproduced it under load and narrowed it to one merchant."),
    ]
    assert score_call(paused).band != "insufficient signal"


def test_three_turns_in_a_row_all_merge():
    runs = [
        T(0, "agent", "Tell me."),
        T(10, "caller", "one"),
        T(15, "caller", "two"),
        T(20, "caller", "three"),
    ]
    units = to_qa_units(runs)
    assert len(units) == 1
    assert units[0].answer == "one two three"


# --- numbers said out loud ------------------------------------------------------


@pytest.mark.parametrize("text", [
    "retry volume dropped by ninety percent",
    "about twelve hundred a second before, forty thousand after",
    "eleven double settlements over about six weeks",
    "two workers could read the same batch",
    "batch time roughly doubled",
    "latency went from 400ms to 30ms",
])
def test_a_number_is_a_number_however_it_is_written(text):
    """The interview's central probe is "give me a number". People say numbers out
    loud and recognition writes them as words, so a digits-only detector misses every
    figure the interview was designed to extract."""
    from zeg.scoring import has_number

    assert has_number(text), text


@pytest.mark.parametrize("text", [
    "one of the things we worked on",
    "we did various stuff around the backend",
    "it depends on the access patterns",
])
def test_ordinary_speech_is_not_mistaken_for_a_measurement(text):
    """A false positive here credits an answer that gave no figure at all."""
    from zeg.scoring import has_number

    assert not has_number(text), text


def test_a_spoken_number_earns_technical_depth():
    spoken = [
        T(0, "agent", "What was the impact?"),
        T(10, "caller", "Retry volume dropped by ninety percent during the next incident."),
        T(20, "agent", "And before?"),
        T(30, "caller", "We were seeing about twelve hundred retries a second."),
    ]
    depth = next(d for d in score_call(spoken).dimensions
                 if d.dimension == "technical_depth")
    assert not depth.insufficient


# --- only the interview itself is scored --------------------------------------------


def _with_consent_and_closing():
    from zeg.prompts import GREETING, WRAP_UP

    return [
        T(0, "agent", GREETING),
        T(8, "caller", "Yes, that's fine, because I'd like the recruiter to hear it."),
        T(30, "agent", "Tell me about a recent project."),
        T(40, "caller", "We moved a pipeline to streaming."),
        T(60, "agent", "What did you personally do?"),
        T(70, "caller", "I was part of the team that did it."),
        T(90, "agent", "Any numbers?"),
        T(100, "caller", "It got faster."),
        T(820, "agent", WRAP_UP),
        T(830, "caller", "Why did the team move to that queue, because I scaled one to "
                         "40000 messages a second and I fixed its root cause myself?"),
    ]


def test_the_consent_answer_and_the_closing_question_are_not_scored():
    """Every agent line was paired with the reply after it. A candidate with nothing
    checkable in the interview scored 9 out of 10, with technical depth and communication
    quoting why they agreed to be recorded and ownership quoting a question they asked."""
    a = score_call(_with_consent_and_closing(), window=(8, 820))
    assert a.band == "insufficient signal"
    quotes = [e.quote for d in a.dimensions for e in d.evidence]
    assert not any("recruiter to hear it" in q or "messages a second" in q for q in quotes)


def test_the_first_question_after_consent_is_inside_the_interview():
    units = to_qa_units(_with_consent_and_closing(), window=(8, 820))
    assert units[0].question == "Tell me about a recent project."


def test_the_wrap_up_itself_is_outside_the_interview():
    units = to_qa_units(_with_consent_and_closing(), window=(8, 820))
    assert units[-1].question == "Any numbers?"


def test_without_a_window_every_exchange_is_still_paired():
    """What the evals rely on, and what used to happen to every live call."""
    assert len(to_qa_units(_with_consent_and_closing())) == 5


# --- a hesitation is not an answer ---------------------------------------------------


def test_a_hesitation_is_not_taken_as_the_answer_to_a_question():
    """"um" was recorded as the answer, and the real answer was paired with the agent's
    "take your time" as though that were the question."""
    units = to_qa_units([
        T(30, "agent", "What did you personally do there?"),
        T(32, "caller", "um"),
        T(34, "agent", "Take your time."),
        T(40, "caller", "I wrote the advisory lock fix myself"),
    ])
    assert [(u.question, u.answer) for u in units] == [
        ("What did you personally do there?", "I wrote the advisory lock fix myself"),
    ]


def test_a_real_question_after_a_hesitation_is_what_gets_answered():
    """If the agent asks something new after the hesitation, the reply answers that."""
    units = to_qa_units([
        T(30, "agent", "What did you personally do there?"),
        T(32, "caller", "um"),
        T(34, "agent", "Which part of the fix did you write?"),
        T(40, "caller", "the advisory lock"),
    ])
    assert [(u.question, u.answer) for u in units] == [
        ("Which part of the fix did you write?", "the advisory lock"),
    ]


def test_a_hesitation_after_an_answer_is_not_merged_into_it():
    units = to_qa_units([
        T(30, "agent", "What did you personally do there?"),
        T(40, "caller", "I wrote the advisory lock fix myself"),
        T(45, "caller", "um"),
    ])
    assert units[0].answer == "I wrote the advisory lock fix myself"


def test_a_question_answered_only_with_a_hesitation_has_no_answer():
    assert to_qa_units([
        T(30, "agent", "What did you personally do there?"),
        T(32, "caller", "um"),
    ]) == []


# --- the quote in the report is the evidence, not the lead-in ------------------------

LONG_ANSWERS = {
    "ownership": ("so the reconciler was double settling payments during peak hours and "
                  "after a lot of back and forth I wrote the advisory lock fix myself",
                  "I wrote the advisory lock fix"),
    "technical_depth": ("we measured it over the six weeks before the fix and there were "
                        "eleven double settlements, costing about forty thousand dollars",
                        # The window sits on the first figure the judge matched.
                        "over the six weeks before the fix"),
    "tradeoffs": ("the lock serialises writers on a batch so to be honest we gave up some "
                  "write throughput, maybe fifteen percent at peak",
                  "gave up some write throughput"),
    "debugging": ("at first nobody could reproduce it in staging, so I suspected the retry "
                  "path and narrowed it to two workers claiming the same batch",
                  # The window sits on the first marker the judge matched, which since
                  # reproducing counts as debugging is "could reproduce it".
                  "could reproduce it in staging"),
}


def long_call():
    out, t = [], 60
    for answer, _ in LONG_ANSWERS.values():
        out += [T(t, "agent", "Tell me more?"), T(t + 5, "caller", answer)]
        t += 60
    return out


def quoted_lines(report):
    return [line.strip() for line in report.splitlines() if line.strip().startswith("[")]


def test_a_long_quote_shows_the_evidence_it_was_scored_on():
    """Cut from the end, every quote in this report stopped before its evidence."""
    report = score_call(long_call()).render()
    for dimension, (_, evidence) in LONG_ANSWERS.items():
        assert evidence in report, "%s quote lost %r:\n%s" % (dimension, evidence, report)


def test_a_quote_excerpt_stays_short_and_on_word_boundaries():
    from zeg.scoring import excerpt

    for dimension, (answer, _) in LONG_ANSWERS.items():
        piece = excerpt(answer, dimension)
        assert len(piece) <= 74, piece
        for word in piece.strip("…").split():
            assert word in answer.split(), "cut mid-word: %r in %r" % (word, piece)


def test_a_short_quote_is_shown_whole():
    from zeg.scoring import excerpt

    assert excerpt("I wrote the fix myself.", "ownership") == "I wrote the fix myself."


def test_a_long_quote_with_no_marker_keeps_both_ends():
    from zeg.scoring import excerpt

    quote = "we spent the first month " + "arguing about the schema " * 4 + "and shipped in May"
    piece = excerpt(quote, "ownership")
    assert piece.startswith("we spent") and piece.endswith("shipped in May")


# --- ownership in the words people actually use -------------------------------------

OWNED = [
    "I wrote the advisory lock fix",
    "I personally rewrote the reconciler",
    "I actually built the repro harness",
    "I then fixed the retry path",
    "I myself debugged it over two nights",
    "I implemented the advisory lock",
    "I added the idempotency key",
    "I refactored the settlement worker",
    "I migrated the queue to the new cluster",
    "I was the one who wrote the fix",
    "I owned the rollout end to end",
    "I drove the migration",
    "I was responsible for the rollout",
    "I isolated it to the settlement worker",
    "I ruled out the network first",
    # Tense is how someone talks, not what they did.
    "I've rewritten the reconciler",
    "I have reproduced it locally",
    "I write the fix myself",
    "I had built the harness before the outage",
    # Possessive claims answer the engine's own probe as naturally as "I did" does.
    "My part was the advisory-lock fix",
    "The advisory lock was my change",
    "That fix was mine",
    "I was in charge of the rollout",
    "The rollout was my responsibility",
    "I took on the migration",
    "I took ownership of the reconciler",
    "My role was the reproduction harness",
]

NOT_OWNED = [
    "we wrote the advisory lock fix",
    "the team implemented it and I watched",
    "I think the platform team built it",
    "someone on my team refactored the worker",
    "I basically was around when they shipped it",
    "I find that hard to say",
    "I run into this kind of thing a lot",
    "I'd rewrite it differently now",
    "Our team's part was the migration",
    "My job is at a payments company",
    "That was my manager's call",
    "It was my first job out of college",
]


@pytest.mark.parametrize("text", OWNED, ids=OWNED)
def test_a_first_person_claim_is_ownership_however_it_is_phrased(text):
    """The engine asks what they personally did. "I personally rewrote it" scored no
    ownership at all; ten of these twelve went unrecognised."""
    from zeg.scoring import signals

    assert "ownership" in signals(text), text


@pytest.mark.parametrize("text", NOT_OWNED, ids=NOT_OWNED)
def test_the_team_doing_it_is_not_ownership(text):
    from zeg.scoring import signals

    assert "ownership" not in signals(text), text


def test_the_same_claim_in_other_words_scores_the_same():
    """Scoring the verb a candidate picked is scoring vocabulary, not ownership."""
    def ownership_of(answer):
        call = [T(0, "agent", "What did you personally do?"), T(5, "caller", answer)]
        return next(d for d in score_call(call).dimensions if d.dimension == "ownership").score

    assert ownership_of("I wrote the advisory lock fix.") == \
        ownership_of("I personally implemented the advisory lock fix.")


# --- tradeoffs and debugging in the words people actually use ------------------------

TRADEOFFS = [
    "we gave up some write throughput",
    "the tradeoff was extra operational complexity",
    "the trade-off was more memory per worker",
    "we accepted higher tail latency to get exactly-once settlement",
    "we sacrificed strict ordering across shards",
    "we chose consistency over availability",
    "it cost us about fifteen percent throughput",
    "in exchange we lost the ability to run batches in parallel",
    "the downside is that reads are slower",
    "we've given up strict ordering",
    "we trade latency for durability",
]
NOT_TRADEOFFS = [
    "we reconcile trades every night",
    "I accepted the offer in March",
    "we chose Postgres for the ledger",
    "we lost a day to the outage",
    "it was the right call",
]
DEBUGGING = [
    "I suspected the retry path",
    "I reproduced it locally",
    "my hypothesis was a lock ordering problem",
    "I added logging and found two workers taking the same batch",
    "I ruled out the network first",
    "I isolated it to the settlement worker",
    "I looked at the flame graph and saw the lock contention",
    "I traced one request through all three services",
    "my guess was clock skew, so I checked the timestamps",
    "I narrowed it down to one commit",
    "I suspect the retry path",
    "I isolate it to the worker",
]
NOT_DEBUGGING = [
    "there is a narrow window before the lock expires",
    "I added a feature flag for the rollout",
    "the profile page loads slowly",
    "I guess we shipped it in May",
    "I checked in with the team every morning",
]


@pytest.mark.parametrize("text", TRADEOFFS, ids=TRADEOFFS)
def test_a_tradeoff_is_recognised_however_it_is_phrased(text):
    """Three of ten were. The list did not contain the word "tradeoff"."""
    from zeg.scoring import signals

    assert "tradeoffs" in signals(text), text


@pytest.mark.parametrize("text", NOT_TRADEOFFS, ids=NOT_TRADEOFFS)
def test_a_choice_or_a_loss_alone_is_not_a_tradeoff(text):
    from zeg.scoring import signals

    assert "tradeoffs" not in signals(text), text


@pytest.mark.parametrize("text", DEBUGGING, ids=DEBUGGING)
def test_debugging_is_recognised_however_it_is_phrased(text):
    """Four of ten were: ruling something out or isolating it counted for nothing."""
    from zeg.scoring import signals

    assert "debugging" in signals(text), text


@pytest.mark.parametrize("text", NOT_DEBUGGING, ids=NOT_DEBUGGING)
def test_ordinary_work_is_not_debugging(text):
    from zeg.scoring import signals

    assert "debugging" not in signals(text), text


# --- explanations and structure in the words people actually use ---------------------

CAUSAL = [
    "because two workers claimed the same batch",
    "it turned out the lock expired early",
    "the lock was taken twice, which caused the double settlements",
    "that led to duplicate payments",
    "as a result the batch was settled twice",
    "the reason was a missing unique constraint on the batch id",
    "that is why the retries charged the card again",
    "the problem was that the lock expired before the write finished",
    "which meant the second worker never saw the first one's row",
]
NOT_CAUSAL = [
    "since March we have been on the new cluster",
    "we moved the ledger to its own database",
    "the batch job runs at midnight",
]
STRUCTURED = [
    "first we reproduced it, then we added the lock, and finally we backfilled the ledger",
    "there were two parts to it: the lock, and the backfill",
    "to answer your question directly, I wrote the lock",
    "short version: a race. Longer version: two workers claimed one batch",
    "step one was the repro, step two the fix",
]
NOT_STRUCTURED = [
    "the first release was in May",
    "I then fixed the retry path",
    "we shipped it and moved on",
]


@pytest.mark.parametrize("text", CAUSAL, ids=CAUSAL)
def test_a_causal_explanation_is_recognised_however_it_is_phrased(text):
    """Three of ten were. The rest explained why and counted for nothing."""
    from zeg.scoring import signals

    got = signals(text)
    assert "technical_depth" in got and "communication" in got, (text, got)


@pytest.mark.parametrize("text", NOT_CAUSAL, ids=NOT_CAUSAL)
def test_a_statement_of_what_happened_is_not_an_explanation(text):
    from zeg.scoring import signals

    assert "communication" not in signals(text), text


@pytest.mark.parametrize("text", STRUCTURED, ids=STRUCTURED)
def test_a_structured_answer_counts_for_communication(text):
    """The brief is structure and responsiveness, and none of these counted."""
    from zeg.scoring import signals

    assert "communication" in signals(text), text


@pytest.mark.parametrize("text", NOT_STRUCTURED, ids=NOT_STRUCTURED)
def test_a_single_step_is_not_structure(text):
    from zeg.scoring import signals

    assert "communication" not in signals(text), text


# --- a vague phrase is not a vague answer --------------------------------------------


def test_a_lead_in_phrase_does_not_mark_down_specific_answers():
    """Each answer opening with "There were a lot of things going on." took this call
    from 9/10, advance, to 6/10 with reservations, on the same evidence."""
    padded = [
        T(e.at_s, e.speaker,
          e.text if e.speaker == "agent" else "There were a lot of things going on. " + e.text)
        for e in strong()
    ]
    plain, lead_in = score_call(strong()), score_call(padded)
    assert lead_in.overall == plain.overall
    assert [d.score for d in lead_in.dimensions] == [d.score for d in plain.dimensions]


def test_answers_with_nothing_in_them_still_cost_a_point():
    units_call = [
        T(0, "agent", "What did you do?"),
        T(5, "caller", "I wrote the retry fix because the lock was taken twice."),
        T(10, "agent", "Anything else?"),
        T(15, "caller", "we basically did various things"),
        T(20, "agent", "Specifically?"),
        T(25, "caller", "pretty much just stuff like that"),
    ]
    ownership = next(d for d in score_call(units_call).dimensions if d.dimension == "ownership")
    assert ownership.score == 2, "one hit is 3, and two content-free answers of three cost 1"
