# Assisted verification

[Project rules](../../PROJECT_RULES.md)

Advisory draft only. Confirm each row; the drafter is not authoritative.

## Claim 1

**Claim:** Evals are useful for helping developers understand whether iterative changes made to an agent actually improve it
**Draft verdict:** NOT_PROVEN

**Evidence ID:** `2fe1cf091e7367798441ac4f8dc8a9d8f94357275f56d947e5c2c070c82c091e`
**Source:** [Evals for taste: Hill-climbing a slide-generation agent](https://www.youtube.com/watch?v=v9FTCvkV_a0)
**Locator:** 00:01:47–00:02:15

**Full supplied evidence snippet:**
> So Evals are systematic tests that measure how well an AI system performs on a specific domain or use case. [...] What’s the quality of the results? What did it do well? What was it not good at? How can we improve? Evals are made up of tasks that define certain scenarios and encode expectations through grading logic.

**Drafter's supporting quote:**
> The transcript discusses what evals are useful for when improving an agent through iterative changes.

**Human response:** agree? `[y/n/edit]`

## All supplied evidence

The complete frozen evidence set shown to the drafter:

### Evidence 1: `2fe1cf091e7367798441ac4f8dc8a9d8f94357275f56d947e5c2c070c82c091e`
**Source:** [Evals for taste: Hill-climbing a slide-generation agent](https://www.youtube.com/watch?v=v9FTCvkV_a0)
**Locator:** 00:01:47–00:02:15

> So Evals are systematic tests that measure how well an AI system performs on a specific domain or use case. [...] What’s the quality of the results? What did it do well? What was it not good at? How can we improve? Evals are made up of tasks that define certain scenarios and encode expectations through grading logic.

## Additional live-retrieval evidence

These items were retrieved for the live question but were **not supplied to the frozen-evidence suite model**. They are included so a human can assess whether the frozen case missed better evidence. They must not be used to validate the stored answer without rerunning synthesis.

### Live evidence 1: `89f0dd7a752aa844c90df8b16a8067a5eb7829b9ce656e29afc4d2ec456669c6`
**Source:** [Grok 4.5 just COOKED Claude and OpenAI](https://www.youtube.com/watch?v=CMjTfpTd-NY)
**Locator:** 00:07:44.870–00:07:44.880

> You can powered business system builder. You can powered business system builder. You can describe what you want to manage and it describe what you want to manage and it describe what you want to manage and it can build the database starter data can build the database starter data can build the database starter data views dashboards and workflows around views dashboards and workflows around views dashboards and workflows around it. […] So if your databases or templates. So if your relationship data is already sitting in relationship data is already sitting in relationship data is already sitting in a spreadsheet or an inbox or another a spreadsheet or an inbox or another a spreadsheet or an inbox or another business tool, the goal is not to business tool, the goal is not to business tool, the goal is not to manually rebuild everything field by manually rebuild everything field by manually rebuild everything field by field. You just describe the system that field. You just describe the system that field. You just describe the system that you want. Bring in the data and refine you want.

### Live evidence 2: `11c5afbe557f59b2e8bbdb7dc084fced2a1d9fda15da0bd997ac71e047e4ac63`
**Source:** [Ship your first Managed Agent](https://www.youtube.com/watch?v=19HDQ9HppOA)
**Locator:** 00:04:43.070–00:04:43.080

> ready agents on Claude. We've seen people build 10 to 15 times We've seen people build 10 to 15 times We've seen people build 10 to 15 times faster to production with Claude managed faster to production with Claude managed faster to production with Claude managed agents by leveraging our purpose-built agents by leveraging our purpose-built agents by leveraging our purpose-built harness. […] So again here to fixing the root cause. So again here for demo purposes, we're stopping at for demo purposes, we're stopping at for demo purposes, we're stopping at just the agent giving us the recommended just the agent giving us the recommended just the agent giving us the recommended actions, but I want you all to imagine actions, but I want you all to imagine actions, but I want you all to imagine the possibilities of where this can go the possibilities of where this can go the possibilities of where this can go if we give our agent more tools, more if we give our agent more tools, more if we give our agent more tools, more ability to take actions, access to your ability to take actions, access to your ability to take actions, access to your code base, ability to put up PRs, code base, ability to put up PRs, code base, ability to put up PRs, ability to fix incidents, so that you as ability to fix incidents, so that you as ability to fix incidents, so that you as a human developer can just become the a human developer can just become the a human developer can just become the oversight and watch over the agents as oversight and watch over the agents as oversight and watch over the agents as they take action, and you no longer have they take action, and you no longer have they take action, and you no longer have to go through and do manual steps like to go through and do manual steps like to go through and do manual steps like actually following the agent's actually following the agent's actually following the agent's instructions here to fix the root cause instructions here to fix the root cause instructions here to fix the root cause of the incident.

### Live evidence 3: `96c492f11d533ebaf909a17d1ec6ffe6b1aadf2a7361b6ac1e44aedbf5ceb7b5`
**Source:** [Tool, skill, or subagent? Decomposing an agent that outgrew its prompt](https://www.youtube.com/watch?v=mWvtOHlZM-I)
**Locator:** 00:02:44.350–00:02:44.360

> I first want to walk you through our problem statement in our through our problem statement in our through our problem statement in our agent. So, for the purposes of this agent. So, for the purposes of this agent. […] So, characteristics of our agent. So, personality and tone and style and personality and tone and style and personality and tone and style and output quality, we're using a output quality, we're using a output quality, we're using a non-deterministic grader as a part of non-deterministic grader as a part of non-deterministic grader as a part of our eval to evaluate our agent's our eval to evaluate our agent's our eval to evaluate our agent's non-deterministic characteristics. […] So, in order to get a set up already. So, in order to get a baseline and run those evals, you have baseline and run those evals, you have baseline and run those evals, you have to run UV run evals \{{}dash} \{{}dash} agent to run UV run evals \{{}dash} \{{}dash} agent to run UV run evals \{{}dash} \{{}dash} agent before. […] Again, this is a a technique if you have evals for your agent. Um again, you have evals for your agent. Um again, you have evals for your agent.

### Live evidence 4: `663b7f29c420196f678d92279fd447bcd77389e80e16c74e206fcfbfa0d46a40`
**Source:** [The thinking lever](https://www.youtube.com/watch?v=T7KqH7kYnE4)
**Locator:** 00:19:45.800–00:19:47.710

> It's probably my favorite eval. eval. eval. This eval is we put Claude into Pokémon This eval is we put Claude into Pokémon This eval is we put Claude into Pokémon Red, and we gave it access to tools to Red, and we gave it access to tools to Red, and we gave it access to tools to trigger buttons on, like, a Gameboy, for trigger buttons on, like, a Gameboy, for trigger buttons on, like, a Gameboy, for example, and we gave it vision over the example, and we gave it vision over the example, and we gave it vision over the game, and we had it execute and try to game, and we had it execute and try to game, and we had it execute and try to beat the Elite Four, which is the beat the Elite Four, which is the beat the Elite Four, which is the objective of Pokémon, if you're not objective of Pokémon, if you're not objective of Pokémon, if you're not familiar. […] You can control that length through the You can control that length through the You can control that length through the effort levels that I described. effort levels that I described. effort levels that I described. Evals are often the best way to find Evals are often the best way to find Evals are often the best way to find your ideal balance.

### Live evidence 5: `1ef7ea308a07ef4355f91fc11363154fa0e3ee81052d80549e2d2ce7992a7430`
**Source:** [Running an AI-native engineering org](https://www.youtube.com/watch?v=IA5LWIGqnyM)
**Locator:** 00:02:10.310–00:02:10.320

> And so I found it's always increasing. And so I found it's always helpful to look at what are either team helpful to look at what are either team helpful to look at what are either team norms that you've set up for your team norms that you've set up for your team norms that you've set up for your team or team processes and always ask or team processes and always ask or team processes and always ask yourself, is it still serving its yourself, is it still serving its yourself, is it still serving its purpose? purpose? […] Or is it still serving its purpose? So, for still serving its purpose? So, for still serving its purpose? […] Again, it's the e- even our team principles and even e- even our team principles and even e- even our team principles and even processes as we put on, even after a few processes as we put on, even after a few processes as we put on, even after a few months when we notice, "Hey, is this months when we notice, "Hey, is this months when we notice, "Hey, is this really serving its intended purpose?" We really serving its intended purpose?" We really serving its intended purpose?"

### Live evidence 6: `7abd810a0066e1bac35fbe9b5cf841acb526c897efb2f10de7ac2fe0788e6940`
**Source:** [Microsoft Just Dropped LLM's Frontier Data Engineering Secrets](https://www.youtube.com/watch?v=aD93kfArOik)
**Locator:** 00:05:28.350–00:05:28.360

> At a small scale, the stem heavy mix. At a small scale, the stem heavy mix looked better on stem stem heavy mix looked better on stem stem heavy mix looked better on stem evals, which is exactly what you would evals, which is exactly what you would evals, which is exactly what you would expect. […] And they even built their own internet. And they even built their own AI content detection model to filter out AI content detection model to filter out AI content detection model to filter out AI slop from the web corpus, too. For AI slop from the web corpus, too. For AI slop from the web corpus, too. For STEM pages, they classify by topic, STEM pages, they classify by topic, STEM pages, they classify by topic, educational value, and education level.

### Live evidence 7: `7425f99a8e5bcc82d14a80b1daae7170ebd25bcd76ab0dedf1757c3776f0dfed`
**Source:** [Code with Claude Tokyo 2026: Opening Keynote](https://www.youtube.com/watch?v=N4efO8viXXo)
**Locator:** 00:22:19.760–00:22:22.070

> product offering. Fable 5 is the best model for building Fable 5 is the best model for building Fable 5 is the best model for building longunning agents, and manage agents is longunning agents, and manage agents is longunning agents, and manage agents is purpose-built for Claude. This means purpose-built for Claude. This means purpose-built for Claude. […] something that can happen today. And we've worked with so many companies And we've worked with so many companies And we've worked with so many companies that have built agentic systems on cloud that have built agentic systems on cloud that have built agentic systems on cloud managed agents. […] And so if memory is called dreaming. And so if memory is real time deciding to write to a file real time deciding to write to a file real time deciding to write to a file system, dreaming allows the agent to system, dreaming allows the agent to system, dreaming allows the agent to look back over all of its past sessions look back over all of its past sessions look back over all of its past sessions and update its memory and its skills so and update its memory and its skills so and update its memory and its skills so that it does even better next time that it does even better next time that it does even better next time around.

### Live evidence 8: `4a1b7429dacdf12b780edda05773f7c042bcceff4d323d0f741b53075ce13681`
**Source:** [Agentic Engineering vs Software Engineering: Beyond Vibe Coding](https://www.youtube.com/watch?v=FgaBdwSvOGM)
**Locator:** 00:05:10.611–00:05:17.075

> So agentic refers to an organization of agents that write the code and the human developer that oversees and validates the output, as the agent or multi-agent system iterates through the subtasks we maintain a human in the loop. Engineering, on the other hand, describes a level of expertise required to use agentic workflows for a meaningful code production that doesn't jeopardize the code quality. […] And finally, we have agentic engineering, which expands beyond code generation entirely. Here, engineers are not just building software, but describing environments and designing them in which autonomous systems can reason, coordinate, evaluate outcomes, and adapt dynamically under constraints. […] And importantly, this is not about removing humans from the loop. In fact, one of the biggest misconceptions around agentic systems is the idea that they eliminate the need for engineering expertise. […] You think about it, if there's a bug, you can often trace it directly to a faulty condition, state transition, or implementation detail. Agentic systems are different.

