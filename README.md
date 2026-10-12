# Issue-to-PR: a multi-agent engineering crew

An AI crew that takes a GitHub issue, plans the change, writes the code, runs the
tests, reviews the diff, and opens a pull request. Built from scratch to learn
agent orchestration, evaluation, and cloud deployment.

> **Status: work in progress.** Phase 1 is complete. See the roadmap below.

## Why this project

Most agent demos never measure anything. This one is built around an evaluation
harness: every change to the crew is judged by resolve rate, cost per task, and
number of steps, and the multi-agent design is compared against a single agent.

## Planned architecture

```
GitHub issue --> Planner --> Coder --> Tester --> Reviewer --> Pull request
                               ^          |           |
                               +----------+-----------+   (failures loop back)
                          Supervisor: routing, retry + budget limits, human approval
```

Target AWS (free-tier) deployment: API Gateway/Lambda (webhook) -> SQS ->
Lambda/EC2 (agents) -> DynamoDB + S3 (run history, logs, diffs), with
Step Functions and CloudWatch for orchestration and observability.

## Roadmap

- [x] **Phase 1:** single agent with a hand-written tool-calling loop
- [ ] **Phase 2:** split into Planner / Coder / Tester with LangGraph
- [ ] **Phase 3:** Reviewer + Supervisor, retry and budget limits
- [ ] **Phase 4:** Docker sandbox for running tests safely
- [ ] **Phase 5:** evaluation harness (15-20 tasks, single vs multi-agent)
- [ ] **Phase 6:** GitHub integration (read issues, open PRs)
- [ ] **Phase 7:** AWS serverless deployment and observability
- [ ] **Phase 8:** write-up and demo

## Results so far

| Task                           | Agent                  | Steps | Tokens | Result         |
| ------------------------------ | ---------------------- | ----- | ------ | -------------- |
| Add pagination to `GET /users` | Single agent (Phase 1) | 6     | 3,592  | 3/3 tests pass |

## Quickstart (Phase 1)

```bash
git clone https://github.com/<Gourish-Pednekar>/issue-crew
git clone https://github.com/<Gourish-Pednekar>/sample-target-app
cd issue-crew
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then fill in your Groq key and the WORKSPACE path
python phase1_agent.py "Add pagination to GET /users using page (default 1) and limit (default 10) query params. Make all tests pass."
```

The agent works inside the `sample-target-app` repo, which ships with failing
tests that describe the feature to build.

## Safety note

The agent writes code and runs `pytest` on your machine. It is **not sandboxed
yet** (Docker isolation is planned for Phase 4), so only point it at repos you
trust.

## License

MIT
