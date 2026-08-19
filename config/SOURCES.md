# Followed Sources

[Project rules](../PROJECT_RULES.md)

Edit this table by hand. Use the handle exactly as shown by the platform. Leave
`Subscribed` and `Since` empty when they are not configured.

Storage folders are derived automatically:

- YouTube: `source/youtube/<handle-without-@>`
- X: `source/x/<handle-without-@>`

Each YouTube video is stored as `videos/YYYYMMDD_<content-id>` and each X post as
`posts/YYYYMMDD_<content-id>`,
where `YYYYMMDD` is the original publication/creation date, not the download date.

The daily library-update worker reads this manifest deterministically. It uses
the global ingestion window in `config/PARAMETERS.json`, skips terminal local
content, and refreshes the evidence index after ingestion. No prompt or model
is used to decide which subscribed posts or videos are downloaded.

| Platform | Name | Handle | Category | Subscribed | Since |
|---|---|---|---|---|---|---|
| youtube | Claude (Anthropic) | @claude | official_lab |  |  |
| youtube | Anthropic | @anthropic-ai | official_lab |  |  |
| youtube | OpenAI | @OpenAI | official_lab |  |  |
| youtube | Google DeepMind | @GoogleDeepMind | official_lab |  |  |
| youtube | Google for Developers | @GoogleDevelopers | official_lab |  |  |
| youtube | Google | @Google | official_lab |  |  |
| youtube | Microsoft Developer | @MicrosoftDeveloper | official_lab |  |  |
| youtube | Microsoft | @Microsoft | official_lab |  |  |
| youtube | IBM Technology | @IBMTechnology | official_lab |  |  |
| youtube | AI Explained | @aiexplained-official | ai_news_analysis |  |  |
| youtube | Matt Wolfe | @mreflow | ai_news_analysis |  |  |
| youtube | Wes Roth | @WesRoth | ai_news_analysis |  |  |
| youtube | Matthew Berman | @matthew_berman | ai_news_analysis |  |  |
| youtube | Two Minute Papers | @TwoMinutePapers | ai_news_analysis |  |  |
| youtube | bycloud | @bycloudAI | ai_news_analysis |  |  |
| youtube | Lex Fridman | @lexfridman | ai_news_analysis |  |  |
| youtube | Cole Medin | @ColeMedin | hands_on_builders |  |  |
| youtube | Sam Witteveen | @samwitteveenai | hands_on_builders |  |  |
| youtube | Fireship | @Fireship | hands_on_builders |  |  |
| youtube | Andrej Karpathy | @AndrejKarpathy | hands_on_builders |  |  |
| youtube | David Ondrej | @DavidOndrej | hands_on_builders |  |  |
| x | Anthropic | @AnthropicAI | official_lab | Y | 2026-07-12T08:00:00+00:00 |
| x | Claude | @claudeai | official_lab | Y | 2026-07-12T08:00:00+00:00 |
| x | Claude Developers | @ClaudeDevs | official_lab | Y | 2026-07-12T08:00:00+00:00 |
| x | Claude Code | @claude_code | official_lab | Y | 2026-07-12T08:00:00+00:00 |
| x | Boris Cherny | @bcherny | engineers | Y | 2026-07-12T08:00:00+00:00 |
| x | Thariq | @trq212 | engineers | Y | 2026-07-12T08:00:00+00:00 |
| x | Cat Wu | @_catwu | engineers | Y | 2026-07-12T08:00:00+00:00 |
| x | zodchiii | @zodchiii | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | hanakoxbt | @hanakoxbt | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | mikenevermiss | @mikenevermiss | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | eng_khairallah1 | @eng_khairallah1 | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | Prajwal Tomar | @PrajwalTomar_ | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | rdominguezibar | @rdominguezibar | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | Av1dlive | @Av1dlive | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | 0xDepressionn | @0xDepressionn | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | Mario Nawfal | @MarioNawfal | clippers | Y | 2026-07-12T08:00:00+00:00 |
| x | Rowan Cheung | @rowancheung | ai_news_analysis | Y | 2026-07-12T12:00:00+00:00 |
| x | Nick Dobos | @NickADobos | ai_news_analysis | Y | 2026-07-12T12:00:00+00:00 |
| x | Testing Catalog | @testingcatalog | ai_news_analysis | Y | 2026-07-12T12:00:00+00:00 |
| x | Wes Roth | @WesRoth | ai_news_analysis | Y | 2026-07-12T12:00:00+00:00 |
| x | Akhil Pachori | @akhilpachori | ai_news_analysis | Y | 2026-07-12T12:00:00+00:00 |
| x | Akif Malik | @akifmalik | ai_news_analysis | Y | 2026-07-12T12:00:00+00:00 |
| x | Google | @Google | official_lab | Y | 2026-07-12T13:20:00+00:00 |
| x | Gemini App | @GeminiApp | official_lab | Y | 2026-07-12T13:20:00+00:00 |
| x | Google Developers | @googledevs | official_lab | Y | 2026-07-12T13:20:00+00:00 |
| x | Microsoft | @Microsoft | official_lab | Y | 2026-07-12T13:20:00+00:00 |
| x | Microsoft Developer | @msdev | official_lab | Y | 2026-07-12T13:20:00+00:00 |
| x | Satya Nadella | @satyanadella | official_lab | Y | 2026-07-12T13:20:00+00:00 |
| x | Mustafa Suleyman | @mustafasuleyman | official_lab | Y | 2026-07-12T13:20:00+00:00 |
| x | Tom Warren | @tomwarren | ai_news_analysis | Y | 2026-07-12T13:20:00+00:00 |
| x | OpenAI | @OpenAI | official_lab | Y | 2026-07-12T15:30:00+00:00 |
| x | Sam Altman | @sama | official_lab | Y | 2026-07-12T15:30:00+00:00 |
| x | Tibor Blaho | @btibor91 | official_lab | Y | 2026-07-12T15:30:00+00:00 |
| x | Greg Brockman | @gdb | official_lab | Y | 2026-07-12T15:30:00+00:00 |
| x | OpenAI Developers | @OpenAIDevs | official_lab | Y | 2026-07-12T15:30:00+00:00 |
| x | Kevin Weil | @kevinweil | official_lab | Y | 2026-07-12T15:30:00+00:00 |
| x | Andrej Karpathy | @karpathy | hands_on_builders | Y | 2026-07-12T15:30:00+00:00 |
| x | François Chollet | @fchollet | hands_on_builders | Y | 2026-07-12T15:30:00+00:00 |
| x | Lee Robinson | @leerob | hands_on_builders | Y | 2026-07-12T15:30:00+00:00 |
| x | Eric Zakariasson | @ericzakariasson | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | Peter Steinberger | @steipete | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | Greg Isenberg | @gregisenberg | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | Riley Brown | @rileybrown | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | Jack Friks | @jackfriks | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | AI Highlight | @AIHighlight | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | swyx | @swyx | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | Sebastian Raschka | @rasbt | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |
| x | Lex Fridman | @lexfridman | hands_on_builders | Y | 2026-07-12T17:00:00+00:00 |

X ingestion currently uses the official API, the global three-day test window, and
the global `x.include_replies` / `x.include_retweets` settings. There is no
keyword or topic filtering. Public accounts use `X_API_BEARER_TOKEN`. Protected
accounts can use `X_API_USER_ACCESS_TOKEN`, an OAuth user-context token belonging
to an X account that follows the protected source. The adapter retries only the
specific resource-authorization error with that token; it does not use browser
cookies or store tokens locally.
Media is stored under each post as `media/`; direct linked documents with a
document extension are stored under `documents/`; X Article metadata is stored
as `article.json`. Existing post records can be enriched with
`scripts/maintenance_backfill_x_post_assets.py`; use `--handle` and `--limit` for a bounded test
before backfilling the complete local archive. Video attachments are converted
to temporary audio and transcribed with the global Whisper script; successful
transcripts are stored under `transcripts/`, and interrupted or failed
transcriptions are retried on the next run. Short videos without usable audio
are retained with screenshots under `screenshots/` and recorded as warnings.
