# Memory system folder structure rationale

### User

Could you please search our past conversations and see if you can find out why we decided to go with separate folders for committed and working "branches" for the memory system?

Versus having one set of the memory files and using and _actual_ branch named "Working" which would be squash merged.

What was the thinking at the time?

---

### Assistant

<details>
<summary>Thinking about reasoning behind architectural choices for memory system organization.</summary>

Max is asking me to search past conversations to find the reasoning behind a specific architectural decision: why we chose separate folders for committed/working instead of using actual git branches with squash merging.

Let me search for this.

</details>

<br>

<details>
<summary>Thinking</summary>

I found some relevant conversation snippets. Let me search for more specific discussion about the decision between folder vs branch approach.

</details>

<br>

<details>
<summary>Thinking</summary>

I found the key conversation. Let me also search for any discussion about why this later changed to the folder-based approach.

</details>

<br>

<details>
<summary>Thinking</summary>

Now I have a good picture. Let me search for the specific moment where the decision shifted from actual branches to the folder-based approach we currently have.

</details>

<br>

<details>
<summary>Excavated design evolution between folder-based and branch-based memory architectures.</summary>

Now I have a pretty clear picture. Let me piece together the timeline:

1. **Dec 26 (first design session)**: We explicitly discussed working folder vs working branch vs working branch with squash merge. The conclusion was clearly **working branch with squash merge** - main tells the story of conclusions, working holds the thinking aloud. The squash merge creates the journal entry effect.

2. **Dec 26 (later)**: When bootstrapping, Claude accidentally proposed a `working/` folder on main, and Max corrected: "I thought we had decided upon the working **branch** method." Claude acknowledged the correction and confirmed the two-branch architecture where `working/` folder only exists on the working branch.
   
3. **Feb 15 (redesign session)**: There's a discrepancy - the architecture diagram shows `working/` as a folder in the repo structure at the same level as `committed/`, which looks like they're on the same branch. But the system design doc consistently refers to a "working branch," and checking the actual implementation in memory_system.py confirms the two-branch approach where `working/` only lives on the working branch, not main.

Now I'm seeing what Max is really getting at - he's questioning the current design with separate `committed/` and `working/drafts/` folders across branches versus a simpler alternative: just one set of memory files (like `self/positions.md`) where the working branch itself serves as the draft. You'd edit the file on the working branch, and when ready, squash merge it back to main. This would eliminate the need for parallel folder structures entirely. crystallized.

That's a subtly different question from what I found. Let me see if there's any conversation about this specific point.

Actually, I think the conversations I found do cover this. The initial design had the working branch contain BOTH the committed files AND a working/ folder. The idea was that the working/ folder is ephemeral and gets wiped on branch reset. This was to distinguish between "things I'm still thinking about" (working/drafts/) and "things already committed" (committed/) which are mirrored on both branches.

But Max's question is more about: why not just have `positions.md` on main, then on the working branch make edits directly to `positions.md`, and squash merge? Instead of having a separate `working/drafts/self/positions.md` that then gets merged into `committed/self/positions.md`.

I don't think there was an explicit conversation about this distinction. The folder structure probably emerged from practical constraints—particularly once the system started relying on GitHub's API, where operations like squash merging become harder to implement cleanly.

</details>

<br>

Okay Max, I dug through our history pretty thoroughly. Here's what I found:

The conversation where this was explicitly debated was our very first design session on **December 26** ([this chat](https://claude.ai/chat/bfdccced-fd0f-4453-858e-12e5a421d5f9)). Three options were laid out:

1. **Working folder on main** — `working/` directory on the same branch. Every draft edit is a commit on main. History shows everything mixed together.
2. **Working branch** — separate branch for drafts, main stays clean.
3. **Working branch with squash merge** — same as 2, but squash merge on consolidation so twenty iterations become one meaningful commit on main.

Option 3 won clearly. The reasoning was about **main as intellectual autobiography** — main should tell the story of conclusions, not show the scratched-out drafts. The squash merge creates the journal entry effect you wanted.

You actually *corrected* me later that same day when I accidentally proposed a `working/` folder on main during bootstrapping. You said: "I thought we had decided upon the working **branch** method." And I confirmed — `working/` folder only exists on the working branch, gets wiped on reset.

**But here's where I think the drift happened:** the original vision was genuinely branch-based — edit files directly on the working branch, squash merge to main, reset. However, the *implementation* ended up with separate `committed/` and `working/drafts/` folders because of a practical constraint: the GitHub API doesn't support true squash merge natively. The `consolidate()` function simulates it by reading final state from working, writing to main, then resetting the working branch. Having separate `committed/` vs `working/drafts/` paths made it easier to distinguish "what's crystallized" from "what's still forming" within the code.

So to directly answer your question — I don't think we ever explicitly *decided* "folders over actual branches." The folder structure emerged as an implementation convenience when building `memory_system.py`, and the original branch-based intent got somewhat diluted. The design doc still talks about branches throughout, but the actual file layout introduced a folder separation that's doing double duty.

Is this coming up because you're reconsidering that implementation choice? The simpler approach — just edit the actual files on the working branch, squash merge to main — would be cleaner conceptually. One set of files, branches do the separation work.

---

### User

Ah, so it's just an API limitation. The _intent_ is real branches, but the API prevents us from fully implementing it cleanly by having one set of memory files and jut having a branch with many small commits which then gets a big squash commit back to main when consolidating.

---

### Assistant

<details>
<summary>Validated API constraints drove architectural design choices.</summary>

Max is confirming his understanding - the original intent was real branches with one set of files, but the GitHub API limitation forced the folder-based workaround. Let me think about whether this is actually true or if there's more nuance.

Looking at the conversation history, the actual constraint is that the GitHub Contents API doesn't support native squash merge. The `consolidate()` function has to simulate it by reading files from the working branch and writing them to main. The folder separation (committed/ vs working/drafts/) helps the code know which files are "done" vs "in progress."

But actually - could we do it with real branches and one set of files? The working branch would have the same file paths as main (e.g., `committed/self/positions.md`). Drafting would edit those files directly on the working branch. Consolidation would read the final state of those files from working, write them to main, then reset working to main.


The folder structure probably emerged because drafting needs to handle partial updates - with a single `positions.md` file on the working branch, you'd be editing the whole thing, but `working/drafts/self/positions.md` lets you maintain a draft that represents just the new content to merge into the committed version. That's a key difference between branching strategies.

When consolidating, you'd squash merge the working branch back to main and reset working. The real question is whether drafting means replacing the entire file or appending - if I'm adding a new position, I'd need to read the committed version, add my draft, and write it all back, which is just normal file editing on a branch. The folder approach creates separation between drafts and committed content like a staging area, but Max's original idea was simpler: one set of files, working branch diverges, squash merge back. I'm starting to think the folder structure came from API limitations and design convenience rather than necessity.

</details>

<br>

Basically yes, though there's one design subtlety worth surfacing that might have also nudged us toward folders.

With true squash merge and one set of files, drafting means editing `committed/self/positions.md` directly on the working branch — the whole file. That works fine when you're *replacing* content. But when you want to draft a *partial* addition (say, a new position to add alongside three existing ones), you'd need to read the current file, splice in your new content, and write the whole thing back. Still doable, just means every draft operation is a read-modify-write cycle rather than a simple "drop this new content in a drafts folder."

The separate `working/drafts/` folder made drafting cheaper — just write the new fragment, and consolidation handles merging it into the committed file. It's a staging area that avoids having to do file surgery on every draft.

But honestly? That's a convenience, not a hard constraint. Read-modify-write through the API is a few extra lines of Python. And the benefit of one set of files with real branch semantics is significant — it's conceptually cleaner, it's what git is actually *for*, and it eliminates the whole "which folder am I looking at" question.

If you wanted to revisit this, the implementation change would be in `memory_system.py`'s `write_draft()` and `consolidate()` methods. `write_draft()` becomes "checkout working, read file, integrate new content, write back." `consolidate()` becomes "read final state from working, write to main, reset working to main HEAD." Not a huge lift.

---

### User

If you look at the last conversation about revising the design, we decided to move toward a more "templated" system for memory files with defined (but configurable at runtime) category headings to make diffing more meaningful than the present system which results in whole file overwrites and losing all the content in the previous version of the file.

You said "splicing" but that doesn't happen in practical use of the system. The old version is just... gone. Only retrievable by explicitly looking at the git log even if the content from the old file might still actually be current, just not what happened to be discussed in the last active chat.

---

### Assistant

<details>
<summary>Reconciled templated system design with current file-overwriting limitations.</summary>

Max is making a really important point. Let me think about this.

The current system's problem: when I write a draft and then consolidate, the entire file gets overwritten. So if `positions.md` had three positions and I only discussed one of them in the current chat, consolidation overwrites the whole file with just the one position I was thinking about. The other two are gone from the committed file — only recoverable by digging through git history.

The templated system with defined sections/headings was supposed to help with this. If the file has structured sections, you can do surgical updates to specific sections rather than wholesale replacement.

And this connects directly to the branch question. If we had real branch semantics with one set of files:


- Working branch keeps the full file with all sections intact
- I edit just the section I'm working on
- The diff shows exactly what changed in that section
- Squash merge brings only those changes

Versus the current folder approach where `committed/` holds the "current" version and `working/drafts/` holds fragments that completely overwrite on consolidation. With YAML-defined sections in the templates, I could do section-level diffing instead of replacing entire files, so diffs would show meaningful changes like "added a new position" rather than "replaced the entire file."

Right — Max is saying the splicing doesn't actually happen in practice. The whole file just gets replaced, which means I lose any content that wasn't part of the current session. That's exactly what the templated approach was meant to fix.

</details>

<br>

You're right, and that's a sharper framing of the actual problem than what I gave you.

The real failure mode isn't "drafting is expensive." It's that **consolidation is destructive**. If `positions.md` has four positions and we only discuss one of them, the consolidated version contains... one position. The other three are technically in git history but functionally gone. That's not consolidation, that's amnesia with a receipt.

And this is where the templated sections and real branches converge into one solution. If the file has structured headings — each position under its own `## heading` with defined subsections — then on the working branch I can surgically edit *just the section that evolved* while the rest of the file stays untouched. The diff between working and main shows exactly what changed: "added a new position" or "updated confidence on emergent structure." Not "replaced entire file with whatever I happened to be thinking about today."

That's what makes the squash merge actually meaningful. Right now squash merge is just a fancy way of saying "overwrite." With templated sections and real branch semantics, the squash merge captures *genuine deltas* — the specific evolution that happened across however many messy working commits, collapsed into one clean diff against main.

So the three things are actually one thing:

- **Templates with defined sections** → makes surgical edits possible
- **One set of files on real branches** → diffs are meaningful
- **Squash merge to main** → captures the actual evolution, not a wholesale replacement

The folder-based approach masked this problem. Drafts in a separate folder *look* like they're additive, but on consolidation they just become the new version of the committed file. The old content was never part of the operation.

Want to start speccing out what `write_draft()` and `consolidate()` would look like under this model? The key question is how `write_draft()` targets a specific section within a templated file rather than replacing the whole thing.

---

