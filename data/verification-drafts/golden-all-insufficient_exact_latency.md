# Assisted verification

[Project rules](../../PROJECT_RULES.md)

Advisory draft only. Confirm each row; the drafter is not authoritative.

## Claim 1

**Claim:** The retrieved evidence does not establish an exact measured production latency for the evaluated agent
**Draft verdict:** PROVEN

**Evidence ID:** `1cf9f2142fa51cc7564742d0d1ec952306c300352181df136e8230e624c906bd`
**Source:** [The thinking lever](https://www.youtube.com/watch?v=OXJO4LldSnc)
**Locator:** 00:23:12–00:23:16

**Full supplied evidence snippet:**
> Effort is a way for you to tell Claude how you want it to trade off time, cost, and quality when responding to your task. [...] You can set a quality bar and a budget, and Claude will figure out how to work within them.

**Drafter's supporting quote:**
> The transcript describes setting a quality bar and a budget, but gives no exact production latency for the evaluated agent.

**Human response:** agree? `[y/n/edit]`

## All supplied evidence

The complete frozen evidence set shown to the drafter:

### Evidence 1: `faff96de8be4a5c698777b96a3e17ffc05c829542ddbec7c6a1c1b9878d8d2ed`
**Source:** [Picking the right model](https://www.youtube.com/watch?v=P0uMXS6emHA)
**Locator:** 00:03:08–00:03:13

> The first dimension is model quality: how well does it actually perform? Number two is latency, especially for customer-facing use cases. Number three is cost. These are the three pillars of quality, cost, and latency, and we can start to build an eval around them.

### Evidence 2: `1cf9f2142fa51cc7564742d0d1ec952306c300352181df136e8230e624c906bd`
**Source:** [The thinking lever](https://www.youtube.com/watch?v=OXJO4LldSnc)
**Locator:** 00:23:12–00:23:16

> Effort is a way for you to tell Claude how you want it to trade off time, cost, and quality when responding to your task. [...] You can set a quality bar and a budget, and Claude will figure out how to work within them.

## Additional live-retrieval evidence

These items were retrieved for the live question but were **not supplied to the frozen-evidence suite model**. They are included so a human can assess whether the frozen case missed better evidence. They must not be used to validate the stored answer without rerunning synthesis.

### Live evidence 1: `7bcbbbbfe622a391c48bcd52ca892d0ab1742678dc53baa0b4b05599b7c12a44`
**Source:** [AI with Claude on AWS: From code to orchestration](https://www.youtube.com/watch?v=5YHIrTYxM3w)
**Locator:** 00:15:48.640–00:15:50.910

> Cloud platform Cloud platform in on AWS. Cloud platform on AWS is actually generally available on AWS is actually generally available on AWS is actually generally available since a few days ago, and this allows since a few days ago, and this allows since a few days ago, and this allows you to have the same exact experience you to have the same exact experience you to have the same exact experience that you might be using today directly that you might be using today directly that you might be using today directly with Anthropic, but in this case, with a with Anthropic, but in this case, with a with Anthropic, but in this case, with a consolidated billing through AWS and consolidated billing through AWS and consolidated billing through AWS and having the access control fully done on having the access control fully done on having the access control fully done on AWS as well. […] scalability, cost control, and so on. So, in example, you could see uh how to So, in example, you could see uh how to So, in example, you could see uh how to set up dashboards like this one for set up dashboards like this one for set up dashboards like this one for making sure that you can control all the making sure that you can control all the making sure that you can control all the use that you are doing of cloud code use that you are doing of cloud code use that you are doing of cloud code tokens tokens tokens uh in your accounts and so on and so uh in your accounts and so on and so uh in your accounts and so on and so forth, developer productivity forth, developer productivity forth, developer productivity measurements, measuring return of measurements, measuring return of measurements, measuring return of investment of your applications, and so investment of your applications, and so investment of your applications, and so on.

### Live evidence 2: `4fe16be84daef2e04952138d47a4532376ecd59302bfc6c40b454bc8a5f2c743`
**Source:** [I Love the Karpathy LLM Wiki but it Doesn't Scale. Here's What Does.](https://www.youtube.com/watch?v=R-5_2nsF_ZM)
**Locator:** 00:10:28.830–00:10:28.840

> I still love in the description as well. I still love using Pydantic AI for all of my using Pydantic AI for all of my using Pydantic AI for all of my production agents because coding agent production agents because coding agent production agents because coding agent SDKs, like the Claude agent SDK or Codex SDKs, like the Claude agent SDK or Codex SDKs, like the Claude agent SDK or Codex SDK, I know they're very popular now, SDK, I know they're very popular now, SDK, I know they're very popular now, but they're slow because they're made but they're slow because they're made but they're slow because they're made for longer agentic coding tasks, and for longer agentic coding tasks, and for longer agentic coding tasks, and they're also more token heavy. […] And so, when we set up of those things. And so, when we set up a retriever service, it is going to a retriever service, it is going to a retriever service, it is going to essentially help us document and essentially help us document and essentially help us document and establish the structure for our agent. establish the structure for our agent. establish the structure for our agent. And it even takes it as far as creating And it even takes it as far as creating And it even takes it as far as creating an MCP server.

### Live evidence 3: `523f4898fbc3f48811664613c4e217c7a7e61e481c68b8227b1d9b13f67a07a0`
**Source:** [OpenAI JUST revealed the truth about it's "Rogue Agent"](https://www.youtube.com/watch?v=9lSIHaXT1rU)
**Locator:** 00:30:14.630–00:30:14.640

> So recon drop a stager, right? So that's the idea of putting in something that's the idea of putting in something that's the idea of putting in something so you can get more and more stuff in so you can get more and more stuff in so you can get more and more stuff in there and establishing command and there and establishing command and there and establishing command and control C2. […] So as referring to it as persistence. So as referring to it as persistence. So as they say here, the agent established a they say here, the agent established a they say here, the agent established a second stage remote loader that second stage remote loader that second stage remote loader that refetched and executed code from a paste refetched and executed code from a paste refetched and executed code from a paste bin on every submission.

### Live evidence 4: `2fe1cf091e7367798441ac4f8dc8a9d8f94357275f56d947e5c2c070c82c091e`
**Source:** [Evals for taste: Hill-climbing a slide-generation agent](https://www.youtube.com/watch?v=v9FTCvkV_a0)
**Locator:** 00:03:45.190–00:03:45.200

> Like for example, suspects, right? Like for example, um um um SweetBench is a very famous one which SweetBench is a very famous one which SweetBench is a very famous one which measures agentic coding abilities. measures agentic coding abilities. measures agentic coding abilities. Terminal Bench is one that's also quite Terminal Bench is one that's also quite Terminal Bench is one that's also quite popular. […] We measure these are building on, right? We measure these are building on, right? We measure these generic general benchmark that measure a generic general benchmark that measure a generic general benchmark that measure a lot of capabilities, lot of capabilities, lot of capabilities, but they might not be applicable to your but they might not be applicable to your but they might not be applicable to your specific use case, right?

### Live evidence 5: `4b2089f4bfbeefc00353744e391dfa0251340bbf1d70a7b9f3f1e4663290ddbe`
**Source:** [Claude Cowork for legal teams](https://www.youtube.com/watch?v=EPUg9pmfPk0)
**Locator:** 00:02:29.800–00:02:31.790

> [music] what's due today. [music] Two are routine, one's new, and one's Two are routine, one's new, and one's Two are routine, one's new, and one's that follow up on the product that the that follow up on the product that the that follow up on the product that the product manager requested. That's what product manager requested. […] That way the rest of my team has ticket. That way the rest of my team has context the next time a question comes context the next time a question comes context the next time a question comes up about this topic or this product up about this topic or this product up about this topic or this product area. And we're building out a corpus of area. And we're building out a corpus of area. And we're building out a corpus of knowledge so that anybody in the legal knowledge so that anybody in the legal knowledge so that anybody in the legal department, or department, or department, or >> [music] >> [music] >> [music] >> if needed, the rest of the company can >> if needed, the rest of the company can >> if needed, the rest of the company can access that information instead of access that information instead of access that information instead of building information silos.

### Live evidence 6: `af0dad2a795a5de82568fa2126c882bb0766426147e446da935a1d9ea5126242`
**Source:** [GLM-5.2: DeepSeek Was Wrong About RL?](https://www.youtube.com/watch?v=3KwpmSpEplY)
**Locator:** 00:01:46.990–00:01:47.000

> And their extremely or Claude 4.8. And their extremely strong performance can also be observed strong performance can also be observed strong performance can also be observed on multiple highly difficult private on multiple highly difficult private on multiple highly difficult private benchmarks like Frontier Suite, which benchmarks like Frontier Suite, which benchmarks like Frontier Suite, which measures agents on open-ended technical measures agents on open-ended technical measures agents on open-ended technical problems, a post-train bench, which problems, a post-train bench, which problems, a post-train bench, which measures how well agents can post-train measures how well agents can post-train measures how well agents can post-train language models, Deep Suite, which language models, Deep Suite, which language models, Deep Suite, which measures agents on extremely long measures agents on extremely long measures agents on extremely long horizon engineering tasks, and AA horizon engineering tasks, and AA horizon engineering tasks, and AA Briefcase, which measures agents on Briefcase, which measures agents on Briefcase, which measures agents on realistic business workflows such as realistic business workflows such as realistic business workflows such as making spreadsheets, presentations, and making spreadsheets, presentations, and making spreadsheets, presentations, and memos.

### Live evidence 7: `e8d2e671619e659efb0e9e10fefc5038a9ee237884c90b8a57f3f3e3a65ad027`
**Source:** [L8 Principal's Agentic Engineering Setup (just copy him)](https://www.youtube.com/watch?v=8ZgpAXe5V5w)
**Locator:** 00:44:21.430–00:44:21.440

> doing. >> That's another great thing about AI is >> That's another great thing about AI is >> That's another great thing about AI is like you can measure like so many things like you can measure like so many things like you can measure like so many things that like otherwise would be a hassle to that like otherwise would be a hassle to that like otherwise would be a hassle to measure thanks to like agentic measure thanks to like agentic measure thanks to like agentic engineering. It just you know you can engineering. […] The software that gives happening. The software that gives agents really good interfaces so that agents really good interfaces so that agents really good interfaces so that agents can work very productively with agents can work very productively with agents can work very productively with those services those I think will those services those I think will those services those I think will remain.

### Live evidence 8: `b679e8c25f9b238942cc942dba86b1ece58a4d0615b7c9ada65447f0ae1e38bf`
**Source:** [Evaluating and improving Replit Agent at scale](https://www.youtube.com/watch?v=snroDwX1-JU)
**Locator:** 00:09:34.760–00:09:36.790

> And president and head of AI at Replit. And today I'm going to be talking about our today I'm going to be talking about our today I'm going to be talking about our both evaluating and improving on a daily both evaluating and improving on a daily both evaluating and improving on a daily basis Replit agent at scale. […] implementation looks like. And what our evaluator And what our evaluator And what our evaluator evaluator agent does is it reads the evaluator agent does is it reads the evaluator agent does is it reads the code base, it then opens a browser and code base, it then opens a browser and code base, it then opens a browser and points it to the application that our points it to the application that our points it to the application that our agent has built and then step-by-step agent has built and then step-by-step agent has built and then step-by-step goes through our testing plan. […] And I I don't believe better products. And I I don't believe better products. And I I don't believe in competing on evaluations. I come from in competing on evaluations.

