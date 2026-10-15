# Issue-to-PR: a multi-agent engineering crew

An AI crew that reads a task or a GitHub issue, plans the change, writes the code,
runs the tests in a Docker sandbox, has the diff reviewed, and opens a pull request.
Built from scratch to learn agent orchestration, evaluation, and cloud deployment.

> **Status: work in progress.** Phases 1-6 are complete. Phase 7 (AWS deployment)
> is next. See the roadmap below.

## Why this project

Most agent demos never measure anything. This one is built around an evaluation
harness: every change to the crew is judged by resolve rate, tokens per task and
number of steps, and the multi-agent design is compared against a single agent.

## Architecture

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
- **Tester**: no LLM. Runs `pytest` in the Docker sandbox and trusts the exit code.
- **Reviewer**: no tools. Reads the `git diff` and returns APPROVE or REJECT.
- **Supervisor**: plain Python routing, with attempt and token limits.
- Each agent only gets the tools it needs, and the LLM call is guarded against
  malformed tool calls and rate limits.

### GitHub integration (Phase 6)

```
 GitHub issue --> issue_to_pr.py --> clone target repo to a temp dir
                                 --> new branch crew/issue-<n>-<timestamp>
                                 --> run the crew (phase3_crew.py)
                                 --> safety checks
                                 --> commit, push, open PR ("Closes #n")
                                 --> comment the result on the issue
```

Planned AWS (free-tier) deployment: API Gateway/Lambda (webhook) -> SQS ->
Lambda/EC2 (agents) -> DynamoDB + S3 (run history, logs, diffs), with
CloudWatch for observability. The crew needs Docker for its tests and Lambda cannot
run Docker, so the runner design is still to be decided.

## Roadmap

- [x] **Phase 1:** single agent with a hand-written tool-calling loop
- [x] **Phase 2:** Planner / Coder / Tester as a LangGraph with a retry loop
- [x] **Phase 3:** Reviewer + Supervisor, retry and token-budget limits
- [x] **Phase 4:** Docker sandbox for running tests safely
- [x] **Phase 5:** evaluation harness (3 tasks, 3 agents, 10-11 runs each)
- [x] **Phase 6:** GitHub integration (read issues, open PRs, comment results)
- [ ] **Phase 7:** AWS serverless deployment and observability

## Early single-run results (Phases 1-4)

Model: `openai/gpt-oss-120b` via Groq. Each row is a **single run**, so treat these
numbers as anecdotes. The repeated runs are in the [Evaluation](#evaluation)
section below.

| Task                               | Agent                            | Coder attempts | Steps | Tokens | Result                            |
| ---------------------------------- | -------------------------------- | -------------- | ----- | ------ | --------------------------------- |
| Add pagination to `GET /users`     | Single agent (Phase 1)           | 1              | 6     | 3,592  | 3/3 tests pass                    |
| Add pagination to `GET /users`     | Crew v1 (Planner/Coder/Tester)   | 1              | 12    | 9,568  | 3/3 tests pass                    |
| Validation (422) + `X-Total-Count` | Crew v1 (Planner/Coder/Tester)   | 1              | 10    | 8,470  | 7/7 tests pass                    |
| Validation (422) + `X-Total-Count` | Crew v2 (+ Reviewer, Supervisor) | 2              | 15    | 16,626 | 7/7 tests pass, reviewer approved |
| Validation (422) + `X-Total-Count` | Crew v2 + Docker sandbox         | 2              | 16    | 20,078 | 7/7 tests pass, reviewer approved |

## What I've learned so far

- On the easy task, the multi-agent crew used about **2.7x the tokens** of the
  single agent for the same outcome. Multi-agent is not automatically better.
- The same crew on the same task cost 8.5k tokens in one run and 16.6k in another
  (a failed first attempt followed by a retry), so a single run says little.
  The Phase 5 runs confirm it: token cost varies a lot between identical runs.
- In several runs of the validation task, the Planner wrote invalid Python into its
  plan (a parameter without a default after one with a default). The Coder copied
  it, the first attempt failed, and the Tester-driven retry fixed it. It showed up
  again during Phase 5 and the Tester caught it. This looks like a systematic
  weakness of plans that contain code.
- Tests run in a Docker sandbox (no network, 512 MB memory, 1 CPU, 128 processes,
  only the target repo mounted). I verified the isolation: a container started with
  `--network none` cannot resolve any hostname.
- The model call itself can fail: a malformed tool call crashed the whole graph
  until the LLM call was guarded and crashes were turned into results.
- A bug found on Windows: files must be read and written as UTF-8, or the model's
  special characters raise an encoding error.
- A harness bug made good runs look bad: the evaluation workspaces had no `.git`,
  so the Reviewer saw an empty diff and rejected everything. Fixing it changed the
  numbers completely, so verify measurements before trusting them.
- The Reviewer was tested on 2 hand-written patches: it approved a clean one and
  rejected a hack that special-cased the tested inputs (`page == 0`, `limit == 101`),
  with accurate reasons. It did not explicitly flag the hardcoded `X-Total-Count`
  value as a hack. Two samples is too few, and a larger set of bad patches has not
  been built yet.

## Evaluation

The harness in `eval/` runs each agent on each task several times and appends
one row per run to `eval/results.csv`.

```
# run one agent type over all tasks, 3 runs each
python eval/run_eval.py --agents single --runs 3 --sleep 5

# turn the CSV into markdown tables
python eval/summarize.py
```

Tasks: `01-validation`, `02-slugify`, `03-cart-bugs`.

### Results

Model: `openai/gpt-oss-120b`. 3 tasks, 10-11 runs per agent.

| agent  | runs | resolved | approved | mean tokens | token range  | mean steps | mean seconds |
| ------ | ---- | -------- | -------- | ----------- | ------------ | ---------- | ------------ |
| single | 11   | 11/11    | -        | 6,609       | 3,842-10,291 | 6.8        | 25           |
| crew1  | 11   | 11/11    | -        | 10,318      | 5,677-21,224 | 11.3       | 56           |
| crew2  | 10   | 10/10    | 9/10     | 16,106      | 8,437-34,865 | 13.6       | 84           |

Per-task tables come from `python eval/summarize.py`.

**What this shows**

- Every agent resolved every task and none modified the tests, so on these
  three tasks success rate does not separate them. The difference is cost.
- Crew v1 used about 1.6x the tokens of the single agent and Crew v2 about
  2.4x, and both were slower (2x and 3.4x wall-clock).
- Variance is large. The same agent on the same task ranged from 9k to 35k
  tokens (Crew v2 on `02-slugify`), depending on how many attempts and
  rejections it took.
- Crew v2's Reviewer rejected one run that passed the tests (`02-slugify`).

**Limits.** Three tasks and a single model are a small sample. These are
cost and variance observations, not a ranking of the architectures.

## Quickstart

```bash
git clone https://github.com/Gourish-Pednekar/issue-crew
git clone https://github.com/Gourish-Pednekar/sample-target-app
cd issue-crew
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then fill in your Groq key and the WORKSPACE path
docker build -t issue-crew-sandbox sandbox   # needs Docker Desktop running
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

## GitHub integration

`issue_to_pr.py` turns a GitHub issue on the target repo into a pull request.

**Setup**

1. Create a fine-grained personal access token limited to the target repo
   (`sample-target-app`), with **Contents**, **Issues** and **Pull requests** set to
   read and write.
2. Put it in `.env` as `GITHUB_TOKEN=...`. `.env` is git-ignored; never commit it.
3. To use a different target repo, set `TARGET_REPO=owner/name` in `.env`.

**Usage**

```bash
# run the crew on issue 1 locally; nothing is pushed and no PR is opened
python issue_to_pr.py 1 --dry-run

# run the crew, push a branch, open a PR, and comment the result on the issue
python issue_to_pr.py 1
```

**What it does and the safety checks**

- Clones the target repo into a temp directory and works on a new branch named
  `crew/issue-<n>-<timestamp>`, so your local copy is never touched.
- Refuses to continue if the tests did not pass, if the crew made no changes, or if
  anything under `tests/` was modified.
- Pushes with an `Authorization` header instead of putting the token in the URL, and
  masks the token in error output.
- The PR description contains `Closes #<n>` and the run summary (tests passed,
  reviewer approval, attempts, steps, tokens).
- `--dry-run` stops before committing, pushing, opening a PR or commenting.

**Example run.** On issue #1 of `sample-target-app` ("Add pagination, validation and
total count to `GET /users`") the crew finished with tests passing, reviewer approval,
2 attempts, 15 steps and 22,473 tokens, and opened
[PR #2](https://github.com/Gourish-Pednekar/sample-target-app/pull/2). I read the diff
by hand: validation uses `Query(..., ge=1)`, `X-Total-Count` is computed from the data,
and only `app/main.py` changed. The crew also added a cap of 100 on `limit`, which the
issue did not ask for. I closed the PR without merging so `main` stays at the failing
baseline; the solution is kept on branch `crew/issue-1-1792077192`.

## Known limitations

- A passing test run plus a Reviewer approval is not proof the change is correct.
  Review every PR by hand before merging.
- Only one issue has been run through the GitHub integration, and the evaluation
  covers three tasks and one model.
- The crew is slower and uses more tokens than a single agent on these tasks.
- The Groq free tier limits runs (about 200K tokens per day for this model).

## Safety note

In the Phase 2 and 3 crews, `pytest` runs inside a Docker container with no network
access and CPU, memory and process limits. Limits of this setup: the target repo is
mounted read-write, the containers share the host kernel, and the Phase 1 single
agent still runs its tests directly on the host. Only point the agents at repos you
trust.

## License

MIT
