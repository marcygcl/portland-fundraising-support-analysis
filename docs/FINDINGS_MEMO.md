# Findings Memo — Campaign Finance and Electoral Performance, Portland 2024

**Status:** Working draft. Living document — append, do not overwrite.
**Scope so far:** Workplan Question 3, all four districts, 2024 City Council.
**Last updated:** first pass, notebooks 10–13.

## How to use this memo

This is the drafting surface between the notebooks and the report. Each finding
records **the number, what it means, and how confident we are** — separated, so
that a reader can disagree with the interpretation without doubting the number.

Confidence labels used throughout:

| Label | Meaning |
|---|---|
| **Solid** | strong effect, large sample, robust across specifications |
| **Probable** | consistent pattern, but sample or method leaves room |
| **Tentative** | suggestive only; do not lead with this |
| **Artifact** | looks like a finding, is not — kept so nobody re-discovers it |

Everything here is **association, not causation.** Money may attract support,
support may attract money, or both may follow from prior public standing.

---

## 1. The data we are describing

| Quantity | Value |
|---|---|
| Candidates on the 2024 ballot (all districts) | 98 |
| Candidates with both finance and ballot data | 65 |
| Missing fundraising records | 33 |
| Missing spending records | 33 |
| Candidates with multiple spending filings | 0 |

**Note on the 33 missing.** These are candidates with ballot results but no
finance filing in our sources. They are excluded from every model below, which
means **all findings describe the 65 candidates who filed, not the whole field.**
The excluded 33 are systematically the smallest campaigns, so our estimates
describe the funded end of the field. This should be stated plainly in the report.

**Note on multiple filings.** We built handling for candidates who filed spending
through several committees. In the 2024 city council data, no candidate did —
so that code is a safeguard for other years, not something that changed these
numbers.

---

## 2. Finding: money and electoral support are strongly associated

**Confidence: Solid.**

| Money measure | Outcome | Pearson | Spearman |
|---|---|---|---|
| Fundraising | Ballot mentions | 0.779 | 0.800 |
| Fundraising | First-place votes | 0.752 | 0.764 |
| Spending | Ballot mentions | 0.448 | 0.800 |
| Spending | First-place votes | 0.507 | 0.803 |

All four are positive and substantial. Answering the workplan question directly:
**yes, we see clear relationships.**

**The interesting detail is in the spending rows.** Pearson (0.45–0.51) sits far
below Spearman (0.80). Rank order is captured well; a straight line in raw
dollars is not. For fundraising the two measures nearly agree, meaning that
relationship is much closer to linear.

That gap is the whole reason the next finding exists.

---

## 3. Finding: fundraising is closer to linear; spending has diminishing returns

**Confidence: Probable.** This is our most analytically interesting result and the
one that most needs a second look.

R² for each specification (n = 65 throughout):

| Outcome | Predictor | R² |
|---|---|---|
| Ballot mentions | Fundraising — **raw dollars** | **0.607** |
| Ballot mentions | Fundraising — log dollars | 0.483 |
| Ballot mentions | Spending — **log dollars** | **0.484** |
| Ballot mentions | Spending — raw dollars | 0.200 |
| First-place votes | Fundraising — **raw dollars** | **0.565** |
| First-place votes | Spending — log dollars | 0.364 |
| First-place votes | Fundraising — log dollars | 0.336 |
| First-place votes | Spending — raw dollars | 0.257 |

**The asymmetry is consistent across both outcomes:** raw dollars win for
fundraising, log dollars win for spending. That repetition is what makes this
more than noise.

### Interpretation

The standard expectation is diminishing returns everywhere. We see it for
**spending** — the first money out the door (signs, a first mailer) buys much
more visibility than the same amount added to an already large budget — but not
for **fundraising**.

The most plausible explanation is that fundraising is not purely a money
variable. Raising more dollars almost always means **more separate donors**, and
each donor is a person who has already decided to support you and may talk to
others. So a fundraising total is partly a measure of how many people are behind
a campaign, and that appears to scale more evenly than spending does. Finding 4
supports this reading directly.

### Why this is Probable and not Solid

- R² comparisons between specifications are informal; we have not tested whether
  the difference is statistically meaningful.
- Raw-dollar fits are more exposed to the largest campaigns. A handful of big
  fundraisers could be doing the work.
- **Action:** re-run finding 3 excluding the top three fundraisers per district
  and see whether the raw-over-log advantage survives.

---

## 4. Finding: the single best predictor is the number of donations, not the dollars

**Confidence: Solid.**

Of 26 fine-grained finance features tested, the strongest is
`total_contribution_count` — how many separate contributions a campaign
received.

| Feature | Outcome | Pearson | Spearman | R² |
|---|---|---|---|---|
| total_contribution_count | Ballot mentions | 0.725 | 0.755 | 0.525 |
| total_contribution_count | First-place votes | 0.679 | 0.714 | 0.461 |

It is the top feature for **both** outcomes, and Pearson and Spearman agree
closely — so it is not being manufactured by one or two extreme candidates.

### Interpretation, stated carefully

This says **breadth of financial support tracks electoral support at least as
well as depth of it.** In a proportional ranked-choice election, where being
widely acceptable matters more than being intensely preferred by a few, that is
a coherent result rather than a surprise.

**The honest caveat:** donation count is partly a size measure. Campaigns with
more donors generally raised more money, so this partly restates finding 2
rather than adding to it. It does **not** cleanly separate "many small donors"
from "a large campaign."

**Action:** test donation count against fundraising totals directly — for
candidates with similar dollar totals, does the one with more donors do better?
That is the test that would turn this into an independent finding. Notebook 13
sets this up.

**Terminology discipline:** the underlying data counts **contribution records,
not unique donors.** One person giving three times counts three times. Every
sentence in the report must say "contributions," never "donors."

---

## 5. Finding: a non-monotonic pattern in spending size — flagged, not concluded

**Confidence: Tentative.** Interesting enough to record, not solid enough to publish.

Correlations with ballot mentions, by expenditure size band:

| Spending band | Pearson | Spearman | R² |
|---|---|---|---|
| Mega (over $1,000) | **+0.598** | +0.658 | 0.358 |
| Large ($250–$1,000) | **−0.541** | −0.605 | 0.293 |
| Medium ($100–$250) | −0.463 | −0.568 | 0.215 |
| Micro (up to $25) | −0.407 | −0.557 | 0.166 |

The same pattern holds for first-place votes. The sign flips between Mega and
Large — not a monotonic gradient.

### Why we cannot conclude much from this yet

**These shares are compositional: they sum to 1.** A positive coefficient on
Mega share mathematically requires negative coefficients elsewhere. So this may
be a single fact — "campaigns whose spending skews to large transactions did
better" — appearing four times with alternating signs, rather than four findings.

**And the bins measure transaction size, not purpose.** A $40,000 expenditure
lands in Mega whether it was television advertising or a payroll run. So we
cannot currently distinguish "spent on mass communication" from "had employees."

**Action:** obtain the spending *purpose* codes from ORESTAR. Only then can we
say anything useful about what kinds of spending relate to visibility — and only
then does this become relevant to Workplan Question 6 (how candidates might
improve their profiles).

**Do not write** "large expenditures cause visibility." The most we can currently
say is that campaigns operating at a scale where large transactions dominate also
tended to be more visible — which may be scale restated.

---

## 6. Finding: money separates viable from non-viable candidates, but unevenly by district

**Confidence: Solid for the gap; Probable for the district variation.**

| Group | Candidates | Median fundraising | Median spending | Median contributions |
|---|---|---|---|---|
| Viable | 29 | \$49,453 | \$136,928 | 1,055 |
| Not viable | 69 | \$7,281 | \$16,523 | 276 |

A **6.8x gap in median fundraising.** Note the medians are far below the means in
both groups, so each contains at least one much larger campaign.

Correlation between fundraising and viability, by district:

| District | Correlation | n |
|---|---|---|
| 3 | **0.919** | 15 |
| 1 | 0.835 | 13 |
| 2 | 0.669 | 20 |
| 4 | **0.506** | 17 |

Linear probability model R² tells the same story: D1 0.833 and D3 0.700 versus
**D4 0.294**.

### Interpretation

**In District 4, money predicted viability far less well than anywhere else.** D4
is exactly where our most striking qualitative cases sit: Stanley Penkin and
Moses Ross both raised viable-level money and were not viable, while Sarah Silkie
was viable on modest money. Something other than money was doing more work in D4
than in D1 or D3.

**Caveat:** with 11–20 candidates per district these figures are unstable. Treat
the D4-vs-D3 contrast as a real signal worth explaining, but not as a precise
measurement.

### One methodological point the report must state

Our viability measure is defined as ballot mentions crossing the district STV
threshold. So **viability and mentions are built from the same quantity.**
Finance-to-mentions and finance-to-viability are two views of one relationship,
not two independent confirmations. Presenting them as mutually reinforcing
evidence would overstate the case.

---

## 7. Finding: who breaks the pattern — the qualitative core

**Confidence: Solid** on who the outliers are (arithmetic).
**Probable** on the interpretation.

Residuals are computed **within each district**, using log fundraising against
ballot mentions.

### Largest over-performers

| Candidate | District | Raised | Mentions | Predicted | Residual |
|---|---|---|---|---|---|
| Olivia Clark | 4 | \$95,639 | 45,205 | 26,714 | **+18,491** |
| Eric Zimmerman | 4 | \$41,879 | 36,731 | 22,981 | +13,750 |
| Michelle DePass | 2 | \$32,578 | 32,612 | 19,557 | +13,055 |
| Elana Pirtle-Guiney | 2 | \$47,040 | 34,268 | 22,362 | +11,906 |
| Sarah Silkie | 4 | \$25,478 | 32,039 | 20,735 | +11,304 |
| Sameer Kanal | 2 | \$34,712 | 31,168 | 20,042 | +11,126 |
| Steve Novick | 3 | \$87,241 | 51,189 | 40,295 | +10,894 |
| Angelita Morillo | 3 | \$64,641 | 47,477 | 37,092 | +10,385 |

### Largest under-performers

| Candidate | District | Raised | Mentions | Predicted | Residual |
|---|---|---|---|---|---|
| Moses Ross | 4 | \$27,897 | 5,238 | 21,145 | **−15,907** |
| Stanley Penkin | 4 | \$61,847 | 9,570 | 24,744 | −15,174 |
| Harrison Kass | 3 | \$16,058 | 9,223 | 22,217 | −12,994 |
| Mike DiNapoli | 4 | \$7,289 | 3,001 | 15,078 | −12,077 |
| Nabil Zaghloul | 2 | \$26,484 | 6,482 | 17,976 | −11,494 |
| Debbie Kitchin | 2 | \$34,885 | 9,088 | 20,080 | −10,992 |
| Theo Hathaway Saner | 3 | \$7,505 | 3,525 | 14,092 | −10,567 |

### The interpretation, cross-referenced against the bios

Read against `2024_candidate_bios.md`, the two lists split along a line the
numbers alone do not show.

**Over-performers held prior roles with citywide or countywide visibility.**
Clark was legislative director to Governor Kitzhaber and worked on TriMet light
rail funding. Zimmerman was chief of staff to a county commissioner and Central
City adviser to the mayor. Novick was a city commissioner from 2013 to 2017.
DePass chaired the Portland Public Schools board — its first person of colour to
do so. Morillo worked in a commissioner's office and had a substantial
public-facing social media presence explaining local government.

**Under-performers had recognition that was real but bounded.** Penkin was Pearl
District Neighborhood Association president for seven years, sat on multiple arts
boards, and has a "Stan Penkin Day" proclaimed by the City Council. Ross chairs
the Multnomah Neighborhood Association, runs a Democratic political consulting
firm, and has been a national convention delegate four times. Kitchin served on
the Charter Review Commission that designed this very system. Zaghloul spent
nearly 30 years in county government.

**So the refined hypothesis is not "prior recognition helps."** It is that
recognition from a **visible public office** transfers to a broad electorate,
while recognition from **neighbourhood associations, party structures, and
appointed commissions** does not transfer the same way — however genuine and
however hard-earned it is.

This is the most valuable thing we have found, and **it is only visible by
combining the residuals with the profiles.** Neither source shows it alone.

### The counter-examples that keep this honest

Three over-performers had **no** prior office:

- **Sarah Silkie** (+11,304) — city environmental engineer, Oregon Labor
  Candidate School, no prior office, modest money.
- **Sameer Kanal** (+11,126) — city policy role, entered late, assembled a long
  endorsement list including the Mercury's top ranking, no prior office.
- **Mitch Green** — won outright with no prior office, on a labour coalition
  (PAT, UFCW 555, PROTEC17, IBEW Local 48).

Plus **Eli Arnold**, a first-time candidate and police officer with no prior
public role and no labour base, who was the last candidate eliminated in D4
before the winners were finalised.

**What this means:** prior office is one route to recognition-without-money, and
organisational endorsement is another. Neither is necessary. The report must
present this as two substitutable paths, not one rule with exceptions.

---

## 8. Artifact: Matthew Anderson is not an over-performance case

**Confidence: Artifact. Do not cite.**

Anderson (D3) appears in the residual table with +15,589, apparently the second
largest over-performer. He is not one.

He raised roughly **\$710**, far below the range where the D3 regression carries
information, and the model's prediction for him is **−11,083 mentions** — a
negative count, which is impossible. The large residual is the arithmetic
consequence of an impossible prediction, not evidence about his campaign.

**Recorded here so the mistake is made once.** Notebook 13 adds a diagnostic
that flags any candidate whose predicted value falls outside the possible range.

**General lesson for the report:** every large residual needs a check that the
prediction itself is sensible before it becomes a story.

---

## 9. Data quality items to resolve before publication

| Item | Status |
|---|---|
| **Loretta Smith** — ORESTAR spending far exceeds reported fundraising | Unresolved. Verify whether independent or committee spending entered the candidate total. |
| **Chris Henry** — spending exceeds fundraising | Unresolved. Same check. |
| 33 candidates with no finance record | Understood; state the limitation explicitly rather than fixing. |
| ORESTAR fundraising as a second source | Not yet available. When it exists, re-run findings 2 and 3 against it. |
| Public matching funds per candidate, 2024 | **Not held.** This is the most important gap: matching funds change what a private-dollar total means, and Portland's Small Donor Elections programme multiplies small contributions. Finding 4 could partly reflect the matching formula rather than voter behaviour. |
| Spending purpose codes | Not held. Required before finding 5 can be used. |
| Endorsement counts as a structured variable | Not held. Required to test the organisational-base path in finding 7 quantitatively. |

The matching-funds gap deserves emphasis. If the programme matches small
contributions at a multiple, then contribution count and dollar totals are
mechanically linked through policy, and finding 4 may partly describe the
programme's design rather than a political fact.

---

## 10. What we can and cannot say in the report

### Can say

- Money and electoral support were strongly and positively associated across all
  four districts in 2024.
- The association was **stronger for ballot mentions than for first-place
  votes** — campaign scale tracked broad consideration better than exact first
  choice, which is a meaningful observation in a ranked-choice system.
- The number of contributions was the single best individual predictor.
- Money separated viable from non-viable candidates, with a 6.8x median gap, but
  **noticeably less well in District 4** than in Districts 1 and 3.
- Several candidates performed very differently from their money, and their
  prior public roles differ systematically between the two groups.

### Cannot say

- That money **causes** support. The direction is not identified.
- That composition of giving matters independently of scale. Not yet separated.
- That any specific candidate over-performed **because of** incumbency,
  endorsements, or recognition. We have identified the cases; the explanations
  remain hypotheses.
- Anything quantitative about **why** District 4 differs. We have the contrast,
  not the mechanism.
- Anything about the 33 candidates with no finance records.

---

## 11. Next steps, in priority order

1. **Obtain 2024 public matching funds per candidate.** Highest value: it may
   reframe finding 4.
2. **Robustness-check finding 3** by dropping the top three fundraisers per
   district.
3. **Separate breadth from scale** — compare candidates with similar dollar
   totals but different contribution counts (notebook 13).
4. **Fill the District 3 bios gap** — Harrison Kass, Theo Hathaway Saner, and
   Luke Zak are all large under-performers with no profile.
5. **Structure the endorsement variable** so the organisational-base path in
   finding 7 can be tested rather than argued from four examples.
6. **Get spending purpose codes** to make finding 5 usable.
7. Then proceed to Workplan Question 4 (shared support and finance-profile
   similarity), where the five contribution-size dimensions from notebook 11
   become the clustering inputs.

---

## Appendix: revision log

| Date | Change |
|---|---|
| First pass | Created from notebooks 10–12 outputs and the 2024 bios document. Findings 1–8 recorded; Anderson artifact documented; matching-funds gap identified as top priority. |
