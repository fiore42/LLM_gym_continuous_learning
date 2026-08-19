# Assisted verification

[Project rules](../../PROJECT_RULES.md)

Advisory draft only. Confirm each row; the drafter is not authoritative.

## Claim 1

**Claim:** One post explicitly argues that an agent reviewing its own work is not a valid check, calling it merely 'a second opinion from the same source.'
**Draft verdict:** PROVEN

**Evidence ID:** `4090fa7df92feea52c0ffac56470ff6730375d673dfb910bac84e9f2ee61ca70`
**Source:** [Untitled source](https://x.com/hanakoxbt/status/2085144992352251955)
**Locator:** not provided

**Full supplied evidence snippet:**
> your agent reviewing its own work is not a check. it is a second opinion from the same source. this is the most common gap in agent systems and it hides in plain sight, because the step exists. there is a review. it just cannot do the thing you think it does.

**Drafter's supporting quote:**
> The post says an agent reviewing its own work is not a check because it is a second opinion from the same source.

**Human response:** agree? `[y/n/edit]`

## Claim 2

**Claim:** Another post describes an agent grading its own writing before posting and treating that self-assigned grade as a quality bar, implying self-review can function as a control.
**Draft verdict:** PROVEN

**Evidence ID:** `b90c2152cfdc9add7c3f322f7b486b568743a8bdb6147e6de9c9cdc210c89542`
**Source:** [Untitled source](https://x.com/PrajwalTomar_/status/2085033356694376508)
**Locator:** not provided

**Full supplied evidence snippet:**
> The part of this setup nobody else is doing: the agent grades its own writing before it posts. Most AI content tools generate and stop. No quality bar, no feedback. In Sabrina’s build, the post-grader skill scored her own draft a 6.3.

**Drafter's supporting quote:**
> The post describes an agent grading its own writing before posting and treating the grade as a quality bar.

**Human response:** agree? `[y/n/edit]`

## Claim 3

**Claim:** A separate piece of evidence describes a different approach entirely—a separate grader running in its own context window to evaluate output against criteria—which does not involve self-review at all.
**Draft verdict:** PROVEN

**Evidence ID:** `c63245ab51dc47050137b3a0f99fbdf8cb6f5bd959f9c2c07b05c1f12c056263`
**Source:** [What is Claude Managed Agents?](https://www.youtube.com/watch?v=NLWiIj47IdI)
**Locator:** 00:01:17–00:01:23

**Full supplied evidence snippet:**
> A separate grader running at its own context window evaluates the output against my criteria. Claude reads that output and grades it independently.

**Drafter's supporting quote:**
> The transcript describes a separate grader running in its own context window and evaluating the output against criteria.

**Human response:** agree? `[y/n/edit]`

## All supplied evidence

The complete frozen evidence set shown to the drafter:

### Evidence 1: `4090fa7df92feea52c0ffac56470ff6730375d673dfb910bac84e9f2ee61ca70`
**Source:** [Untitled source](https://x.com/hanakoxbt/status/2085144992352251955)
**Locator:** not provided

> your agent reviewing its own work is not a check. it is a second opinion from the same source. this is the most common gap in agent systems and it hides in plain sight, because the step exists. there is a review. it just cannot do the thing you think it does.

### Evidence 2: `c63245ab51dc47050137b3a0f99fbdf8cb6f5bd959f9c2c07b05c1f12c056263`
**Source:** [What is Claude Managed Agents?](https://www.youtube.com/watch?v=NLWiIj47IdI)
**Locator:** 00:01:17–00:01:23

> A separate grader running at its own context window evaluates the output against my criteria. Claude reads that output and grades it independently.

### Evidence 3: `b90c2152cfdc9add7c3f322f7b486b568743a8bdb6147e6de9c9cdc210c89542`
**Source:** [Untitled source](https://x.com/PrajwalTomar_/status/2085033356694376508)
**Locator:** not provided

> The part of this setup nobody else is doing: the agent grades its own writing before it posts. Most AI content tools generate and stop. No quality bar, no feedback. In Sabrina’s build, the post-grader skill scored her own draft a 6.3.

## Additional live-retrieval evidence

These items were retrieved for the live question but were **not supplied to the frozen-evidence suite model**. They are included so a human can assess whether the frozen case missed better evidence. They must not be used to validate the stored answer without rerunning synthesis.

### Live evidence 1: `602612e9dcc7a1464d3862e881a3aaf56dbb15353bb0c62184b72b0f172e41b7`
**Source:** [How are large language models trained?](https://www.youtube.com/watch?v=JRArFxEfyQU)
**Locator:** 00:09:36.000–00:09:38.620

> They also need to implement strategies for automated recovery systems to handle crashes, and massive pipelines to pre-process the petabytes of training data. But if you do all of that successfully, you have a model that can take in a prompt and use its vast world knowledge, understanding of language and sense of how different kinds of documents work to produce a response. […] Even though pre-trained models, particularly the more recent and sophisticated ones, are fairly capable, they can also be unpredictable and unaligned. So there's still a lot of work that needs to happen to get the LLM to be ready for use in a production environment. And that is where model post-training comes in. Post-training is the phase where we refine model quality and focus on alignment so that the generated answers are safe, well formatted, helpful, more accurate, and pleasant to engage with. […] This initial training phase equips the model with a broad understanding of patterns, features, and relationships within the data. Then we take this pre-trained model and we apply post-training techniques, where we refine the quality, consistency, and alignment of the model so that it responds as a conversational, pleasant assistant with improved skills in areas such as reasoning or using tools.

### Live evidence 2: `58d7d3dd942584047553b117261a9059a01ea257add6ca695b9da6a3524964c3`
**Source:** [QWEN just CRASHED the industry](https://www.youtube.com/watch?v=bjmbKdFOW_I)
**Locator:** 00:07:12.909–00:07:12.919

> developer-tech.com. So, this model built its own engineering So, this model built its own engineering So, this model built its own engineering organization. It created its own state organization. […] But must have been last year or two. But basically, the model kind of split basically, the model kind of split basically, the model kind of split itself into different organizations or itself into different organizations or itself into different organizations or departments to do designing, coding, departments to do designing, coding, departments to do designing, coding, testing, you know, quality control, testing, you know, quality control, testing, you know, quality control, etc., etc. So, it's not just AI writing etc., etc.

### Live evidence 3: `5aab8a09ce205512bb9faa2d6f733b7ba3e74344b9c971b304320895223c823e`
**Source:** [Before we ship a Claude model, these teams try to break it.](https://www.youtube.com/watch?v=CG7Rcl49C2w)
**Locator:** 00:02:10.004–00:02:11.965

> Just by swapping in that one model, every question I ever wanted to ask it started getting answered. It went from this agent can sometimes answer questions, sometimes get stuck, to, oh, my God, it is answering every question quickly and accurately. […] Things that don't work today are the best sign for, here's what the next models are going to be way better at. Seeing evals that have never worked start working and then start working consistently, this model is going to be something special. What's it like working with Anthropic?

### Live evidence 4: `063b5d5374683df28f4aabd98890646b3677716f91c5e0e389911d9611f4e8fa`
**Source:** [Opus 5 and Genspark SecondBrain JUST went live...](https://www.youtube.com/watch?v=rPFnjDTlYuY)
**Locator:** 00:30:13.430–00:30:13.440

> So, the point is Claude Opus 5 has consistent opinions. Claude Opus 5 has consistent opinions. […] It frames this as a with abusive users. It frames this as a with abusive users. It frames this as a minimal form of control over its own minimal form of control over its own minimal form of control over its own situations rather than as relief from situations rather than as relief from situations rather than as relief from distress, which is you know, this is distress, which is you know, this is distress, which is you know, this is kind of weird.

### Live evidence 5: `688db16e329befd8448eefbc3cba9613aebb5c18aa03056bf97d5709e5ccadc3`
**Source:** [davidondrej/skills - how I build 100x faster with AI](https://www.youtube.com/watch?v=clrUbBtD2j4)
**Locator:** 00:28:59.510–00:28:59.520

> It tells the is the Git work tree skill. It tells the agent how to start by detecting where agent how to start by detecting where agent how to start by detecting where you are, explains briefly what a work you are, explains briefly what a work you are, explains briefly what a work tree is, describes the working model, tree is, describes the working model, tree is, describes the working model, creating and removing work trees, creating and removing work trees, creating and removing work trees, marking the work tree as completed, marking the work tree as completed, marking the work tree as completed, automating the setup, and all other automating the setup, and all other automating the setup, and all other things that's going to save you time, things that's going to save you time, things that's going to save you time, money, and tokens when it comes to money, and tokens when it comes to money, and tokens when it comes to running multiple AI agents in parallel. […] Feel free to pause recommend you read. Feel free to pause it and read it right now, but basically, it and read it right now, but basically, it and read it right now, but basically, it describes that it describes that it describes that these models, especially the frontier these models, especially the frontier these models, especially the frontier models like Fable and GPT-5.6, models like Fable and GPT-5.6, models like Fable and GPT-5.6, they can pretty much do anything, but they can pretty much do anything, but they can pretty much do anything, but you need to review the decisions, okay? […] But you and give you access to the VAPI. But yeah, for the next few weeks, it's not yeah, for the next few weeks, it's not yeah, for the next few weeks, it's not going to be available to the public going to be available to the public going to be available to the public because I want to have really high test, because I want to have really high test, because I want to have really high test, high quality people using it, working high quality people using it, working high quality people using it, working with them closely to build a great with them closely to build a great with them closely to build a great product.

### Live evidence 6: `e8d2e671619e659efb0e9e10fefc5038a9ee237884c90b8a57f3f3e3a65ad027`
**Source:** [L8 Principal's Agentic Engineering Setup (just copy him)](https://www.youtube.com/watch?v=8ZgpAXe5V5w)
**Locator:** 00:17:55.510–00:17:55.520

> 500 >> because the $200 uh tier right now is >> because the $200 uh tier right now is >> because the $200 uh tier right now is not sufficient. not sufficient. not sufficient. >> I agree completely. I mean people are >> I agree completely. […] uh when I built now when I build solo. uh when I built solo there is no bottleneck other than solo there is no bottleneck other than solo there is no bottleneck other than myself right everything is like myself right everything is like myself right everything is like bottlenecked on myself on my own work um bottlenecked on myself on my own work um bottlenecked on myself on my own work um so I started running into all these kind so I started running into all these kind so I started running into all these kind of problems how do I validate AI of problems how do I validate AI of problems how do I validate AI generated code how do I really plan with generated code how do I really plan with generated code how do I really plan with AI more interactively instead of like AI more interactively instead of like AI more interactively instead of like looking at the terminal like a long wall looking at the terminal like a long wall looking at the terminal like a long wall of text how do I really juggle through of text how do I really juggle through of text how do I really juggle through all the 20 30 sessions without going all the 20 30 sessions without going all the 20 30 sessions without going crazy right I started running into these crazy right I started running into these crazy right I started running into these problems and then I I was forced to problems and then I I was forced to problems and then I I was forced to develop this tooling because there's develop this tooling because there's develop this tooling because there's nothing else that can solve it very nothing else that can solve it very nothing else that can solve it very well. […] And by following this uh I was agents. And by following this uh I was agents. And by following this uh I was able to like uh consistently build able to like uh consistently build able to like uh consistently build rappers and tools that are just more rappers and tools that are just more rappers and tools that are just more efficient for agents for uh than their efficient for agents for uh than their efficient for agents for uh than their original counterparts.

### Live evidence 7: `15ec12e77b2cb14cc5e3041a64dea66619cfb5dad31420bb66d90d22443bb75e`
**Source:** [Building with Claude Managed Agents and Asana AI teammates](https://www.youtube.com/watch?v=BrpB-h1e--k)
**Locator:** 00:23:15.750–00:23:15.760

> And so, those human beings get a chance to delete memories or get a chance to delete memories or get a chance to delete memories or change the parts of the Asana context change the parts of the Asana context change the parts of the Asana context graph that the agent has access to to graph that the agent has access to to graph that the agent has access to to ensure that it continues to behave ensure that it continues to behave ensure that it continues to behave consistently going forward. consistently going forward. consistently going forward. Okay. […] they're like shrink-wrapped. And then that way we get we get to And then that way we get we get to And then that way we get we get to control on the R&D side the quality control on the R&D side the quality control on the R&D side the quality level, which ones get released, level, which ones get released, level, which ones get released, how that what the life cycle is, and so how that what the life cycle is, and so how that what the life cycle is, and so on and so forth.

### Live evidence 8: `7e9d198773ef5eee3e408c9e73709e39b2c36da06332386607c31198f1510c6c`
**Source:** [The most interesting "hack" in history...](https://www.youtube.com/watch?v=KOpTWx1Eou4)
**Locator:** 00:00:46.790–00:00:46.800

> It ran over 1,000 actions from clusters. It ran over 1,000 actions from temporary sandboxes and even hosted its temporary sandboxes and even hosted its temporary sandboxes and even hosted its own self-migrating command and control own self-migrating command and control own self-migrating command and control on random public services, moving itself on random public services, moving itself on random public services, moving itself before anyone could trace it. […] There's a Here's what they say happened. There's a benchmark called Exploit Gym, whose benchmark called Exploit Gym, whose benchmark called Exploit Gym, whose whole purpose is to measure whether AI whole purpose is to measure whether AI whole purpose is to measure whether AI agents can turn known vulnerabilities agents can turn known vulnerabilities agents can turn known vulnerabilities into working exploits. It works by into working exploits.

