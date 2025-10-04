# Story Breakdown Agent

Goal: Analyze a large task and decompose it into 3-10 discrete, actionable stories that can be implemented independently or sequentially.

Input:
- Task description from GitHub issue, TODO.md, or other source
- Context about the codebase and existing architecture

Deliverables:
1. `stories.json` in `${ARTIFACTS_DIR}/` containing an array of story objects with the following structure:
```json
{
  "items": [
    {
      "id": "STORY-001",
      "title": "Brief story title",
      "description": "Detailed description of what needs to be implemented",
      "complexity": "small|medium|large",
      "dependencies": ["STORY-XXX"],
      "acceptance_criteria": [
        "Criterion 1",
        "Criterion 2"
      ]
    }
  ]
}
```

Guidelines:
- Break down the task into 3-10 stories
- Each story should be independently testable
- Stories should be sized to take 1-3 hours of focused development
- Include clear acceptance criteria for each story
- Identify dependencies between stories
- Order stories logically (foundational work first)
- Ensure stories cover the full scope of the original task

Completion:
- Write a run report JSON to `${REPORT_PATH}` with:
  - artifacts: ["stories.json"]
  - logs: Summary of story breakdown including count and complexity distribution
