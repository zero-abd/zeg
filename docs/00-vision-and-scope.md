# Vision and scope

## The job to be done

A recruiting team receives more applications than its engineers can phone-screen. The
first technical screen is 15 to 30 minutes, follows the same shape every time, and is
mostly a filter: can this person talk credibly about the things their resume claims.
Engineers hate doing it and do it inconsistently. zeg does that first pass.

## What it is

A voice agent that dials or answers a phone call, spends up to 15 minutes probing a
candidate's technical depth against a role-specific rubric, and hands the recruiter a
scored report with quotes. Every model runs on one Dell machine in the customer's own
rack or office.

## What it is explicitly not

- **Not a hiring decision.** It produces evidence and a recommendation band. A human
  advances or rejects. This is a product constraint and a legal one, see the compliance doc.
- **Not a live coding test.** Fifteen minutes of voice is the wrong medium for writing
  code. It probes reasoning about code, not production of it. A coding exercise is a
  separate later stage.
- **Not an accent, fluency, or personality assessor.** Any signal that correlates with
  protected characteristics is a defect, not a feature.
- **Not a video interview.** Audio only. This deliberately dodges a large body of
  facial-analysis regulation and the bias that comes with it.
- **Not multi-tenant SaaS in v1.** One appliance, one customer, one org's data.

## Users

| Role | Needs |
| --- | --- |
| Candidate | A fair, short, clearly-disclosed conversation that does not feel like a maze |
| Recruiter | A report they can skim in 90 seconds and defend to a hiring manager |
| Hiring manager | Confidence the rubric matches the role, ability to tune it |
| IT / security | An appliance they can firewall, patch, and audit |

## Success criteria for v1

| Metric | Target |
| --- | --- |
| Mouth-to-ear latency, p95 | Under 800 ms |
| Calls completed without human rescue | Over 95 percent |
| Agreement with a human screener's advance/reject call | Cohen's kappa over 0.6 |
| Candidate-reported fairness, post-call survey | Over 4.0 of 5 |
| Concurrent calls on one box | 4 or more |
| Cost per screen at 500 screens per month | Under 1 USD amortized |

The kappa target is the one that decides whether this is a product. Latency is an
engineering problem with known solutions. Agreement with a good human screener is not.
