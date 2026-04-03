# Architecture Report: Next-Gen OpenCode Async Bridge
**Project Codename:** Gemini Reviewer Interceptor (v2)
**Objective:** Transition from blocking CLI hooks to an asynchronous, multi-model subagent orchestration layer using OpenCode Server.

---

## 1. System Overview
The system facilitates the offloading of high-latency subagent tasks (e.g., `superpowers:code-reviewer`) from the primary **Claude Code** instance to an **OpenCode Server** harness. This allows for parallel execution, multi-model flexibility (swapping Claude for Gemini), and real-time visibility into worker progress without blocking the main developer workspace.

## 2. Core Components

### A. The Orchestrator (Claude Code)
The "Brain" of the operation. It maintains the primary developer context and delegates tasks via the `agent` tool. It is "hooked" at the `pretooluse` stage.

### B. The Dispatcher (Next-Gen Hook)
A sophisticated interceptor that replaces the legacy `gemini -p` logic.
- **Logic:** Matches subagent type strings (e.g., `superpowers:*`).
- **Mapping:** Consults a `.toml` configuration to determine the optimal provider/model for the task.
- **Initialization:** Triggers a `POST /session` request to the OpenCode Server.
- **Response:** Returns a `deny` status to the orchestrator with an "Actionable Ticket" containing the file paths for polling.

### C. The Harness (OpenCode Server)
A persistent server running in **YOLO mode** (`--yolo`).
- **Function:** Manages the lifecycle of the worker LLM.
- **Isolation:** Runs workers in dedicated directories with specific tool permissions (e.g., `bash: deny` for reviewers).
- **Communication:** Exposes REST endpoints for control and SSE (Server-Sent Events) for real-time logging.

### D. The Persistence Layer (Handshake Files)
The mechanism for asynchronous communication between the Harness and the Orchestrator.
- **Status File:** `.opencode/task_[ID].status` (Contains `PENDING`, `RUNNING`, or `COMPLETED`).
- **Result File:** `.opencode/task_[ID].report.md` (The final output from the worker).
- **Stream Log:** `.opencode/task_[ID].log` (A raw dump of the worker's thinking process).

---

## 3. The Async Workflow Lifecycle

1. **Trigger:** User asks Claude Code to "Review this PR." Claude calls the `agent` tool with the `superpowers:code-reviewer` string.
2. **Interception:** The hook catches the call, blocks it, and generates a Task ID.
3. **Dispatch:** The hook sends the prompt to OpenCode Server, specifying the subagent persona and the "Handshake" output paths.
4. **Handoff:** The hook returns a "Deny Reason" to Claude Code: *"Task offloaded. Check [Path] in 2 minutes for the final report."*
5. **Execution:** The OpenCode worker (e.g., Gemini 2.0 Pro) processes the review, writing its internal logs and final report to the specified paths.
6. **Supervision:** The primary Claude instance remains free. It may perform other tasks or "sleep" briefly before using the `read` tool to check the status file.
7. **Ingestion:** Once the status is `COMPLETED`, Claude reads the report, presents it to the user, and incorporates the findings into the main chat context.

---

## 4. Key Advantages
- **No Blocking:** The developer can continue coding while a heavy review runs in the background.
- **Model Heterogeneity:** Use Gemini for broad codebase reviews to save Claude's token usage or leverage specific model strengths.
- **Visibility:** Users can `tail -f` the log files to watch the subagent work in real-time.
- **Auditability:** Every subagent call leaves a persistent trail in the `.opencode/` directory.

---

## 5. Brainstorming Points for Claude
- **Polling Strategy:** How can we prompt the main Claude instance to be patient without it getting "confused" by the denial?
- **Error Recovery:** What happens if the OpenCode server crashes? The hook should likely have a fallback to the original `agent` tool call.
- **Recursive Agents:** Could the subagent spawn its own subagents within the same OpenCode harness?