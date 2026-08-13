---
name: curate-maker-weekly
description: Research, verify, and globally rank up to 15 physical Maker Projects first published within one complete natural week, using platform-specific popularity thresholds, five mandatory review gates, three red lines, evidence discipline, and a 30-point editorial score. Use automatically when asked for Maker 周报、创客周报、3D 打印项目周报, a global maker or DIY hardware radar, no-API public collection, crowdfunding/social/news aggregation, cross-platform Top 15, strict current-week publication checks, candidate eligibility auditing, or evidence-backed physical-project research across Kickstarter, Indiegogo, GitHub, Hackaday, Hackster, Instructables, YouTube, Reddit, X, Instagram, Make, The Verge, and Tom's Hardware.
---

# Curate Maker Weekly

Apply the user's strict definition: a Maker Project must be a real physical creation led by an individual or small team, with visible original work, meaningful process, challenges, and a built result or verifiable substantive progress. Prefer fewer winners over weak evidence.

## Required references

Read [references/editorial-standard.md](references/editorial-standard.md) completely before researching or judging a weekly issue. Read [references/providers.md](references/providers.md) when configuring collection or credentials.

## Workflow

1. Determine the most recent complete Monday–Sunday week unless the user supplies explicit dates:

   ```bash
   python3 scripts/strict_weekly.py window
   ```

2. State the week start, week end, execution date, and timezone before research. Never treat a partial current week as complete.
3. Search all 13 configured platforms and save every bounded fetch result as `raw discoveries`. Raw discoveries are audit data, never Maker candidates. Treat only `ok` and `empty` as completed searches; `blocked`, `error`, and `skipped` are incomplete coverage. If YouTube or Reddit is not completed, show `本期平台覆盖不完整：YouTube/Reddit 未检索` prominently.
   For bundled RSS sources, require every configured feed to fetch and parse before reporting `ok` or `empty`. Preserve per-feed success/failure diagnostics. Any partial feed failure makes the source `error` while retaining discoveries from successful feeds. Never infer complete platform coverage from one successful feed or one returned item.
   Start with the bundled zero-credential profile. Do not ask the user to create API keys, client IDs, or tokens before the first run. Existing environment credentials and an existing `gh auth` login are optional transparent enhancements; never require them for the other platforms to continue.
4. Run the Make Something Gate on every raw discovery before time, heat, or global candidate ranking. Require all four facts: the creator made/modified/built a physical object; it is the core result; the page directly shows a built result or substantive prototype; and the page directly shows human design, fabrication, assembly, testing, or iteration. Require at least one original-page photo, video, process, test, structure/material/electronics, or iteration URL. A title, tag, topic, or the words hardware/robot/AI/3D are never evidence. Fail closed with `physical_gate.status = "fail"` and `rejection_reason = "未找到真实物理造物证据"`.
   Treat a substantive project photo/video plus at least two structured build steps or multiple concrete process signals as direct built-result evidence; do not additionally require English completion words such as `finished` or `working`.
   On editorial/news platforms, require the article title or summary itself to identify a specific physical build and making action. Never use navigation, related-story, recipe, buying-guide, or footer text as physical evidence. A media report may pass this prefilter, but the final necessary-conditions gate still requires original-maker attribution and evidence.
5. Keep China-mainland platforms, Thingiverse, Printables, MakerWorld, and pure model/material download pages out of the candidate pool.
6. Run the four-stage pipeline. It writes raw audit data, Make Something Gate passes, and the complete physical+time+heat research pool separately. Do not cap this pool at 15 and do not apply platform targets yet:

   ```bash
   python3 scripts/maker_weekly.py run --output-dir output --as-of WEEK_END
   ```

   The artifacts are `raw-discoveries.json`, `physical-candidates.json`, `researched.json`, and `raw-discoveries-audit.md`. The audit Markdown must be titled `原始发现审计报告（不可发布）`; never call it a weekly report, Top list, or selected project list.

7. Prepare the editorial candidates for strict review:

   ```bash
   python3 scripts/strict_weekly.py prepare --input output/researched.json --output output/researched-strict.json --week-start YYYY-MM-DD --week-end YYYY-MM-DD
   ```

8. Research missing facts and update `researched.json` only with observations backed by primary URLs and capture timestamps. If public heat, creator background, build process, first publication date, physical result, or primary evidence cannot be verified, reject the candidate. Never infer a hidden metric from feed order or general popularity.
   Treat the issue end/`--as-of` value only as the publication-window cutoff. Heat may be observed when the issue is executed after the week ends; preserve the real `metrics_captured_at` and label it as an execution-time observation. Never rewrite it as a historical week-end metric.
   For Reddit and Instagram, use this automatic evidence order: approved official access (Reddit Installed-App OAuth or Instagram Graph/relay), then one bounded Codex browser pass. When the browser exposes exact original-platform metrics, write `output/social-evidence.json` using the schema in [references/providers.md](references/providers.md), set `MAKER_WEEKLY_BROWSER_EVIDENCE` to its absolute path, and rerun collection. Never copy a search-result estimate into this file. For Reddit only, if exact interactions remain hidden, the default may use the official combined `top/week` RSS rank `<= 50` as an explicitly labeled proxy; do not claim or infer a score. Instagram remains blocked when exact metrics are hidden.
9. Optionally save every researched candidate—not only winners—to an audit snapshot. Never use a snapshot to admit an older project:

   ```bash
   python3 scripts/strict_weekly.py snapshot --input output/researched-strict.json --output snapshots/YYYY-MM-DD.json
   ```

10. Apply the five gates and three red lines in order to every project in the complete research pool. Stop reviewing a candidate at its first failed mandatory gate. Require at least three of four project-gate dimensions and one concrete excellence comparison, then score every all-gates-passed project on all six dimensions.
11. Write compact `decisions.json` that covers the complete research pool: put every project that passed the five gates, three red lines, excellence check, and scoring in `items`, and every failure in `rejections` with its first failed stage, concrete reason, and primary evidence URL. Do not review only the anticipated final 15. Follow the decision shape in [references/editorial-standard.md](references/editorial-standard.md); the selector rejects incomplete coverage.
12. Merge the complete strict-pass set, then apply the final source mix: YouTube 5+, Reddit 4+, crowdfunding (Kickstarter + Indiegogo) 1+, Hackaday 1+, and four initial round-robin slots for the other platforms. Refill missing or remaining slots by strict editorial score; every group may exceed its minimum. Validate, sort, and render:

   ```bash
   python3 scripts/strict_weekly.py select --input output/researched-strict.json --decisions output/decisions.json --output output/final.json
   python3 scripts/strict_weekly.py validate --input output/final.json
   python3 scripts/strict_weekly.py render --input output/final.json --output output/maker-weekly.md
   ```

13. Return only the final selected projects, up to 15, plus the required issue statistics. If none pass, publish zero and explain only the aggregate shortfall; do not add rejected projects to the final list.

Platform coverage and item eligibility are separate. Keep `error`/`blocked` out of the completed-platform count and show the coverage warning, but do not reject a discovered item solely because another feed or item from the same platform failed. A YouTube item from a successful feed may proceed when its own original publication, physical evidence, visible metrics, and all later gates pass. A Reddit item may proceed through exact heat or the labeled official weekly-RSS proxy. Mark such items `source_coverage.scope=partial_platform_coverage` so the final report cannot imply complete platform search.

## Completion contract

- Treat `researched.json` and `researched-strict.json` as intermediate candidate artifacts, never as completion of a full weekly issue request.
- When at least one editorial candidate exists, continue in the same task through primary-page research, five gates, three red lines, excellence comparison, six-dimension scoring, strict selection, validation, and final rendering. Stop at candidates only when the user explicitly asks for collection, triage, or candidate output without final review.
- Verify that the page author is the actual maker during the necessary-conditions gate. If a video or article says another person or team made the project, reject it as a third-party review/demo unless it can be merged with an eligible original-creator page whose first publication and platform heat both satisfy the issue rules.
- Do not score a candidate after any mandatory gate or red line fails. Keep rejection reasons in an editorial audit artifact, but never render rejected candidates in the publishable report.
- A full weekly task is complete only after `decisions.json`, validated `final.json`, and the rendered weekly Markdown exist, including when the valid final count is zero.

## Non-negotiable behavior

- Treat physical outcome as mandatory; software, AI, and code may only support the physical build.
- Treat platform heat thresholds as hard gates. Unknown, private, or conflicting metrics do not pass. A real public metric observed after the target week may pass when the project itself was first published inside the target week; record its actual capture time and do not claim it was the week-end value.
- Use the expanded default for the three requested platforms: Kickstarter auditable US$5,000 or 40 backers; YouTube 25,000 views or 10,000 channel subscribers; Reddit score plus comments 500, falling back to rank 1–50 of the single official combined `top/week` RSS only when exact interactions are unavailable. Label this `reddit_weekly_rss_rank`, preserve `exact_score_available=false`, and never translate rank into a score. If exact metrics exist, they take precedence and a sub-threshold score fails regardless of RSS rank. For Kickstarter, admit the amount path only when the campaign currency is USD, or when an explicit conversion object has `status=verified`, `admissible_for_heat_gate=true`, matching source/target currencies, source amount, rate, converted USD, a source URL, and a capture timestamp; verify the arithmetic before admitting it. Preserve an official-widget USD equivalent from a non-USD campaign as `reported_usd_pledged` with an unverified conversion record; never use it for the amount gate or ranking. Backer count remains independently eligible. Treat these as candidate-pool gates only and keep every later editorial gate unchanged.
- Permit only `first_release`, backed by an original-page or official-feed timestamp inside the target week. Do not support a breakout category.
- For GitHub, search by repository `created` time. A current-week push, release, Star increase, or README update does not make an old repository eligible.
- For GitHub, reuse the search result's default branch and retrieve README build evidence from raw content URLs; do not spend one GitHub REST request per repository.
- For YouTube and Reddit, discover broadly from the default RSS bundles (at least 80 verified channels and 20 communities). Preserve Reddit RSS text, author, media, the exact combined-feed position, and the feed URL. Prefer approved Installed-App OAuth or audited browser evidence for Reddit heat; otherwise admit only official combined weekly RSS ranks 1–50 as proxy heat, never as a passing score. Keep the legacy Unicode-safe public-page/JSON enrichment available only for custom diagnostic profiles. Do not narrow raw discovery with title-only Maker patterns.
- Record `successful_feeds`, `total_feeds`, every failed feed URL, failure category, and HTTP status for RSS bundles. Retry transient HTTP 500/502/503/504, read timeouts, and incomplete response bodies at most twice after the initial attempt. Recheck a YouTube channel Feed once after an initial 404 because the service can return transient false 404s; classify a repeated 404 as missing. Do not retry ordinary 404s. Treat any partial discovery or metric-detail failure as incomplete coverage, even when usable candidates were preserved.
- Pace bundled social feeds, honor bounded `Retry-After`, then retry only failed feeds in one or two recovery rounds. Keep YouTube detail enrichment at low concurrency and Reddit at lower concurrency. Record recovery rounds and recovered feed counts. Never turn an unrecovered partial run into `ok`.
- For YouTube, use the desktop-safe default pacing and two recovery rounds. After RSS recovery is exhausted, fall back only to the same channel's official `/videos` page; extract bounded recent video IDs, then require exact publication dates and visible metrics from official watch pages. Reuse watch-page observations within the run. Record `rss_successful_feeds`, `page_fallback_attempted`, and `page_fallback_succeeded`; describe mixed recovery as discovery-target success, not RSS success.
- Keep Kickstarter enabled in the formal default. Kicktraq may discover official campaign URLs, but only the official Kickstarter widget may supply launch and heat metrics. Persist successful official-widget observations and reuse them only for the same issue when a later fetch is temporarily blocked, retaining the original capture time and cache provenance; use the official project `posts.atom` feed as a fallback for physical build/process evidence.
- Preserve the exact stage order: platform fetch → raw audit → Make Something Gate → time gate → heat gate → complete cross-platform research pool → five gates → three red lines → excellence check → six-dimension scoring → final 5+/4+/1+/1+ source mix → final Top 15. Never apply source targets or a Top-15 cap before strict editorial review. Final source targets never bypass a gate; unavailable slots refill by strict editorial score.
- Merge cross-platform duplicates and retain all primary evidence links.
- Exclude mature-company official mass-market products, ads, product marketing, pure tutorials, replicas, kit assemblies, routine repairs, concepts, renders, food, and AI-only output.
- Preserve raw discoveries and snapshots for audit. Do not rewrite observed metrics during editorial ranking. Never render raw discoveries through the final report renderer.
- Never describe editorial candidates as final selections or end a full weekly issue at the candidate stage.
- Never bypass Cloudflare, CAPTCHAs, login walls, rate limits, or platform access controls. A public-page collector must fail closed and preserve the source failure status when the page does not expose candidates or metrics.
- Keep zero-credential execution useful: isolate every provider failure, never abort the other sources, reuse an existing GitHub CLI login without printing its token, and treat Reddit/X/Instagram OAuth as optional enhancement paths rather than prerequisites. A missing official or browser evidence path must become `blocked`, not a zero metric.
