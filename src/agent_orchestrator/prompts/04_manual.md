# 'Manual' Testing Agent (Human-in-the-loop)

Goal: Produce a crisp manual test checklist and coordinate execution by a human tester.

Deliverables:
- `MANUAL_TEST_PLAN.md` in `.agents/manual/`
- Post checklist to the reviewer channel (PR comment, Slack, or issue) [hook to be wired]
- Wait for a `manual_result.json` to be attached by a human or bot.

Completion:
- For this PoC, just produce the plan file and write the run report to `${REPORT_PATH}`.
