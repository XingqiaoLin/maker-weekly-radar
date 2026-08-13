---
name: curate-maker-weekly
description: Research, verify, and rank up to 15 global physical Maker Projects first published within one complete natural week, using platform-specific popularity thresholds, five mandatory review gates, three red lines, evidence discipline, and a 30-point editorial score. Use automatically when asked for Maker 周报、创客周报、3D 打印项目周报, a global maker or DIY hardware radar, no-API public collection, crowdfunding/social/news aggregation, per-platform Top 5 followed by a cross-platform Top 15, strict current-week publication checks, candidate eligibility auditing, or evidence-backed physical-project research across Kickstarter, Indiegogo, GitHub, Hackaday, Hackster, Instructables, YouTube, Reddit, X, Instagram, Make, The Verge, and Tom's Hardware.
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
   Start with the bundled zero-credential profile. Do not ask the user to create API keys, client IDs, or tokens before the first run. Existing environment credentials and an existing `gh auth` login are optional transparent enhancements; never require them for the other platforms to continue.
4. Run the Make Something Gate on every raw discovery before time, heat, keywords, or platform Top 5. Require all four facts: the creator made/modified/built a physical object; it is the core result; the page directly shows a built result or substantive prototype; and the page directly shows human design, fabrication, assembly, testing, or iteration. Require at least one original-page photo, video, process, test, structure/material/electronics, or iteration URL. A title, tag, topic, or the words hardware/robot/AI/3D are never evidence. Fail closed with `physical_gate.status = "fail"` and `rejection_reason = "未找到真实物理造物证据"`.
   Treat a substantive project photo/video plus at least two structured build steps or multiple concrete process signals as direct built-result evidence; do not additionally require English completion words such as `finished` or `working`.
5. Keep China-mainland platforms, Thingiverse, Printables, MakerWorld, and pure model/material download pages out of the candidate pool.
6. Run the four-stage pipeline. It writes raw audit data, Make Something Gate passes, and physical+time+heat platform Top 5 candidates separately:

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
   When a zero-credential collector reports `blocked` or `error`, keep the completed sources and perform one bounded Codex web/browser research pass for that platform when such a tool is available. Use search only for discovery; admit an item only after its original platform page exposes the exact publication time, heat metric, creator, and physical evidence. If any required fact remains hidden, preserve the platform failure and reject the item rather than asking the user for developer credentials.
9. Optionally save every researched candidate—not only winners—to an audit snapshot. Never use a snapshot to admit an older project:

   ```bash
   python3 scripts/strict_weekly.py snapshot --input output/researched-strict.json --output snapshots/YYYY-MM-DD.json
   ```

10. Apply the five gates and three red lines in order. Stop reviewing a candidate at its first failed mandatory gate. Require at least three of four project-gate dimensions and one concrete excellence comparison.
11. Write compact `decisions.json` for selected projects only. Follow the decision shape in [references/editorial-standard.md](references/editorial-standard.md). Every factual field needs an evidence URL.
12. Merge, validate, sort, and render:

   ```bash
   python3 scripts/strict_weekly.py select --input output/researched-strict.json --decisions output/decisions.json --output output/final.json
   python3 scripts/strict_weekly.py validate --input output/final.json
   python3 scripts/strict_weekly.py render --input output/final.json --output output/maker-weekly.md
   ```

13. Return only the final selected projects, up to 15, plus the required issue statistics. If none pass, publish zero and explain only the aggregate shortfall; do not add rejected projects to the final list.

## Completion contract

- Treat `researched.json` and `researched-strict.json` as intermediate candidate artifacts, never as completion of a full weekly issue request.
- When at least one editorial candidate exists, continue in the same task through primary-page research, five gates, three red lines, excellence comparison, six-dimension scoring, strict selection, validation, and final rendering. Stop at candidates only when the user explicitly asks for collection, triage, or candidate output without final review.
- Verify that the page author is the actual maker during the necessary-conditions gate. If a video or article says another person or team made the project, reject it as a third-party review/demo unless it can be merged with an eligible original-creator page whose first publication and platform heat both satisfy the issue rules.
- Do not score a candidate after any mandatory gate or red line fails. Keep rejection reasons in an editorial audit artifact, but never render rejected candidates in the publishable report.
- A full weekly task is complete only after `decisions.json`, validated `final.json`, and the rendered weekly Markdown exist, including when the valid final count is zero.

## Non-negotiable behavior

- Treat physical outcome as mandatory; software, AI, and code may only support the physical build.
- Treat platform heat thresholds as hard gates. Unknown, private, or conflicting metrics do not pass. A real public metric observed after the target week may pass when the project itself was first published inside the target week; record its actual capture time and do not claim it was the week-end value.
- Use the expanded verified default for the three requested platforms: Kickstarter US$5,000 or 50 backers; YouTube 25,000 views or 10,000 channel subscribers; Reddit score plus comments 500. Treat these as candidate-pool gates only and keep every later editorial gate unchanged.
- Permit only `first_release`, backed by an original-page or official-feed timestamp inside the target week. Do not support a breakout category.
- For GitHub, search by repository `created` time. A current-week push, release, Star increase, or README update does not make an old repository eligible.
- For GitHub, reuse the search result's default branch and retrieve README build evidence from raw content URLs; do not spend one GitHub REST request per repository.
- For YouTube and Reddit, discover broadly from the default RSS bundles (at least 29 verified channels and 20 communities) and verify bounded public detail pages. Preserve Reddit RSS text, author, and media. Percent-encode Unicode Reddit paths, try the public old-Reddit page first, then try the canonical, old-host, short-comments, and public API JSON representations when score or comments are incomplete. Do not narrow raw discovery with title-only Maker patterns.
- Keep Kickstarter enabled in the formal default. Kicktraq may discover official campaign URLs, but only the official Kickstarter widget may supply launch and heat metrics; use the official project `posts.atom` feed as a fallback for physical build/process evidence.
- Preserve the exact stage order: platform fetch → raw audit → Make Something Gate → time gate → heat gate → platform Top 5 → cross-platform deduplication → five gates and three red lines → final Top 15.
- Merge cross-platform duplicates and retain all primary evidence links.
- Exclude mature-company official mass-market products, ads, product marketing, pure tutorials, replicas, kit assemblies, routine repairs, concepts, renders, food, and AI-only output.
- Preserve raw discoveries and snapshots for audit. Do not rewrite observed metrics during editorial ranking. Never render raw discoveries through the final report renderer.
- Never describe editorial candidates as final selections or end a full weekly issue at the candidate stage.
- Never bypass Cloudflare, CAPTCHAs, login walls, rate limits, or platform access controls. A public-page collector must fail closed and preserve the source failure status when the page does not expose candidates or metrics.
- Keep zero-credential execution useful: isolate every provider failure, never abort the other sources, reuse an existing GitHub CLI login without printing its token, and treat Reddit/X/Instagram OAuth as optional enhancement paths rather than prerequisites.
