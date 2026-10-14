# Issue-to-PR: a multi-agent engineering crew

An AI crew that takes a task, plans the change, writes the code, runs the tests,
and has the diff reviewed. The end goal is a crew that reads a GitHub issue and
opens a pull request. Built from scratch to learn agent orchestration,
evaluation, and cloud deployment.

> **Status: work in progress.** Phases 1-3 are complete. See the roadmap below.

## Why this project

Most agent demos never measure anything. This one is built around an evaluation
harness: every change to the crew is judged by resolve rate, tokens per task and
number of steps, and the multi-agent design is compared against a single agent.

## Architecture (implemented in Phase 3)

```
                +---------+     +-------+     +--------+
 task --------->| Planner |---->| Coder |---->| Tester |--- tests fail --> Coder (retry)
                +---------+     +-------+     +--------+
                                    ^              |
                                    |            tests pass
                                    |              v
                                    |         +----------+
                                    +- reject-| Reviewer |--- approve --> done
                                              +----------+

 Supervisor (routing logic): max 3 coder attempts, 40k token budget
```

- **Planner**: read-only tools (`list_files`, `read_file`); produces a short plan.
- **Coder**: can read and write files; gets test failures or reviewer feedback on retries.
- **Tester**: no LLM. Runs `pytest` and trusts the exit code.
- **Reviewer**: no tools. Reads the `git diff` and returns APPROVE or REJECT.
- **Supervisor**: plain Python routing, with attempt and token limits.
- Each agent only gets the tools it needs, and the LLM call is guarded against
  malformed tool calls and rate limits.

Planned AWS (free-tier) deployment: API Gateway/Lambda (webhook) -> SQS ->
Lambda/EC2 (agents) -> DynamoDB + S3 (run history, logs, diffs), with
Step Functions and CloudWatch for orchestration and observability.

## Roadmap

- [x] **Phase 1:** single agent with a hand-written tool-calling loop
- [x] **Phase 2:** Planner / Coder / Tester as a LangGraph with a retry loop
- [x] **Phase 3:** Reviewer + Supervisor, retry and token-budget limits
- [ ] **Phase 4:** Docker sandbox for running tests safely
- [ ] **Phase 5:** evaluation harness (15-20 tasks, several runs each, single vs multi-agent)
- [ ] **Phase 6:** GitHub integration (read issues, open PRs)
- [ ] **Phase 7:** AWS serverless deployment and observability
- [ ] **Phase 8:** write-up and demo

## Results so far

Model: `openai/gpt-oss-120b` via Groq. Each row is a **single run**, so treat the
numbers as anecdotes until the evaluation harness (Phase 5) runs each task many times.

| Task                               | Agent                            | Coder attempts | Steps | Tokens | Result                            |
| ---------------------------------- | -------------------------------- | -------------- | ----- | ------ | --------------------------------- |
| Add pagination to `GET /users`     | Single agent (Phase 1)           | 1              | 6     | 3,592  | 3/3 tests pass                    |
| Add pagination to `GET /users`     | Crew v1 (Planner/Coder/Tester)   | 1              | 12    | 9,568  | 3/3 tests pass                    |
| Validation (422) + `X-Total-Count` | Crew v1 (Planner/Coder/Tester)   | 1              | 10    | 8,470  | 7/7 tests pass                    |
| Validation (422) + `X-Total-Count` | Crew v2 (+ Reviewer, Supervisor) | 2              | 15    | 16,626 | 7/7 tests pass, reviewer approved |

## What I've learned so far

- On the easy task, the multi-agent crew used about **2.7x the tokens** of the
  single agent for the same outcome. Multi-agent is not automatically better.
- The same crew on the same task cost 8.5k tokens in one run and 16.6k in another
  (a failed first attempt followed by a retry), so a single run says little.
- The Planner sometimes wrote invalid Python into its plan (a parameter without a
  default after one with a default), which broke the Coder's first attempt. The
  Tester caught it and the retry loop fixed it.
- The model call itself can fail: a malformed tool call crashed the whole graph
  until the LLM call was guarded and crashes were turned into results.
- A bug found on Windows: files must be read and written as UTF-8, or the model's
  special characters raise an encoding error.
- The Reviewer was tested on 2 hand-written patches: it approved a clean one and
  rejected a hack that special-cased the tested inputs (`page == 0`, `limit == 101`),
  with accurate reasons. It did not explicitly flag the hardcoded `X-Total-Count`
  value as a hack. Two samples is too few; a larger set of bad patches is planned
  for Phase 5.

## Quickstart

```bash
git clone https://github.com/Gourish-Pednekar/issue-crew
git clone https://github.com/Gourish-Pednekar/sample-target-app
cd issue-crew
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then fill in your Groq key and the WORKSPACE path
```

Put the target repo at its failing baseline first (see the
[sample-target-app](https://github.com/Gourish-Pednekar/sample-target-app) README), then run:

```bash
# Phase 1: single agent
python phase1_agent.py "Add pagination to GET /users using page (default 1) and limit (default 10) query params. Make all tests pass."

# Phase 2: Planner -> Coder -> Tester
python phase2_crew.py "Make all tests in tests/test_users.py pass. Invalid page or limit values must be rejected with 422, and the response must include an X-Total-Count header."

# Phase 3: adds the Reviewer and Supervisor
python phase3_crew.py "Make all tests in tests/test_users.py pass. Invalid page or limit values must be rejected with 422, and the response must include an X-Total-Count header."
```

## Safety note

The agents write code and run `pytest` on your machine. They are **not sandboxed
yet** (Docker isolation is planned for Phase 4), so only point them at repos you
trust.

## License

MIT
