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
4. Run the Make Something Gate on every raw discovery before time, heat, keywords, or platform Top 5. Require all four facts: the creator made/modified/built a physical object; it is the core result; the page directly shows a built result or substantive prototype; and the page directly shows human design, fabrication, assembly, testing, or iteration. Require at least one original-page photo, video, process, test, structure/material/electronics, or iteration URL. A title, tag, topic, or the words hardware/robot/AI/3D are never evidence. Fail closed with `physical_gate.status = "fail"` and `rejection_reason = "未找到真实物理造物证据"`.
5. Keep China-mainland platforms, Thingiverse, Printables, MakerWorld, and pure model/material download pages out of the candidate pool.
6. Run the four-stage pipeline. It writes raw audit data, Make Something Gate passes, and physical+time+heat platform Top 5 candidates separately:

   ```bash
   python3 scripts/maker_weekly.py run --config maker-weekly.json --output-dir output --as-of WEEK_END
   ```

   The artifacts are `raw-discoveries.json`, `physical-candidates.json`, `researched.json`, and `raw-discoveries-audit.md`. The audit Markdown must be titled `原始发现审计报告（不可发布）`; never call it a weekly report, Top list, or selected project list.

7. Prepare the editorial candidates for strict review:

   ```bash
   python3 scripts/strict_weekly.py prepare --input output/researched.json --output output/researched-strict.json --week-start YYYY-MM-DD --week-end YYYY-MM-DD
   ```

8. Research missing facts and update `researched.json` only with observations backed by primary URLs and capture timestamps. If public heat, creator background, build process, first publication date, physical result, or primary evidence cannot be verified, reject the candidate. Never infer a hidden metric from feed order or general popularity.
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

## Non-negotiable behavior

- Treat physical outcome as mandatory; software, AI, and code may only support the physical build.
- Treat platform heat thresholds as hard gates. Unknown, private, conflicting, or post-window metrics do not pass.
- Permit only `first_release`, backed by an original-page or official-feed timestamp inside the target week. Do not support a breakout category.
- For GitHub, search by repository `created` time. A current-week push, release, Star increase, or README update does not make an old repository eligible.
- For YouTube and Reddit, discover broadly from the default RSS bundles and verify bounded public detail pages. Do not narrow raw discovery with title-only Maker patterns. The Make Something, time, and verified heat gates remove nonprojects before selecting the platform Top 5.
- Keep Kickstarter enabled in the formal default. Kicktraq may discover official campaign URLs, but only the official Kickstarter widget may supply launch and heat metrics.
- Preserve the exact stage order: platform fetch → raw audit → Make Something Gate → time gate → heat gate → platform Top 5 → cross-platform deduplication → five gates and three red lines → final Top 15.
- Merge cross-platform duplicates and retain all primary evidence links.
- Exclude mature-company official mass-market products, ads, product marketing, pure tutorials, replicas, kit assemblies, routine repairs, concepts, renders, food, and AI-only output.
- Preserve raw discoveries and snapshots for audit. Do not rewrite observed metrics during editorial ranking. Never render raw discoveries through the final report renderer.
- Never bypass Cloudflare, CAPTCHAs, login walls, rate limits, or platform access controls. A public-page collector must fail closed and preserve the source failure status when the page does not expose candidates or metrics.
