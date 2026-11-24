# State Update Triggers

Write to `coaching_state.md` whenever:

- **kickoff** creates a new profile and populates Resume Analysis from resume analysis. Also initializes empty sections: Meta-Check Log, Active Coaching Strategy, Interview Loops, Coaching Notes.
- **research** adds a new company entry (lightweight, in Interview Loops with Status: Researched, plus fit verdict, fit confidence, fit signals, structural gaps, and date)
- **stories** adds, improves, or retires stories (write full STAR text to Story Details, not just index row)
- **analyze**, **practice**, or **mock** produces scores (add to Score History — practice sub-commands that use the 5-dimension rubric add to Score History; retrieval drills log to Session Log only) — analyze also updates Active Coaching Strategy after triage decision. When updating Active Coaching Strategy, always preserve Previous approaches — move the old approach there before writing the new one. Analyze also extracts questions and scores to Interview Intelligence Question Bank, updates Effective/Ineffective Patterns if 3+ data points reveal a pattern, updates Company Patterns, and checks for cross-dimension root causes (updates Calibration State → Cross-Dimension Root Causes if a root cause appears across 2+ answers).
- **concerns** generates ranked concerns (save to Interview Loops under the relevant company's Concerns surfaced, or to Active Coaching Strategy if general)
- **questions** generates tailored questions (save top 3 to Interview Loops under Prepared questions for the relevant company)
- **debrief** captures post-interview data (add to Interview Loops, update storybank Last Used dates and increment Use Count for each story used, add to Outcome Log as pending). Also extracts recalled questions to Interview Intelligence Question Bank (marked "recall-only") and captures recruiter/interviewer feedback to the Recruiter/Interviewer Feedback table.
- **feedback** captures ad-hoc input: recruiter feedback (add to Recruiter/Interviewer Feedback — also check for drift signals when feedback contradicts coach scoring), outcomes (update Outcome Log + Question Bank Outcome column — trigger calibration check when 3-outcome threshold is crossed), corrections (evaluate and adjust if warranted — may update Score History or Storybank ratings, record in Coaching Notes), post-session memories (route to Question Bank, Storybank, Interview Loops, or Company Patterns as appropriate), and meta-feedback (record in Meta-Check Log)
- **progress** reviews trends (update Active Coaching Strategy, check Score History archival, check Interview Intelligence archival thresholds). Also runs calibration check when 3+ outcomes exist (scoring drift detection, cross-dimension root cause review, success pattern analysis) — updates Calibration State.
- **User reports a real interview outcome** (add to Outcome Log)
- **linkedin** produces profile audit (save LinkedIn Analysis section to coaching_state.md — date, depth, overall score, dimension scores, top fixes pending, positioning gaps)
- **resume** produces resume audit (save Resume Optimization section to coaching_state.md — date, depth, overall score, dimension scores, top fixes pending, JD-targeted status, cross-surface gaps)
- **pitch** produces a positioning statement (save Positioning Statement section to coaching_state.md — date, depth, core statement, hook, key differentiator, earned secret anchor, target audience, variant status, consistency status)
- **outreach** produces outreach coaching (save Outreach Strategy section to coaching_state.md — date, depth, positioning source, message types coached, targets contacted, channel strategy, follow-up status, LinkedIn profile flagged, key hooks identified)
- **decode** produces JD analysis (save JD Analysis section per JD to coaching_state.md — date, depth, fit verdict, top competencies, frameable gaps, structural gaps, unverified assumptions, batch triage rank). Multiple JD Analysis sections can exist. Also update Interview Loops: if decode is for a company already in loops, add/update JD decode data; if new company, add lightweight entry with Status: Decoded.
- **present** produces presentation prep (save Presentation Prep section as top-level section in coaching_state.md — include company name in header when company-specific — date, depth, framework, time target, content status, top predicted questions, key adjustment)
- **salary** produces comp strategy (save Comp Strategy section to coaching_state.md — date, depth, target range, range basis, research completeness, stage coached, jurisdiction notes, scripts provided, key principle)
- **apply** drafts written application answers (save to `job-search/[company]_application.md`, add to Session Log)
- **prep** starts a new company loop or updates interviewer intel, round formats, fit verdict, fit confidence, and structural gaps (add to Interview Loops)
- **negotiate** receives an offer (add to Outcome Log with Result: offer)
- **reflect** archives the coaching state (add Status: Archived header)
- **Meta-check conversations** (record candidate's response and any coaching adjustment to Meta-Check Log)
- **Any session where the candidate reveals coaching-relevant personal context** — preferences, emotional patterns, interview anxieties, scheduling preferences, etc. (add to Coaching Notes)
