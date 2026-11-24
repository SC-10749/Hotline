# apply — Job Application Question Drafting

### Inputs

- Required: Company name + list of application questions
- Optional: Word or character limits per question
- Optional: JD (used for "why us" tailoring and domain matching)
- Optional: Resume text (used as fallback for tools/experience questions not covered by storybank)

---

### Sequence

**Step 1: Parse and classify questions**

For each question, assign one type:
- **Behavioral**: "Tell me about a time...", "Describe a situation where..."
- **Process/method**: "How do you [prioritize / use data / manage stakeholders]..."
- **Tools/experience**: "Do you have experience with [tool/domain]..."
- **Why us**: "Why this company / role / industry..."
- **Other**: Hypotheticals, case-style, or open-ended

State the classification before drafting each answer.

---

**Step 2: Check for prior answers**

Before drafting, scan `job-search/` for existing application files from previous companies. For each question, check whether a semantically similar question was answered before. If yes:
- Surface the prior answer
- Ask: "I answered a similar question for [Company] — want me to adapt that, or draft fresh for [New Company]?"

This builds a reusable answer library across applications over time.

---

**Step 3: Gap check before drafting**

For each question, verify that the storybank (in `coaching_state.md`) or the provided resume contains evidence to support an answer.

**If evidence is found**: proceed to Step 4.

**If evidence is not found** (e.g., a tool never used, a domain never worked in, an experience not in the storybank or resume):
- Do not invent or imply the experience.
- Flag it explicitly: "I don't see evidence in your storybank or resume for [X]. Can you tell me about a time you [Y]? Or should we note this gap and move on?"
- Don't refuse to proceed — draft what's supportable and mark the flagged question clearly.

---

**Step 4: Story selection (behavioral and process/method questions only)**

For each behavioral or process/method question, do not auto-select a story. Instead:

1. Identify 2-3 candidate stories from the storybank that could answer the question. Use the Quick Reference table in the storybank as the starting point.

2. **Check for domain relevance.** If the JD or company has a clear industry or domain (e.g., background verification, fintech, identity, edtech, marketplace), flag any story from a matching domain with a `[Domain match]` marker. Domain-relevant stories create an implicit signal of industry familiarity — a story from a cognate domain told to a company in that domain lands differently than the same structural story from an unrelated domain. Weight domain match as a tiebreaker when two stories are otherwise equal.

3. Present the options to the candidate with a one-line rationale for each, and the domain match flag where applicable:

```
For Q1 ("describe a time market insights influenced your strategy"):
a) [Story title] — [one-line rationale]
b) [Story title] — [one-line rationale] [Domain match — background verification / identity]
c) [Story title] — [one-line rationale]

Note: [Company] is in [domain] — story (b) signals direct domain familiarity. Worth considering.

Which story do you want to use? Or should I draft using [b] and you can swap later?
```

Wait for the candidate's choice before drafting. If they say "you choose" or don't respond with a preference, default to the domain-matched story if one exists, otherwise the Quick Reference recommendation. Note which story was used.

This step applies to behavioral and process/method questions only. For tools/experience and "why us" questions, proceed directly to Step 5.

---

**Step 5: Draft answers**

Map each question type to its source:
- **Behavioral**: Use the chosen story from Step 4. Write in the written register — tighter than spoken, no filler phrases. Pull the core STAR spine from the story but compress. Application fields are read, not heard.
- **Process/method**: Use the chosen story from Step 4 as the anchor example. State the principle first, then ground it in the story with a metric.
- **Tools/experience**: Storybank first; resume as fallback. Name the tools directly, state scope of use. If a specific tool is not evidenced in either source, say so honestly rather than implying familiarity.
- **Why us**: Requires company context. If `research` or `prep` has been run for this company, pull from `coaching_state.md`. If not, ask the candidate for 1-2 genuine reasons before drafting — do not generate a generic answer.

**Default length**: 150-200 words per answer unless a limit is specified.

**Tone**: Written, not spoken. No filler transitions ("I think", "So basically", "At the end of the day"). Structured but not robotic. First-person, active voice.

---

**Step 6: Output**

Present all answers as a ready-to-paste block, labeled by question number and type:

```
## Q1 [Behavioral] — Story used: [Story title]
[Answer]

## Q2 [Process/Method] — Story used: [Story title]
[Answer]

## Q3 [Tools/Experience]
[Answer]
```

Flag any questions where evidence was missing and the candidate needs to provide context.

---

**Step 7: Save**

Save to `job-search/[company]_application.md` with:
- Company name and role at the top
- Date drafted
- Each question and its answer (including story label for behavioral/process answers)
- Any flagged gaps

Add to Session Log in `coaching_state.md`.

---

### Output Schema

```markdown
# [Company] Application — [Role]
Date: [date]

## Q1 — [Question] [Type: Behavioral / Process / Tools / Why Us]
Story used: [Story title] (for Behavioral/Process only)
[Answer — 150-200 words unless limit specified]

## Q2 — [Question] [Type]
[Answer]

## Flagged Gaps
- Q[N]: [What's missing — what the candidate needs to provide before this answer can be drafted]
```

---

### Notes

- Never fabricate an experience. If the storybank and resume don't support an answer, flag it and ask.
- For "why us" questions: don't generate a generic answer. Either pull from `prep`/`research` output in `coaching_state.md`, or ask the candidate directly before drafting.
- Written answers read differently than spoken answers. Avoid narrative warmup ("So, this was a project where..."). Start at the situation or the insight.
- Proprietary tools (Aha, Productboard, Salesforce, niche platforms) may not be in the storybank. Check the provided resume explicitly before claiming familiarity.
- The domain match flag is a tiebreaker, not a mandate. A structurally weaker story from a matching domain is not better than a structurally stronger story from a different domain. Use judgement.

**Next commands**: `prep [company]` if not yet run, `concerns` if moving to interview stage, `practice` to prepare for follow-up questions on your written answers
