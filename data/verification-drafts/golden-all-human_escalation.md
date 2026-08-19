# Assisted verification

[Project rules](../../PROJECT_RULES.md)

Advisory draft only. Confirm each row; the drafter is not authoritative.

## Claim 1

**Claim:** An agent should escalate unresolved conflict to a human rather than allowing the agent to silently choose a resolution
**Draft verdict:** PROVEN

**Evidence ID:** `fa49a5905610c5d0560f6542e3ca7b1b600c770518e68e816013bdc67269ffeb`
**Source:** [The prompting playbook](https://www.youtube.com/watch?v=G2B0YWuJUgI)
**Locator:** 00:20:30–00:20:46

**Full supplied evidence snippet:**
> We need to make sure that it's escalating to a human whenever there is a billing error. In this scenario, there is a billing conflict, and what we really want is the agent to escalate this to a human.

**Drafter's supporting quote:**
> The transcript describes escalating unresolved conflict to a human rather than allowing the agent to silently choose.

**Human response:** agree? `[y/n/edit]`

## Claim 2

**Claim:** An agent should escalate work to a human when the agent cannot safely resolve it
**Draft verdict:** PROVEN

**Evidence ID:** `7f10c524a16177d144b3badb5a389db319f476f22699b9dad6d514f492e37a87`
**Source:** [Pydantic AI 2.0: The New Best Way to Build AI Agents is Composing Capabilities](https://www.youtube.com/watch?v=PY7xIxybYNc)
**Locator:** 00:11:58–00:12:02

**Full supplied evidence snippet:**
> A support agent needs to access the knowledge base and also be able to escalate things to a human. [...] Someone comes to the customer support bot with a concern that needs to be escalated to a human, like “I was charged twice this month for my subscription.”

**Drafter's supporting quote:**
> The discussion describes escalating work to a human when the agent cannot safely resolve it.

**Human response:** agree? `[y/n/edit]`

## All supplied evidence

The complete frozen evidence set shown to the drafter:

### Evidence 1: `fa49a5905610c5d0560f6542e3ca7b1b600c770518e68e816013bdc67269ffeb`
**Source:** [The prompting playbook](https://www.youtube.com/watch?v=G2B0YWuJUgI)
**Locator:** 00:20:30–00:20:46

> We need to make sure that it's escalating to a human whenever there is a billing error. In this scenario, there is a billing conflict, and what we really want is the agent to escalate this to a human.

### Evidence 2: `7f10c524a16177d144b3badb5a389db319f476f22699b9dad6d514f492e37a87`
**Source:** [Pydantic AI 2.0: The New Best Way to Build AI Agents is Composing Capabilities](https://www.youtube.com/watch?v=PY7xIxybYNc)
**Locator:** 00:11:58–00:12:02

> A support agent needs to access the knowledge base and also be able to escalate things to a human. [...] Someone comes to the customer support bot with a concern that needs to be escalated to a human, like “I was charged twice this month for my subscription.”

## Additional live-retrieval evidence

These items were retrieved for the live question but were **not supplied to the frozen-evidence suite model**. They are included so a human can assess whether the frozen case missed better evidence. They must not be used to validate the stored answer without rerunning synthesis.

### Live evidence 1: `fa49a5905610c5d0560f6542e3ca7b1b600c770518e68e816013bdc67269ffeb`
**Source:** [The prompting playbook](https://www.youtube.com/watch?v=G2B0YWuJUgI)
**Locator:** 00:20:44.110–00:20:44.120

> covered by our policy. Um we need to make sure that it's Um we need to make sure that it's Um we need to make sure that it's escalating to a human whenever there is escalating to a human whenever there is escalating to a human whenever there is um a billing error. […] So, now we have one final failing test So, now we have one final failing test So, now we have one final failing test case, which we need to address, which is case, which we need to address, which is case, which we need to address, which is the billing error here. In this scenario, there is a billing In this scenario, there is a billing In this scenario, there is a billing conflict, and what we really want is the conflict, and what we really want is the conflict, and what we really want is the agent to escalate this to a human. And agent to escalate this to a human. And agent to escalate this to a human. And what we're seeing it doing instead is what we're seeing it doing instead is what we're seeing it doing instead is it's trying to it's trying to it's trying to explain to the customer what the reason explain to the customer what the reason explain to the customer what the reason behind it might be.

### Live evidence 2: `7f10c524a16177d144b3badb5a389db319f476f22699b9dad6d514f492e37a87`
**Source:** [Pydantic AI 2.0: The New Best Way to Build AI Agents is Composing Capabilities](https://www.youtube.com/watch?v=PY7xIxybYNc)
**Locator:** 00:09:16.030–00:09:16.040

> Like this first one is a support agents. Like this first one is a support agent, so it needs to access the agent, so it needs to access the agent, so it needs to access the knowledge base like perform rag in our knowledge base like perform rag in our knowledge base like perform rag in our database and then also be able to database and then also be able to database and then also be able to escalate things to a human. And then escalate things to a human. And then escalate things to a human. And then imagine at the front of your platform imagine at the front of your platform imagine at the front of your platform you have the FAQ widget where there's no you have the FAQ widget where there's no you have the FAQ widget where there's no escalation here, but it still needs escalation here, but it still needs escalation here, but it still needs access to the knowledge base to answer access to the knowledge base to answer access to the knowledge base to answer basic user questions. […] But let's say someone comes to the But let's say someone comes to the But let's say someone comes to the customer support bot where they actually customer support bot where they actually customer support bot where they actually have a concern that needs to be have a concern that needs to be have a concern that needs to be escalated to a human. Like I was charged escalated to a human. Like I was charged escalated to a human.

### Live evidence 3: `c4c1b249ad89b4fdc6ec9a9d3add46ae4fdb7c6f4f989c731ddc2a21826031f7`
**Source:** [Giving coding agents their own computers: How Cursor built cloud agents](https://www.youtube.com/watch?v=BbYSGxtsMic)
**Locator:** 00:10:45.630–00:10:45.640

> Um it's really just like what come up. Um it's really just like what we do with uh the pattern I was we do with uh the pattern I was we do with uh the pattern I was describing for humans, where if you see describing for humans, where if you see describing for humans, where if you see something wrong, say something, uh something wrong, say something, uh something wrong, say something, uh report it, and and try to work on a fix. […] It's really again very system of record. It's really again very uh uh uh similar to how human human systems work. similar to how human human systems work.

### Live evidence 4: `523f4898fbc3f48811664613c4e217c7a7e61e481c68b8227b1d9b13f67a07a0`
**Source:** [OpenAI JUST revealed the truth about it's "Rogue Agent"](https://www.youtube.com/watch?v=9lSIHaXT1rU)
**Locator:** 00:20:58.559–00:21:00.310

> third-party provers's infrastructure. How open described is it moved laterally How open described is it moved laterally How open described is it moved laterally and it also had privilege escalations. and it also had privilege escalations. […] So the agent they're saying here. So the agent they're saying here. So the agent followed a standard escalation shape. So followed a standard escalation shape. […] And the don't understand the answer. And the reason that puzzle works, I think, is reason that puzzle works, I think, is reason that puzzle works, I think, is because the answer is really obvious.

### Live evidence 5: `282cce7ace5ddd253f009df4009fed84168d395f9d37f466a4e001ae0143f6fe`
**Source:** [CLAUDE IS CONSCIOUS](https://www.youtube.com/watch?v=6CljfqMX9i4)
**Locator:** 00:23:39.190–00:23:39.200

> thoughts you can describe, accessible. thoughts you can describe, accessible. thoughts you can describe, hold in mind, and reason with. We found hold in mind, and reason with. […] Then you ask a milk in their brain. Then you ask a perfectly reasonable functional adult perfectly reasonable functional adult perfectly reasonable functional adult human being. What do cows drink? And human being. […] Some theories kind we were both happy. Some theories kind of suggest that maybe this is either the of suggest that maybe this is either the of suggest that maybe this is either the reason for humans developing reason for humans developing reason for humans developing consciousness or or one of the reasons consciousness or or one of the reasons consciousness or or one of the reasons is just the ability to sort of model is just the ability to sort of model is just the ability to sort of model ourselves and how we function in the ourselves and how we function in the ourselves and how we function in the world.

### Live evidence 6: `688db16e329befd8448eefbc3cba9613aebb5c18aa03056bf97d5709e5ccadc3`
**Source:** [davidondrej/skills - how I build 100x faster with AI](https://www.youtube.com/watch?v=clrUbBtD2j4)
**Locator:** 00:07:01.470–00:07:01.480

> It tells the is the Git work tree skill. It tells the agent how to start by detecting where agent how to start by detecting where agent how to start by detecting where you are, explains briefly what a work you are, explains briefly what a work you are, explains briefly what a work tree is, describes the working model, tree is, describes the working model, tree is, describes the working model, creating and removing work trees, creating and removing work trees, creating and removing work trees, marking the work tree as completed, marking the work tree as completed, marking the work tree as completed, automating the setup, and all other automating the setup, and all other automating the setup, and all other things that's going to save you time, things that's going to save you time, things that's going to save you time, money, and tokens when it comes to money, and tokens when it comes to money, and tokens when it comes to running multiple AI agents in parallel. […] Feel free to pause recommend you read. Feel free to pause it and read it right now, but basically, it and read it right now, but basically, it and read it right now, but basically, it describes that it describes that it describes that these models, especially the frontier these models, especially the frontier these models, especially the frontier models like Fable and GPT-5.6, models like Fable and GPT-5.6, models like Fable and GPT-5.6, they can pretty much do anything, but they can pretty much do anything, but they can pretty much do anything, but you need to review the decisions, okay?

### Live evidence 7: `7425f99a8e5bcc82d14a80b1daae7170ebd25bcd76ab0dedf1757c3776f0dfed`
**Source:** [Code with Claude Tokyo 2026: Opening Keynote](https://www.youtube.com/watch?v=N4efO8viXXo)
**Locator:** 00:25:04.480–00:25:07.110

> These are agents to build AI teammates. These are collaborative AI agents that work collaborative AI agents that work collaborative AI agents that work alongside humans inside Asa projects. […] almost 400 km hour. To show you an example of Claude managed To show you an example of Claude managed To show you an example of Claude managed agents in action, we worked with a agents in action, we worked with a agents in action, we worked with a fictional racing team called Shankiro fictional racing team called Shankiro fictional racing team called Shankiro Racing. […] So the cloud code on the right task. So the work that used to require a human to work that used to require a human to work that used to require a human to manually kick off, routines can take manually kick off, routines can take manually kick off, routines can take care of for you.

### Live evidence 8: `165718deccbb1583956121d4fa860b1a4b9ac47d58c40d5d276d7a93ea4bd934`
**Source:** [Gary Gallagher: American Civil War, Slavery, Lincoln, Grant & Lee | Lex Fridman Podcast #499](https://www.youtube.com/watch?v=XyXBwO5jYpw)
**Locator:** 00:04:59.720–00:05:00.480

> They are much despised even across much of the North because they were seen as agitators who roiled the Union and deepened rifts that might bring a significant political break. - So how did this escalate to a civil war, this almost policy discussion about the institution of slavery? How did it actually escalate? […] The only reason the war lasted as long as it did is because the central government did things no one ever would have believed they would do. He also got rid of habeas corpus just like Abraham Lincoln did in selected situations. […] If you're the farmer who experiences an army coming by and they, they take all, take or kill all your livestock and destroy your crops, and that's, that's pretty much like a total war, even if they don't kill you. - So the war escalates.

