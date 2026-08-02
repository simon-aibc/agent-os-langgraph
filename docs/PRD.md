# agent-os-langgraph — Product Requirements Document

- **Version:** 1.0.1 (patch)
- **Author:** Simon (Tran Khai Minh) + Claude Code (drafter)
- **Created:** 2026-08-01
- **Shipped:** 2026-08-02 (R11 commit `641ca12`, tag `v1.0.0`)
- **Patch v1.0.1:** 2026-08-02 — dogfood fixes for mid-run resume, bash exit propagation, Tier-1 multiline write docs, and transient LLM retry.
- **Status:** SHIPPED — R1-R9 + R11 delivered; R10 (demo video) deferred to v1.1
- **Repo:** https://github.com/simon-aibc/agent-os-langgraph
- **Tests at v1.0.1:** 200 unit + 3 integration, `-W error` clean, Ruff clean, CI green on Python 3.11+3.12
- **Executors used:** Claude Code (architect/reviewer) + Codex CLI (task splitter + reviewer) + Antigravity IDE (implementer, courier: Simon)

---

## Legend

- 🔶 **Assumption** — plausible but unvalidated; Simon should confirm
- 🔵 **Open Question** — unknown, needs decision before execution
- ✅ **Confirmed** — validated in conversation 2026-08-01

---

## 1. Executive Summary

We're building **SimonOS-LangGraph**, a Python port of Simon's existing personal AI orchestration system (Hermes + Claude Code + Codex CLI + skills + vault memory) rebuilt on the **LangGraph** framework. The goal is dual-purpose: (1) produce a client-shippable, industry-standard agent codebase that serves as a **portfolio piece** demonstrating multi-agent orchestration expertise for freelance AI-engineering work ($100–150/hr tier), and (2) provide Simon with a **maintainable, type-safe, checkpointed** version of SimonOS that can evolve into a productized offering.

**Target outcome:** Within 4 weeks, ship a working LangGraph implementation that mirrors 80% of SimonOS's core orchestration behavior (routing, delegation, human-in-the-loop, memory), pushed to a public GitHub repo with README + demo video, ready to reference in Upwork/Wellfound proposals.

---

## 2. Problem Statement

### Who has this problem?
Simon — a solo builder positioning for AI-automation freelance income (cash-flow-first strategy, post-RRecruiter, 2026-07-26 departure).

### What is the problem?
Simon has spent 6+ months building **SimonOS/Hermes** — a bespoke personal AI OS with:
- Multi-agent routing (Hermes → Claude Code / Codex / scripts)
- Human-in-the-loop approval gates ("apply"/"confirm")
- Memory hierarchy (hot.md / memory.md / log.md)
- Skill-based tool ecosystem
- Scheduled autonomous execution (launchd)

**This system embodies the exact patterns that "AI Agent Engineer" job postings on Upwork/Wellfound demand** — but it is:
1. **Not portable** — built on personal vault, shell scripts, markdown prompts; unreadable to a hiring manager or client engineering team
2. **Not framework-recognized** — no "LangGraph" / "LangChain" / "CrewAI" keyword in Simon's public profile
3. **Not demo-able** — cannot be shown in a portfolio, GitHub repo, or client pitch as-is
4. **Not deployable** — cannot be handed to a client to run on their infra

### Why is it painful?
- **Income impact:** Simon is qualified for $100+/hr agent-engineering roles but lacks the vocabulary + artifact to prove it. Under-earning by an estimated $60–120/hr on freelance rates. 🔶
- **Opportunity cost:** Every week without portable proof = missed applications on Upwork/Wellfound/Contra where LangGraph is a listed keyword.
- **Learning waste:** Simon has already internalized the hardest concepts (routing, delegation, HITL, memory) — re-learning them via tutorials would be redundant. He just needs to **translate**, not learn from scratch.

### Evidence
- **Conversation 2026-08-01:** Simon self-identified LangGraph/CrewAI as looking "just like SimonOS" — confirming pattern recognition is already there
- **Freelance research 2026-08-01:** AI automation demand +109% YoY; LangGraph explicitly named in Upwork/Wellfound AI-agent postings
- **SimonOS artifacts:** `~/.hermes/` (routing, skills, SOUL.md), `Second Brain/AI/` (memory hierarchy), `~/.claude/skills/codex-*` (delegation patterns) — all evidence of existing multi-agent OS
- **Global CLAUDE.md:** documents brain/executor split, token economy, loop discipline — production-grade concepts already in use

---

## 3. Target Users & Personas

### Primary Persona: Simon (self)
- **Role:** Solo builder, freelance AI-automation engineer (target lane)
- **Technical level:** Intermediate-to-advanced — comfortable JS/APIs/low-code, reads Python, prefers to review over write
- **Goals:**
  - Ship portfolio piece within 4 weeks
  - Learn LangGraph vocabulary while translating, not from scratch
  - Have a codebase he can point clients to
- **Constraints:** 10–20 hrs/week available; won't hand-code executor work (delegates to Antigravity/Codex per 2026-08-01 decision)

### Secondary Persona: Future Freelance Client
- **Role:** Startup CTO / product lead needing AI-agent workflows built
- **Needs:** Type-safe, maintainable, deployable agent code with clear documentation
- **How they interact:** Read GitHub README → view demo → hire Simon → receive similar-architecture code

### Tertiary Persona: Hiring manager / recruiter
- **Role:** Screener at agent-engineering roles ($90–170/hr tier)
- **Needs:** 5-minute portfolio scan proving "candidate has actually built multi-agent systems, not just watched a course"
- **How they interact:** GitHub repo, README, architecture diagram, demo video

---

## 4. Strategic Context

### Business goals
- **Simon's Q3-Q4 2026 income OKR:** Cash-flow-first — replace lost RRecruiter income via freelance AI-engineering work at ≥$80/hr
- **Positioning goal:** Move from "no-code AI freelancer" (crowded, $20-40/hr) to "AI Agent Engineer" ($90-170/hr, less crowded)

### Market opportunity
- **AI automation freelance market:** +109% YoY demand (2026 research)
- **LangGraph-specific listings on Upwork/Wellfound:** growing category, undersupplied by qualified builders 🔶
- **Simon's differentiator:** Most AI freelancers can wire Zapier/n8n. Very few have built a multi-agent OS with HITL + persistent memory + delegation. Simon has — just needs to prove it in standard framework.

### Competitive landscape
- **Zapier/n8n integrators:** Commoditized, low-rate
- **LangChain-only builders:** Common, but LangGraph (stateful graph agents) is newer and rarer
- **CrewAI prototype demos:** Many, but few production-grade portfolio pieces
- **Simon's edge:** Bespoke OS experience → deeper architectural intuition than the average "tutorial-follower"

### Why now?
- **RRecruiter closed 2026-07-26** — active income lane needs replacing
- **AITrading shelved 2026-08-01** — opportunity cost freed up
- **Simon just finished conversation 2026-08-01** explicitly recognizing SimonOS ≈ LangGraph — insight is fresh, momentum is high
- **Framework maturity:** LangGraph reached stable/production-ready in 2024-2025; adoption curve is now, not later

---

## 5. Solution Overview

### High-level architecture

```
                    ┌─────────────────────────────────────┐
                    │       SimonOS-LangGraph (v1)        │
                    │           StateGraph                │
                    └─────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
   [planner_node]           [supervisor_node]            [human_gate]
   (Cowork role)            (Hermes role)                (Simon approval)
   Simon intent →           routing table →              interrupt()
   structured plan          decide next agent
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
      [architect_agent]      [executor_agent]      [tool_dispatcher]
      (Claude Code role)     (Codex role)          (skills/scripts/MCP)
      plan, review           edit, bash, test      graphify, browser
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    │
                             [verify_node]
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
              [brain_sync]                   [supervisor_loop]
              persist state                  more work? → loop back
                    │
                   END
```

### Core components (v1 scope)

| Component | Purpose | Maps to SimonOS |
|---|---|---|
| `SimonState` (TypedDict) | Type-safe graph state | replaces flat `hot.md`/`memory.md` reads |
| `planner_node` | Convert user intent → structured plan | Cowork planning role |
| `supervisor_node` | Route tasks to specialist agents | Hermes brain + routing table |
| `architect_agent` | Design/review sub-graph | Claude Code role |
| `executor_agent` | Implementation sub-graph | Codex CLI role |
| `tool_dispatcher` | Skills/scripts/MCP wrapper | Hermes skill invocation |
| `human_gate` | `interrupt()` for approval | "apply"/"confirm" gate |
| `verify_node` | Post-execution verification | Standards' evidence rule |
| `brain_sync` | Persist state to checkpointer | brain-sync skill |
| SQLite checkpointer | Durable state across sessions | Vault files (memory.md/hot.md/log.md) |

### User flow (v1 demo scenario)

**Scenario:** User asks agent to "refactor `foo.py` to add logging"

1. `planner_node` — LLM converts request into structured plan `{task: "refactor", target: "foo.py", scope: "add logging"}`
2. `supervisor_node` — Routing: has architect done a review? No → route to `architect_agent`
3. `architect_agent` — Reviews `foo.py`, produces brief `{files: ["foo.py"], changes: [...], verify: "pytest -k logging"}`
4. `human_gate` — `interrupt()` shows brief to user, waits for approve/reject
5. On approve → `supervisor_node` routes to `executor_agent`
6. `executor_agent` — Applies changes, runs verify command
7. `verify_node` — Confirms tests pass, diff matches brief
8. `brain_sync` — Checkpoints state; workflow ends

### Key features (v1)
- ✅ Typed state schema (Pydantic)
- ✅ Multi-agent supervisor pattern
- ✅ Human-in-the-loop gate via `interrupt()`
- ✅ SQLite checkpointer (resume after crash)
- ✅ At least 2 tool integrations (bash + one MCP)
- ✅ CLI entry point (`python -m simonos_langgraph.run "task description"`)
- ✅ Streaming output (real-time progress)
- 🔶 Simple in-repo demo (not deployed cloud service in v1)

---

## 6. Success Metrics

### Primary Metric
**Portfolio-generated freelance leads within 60 days of shipping v1**
- **Current:** 0 leads from AI-agent positioning
- **Target:** ≥3 inbound/reply-to-outbound conversations mentioning "saw your LangGraph repo"
- **Timeline:** Measure 60 days after repo goes public
- **Rationale:** Direct proxy for the whole point of the project (income impact)

### Secondary Metrics
| Metric | Current | Target | When measured |
|---|---|---|---|
| GitHub repo star count | 0 | ≥10 organic | 90 days post-launch |
| README completion score (has: arch diagram, quickstart, demo GIF, deploy guide) | 0/4 | 4/4 | Launch day |
| Codebase runs end-to-end (fresh clone → demo works) | N/A | Yes | Launch day |
| Simon's freelance proposal template mentions repo | No | Yes, in top 3 lines | Launch + 7 days |
| Learning outcome: Simon can explain LangGraph state/checkpointer/interrupt in ≤3 sentences each | No | Yes | End of week 2 |

### Guardrail Metrics
| Metric | Constraint |
|---|---|
| Time spent by Simon (hands-on) | ≤20 hrs total (execution delegated to Antigravity/Codex) |
| Scope creep | v1 ships **without** UI, cloud deploy, or non-core integrations |
| Correctness — no invented features | Every feature in codebase traces to a section in this PRD |

---

## 7. User Stories & Requirements

### Epic Hypothesis
> We believe that translating SimonOS into a public LangGraph codebase will generate qualified freelance leads for Simon in the AI-agent-engineering tier ($90-170/hr) because it converts existing bespoke expertise into industry-standard, demoable artifact — and we'll measure success by inbound conversations referencing the repo within 60 days.

### Requirements — grouped by workflow slice

#### R1: State schema & core graph skeleton
**As** a Python engineer reading the repo, **I want** a typed `SimonState` schema and minimal 3-node graph, **so that** I can understand the architecture in <10 minutes.

**Acceptance criteria:**
- [ ] `SimonState` TypedDict with: `messages`, `task`, `plan`, `executor_output`, `approval`, `hot_context`
- [ ] `StateGraph(SimonState)` compiles without error
- [ ] Minimum viable graph: `START → planner → supervisor → END`
- [ ] Unit test: `python -m pytest tests/test_state.py` passes

#### R2: Supervisor routing
**As** the graph runtime, **I want** a supervisor node that reads state and returns the next node name, **so that** the graph can route tasks to correct specialist.

**Acceptance criteria:**
- [ ] `supervisor_node` returns `Command(goto="architect" | "executor" | "tool" | "end")`
- [ ] `conditional_edges` correctly dispatch based on router output
- [ ] Router has explicit `skill-first` check: if task matches known skill → dispatch to `tool_dispatcher` before spinning up an agent
- [ ] Recursion limit configured (max 6 hops before forcing end) — mirrors SimonOS "max 3 rounds" rule

#### R3: Architect sub-graph
**As** the supervisor, **I want** to delegate design/review work to an architect sub-graph, **so that** planning stays isolated from execution.

**Acceptance criteria:**
- [ ] `architect_agent` = `create_react_agent(llm, tools=[read_file, grep, plan_writer])`
- [ ] Returns structured brief: `{files: list, changes: list, verify_cmd: str}`
- [ ] Does NOT execute code (read-only tools)
- [ ] Sub-graph tested with mock LLM

#### R4: Executor sub-graph
**As** the supervisor, **I want** to delegate implementation to an executor sub-graph, **so that** file edits happen with tool boundaries clear.

**Acceptance criteria:**
- [ ] `executor_agent` = `create_react_agent(llm, tools=[edit_file, bash, run_tests])`
- [ ] Accepts structured brief from architect
- [ ] Reports back: `{diff: str, verify_output: str, success: bool}`
- [ ] Sandboxed to project dir (no writes outside `~/Projects/simonos-langgraph-demo/`)

#### R5: Human-in-the-loop gate
**As** Simon (or client user), **I want** to approve or reject actions before they run, **so that** the agent cannot autonomously execute risky ops.

**Acceptance criteria:**
- [ ] `human_gate` node uses `interrupt("Approve? [y/n]")` from `langgraph.types`
- [ ] Graph pauses cleanly, checkpoint saved
- [ ] Resume via `graph.invoke(Command(resume="y"), config=thread)` works
- [ ] Rejected → routes back to `supervisor` with feedback in state
- [ ] Approved → routes to next execution node

#### R6: SQLite checkpointer
**As** the graph runtime, **I want** state persisted to SQLite across sessions, **so that** interrupted workflows can resume without losing context.

**Acceptance criteria:**
- [ ] `SqliteSaver` configured with local file `./checkpoints.db`
- [ ] Test: run graph → kill process at `human_gate` → restart → resume from checkpoint successfully
- [ ] Thread ID scheme documented (one thread per user task)

#### R7: Tool dispatcher — 3-tier cascading router
**As** the supervisor, **I want** to route "known tasks" through progressively smarter (and more expensive) routers, **so that** we save tokens on deterministic work and only escalate on ambiguity.

**Acceptance criteria:**
- [ ] **Tier 1: Deterministic** — Python `if/elif` matches `task.type` against `KNOWN_SKILLS` registry → invoke tool directly. Cost: $0, latency: 0ms
- [ ] **Tier 2: Cheap LLM router** — if Tier 1 misses, cheap local model (`qwen2.5:14b` via Ollama) classifies task → picks tool from registered list. Cost: $0, latency: ~200ms
- [ ] **Tier 3: Escalate** — if Tier 2 confidence < 0.7, return `Command(goto="supervisor")` for Claude Opus to decide
- [ ] Registered tools via `@tool`: `bash`, `read_file`, `write_file`
- [ ] 3 MCP integrations wrapped: **filesystem**, **codegraph**, **gbrain** (via `langchain-mcp-adapters`)
- [ ] Registry pluggable — new tools added via config, no code change in dispatcher

#### R8: CLI entrypoint + streaming
**As** a demo viewer, **I want** to run the agent from a single CLI command and see streaming output, **so that** the demo feels real.

**Acceptance criteria:**
- [ ] `python -m simonos_langgraph "task description"` works from fresh clone (after `pip install -e .`)
- [ ] Streams events via `graph.astream_events()` or equivalent
- [ ] Prints supervisor decisions, agent thoughts, tool calls in structured format
- [ ] Human gate prompts appear inline in CLI

#### R9: Repo hygiene (portfolio-grade)
**As** a hiring manager, **I want** the README to convey system value in <5 min, **so that** I can qualify Simon as a candidate.

**Acceptance criteria:**
- [ ] `README.md` with: 1-paragraph hook, architecture diagram (mermaid or PNG), quickstart, demo GIF, "why this architecture" section
- [ ] `docs/PRD.md` (this file) linked
- [ ] `docs/architecture.md` — deeper technical write-up
- [ ] `.env.example`, no committed secrets
- [ ] MIT license, pinned deps in `pyproject.toml`
- [ ] Basic CI: lint + tests on push (GitHub Actions) 🔶

#### R10: Demo video / GIF
**As** a hiring manager, **I want** to see the agent run end-to-end in ~60 seconds, **so that** I don't need to install anything to evaluate it.

**Acceptance criteria:**
- [ ] 60-90 second screen recording: CLI invocation → supervisor routing → architect brief → HITL approval → executor edit → verify success
- [ ] Embedded in README as GIF (or linked video)
- [ ] Recorded on a real task (not staged)

#### R11: Token economy patterns (portfolio differentiator)
**As** a hiring manager reviewing this repo, **I want** to see production-grade cost-awareness baked in, **so that** it signals a senior engineer, not a tutorial-follower.

**Acceptance criteria:**
- [ ] **LiteLLM router** wired — provider swap via `.env` (`LLM_PROVIDER_ARCHITECT=anthropic/claude-opus-4-8`)
- [ ] **Prompt caching** enabled on Anthropic calls (`cache_control: {"type": "ephemeral"}`) — targets 90% cost reduction on cached tokens
- [ ] **Message trimming** — `trim_messages(max_tokens=8000, strategy="last")` before every LLM call
- [ ] **Structured outputs** — every agent returns Pydantic model, not free-text (saves tokens + prevents parsing bugs)
- [ ] **Cascading router** (per R7) — deterministic → cheap LLM → expensive LLM only when needed
- [ ] **Human-in-the-loop as cost gate** — `interrupt()` = pause = $0 while awaiting user
- [ ] **README section "Token Economy"** — showcases all 6 patterns above with cost benchmarks (before/after)

### Edge cases & constraints

- **Cost ceiling:** ≤$5/day API spend during development (enforced via LiteLLM budget hooks)
- **Secrets:** No API keys in repo — use `.env` + `python-dotenv`, `.env.example` committed
- **Python version:** 3.11+ (LangGraph requirement)
- **Concurrent state writes:** v1 = single-user, single-thread; multi-user is out of scope
- **Ollama dependency:** Cheap-tier requires local Ollama running; graceful fallback to cheapest paid model if Ollama unreachable

---

## 8. Out of Scope (v1)

Explicitly **NOT** in v1 — flagged so Antigravity/Codex don't build them:

- ❌ **Web UI / chat interface** — CLI only. UI is v2 if leads validate the concept.
- ❌ **Cloud deploy / hosting** — runs locally. LangGraph Cloud or self-hosted is v2.
- ❌ **Multi-tenant / auth** — single-user, local.
- ❌ **Full port of every SimonOS skill** — v1 ports the ORCHESTRATION PATTERN, not the RRecruiter/CV/format skills. Those stay in Hermes.
- ❌ **Vault integration** — v1 uses SQLite checkpointer, not markdown vault. Vault sync is v2.
- ❌ **Voice / TTS** — text only.
- ❌ **Autonomous scheduling** — launchd/cron replacement is v2.
- ❌ **CrewAI comparison / dual implementation** — LangGraph only. CrewAI variant is a possible v2 experiment.
- ❌ **Fine-tuning / custom models** — off-the-shelf LLM providers only.

**Rationale:** every item above is either (a) 10x scope, (b) not needed to prove the pattern, or (c) not what freelance clients actually pay for (they pay for architecture, not UIs — those come with a design system already).

---

## 9. Dependencies & Risks

### Dependencies

| Dependency | Type | Blocking? | Owner |
|---|---|---|---|
| Python 3.11+ | Runtime | Yes | Simon (already has) |
| LangGraph latest stable | Framework | Yes | pip install |
| LLM API key (Anthropic / OpenAI / other) | External | Yes | Simon (already has Claude/other) |
| GitHub repo (public) | Infra | For portfolio only | Simon |
| Antigravity + Codex CLI available | Executor | Yes for execution phase | Simon (already has) |

### Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope creep — Simon adds "just one more feature" mid-build | HIGH | Delays launch | This PRD is the contract; new ideas → v2 backlog, not v1 |
| Antigravity/Codex produce non-idiomatic LangGraph code | MEDIUM | Portfolio quality drops | Simon reviews each PR before merge; require idiom checks in code review |
| Learning curve on typed state / interrupt semantics slows Simon's review | MEDIUM | Delays merges | 1-day upfront LangGraph tutorial for Simon before execution starts |
| No inbound leads within 60 days despite shipping | MEDIUM | Success metric misses | Repo is still useful as portfolio artifact for outbound proposals; adjust GTM (LinkedIn post, Reddit r/LocalLLaMA share) rather than blame product |
| LangGraph API breaks (still evolving) | LOW-MED | Rework needed | Pin exact version in `pyproject.toml`; note in README |
| Simon burns out on rebuild since SimonOS already works | MEDIUM | Project stalls | Frame as ≤4 weeks max — after that, cut scope not extend deadline |

---

## 10. Resolved Decisions (was: Open Questions)

Confirmed by Simon 2026-08-01:

1. ✅ **LLM providers — multi-provider via LiteLLM router:**
   - `supervisor_node` + `architect_agent` → **Anthropic Claude Opus 4.8** (reasoning)
   - `executor_agent` → **OpenAI GPT-5.5** (Codex-style, implementation)
   - `tool_dispatcher` Tier 2 + summarize/extract → **Ollama `qwen2.5:14b`** (local, free)
   - Fallback tier: **Ollama `mistral-small3.2`** (also local, already installed)
   - Prompt caching enabled on Anthropic calls (`cache_control: ephemeral`, 1h TTL)
   - Config via `.env` — providers swappable without code change

2. ✅ **MCP tools wrapped in v1 — 3 servers via `langchain-mcp-adapters`:**
   - **filesystem** (universal, portable, client-friendly)
   - **codegraph** (Simon signature; cross-CLI proven; Docker/npm install)
   - **gbrain** (knowledge graph — differentiator vs generic tutorials; `localhost:3131/mcp`)
   - MCP config in `mcp_config.json` at repo root; not committed if contains local paths

3. ✅ **Repo public from day 1** — `simon-aibc/agent-os-langgraph` on GitHub
   - License: MIT
   - Strategy: "learn in public" — commit history proves authorship
   - Simon to run `gh repo create` command (or approve Claude Code to do it)

4. ✅ **Execution chain (revised 2026-08-01 by Simon):**

   ```
   Claude Code (Sonnet)  — brief + final architecture review + debug
        ↓
   Codex CLI             — reads brief, breaks into micro sub-tasks, reviews returns
        ↓ (Simon = manual courier, copy each sub-task)
   Antigravity IDE       — actual code writer (Gemini free tokens = cheapest)
        ↓ (Simon copies output back)
   Codex CLI             — reviews Anti's output, loops to next sub-task
        ↓ (milestone complete)
   Claude Code           — architecture review across changes, debug, fix
   ```

   - **Why this chain:** Antigravity CLI can't be called by 3rd parties (standalone), Codex is chain-able. Simon serves as courier. Trade-off = manual copy/paste overhead, gain = free execution tokens + multi-model perspective.
   - **Loop discipline still applies:** max 3 sub-task iterations without Simon check-in.

5. ✅ **Demo video — deferred to post-v1** (not blocking)
   - v1 ships without video; can be added after Simon uses it once and captures a real recording
   - README will have text walkthrough + arch diagram in place of video

6. ✅ **Timeline — ASAP**
   - No fixed weekly milestones. Ship as fast as executor throughput allows
   - Milestones ordered by requirement number (R1 → R11), each = 1 mergeable PR
   - Simon reviews each PR; no batch-and-merge

7. ✅ **CrewAI = v2 experiment (not dropped)**
   - After v1 lands, port 1 slice to CrewAI as comparison exhibit
   - Portfolio angle: "same problem, 2 frameworks" is a stronger signal than one

---

## Appendix A — SimonOS → LangGraph concept map (reference)

| SimonOS concept | LangGraph equivalent | v1? |
|---|---|---|
| Hermes brain | `supervisor_node` | ✅ |
| Routing table | `conditional_edges` + router fn | ✅ |
| Claude Code (architect) | `architect_agent` sub-graph | ✅ |
| Codex CLI (executor) | `executor_agent` sub-graph | ✅ |
| Skills (`.md` runbooks) | `@tool` functions | ✅ (subset) |
| Approval gate ("apply"/"confirm") | `interrupt()` | ✅ |
| `hot.md` / `memory.md` / `log.md` | TypedDict state + SQLite checkpointer | ✅ (checkpointer only, no vault) |
| `AI/Decisions/` immutable log | Event log (checkpointer history) | ✅ (implicit) |
| Loop discipline (max 3 rounds) | `recursion_limit` | ✅ |
| Scheduled autonomy (launchd) | External cron + graph resume | ❌ (v2) |
| Cowork planning chat | `planner_node` | ✅ (basic) |
| brain_brief.sh session init | State initializer | ✅ |
| Graphify vault query | Tool wrapper | ❌ (v2 — vault integration deferred) |

---

## Appendix B — Timeline (proposed, needs Simon confirmation)

| Week | Milestone | Executor | Simon effort |
|---|---|---|---|
| Week 1 | LangGraph tutorial + repo scaffold + R1 (state + skeleton) | Simon self + Codex | 6 hrs |
| Week 2 | R2 supervisor + R3 architect + R4 executor sub-graphs | Antigravity plans, Codex builds | 5 hrs |
| Week 3 | R5 HITL + R6 checkpointer + R7 tool dispatcher | Codex | 4 hrs |
| Week 4 | R8 CLI + R9 README/repo hygiene + R10 demo video + GTM push | Simon + Codex | 5 hrs |
| **Total** | v1 shipped | | **~20 hrs Simon time** |

---

## Approval

Before executor (Antigravity + Codex) starts:

- [x] Simon reviews this PRD end-to-end (2026-08-01)
- [x] Open Questions resolved (all 7 answered 2026-08-01)
- [ ] Simon says **"apply"** in chat → this becomes v1.0 (execution begins)

**Simon's approval marker:** _____________  (date: _____________)

---

## Execution kickoff — post-approval sequence

Once Simon says "apply", Claude Code will:

1. **Write handoff brief for Codex** (`Second Brain/AI/Handoffs/2026-08-01-agent-os-langgraph-kickoff.md`) — includes PRD link, execution chain, Codex's role (sub-task splitter + reviewer, not implementer), Simon's role (courier), first target R1.
2. **Ask Simon** to run (or approve Claude Code to run) `gh repo create simon-aibc/agent-os-langgraph --public` — irreversible public action, needs explicit go.
3. Simon opens Codex CLI → paste handoff brief → Codex reads PRD + brief → returns first micro-batch of sub-tasks.
4. Simon copies sub-tasks one by one to Antigravity → Anti implements → Simon pastes back to Codex.
5. Codex reviews + presents next sub-task. Loop.
6. After R1 milestone → Simon returns to Claude Code (me) → I review architecture + flag issues → next requirement (R2).
7. Log to `Second Brain/AI/Logs/2026-08-01-agent-os-langgraph-session.md` per session (per Standards).

**NOTE:** Project skeleton files (`pyproject.toml`, `.env.example`, `README.md`, etc.) are now written by the Anti-Codex chain, NOT by Claude Code inline. Claude Code only writes briefs + reviews.
