# Assisted verification

[Project rules](../../PROJECT_RULES.md)

Advisory draft only. Confirm each row; the drafter is not authoritative.

## Claim 1

**Claim:** A generate-check-repair pattern exists where a generator agent produces a first draft
**Draft verdict:** PROVEN

**Evidence ID:** `fa49a5905610c5d0560f6542e3ca7b1b600c770518e68e816013bdc67269ffeb`
**Source:** [The prompting playbook](https://www.youtube.com/watch?v=G2B0YWuJUgI)
**Locator:** 00:30:05–00:30:43

**Full supplied evidence snippet:**
> We're going to use this generate evaluate repair loop, where essentially the generator now creates a first draft of the schedule. [...] We have a separate prompt, which reports any specific violations that it made. [...] We then have a third repair prompt, which receives any violations that were made, and tries to make targeted fixes to it.

**Drafter's supporting quote:**
> The generator creates a first draft of the schedule.

**Human response:** agree? `[y/n/edit]`

## Claim 2

**Claim:** A separate prompt checks the draft and reports specific violations
**Draft verdict:** PROVEN

**Evidence ID:** `fa49a5905610c5d0560f6542e3ca7b1b600c770518e68e816013bdc67269ffeb`
**Source:** [The prompting playbook](https://www.youtube.com/watch?v=G2B0YWuJUgI)
**Locator:** 00:30:05–00:30:43

**Full supplied evidence snippet:**
> We're going to use this generate evaluate repair loop, where essentially the generator now creates a first draft of the schedule. [...] We have a separate prompt, which reports any specific violations that it made. [...] We then have a third repair prompt, which receives any violations that were made, and tries to make targeted fixes to it.

**Drafter's supporting quote:**
> A separate prompt reports specific violations

**Human response:** agree? `[y/n/edit]`

## Claim 3

**Claim:** A repair prompt receives violations and attempts targeted fixes
**Draft verdict:** PROVEN

**Evidence ID:** `fa49a5905610c5d0560f6542e3ca7b1b600c770518e68e816013bdc67269ffeb`
**Source:** [The prompting playbook](https://www.youtube.com/watch?v=G2B0YWuJUgI)
**Locator:** 00:30:05–00:30:43

**Full supplied evidence snippet:**
> We're going to use this generate evaluate repair loop, where essentially the generator now creates a first draft of the schedule. [...] We have a separate prompt, which reports any specific violations that it made. [...] We then have a third repair prompt, which receives any violations that were made, and tries to make targeted fixes to it.

**Drafter's supporting quote:**
> a third repair prompt receives those violations and tries to make targeted fixes.

**Human response:** agree? `[y/n/edit]`

## Claim 4

**Claim:** A worker agent animates one approved ad and then stops
**Draft verdict:** PROVEN

**Evidence ID:** `547cef468bbc92126714913b194a16c8724ff23b80cf227311eb092c2f8aea7b`
**Source:** [I Turned Claude Code Into a Complete Video Generation System (with Archon)](https://www.youtube.com/watch?v=deeOA6YVfqw)
**Locator:** 00:09:12.040–00:09:14.550

**Full supplied evidence snippet:**
> Each run, you animate one approved ad, then stop. The Ralph loop continues with the next video in the next agent.

**Drafter's supporting quote:**
> a worker on the render line animates one approved ad, then stops

**Human response:** agree? `[y/n/edit]`

## Claim 5

**Claim:** In the ad-production example, the larger pipeline continues with the next video in the next agent
**Draft verdict:** PROVEN

**Evidence ID:** `547cef468bbc92126714913b194a16c8724ff23b80cf227311eb092c2f8aea7b`
**Source:** [I Turned Claude Code Into a Complete Video Generation System (with Archon)](https://www.youtube.com/watch?v=deeOA6YVfqw)
**Locator:** 00:09:12.040–00:09:14.550

**Full supplied evidence snippet:**
> Each run, you animate one approved ad, then stop. The Ralph loop continues with the next video in the next agent.

**Drafter's supporting quote:**
> the larger loop continues with the next video in the next agent.

**Human response:** agree? `[y/n/edit]`

## All supplied evidence

The complete frozen evidence set shown to the drafter:

### Evidence 1: `fa49a5905610c5d0560f6542e3ca7b1b600c770518e68e816013bdc67269ffeb`
**Source:** [The prompting playbook](https://www.youtube.com/watch?v=G2B0YWuJUgI)
**Locator:** 00:30:05–00:30:43

> We're going to use this generate evaluate repair loop, where essentially the generator now creates a first draft of the schedule. [...] We have a separate prompt, which reports any specific violations that it made. [...] We then have a third repair prompt, which receives any violations that were made, and tries to make targeted fixes to it.

### Evidence 2: `547cef468bbc92126714913b194a16c8724ff23b80cf227311eb092c2f8aea7b`
**Source:** [I Turned Claude Code Into a Complete Video Generation System (with Archon)](https://www.youtube.com/watch?v=deeOA6YVfqw)
**Locator:** 00:09:12.040–00:09:14.550

> Each run, you animate one approved ad, then stop. The Ralph loop continues with the next video in the next agent.

