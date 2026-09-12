#!/usr/bin/env python3
"""Build the zeg pitch deck.

Edit SLIDES below, run this, open the HTML. No dependencies, stdlib only, the
same rule the agent service follows.

    python3 tools/build_deck.py              # writes deck.html
    python3 tools/build_deck.py out/x.html   # writes somewhere else

Presenting: arrow keys or space to move, F for fullscreen, N for speaker notes,
Escape to leave fullscreen. It prints to PDF from the browser, one slide a page.
"""

import html
import json
import sys

# --------------------------------------------------------------------------
# The deck. Every slide is a dict with a `kind` that picks its layout, and a
# `notes` string that only the presenter sees.
#
# Keep the words few. The slide is a headline, not a paragraph; if a sentence
# needs a second line to survive, it belongs in the notes.
# --------------------------------------------------------------------------

SLIDES = [
    {
        "kind": "title",
        "wordmark": "zeg",
        "headline": "The first interview,\ndone for you.",
        "sub": "A screening agent for recruiters. Runs on one machine you own.",
        "team": "Abdullah · Hyunsuh · Eunice",
        "notes": "We built zeg. It does a recruiter's first screening call and hands back "
                 "evidence instead of a gut feeling. All of it on one machine in your office.",
    },
    {
        "kind": "stats",
        "eyebrow": "The problem",
        "headline": "Too many people to talk to.",
        "stats": [
            ("200", "applicants for one role"),
            ("30 min", "for every first call"),
            ("100 hrs", "of engineer time. Per role."),
        ],
        "kicker": "So most people get judged on a résumé. Or never hear back at all.",
        "notes": "More applicants than engineers can phone-screen. The first call is half an "
                 "hour and it is the same shape every time. Nobody has 100 hours, so the "
                 "filter becomes the résumé — which is a guess.",
    },
    {
        "kind": "rows",
        "eyebrow": "Today",
        "headline": "The first screen is the weak link.",
        "rows": [
            ("Résumés are guesses", "Keywords. Not whether they can actually do it."),
            ("Every screener is different", "Different engineer, different bar, same job."),
            ("Good people slip away", "The best candidates stop waiting and take the other offer."),
        ],
        "notes": "Three failures. Résumés measure keywords. Two engineers hold two different "
                 "bars. And the strongest candidates have other offers, so delay loses them first.",
    },
    {
        "kind": "statement",
        "eyebrow": "What we built",
        "headline": "zeg talks to every candidate — then tells you who is worth your time.",
        "kicker": "And it shows you the quotes that made it say so.",
        "notes": "One sentence. It does the first call with everyone and gives back an "
                 "evidenced shortlist. The important half is the second line: it shows its work.",
    },
    {
        "kind": "steps",
        "eyebrow": "How it works",
        "headline": "Three steps.",
        "steps": [
            ("They click a link", "No app, no install, no scheduling back and forth."),
            ("A 15-minute call", "A real conversation. They can interrupt it."),
            ("You get a report", "A score, and the quotes behind every part of it."),
        ],
        "kicker": "Same questions, same clock, same bar — for everyone who applies.",
        "notes": "Candidate side: a link and a microphone. Recruiter side: a report. The quiet "
                 "win is consistency — everybody gets the same interview.",
    },
    {
        "kind": "transcript",
        "eyebrow": "What makes it different",
        "headline": "It does not take the first answer.",
        "turns": [
            ("agent",  "00:18", "Tell me about the hardest bug you shipped a fix for this year."),
            ("caller", "00:28", "A race condition in our payment reconciler."),
            ("agent",  "00:28", "What did you personally do there, as opposed to the rest of the team?"),
            ("caller", "00:38", "I wrote the fix and the repro harness."),
            ("agent",  "00:38", "Do you remember roughly what the throughput was before and after?"),
            ("caller", "00:47", "About twelve hundred a second before, forty thousand after."),
            ("agent",  "00:47", "What did you give up to get that? Every fix costs something."),
        ],
        "kicker": "Four follow-ups deep. That is where the real answer lives.",
        "notes": "This is the beat that matters. Anyone can ask a question. zeg keeps going: "
                 "what did YOU do, give me a number, what did it cost. It stops when the answer "
                 "gets specific. That is the difference between a chatbot and a screen.",
    },
    {
        "kind": "report",
        "eyebrow": "The report",
        "headline": "Every score comes with its quote.",
        "lede": "A recruiter reads it in 90 seconds. A hiring manager can argue with it, "
                "because the evidence is right there.",
        "score": "7",
        "band": "advance with reservations",
        "lines": [
            ("Ownership",  "3/4", "00:38", "i wrote the fix and the repro harness"),
            ("Trade-offs", "3/4", "00:52", "we gave up strict ordering across shards"),
            ("Debugging",  "3/4", "01:00", "a downstream report started double counting"),
        ],
        "foot": "A human decides. zeg only gathers the evidence.",
        "notes": "This is what the recruiter actually sees. Not a black-box number — a number "
                 "with the candidate's own words under it. That is what makes it defensible.",
    },
    {
        "kind": "compare",
        "eyebrow": "The part we are proudest of",
        "headline": "It tells you when it does not know.",
        "left":  ("Most tools", "Thin answer, quiet guess.", "You get a low score and no idea why."),
        "right": ("zeg", "“Not enough evidence.”", "That is an answer, not a failure."),
        "kicker": "A made-up number in a hiring report is worse than no report.",
        "notes": "Short call, dropped connection, a topic that never came up — zeg says so. It "
                 "does not turn absence of evidence into a low score. Insufficient signal is a "
                 "real outcome, and its recommendation is: give this person a human screen.",
    },
    {
        "kind": "bias",
        "eyebrow": "Fairness",
        "headline": "What they said. Not how they said it.",
        "lede": "We tested it against itself: the same answer twice, one with “um” "
                "and “you know” left in.",
        "before": ("Before", "7", "4", "Identical facts. Three points lost for sounding nervous."),
        "after":  ("After the fix", "7", "7", "Filler is stripped before anything is judged."),
        "kicker": "Nervousness and a second language are not weaknesses.",
        "notes": "We found this in our own system with our own fairness tests. Identical facts, "
                 "and filler alone dropped a candidate from advance to reject. That is scoring "
                 "how someone sounds. It is fixed, and the test runs every time now.",
    },
    {
        "kind": "ondevice",
        "eyebrow": "Where it runs",
        "headline": "The audio never leaves your office.",
        "here": ["The voice", "The questions", "The transcript", "The score"],
        "absent": ["Hosted speech API", "Frontier model vendor", "Transcription service"],
        "kicker": "Nothing to add to a contract. Nothing to explain to your lawyer.",
        "notes": "Pull the network cable after the call connects and the interview still "
                 "finishes. For a small company this is the whole sale: no third party in the "
                 "audio path, so no data agreement to negotiate.",
    },
    {
        "kind": "cost",
        "eyebrow": "Cost",
        "headline": "Rent forever, or buy once.",
        "per_interview": 10,
        "box": 5000,
        "volumes": [250, 500, 1000, 2500],
        "facts": [
            ("~$10", "what one hosted interview costs. Every time."),
            ("~$5,000", "one machine, once. Still yours next year."),
            ("500", "interviews to break even. Then it is electricity."),
        ],
        "foot": "Our own estimate, not a quote from anyone. Put your numbers in; "
                "the crossover moves, the shape does not.",
        "notes": "Hosted screening is priced per interview, so the bill grows with exactly the "
                 "thing you want more of. A machine is bought once. Around 500 interviews it "
                 "has paid for itself; after that the next one costs electricity.",
    },
    {
        "kind": "demo",
        "eyebrow": "Live",
        "headline": "Demo",
        "watch": [
            ("It follows up", "The second question is better than the first."),
            ("You can interrupt it", "Talk over it and it stops, like a person would."),
            ("The report at the end", "A score, and the words that earned it."),
        ],
        "notes": "Run the call. Point at the machine. If anyone asks: yes, it is that box, and "
                 "no, nothing is going out to the internet.",
    },
    {
        "kind": "limits",
        "eyebrow": "Being straight with you",
        "headline": "What it does not do.",
        "items": [
            ("It does not decide", "It recommends. A person makes every call."),
            ("One call at a time", "One machine, one conversation. Scale by adding machines."),
            ("It is a first screen", "Not the whole process. It buys back the top of the funnel."),
        ],
        "kicker": "It gathers the evidence. You still do the hiring.",
        "notes": "We would rather say this than be caught by it. A recommendation engine, not a "
                 "decision maker. One call at a time — the answer to scale is more boxes, which "
                 "is also the business model.",
    },
    {
        "kind": "close",
        "headline": "Better candidates.\nLess guessing.",
        "wordmark": "zeg",
        "sub": "Every candidate gets the same 15 minutes. You get the evidence.",
        "notes": "Close on the message: every applicant gets a real conversation instead of a "
                 "résumé filter, and the recruiter gets evidence instead of a hunch. Questions.",
    },
]

TITLE = "zeg pitch deck"

# --------------------------------------------------------------------------
# Look and feel. One place for every colour and size.
# --------------------------------------------------------------------------

CSS = r"""
*,*::before,*::after{box-sizing:border-box}

:root{
  --ink:#070C0B;
  --stage:#0B1413;
  --panel:#111E1C;
  --panel-lift:#16403A;
  --edge:#1E2F2C;
  --edge-lit:#215049;
  --teal:#2DD4BF;
  --teal-dim:#1B8478;
  --paper:#E9F1EF;
  --muted:#7F918D;
  --faint:#54635F;
  --warn:#E8834A;

  --display:"Bricolage Grotesque","Trebuchet MS",system-ui,sans-serif;
  --body:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,"Courier New",monospace;
}

html,body{margin:0;height:100%}
body{
  background:var(--ink);
  color:var(--paper);
  font-family:var(--body);
  -webkit-font-smoothing:antialiased;
  overflow:hidden;
}

/* ---- the stage -------------------------------------------------------- */
#viewport{
  position:fixed; inset:0;
  display:grid; place-items:center;
  padding:16px;
}
#stage{
  width:1280px; height:720px;
  position:relative;
  transform-origin:center center;
  background:var(--stage);
  border-radius:14px;
  overflow:hidden;
  box-shadow:0 40px 120px rgba(0,0,0,.6), 0 0 0 1px var(--edge);
}

.slide{
  position:absolute; inset:0;
  padding:64px 72px;
  display:none;
  flex-direction:column;
}
.slide.on{display:flex}

/* Content animates in from a visible resting state: the first frame of every
   slide is already complete, the motion only softens the change. */
@media (prefers-reduced-motion:no-preference){
  .slide.on>*{animation:rise .42s cubic-bezier(.2,.7,.3,1) backwards}
  .slide.on>*:nth-child(2){animation-delay:.04s}
  .slide.on>*:nth-child(3){animation-delay:.08s}
  .slide.on>*:nth-child(4){animation-delay:.12s}
  @keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
}

/* ---- type ------------------------------------------------------------- */
.eyebrow{
  font-family:var(--mono);
  font-size:12px; font-weight:600; letter-spacing:.18em; text-transform:uppercase;
  color:var(--teal); margin:0 0 14px;
}
h1{
  font-family:var(--display);
  font-weight:800; font-size:54px; line-height:1.06; letter-spacing:-.022em;
  margin:0; text-wrap:balance; color:#fff;
}
h1.big{font-size:76px;line-height:1.02}
h1.huge{font-size:96px;line-height:1}
.kicker{
  font-family:var(--display);
  font-size:25px; font-weight:600; line-height:1.3; letter-spacing:-.01em;
  color:var(--teal); margin:0;
}
.kicker.plain{color:var(--paper)}
.lede{font-size:17px;line-height:1.55;color:var(--muted);margin:0;max-width:62ch}
.foot{font-size:13.5px;line-height:1.5;color:var(--faint);margin:0}
.spacer{flex:1;min-height:18px}

/* ---- panels ----------------------------------------------------------- */
.grid{display:grid;gap:18px}
.g3{grid-template-columns:repeat(3,1fr)}
.g2{grid-template-columns:1fr 1fr}

.panel{
  background:var(--panel);
  border:1px solid var(--edge);
  border-radius:12px;
  padding:26px 28px;
}
.panel.lit{background:#0F2A26;border-color:var(--edge-lit)}

.stat .n{
  font-family:var(--display); font-weight:800; font-size:52px; line-height:1;
  letter-spacing:-.03em; color:var(--teal); font-variant-numeric:tabular-nums;
}
.stat .l{margin-top:12px;font-size:14.5px;color:var(--muted);line-height:1.45}

/* A row list is not a card stack: one hairline between items, no boxes. */
.rowlist{display:flex;flex-direction:column}
.row{display:flex;gap:24px;align-items:baseline;padding:22px 0;border-top:1px solid var(--edge)}
.row:last-child{border-bottom:1px solid var(--edge)}
.row .t{font-family:var(--display);font-weight:700;font-size:23px;letter-spacing:-.01em;color:#fff;flex:0 0 330px}
.row .d{font-size:16px;color:var(--muted);line-height:1.5}

.step .k{
  font-family:var(--mono); font-size:12px; font-weight:600; letter-spacing:.16em;
  color:var(--teal-dim); text-transform:uppercase;
}
.step .t{font-family:var(--display);font-weight:700;font-size:23px;letter-spacing:-.01em;margin:14px 0 10px;color:#fff}
.step .d{font-size:15px;color:var(--muted);line-height:1.5}

/* ---- transcript ------------------------------------------------------- */
.turns{display:flex;flex-direction:column;gap:9px}
.turn{display:flex;gap:16px;align-items:flex-start}
.turn .ts{
  font-family:var(--mono);font-size:12.5px;color:var(--faint);
  padding-top:9px;flex:0 0 52px;font-variant-numeric:tabular-nums;
}
.turn .bubble{
  padding:10px 18px;border-radius:11px;font-size:16.5px;line-height:1.45;max-width:820px;
}
.turn.agent .bubble{background:var(--panel);border:1px solid var(--edge);color:var(--paper)}
.turn.caller{flex-direction:row-reverse}
.turn.caller .ts{text-align:right}
.turn.caller .bubble{background:#12332E;border:1px solid var(--edge-lit);color:#fff}

/* ---- report card ------------------------------------------------------ */
.report{background:var(--panel);border:1px solid var(--edge);border-radius:14px;padding:30px 32px}
.report .head{display:flex;align-items:baseline;gap:16px;padding-bottom:20px;border-bottom:1px solid var(--edge)}
.report .score{font-family:var(--display);font-weight:800;font-size:56px;line-height:1;color:var(--teal);letter-spacing:-.03em}
.report .of{font-family:var(--mono);font-size:15px;color:var(--faint)}
.report .band{font-size:15px;color:var(--muted);margin-left:auto}
.dim{padding:16px 0;border-bottom:1px solid var(--edge)}
.dim .top{display:flex;align-items:baseline;gap:12px}
.dim .name{font-family:var(--display);font-weight:700;font-size:17px;color:#fff}
.dim .sc{font-family:var(--mono);font-size:14px;color:var(--teal);margin-left:auto;font-variant-numeric:tabular-nums}
.dim .q{margin-top:7px;font-size:15.5px;color:var(--muted);font-style:italic}
.dim .q .ts{font-family:var(--mono);font-style:normal;color:var(--faint);margin-right:9px;font-size:12.5px}

/* ---- bias ------------------------------------------------------------- */
.pairs{display:flex;gap:34px;align-items:flex-end}
.pair{text-align:left}
.pair .v{font-family:var(--display);font-weight:800;font-size:60px;line-height:1;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.pair .c{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin-top:10px;letter-spacing:.04em}
.v.good{color:var(--teal)} .v.bad{color:var(--warn)} .v.flat{color:var(--muted)}
.arrow{font-size:30px;color:var(--faint);padding-bottom:26px}

/* ---- on device -------------------------------------------------------- */
.boundary{display:flex;gap:20px;align-items:stretch}
.chip{
  font-family:var(--mono);font-size:13px;color:var(--paper);
  background:#0F2A26;border:1px solid var(--edge-lit);border-radius:8px;padding:9px 14px;
}
.gone{display:flex;gap:12px;flex-wrap:wrap}
.gone span{
  font-family:var(--mono);font-size:13px;color:var(--faint);
  text-decoration:line-through;text-decoration-color:#3A4B47;
}

/* ---- chart ------------------------------------------------------------ */
.chartwrap{display:flex;gap:34px;align-items:stretch}
.legend{display:flex;gap:20px;font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:6px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:7px;vertical-align:-1px}
.fact .k{font-family:var(--display);font-weight:800;font-size:29px;color:var(--teal);letter-spacing:-.02em}
.fact .v{font-size:13.5px;color:var(--muted);margin-top:7px;line-height:1.45}

/* ---- title & close ---------------------------------------------------- */
.wordmark{font-family:var(--display);font-weight:800;font-size:64px;color:var(--teal);letter-spacing:-.04em;line-height:1}
.title-slide{justify-content:center}
.title-slide .sub{font-size:18px;color:var(--muted);margin:0}
.title-slide .team{font-family:var(--mono);font-size:13px;color:var(--faint);position:absolute;left:72px;bottom:56px}
#wave{position:absolute;right:0;bottom:0;width:560px;height:280px;opacity:.5;pointer-events:none}

/* ---- chrome ----------------------------------------------------------- */
#rail{position:absolute;left:0;right:0;bottom:0;height:3px;background:#12201E}
#railfill{height:100%;background:var(--teal);width:0;transition:width .3s ease}
#counter{
  position:absolute;right:26px;bottom:18px;
  font-family:var(--mono);font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums;
}
#notes{
  position:fixed;left:0;right:0;bottom:0;max-height:42vh;overflow:auto;
  background:#0A1211;border-top:1px solid var(--edge);
  padding:18px 24px;font-size:14.5px;line-height:1.6;color:var(--muted);
  display:none;
}
#notes.on{display:block}
#notes b{color:var(--teal);font-family:var(--mono);font-size:12px;letter-spacing:.1em;
  text-transform:uppercase;display:block;margin-bottom:8px}
#help{
  position:fixed;left:16px;bottom:14px;font-family:var(--mono);font-size:11.5px;
  color:#3C4A47;
}
#help kbd{color:var(--faint);background:none;border:none;font:inherit}
button.nav{
  position:fixed;top:50%;transform:translateY(-50%);
  width:44px;height:64px;border:none;border-radius:8px;
  background:transparent;color:#33423F;font-size:26px;cursor:pointer;
}
button.nav:hover{color:var(--teal)}
button.nav:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
#prev{left:8px} #next{right:8px}

@media print{
  body{overflow:visible;background:#fff}
  #viewport{position:static;display:block;padding:0}
  #stage{transform:none!important;width:1280px;height:720px;box-shadow:none;border-radius:0}
  .slide{display:flex!important;page-break-after:always;position:relative;width:1280px;height:720px}
  button.nav,#help,#notes,#counter{display:none}
}
"""


# --------------------------------------------------------------------------
# Rendering. One function per slide kind; each returns the slide's inner HTML.
# --------------------------------------------------------------------------

def e(s):
    return html.escape(str(s))


def head(s, cls=""):
    """Eyebrow plus headline, the opening of most slides."""
    out = ""
    if s.get("eyebrow"):
        out += '<p class="eyebrow">%s</p>' % e(s["eyebrow"])
    out += '<h1 class="%s">%s</h1>' % (cls, e(s["headline"]).replace("\n", "<br>"))
    return out


def r_title(s):
    return (
        '<div class="wordmark">%s</div>'
        '<h1 class="big" style="margin-top:26px">%s</h1>'
        '<p class="sub" style="margin-top:30px">%s</p>'
        '<div class="team">%s</div>'
        '<canvas id="wave" width="1120" height="560" aria-hidden="true"></canvas>'
        % (e(s["wordmark"]), e(s["headline"]).replace("\n", "<br>"),
           e(s["sub"]), e(s["team"]))
    )


def r_stats(s):
    cards = "".join(
        '<div class="panel stat"><div class="n">%s</div><div class="l">%s</div></div>'
        % (e(n), e(l)) for n, l in s["stats"]
    )
    return (head(s) + '<div class="spacer"></div>'
            + '<div class="grid g3">%s</div>' % cards
            + '<div class="spacer"></div>'
            + '<p class="kicker plain">%s</p>' % e(s["kicker"]))


def r_rows(s):
    rows = "".join(
        '<div class="row"><div class="t">%s</div><div class="d">%s</div></div>'
        % (e(t), e(d)) for t, d in s["rows"]
    )
    return head(s) + '<div class="spacer"></div><div class="rowlist">%s</div>' % rows + '<div class="spacer"></div>'


def r_statement(s):
    return (head(s, "big") + '<div class="spacer"></div>'
            + '<p class="kicker">%s</p>' % e(s["kicker"]))


def r_steps(s):
    cards = ""
    for i, (t, d) in enumerate(s["steps"], 1):
        cards += ('<div class="panel step"><div class="k">Step %d</div>'
                  '<div class="t">%s</div><div class="d">%s</div></div>' % (i, e(t), e(d)))
    return (head(s) + '<div class="spacer"></div>'
            + '<div class="grid g3">%s</div>' % cards
            + '<div class="spacer"></div>'
            + '<p class="foot">%s</p>' % e(s["kicker"]))


def r_transcript(s):
    turns = ""
    for who, ts, text in s["turns"]:
        turns += ('<div class="turn %s"><div class="ts">%s</div>'
                  '<div class="bubble">%s</div></div>' % (who, e(ts), e(text)))
    return (head(s) + '<div class="spacer" style="min-height:10px"></div>'
            + '<div class="turns">%s</div>' % turns
            + '<div class="spacer" style="min-height:10px"></div>'
            + '<p class="kicker">%s</p>' % e(s["kicker"]))


def r_report(s):
    dims = ""
    for name, sc, ts, quote in s["lines"]:
        dims += ('<div class="dim"><div class="top"><span class="name">%s</span>'
                 '<span class="sc">%s</span></div>'
                 '<div class="q"><span class="ts">%s</span>“%s”</div></div>'
                 % (e(name), e(sc), e(ts), e(quote)))
    card = ('<div class="report"><div class="head">'
            '<span class="score">%s</span><span class="of">/ 10</span>'
            '<span class="band">%s</span></div>%s'
            '<p class="foot" style="margin-top:18px">%s</p></div>'
            % (e(s["score"]), e(s["band"]), dims, e(s["foot"])))
    return (head(s)
            + '<p class="lede" style="margin-top:16px">%s</p>' % e(s["lede"])
            + '<div class="spacer" style="min-height:14px"></div>' + card)


def r_compare(s):
    def side(t, cls):
        name, line1, line2 = t
        return ('<div class="panel %s"><div class="step"><div class="t" style="margin-top:0">%s</div>'
                '<div class="d" style="font-size:17px;color:%s">%s<br>%s</div></div></div>'
                % (cls, e(name), "var(--paper)" if cls == "lit" else "var(--faint)",
                   e(line1), e(line2)))
    return (head(s) + '<div class="spacer"></div>'
            + '<div class="grid g2">%s%s</div>' % (side(s["left"], ""), side(s["right"], "lit"))
            + '<div class="spacer"></div>'
            + '<p class="kicker plain">%s</p>' % e(s["kicker"]))


def r_bias(s):
    def block(t, lit):
        label, a, b, note = t
        av = "good" if lit else "flat"
        bv = "good" if lit else "bad"
        return ('<div class="panel %s"><div class="step"><div class="k">%s</div>'
                '<div class="pairs" style="margin-top:18px">'
                '<div class="pair"><div class="v %s">%s<span style="font-size:24px;color:var(--faint)">/10</span></div>'
                '<div class="c">plain answer</div></div>'
                '<div class="arrow">→</div>'
                '<div class="pair"><div class="v %s">%s<span style="font-size:24px;color:var(--faint)">/10</span></div>'
                '<div class="c">with “um” left in</div></div>'
                '</div><div class="d" style="margin-top:20px">%s</div></div></div>'
                % ("lit" if lit else "", e(label), av, e(a), bv, e(b), e(note)))
    return (head(s)
            + '<p class="lede" style="margin-top:14px">%s</p>' % e(s["lede"])
            + '<div class="spacer" style="min-height:14px"></div>'
            + '<div class="grid g2">%s%s</div>' % (block(s["before"], False), block(s["after"], True))
            + '<div class="spacer"></div>'
            + '<p class="kicker plain">%s</p>' % e(s["kicker"]))


def r_ondevice(s):
    chips = "".join('<div class="chip">%s</div>' % e(x) for x in s["here"])
    gone = "".join("<span>%s</span>" % e(x) for x in s["absent"])
    return (head(s) + '<div class="spacer"></div>'
            + '<div class="boundary">'
            + '<div class="panel" style="flex:0 0 300px"><div class="step">'
              '<div class="k">Their side</div><div class="t">A browser</div>'
              '<div class="d">A link and a microphone. Nothing to install.</div></div></div>'
            + '<div style="display:grid;place-items:center;color:var(--teal);font-size:26px">→</div>'
            + '<div class="panel lit" style="flex:1"><div class="step">'
              '<div class="k">Your side</div><div class="t">One machine, in your building</div>'
              '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">%s</div>'
              '</div></div></div>' % chips
            + '<div class="spacer"></div>'
            + '<div class="gone">%s<span style="text-decoration:none;color:var(--muted)">'
              '— none of these are in the diagram.</span></div>' % gone
            + '<div class="spacer" style="min-height:14px"></div>'
            + '<p class="kicker">%s</p>' % e(s["kicker"]))


def r_cost(s):
    """A grouped bar chart, drawn to one scale, with room in the viewBox for labels."""
    import math
    vols, per, box = s["volumes"], s["per_interview"], s["box"]
    series = [(v, v * per, box) for v in vols]
    peak = max(max(a, b) for _, a, b in series)

    # Round money, not whatever the data divided into. An axis reading $8,333
    # tells the room the chart was drawn by a machine that did not care.
    raw = peak / 5.0
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
    top = math.ceil(peak / step) * step
    ticks = int(round(top / step))

    W, H = 620, 330
    pad_l, pad_b, pad_t = 62, 42, 14
    plot_w, plot_h = W - pad_l - 12, H - pad_b - pad_t
    group = plot_w / len(series)
    bw = group * 0.30

    parts = []
    for i in range(ticks + 1):                           # gridlines + value axis
        val = step * i
        y = pad_t + plot_h - plot_h * (val / top)
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#1E2F2C" stroke-width="1"/>'
                     % (pad_l, y, W - 12, y))
        parts.append('<text x="%.1f" y="%.1f" fill="#54635F" font-size="11" font-family="IBM Plex Mono, monospace" '
                     'text-anchor="end">$%s</text>' % (pad_l - 10, y + 4, format(int(val), ",")))

    for i, (v, hosted, ours) in enumerate(series):
        cx = pad_l + group * i + group / 2
        for j, (val, fill) in enumerate(((hosted, "#33443F"), (ours, "#2DD4BF"))):
            h = plot_h * (val / top)
            x = cx - bw + j * bw
            parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"/>'
                         % (x, pad_t + plot_h - h, bw - 3, max(h, 2), fill))
        parts.append('<text x="%.1f" y="%.1f" fill="#7F918D" font-size="12" '
                     'font-family="IBM Plex Mono, monospace" text-anchor="middle">%s</text>'
                     % (cx, H - 22, format(v, ",")))
    parts.append('<text x="%.1f" y="%.1f" fill="#54635F" font-size="11" '
                 'font-family="IBM Plex Mono, monospace" text-anchor="middle">interviews</text>'
                 % (pad_l + plot_w / 2, H - 5))

    svg = ('<svg viewBox="0 0 %d %d" width="100%%" role="img" '
           'aria-label="Cost of paying per interview against one machine, by volume">%s</svg>'
           % (W, H, "".join(parts)))

    facts = "".join('<div class="panel fact"><div class="k">%s</div><div class="v">%s</div></div>'
                    % (e(k), e(v)) for k, v in s["facts"])
    legend = ('<div class="legend">'
              '<span><i style="background:#33443F"></i>Paying per interview</span>'
              '<span><i style="background:#2DD4BF"></i>zeg, one machine</span></div>')
    return (head(s) + '<div class="spacer" style="min-height:12px"></div>'
            + '<div class="chartwrap"><div style="flex:1">%s%s</div>'
              '<div class="grid" style="flex:0 0 320px;align-content:start">%s</div></div>' % (svg, legend, facts)
            + '<div class="spacer" style="min-height:10px"></div>'
            + '<p class="foot">%s</p>' % e(s["foot"]))


def r_demo(s):
    cards = "".join(
        '<div class="panel step"><div class="t" style="margin-top:0">%s</div>'
        '<div class="d">%s</div></div>' % (e(t), e(d)) for t, d in s["watch"]
    )
    return ('<p class="eyebrow">%s</p><h1 class="huge">%s</h1>' % (e(s["eyebrow"]), e(s["headline"]))
            + '<p class="kicker" style="margin-top:22px">Watch for three things.</p>'
            + '<div class="spacer"></div>'
            + '<div class="grid g3">%s</div>' % cards)


def r_limits(s):
    cards = "".join(
        '<div class="panel step"><div class="t" style="margin-top:0">%s</div>'
        '<div class="d">%s</div></div>' % (e(t), e(d)) for t, d in s["items"]
    )
    return (head(s) + '<div class="spacer"></div>'
            + '<div class="grid g3">%s</div>' % cards
            + '<div class="spacer"></div>'
            + '<p class="kicker">%s</p>' % e(s["kicker"]))


def r_close(s):
    return ('<div class="spacer"></div>'
            + '<h1 class="huge">%s</h1>' % e(s["headline"]).replace("\n", "<br>")
            + '<div class="wordmark" style="font-size:44px;margin-top:44px">%s</div>' % e(s["wordmark"])
            + '<p class="sub" style="color:var(--muted);font-size:17px;margin-top:16px">%s</p>' % e(s["sub"])
            + '<div class="spacer"></div>')


RENDERERS = {
    "title": r_title, "stats": r_stats, "rows": r_rows, "statement": r_statement,
    "steps": r_steps, "transcript": r_transcript, "report": r_report,
    "compare": r_compare, "bias": r_bias, "ondevice": r_ondevice, "cost": r_cost,
    "demo": r_demo, "limits": r_limits, "close": r_close,
}


JS = r"""
const slides=[...document.querySelectorAll('.slide')];
const notesData=window.__NOTES__||[];
const stage=document.getElementById('stage');
const rail=document.getElementById('railfill');
const counter=document.getElementById('counter');
const notes=document.getElementById('notes');
let i=0;

function fit(){
  const pad=32;
  const k=Math.min((innerWidth-pad)/1280,(innerHeight-pad)/720);
  stage.style.transform='scale('+k+')';
}
addEventListener('resize',fit); fit();

function show(n){
  i=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((s,j)=>s.classList.toggle('on',j===i));
  rail.style.width=((i+1)/slides.length*100)+'%';
  counter.textContent=String(i+1).padStart(2,'0')+' / '+String(slides.length).padStart(2,'0');
  notes.innerHTML='<b>Speaker notes · slide '+(i+1)+'</b>'+(notesData[i]||'');
  try{location.hash=String(i+1)}catch(_){}
}
addEventListener('keydown',ev=>{
  const k=ev.key;
  if(k==='ArrowRight'||k==='ArrowDown'||k===' '||k==='PageDown'){ev.preventDefault();show(i+1)}
  else if(k==='ArrowLeft'||k==='ArrowUp'||k==='PageUp'){ev.preventDefault();show(i-1)}
  else if(k==='Home'){show(0)} else if(k==='End'){show(slides.length-1)}
  else if(k==='n'||k==='N'){notes.classList.toggle('on')}
  else if(k==='f'||k==='F'){
    if(document.fullscreenElement){document.exitFullscreen()}
    else{document.documentElement.requestFullscreen?.()}
  }
});
document.getElementById('prev').onclick=()=>show(i-1);
document.getElementById('next').onclick=()=>show(i+1);

/* The title slide's waveform: the subject of the product, drawn rather than
   decorated. Idles quietly and stops entirely under reduced-motion. */
(function(){
  const c=document.getElementById('wave'); if(!c) return;
  const x=c.getContext('2d'); const N=58; let t=0;
  const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
  function draw(){
    x.clearRect(0,0,c.width,c.height);
    const bw=c.width/N;
    for(let k=0;k<N;k++){
      const p=k/N;
      const a=Math.sin(t+k*0.34)*Math.sin(t*0.6+k*0.11)*0.5+0.5;
      const h=(18+a*a*230)*(0.35+p*0.65);
      const g=x.createLinearGradient(0,c.height-h,0,c.height);
      g.addColorStop(0,'rgba(45,212,191,'+(0.12+p*0.55)+')');
      g.addColorStop(1,'rgba(45,212,191,0.02)');
      x.fillStyle=g;
      x.fillRect(k*bw+bw*0.28,c.height-h,bw*0.44,h);
    }
    if(!still){t+=0.022; requestAnimationFrame(draw)}
  }
  draw();
})();

addEventListener('hashchange',()=>{
  const n=parseInt((location.hash||'').slice(1),10);
  if(Number.isFinite(n)&&n>0&&n-1!==i) show(n-1);
});
const start=parseInt((location.hash||'').slice(1),10);
show(Number.isFinite(start)&&start>0?start-1:0);
"""


def build():
    body, notes = [], []
    for s in SLIDES:
        kind = s["kind"]
        cls = "slide title-slide" if kind in ("title", "close") else "slide"
        body.append('<section class="%s" aria-label="Slide %d">%s</section>'
                    % (cls, len(body) + 1, RENDERERS[kind](s)))
        notes.append(s.get("notes", ""))

    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700;12..96,800&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{css}</style>
</head><body>
<div id="viewport"><div id="stage">
{body}
<div id="rail"><div id="railfill"></div></div>
<div id="counter"></div>
</div></div>
<button class="nav" id="prev" aria-label="Previous slide">&#8249;</button>
<button class="nav" id="next" aria-label="Next slide">&#8250;</button>
<div id="notes" aria-live="polite"></div>
<div id="help"><kbd>&#8592; &#8594;</kbd> move &nbsp;<kbd>N</kbd> notes &nbsp;<kbd>F</kbd> fullscreen</div>
<script>window.__NOTES__={notes};</script>
<script>{js}</script>
</body></html>""".format(
        title=e(TITLE), css=CSS, body="\n".join(body),
        notes=json.dumps(notes), js=JS)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "deck.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(build())
    print("wrote %s  (%d slides)" % (out, len(SLIDES)))
