---
name: closeout
description: Close out the current working session. Writes a dated session receipt (request ledger, sources read, verified facts, corrections, deadlines, open loops, archive status) to the owning Google Drive case/project folder as a subordinate addendum, then reads it back to confirm it saved. Use when Jacob types /closeout or asks to close out, wrap up, or archive a session.
argument-hint: "[optional: owning folder name or Drive folder ID]"
---

# /closeout — session closeout receipt

Produce a session closeout receipt and save it where the work lives. The receipt preserves state for the next session; it never replaces the canonical records.

Lifecycle: explain → log → back up → mutate → verify. The only mutation here is creating one new receipt file.

## Hard rules

1. **Never edit canonical files.** Master timelines, AUDIT_LOG, START HERE, control matrices and filing packets stay untouched. The receipt goes in a NEW file and calls itself a subordinate addendum. Point to the canonical files by Drive ID.
2. **No outward action.** Do not file, serve, email, fax, sign, pay, contact any party, or push code as part of a closeout. Record what was or wasn't done; never perform it.
3. **Never upgrade a status.** "Drafted" is not "sent." "Sent" is not "received." "Received/stamped" is not "accepted/perfected." Every status line needs its source (Gmail message ID, Drive file ID, docket entry, commit hash) or a VERIFIED / UNVERIFIED tag.
4. **Separate what this session read from what it inherited.** List primary sources actually read, control documents read, and material NOT read. Anything from a control document or summary is SECONDARY until its original is read.
5. **Refresh state before writing.** Before drafting, look at the owning folder for files modified since the session's last action (Drive search on `modifiedTime > '<last activity>'`). Read the newest dated entries in the controlling status file. If status moved (a filing went in, a deadline passed, an order issued), record it and correct anything in this session's earlier output that it supersedes. Don't carry stale statements forward.
6. **Deadlines get dates and trigger conditions.** Give each deadline its calendar date, the event it runs from, whether that trigger is verified, and days remaining as of the closeout date. Flag any deadline that has passed.
7. **No secrets.** Redact tokens, keys, account numbers and passwords. Never paste .env contents.
8. **Canonical local paths** (`/opt/JarvisOS`, `/opt/EDWARD`, `/opt/DelaneyOS`, `/Volumes/JarvisSSD/`) are named, never created or altered, by a closeout. EDWARD and DelaneyOS are separate subsystems.

## Step 1 — Find the owner

- If `$ARGUMENTS` names a folder or gives a Drive folder ID, use it.
- Otherwise use the case or project folder the session worked in. For the APCo/AEP/PSC family the owner is Drive folder `1L4Fuzdr3EykK4o7Kaifde1etaItvaIvE` (APCo-PSC).
- If the session touched several owners, write one receipt to the primary owner and list the others under Cross-references.
- If the owner can't be determined, ask once with AskUserQuestion. Don't guess.

## Step 2 — Gather (read-only)

- The conversation: every user request, what was delivered, what was deferred, and any corrections the user made.
- The refresh from Hard rule 5.
- For code sessions, also capture: `git status --short`, `git log --oneline` for this session's commits, the branch, whether each commit was pushed, and any PR URL and its CI state.

## Step 3 — Write the receipt

Title: `CHAT_CLOSEOUT_<YYYY-MM-DD>_<CASE-OR-PROJECT>_<TOPIC>` (uppercase, underscores).

Sections, in order. Leave out a section only if it truly doesn't apply, and say so in one line.

0. **Header**
   - INTERNAL STRATEGY / NOT FOR FILING (legal) or INTERNAL / NOT A RELEASE (technical)
   - Session surface and dates worked
   - OWNER folder ID
   - RELATIONSHIP: subordinate receipt; names the canonical files it does NOT replace
   - One line: "No canonical file was edited. No filing / service / email / contact / push was made in this session" (state any exception exactly)
1. **Executive state:** the request in one line, the answer in 3–6 numbered points, and the recommended sequence.
2. **Request ledger:** `RQ-NN (DONE / PARTIAL / CORRECTED / OPEN)`, then deliverable, then what bounded it.
3. **Sources read this session:** primary (with IDs), control documents, NOT read.
4. **Status delta since the session's last action:** the Hard rule 5 refresh. Write "none found" if nothing changed.
5. **Verified facts promoted:** only from primary sources read this session, quoted exactly, with IDs and pin cites.
6. **Corrections and conflicts:**
   - Errors in drafts or earlier output
   - Contradictions between control documents
   - Superseded statements from this session
7. **Fact classification** (legal sessions): legally material / supporting context / dangerous or opponent-useful / missing proof.
8. **Deadlines:** per Hard rule 6.
9. **Open loops:** P0 / P1 / P2. For each, name the existing owner document (no duplicate task queues) and the exact next action. Mark decisions only Jacob can make as **Jacob decision**.
10. **EDWARD learning transfer:** reusable rules as CANDIDATE ONLY, plus a statement that no JarvisOS/EDWARD code, rules, tests or services changed (or exactly what did, with commit hashes).
11. **Artifacts:** every file created this session with ID/path, and whether it is preserved (ephemeral cloud scratch is not).
12. **Closeout audit:**
    - Opponent's or reviewer's fastest denial or failure routes
    - Continuity triggers
    - ARCHIVE STATUS: `ARCHIVE READY` only after readback passes; otherwise `NOT ARCHIVE READY` plus the blocker
    - State that the underlying matter remains OPEN where it does

Writing style: no fluff, no motivational filler, no certainty the record doesn't support.

## Step 4 — Save

- Google Doc: Drive `create_file` with `contentMimeType: "text/html"`, `parentId` set to the owner folder, and the receipt as simple HTML (`h1`/`h2`/`p`/`ul`/`ol`/`b`).
  - If the session produced a substantive standalone deliverable (an audit or report) not yet on Drive, upload it to the same folder unconverted (e.g. `text/markdown`, `disableConversionToGoogleType: true`) and list its ID under Artifacts.
- **Earlier receipt from this same session already exists:**
  - Prefer editing it in place with the Google Docs editor connector, so the link stays the same.
  - If that connector isn't available, create a short dated addendum titled `<original title>__ADDENDUM_<YYYY-MM-DD>` that names the original's ID and contains only what changed. Never trash or overwrite the earlier receipt.
- No Drive access: write the receipt to `/Volumes/JarvisSSD/Closeouts/` when running on Jacob's machine. In a cloud session, write it to the session scratchpad and send it with SendUserFile, and say plainly that it is not preserved.

## Step 5 — Verify

- Read each saved file back (`read_file_content`).
- Confirm all section headers are present, IDs are intact, and the byte size matches for uploaded files.
- Report any rendering defect honestly. Fix it only if it changes meaning.

## Step 6 — Reply

Keep the reply short:
- Links to the saved file(s), in the sentence that says what was saved.
- Archive status.
- The 2–4 open items that matter most, with dates.
- Anything from the status delta that changed since the last report.

Don't paste the receipt into chat.
