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
3. Enforce original publication time before platform ranking. Reject missing dates and every project first published outside the target week, even if it was updated, gained Stars, or recirculated this week.
4. Search every requested platform. Use primary project pages, original posts, original videos, campaign pages, or official platform/editorial pages. Prefer the enabled no-account providers described in `references/providers.md`. For Kickstarter, permit Kicktraq only as URL discovery and require official widget metrics. For Indiegogo, prefer its documented no-key Public API. For configured YouTube and Reddit RSS sources, run bounded public-page detail enrichment before the platform Top 5 cap; otherwise use RSS for discovery only when it lacks heat-gate metrics. Treat `blocked`, `error`, and `skipped` as failed coverage, not as searched platforms.
5. Keep China-mainland platforms, Thingiverse, Printables, MakerWorld, and pure model/material download pages out of the candidate pool.
6. Collect or import candidates. Cap each platform at `top_per_source` only after its own discovery ranking:

   ```bash
   python3 scripts/maker_weekly.py collect --config maker-weekly.json --output output/candidates.json --as-of WEEK_END
   ```

7. Prepare hard-gate and time annotations:

   ```bash
   python3 scripts/strict_weekly.py prepare --input output/candidates.json --output output/researched.json --week-start YYYY-MM-DD --week-end YYYY-MM-DD
   ```

8. Research missing facts and update `researched.json` only with observations backed by primary URLs and capture timestamps. If public heat, creator background, build process, first publication date, physical result, or primary evidence cannot be verified, reject the candidate. Never infer a hidden metric from feed order or general popularity.
9. Optionally save every researched candidate—not only winners—to an audit snapshot. Never use a snapshot to admit an older project:

   ```bash
   python3 scripts/strict_weekly.py snapshot --input output/researched.json --output snapshots/YYYY-MM-DD.json
   ```

10. Apply the five gates and three red lines in order. Stop reviewing a candidate at its first failed mandatory gate. Require at least three of four project-gate dimensions and one concrete excellence comparison.
11. Write compact `decisions.json` for selected projects only. Follow the decision shape in [references/editorial-standard.md](references/editorial-standard.md). Every factual field needs an evidence URL.
12. Merge, validate, sort, and render:

   ```bash
   python3 scripts/strict_weekly.py select --input output/researched.json --decisions output/decisions.json --output output/final.json
   python3 scripts/strict_weekly.py validate --input output/final.json
   python3 scripts/strict_weekly.py render --input output/final.json --output output/maker-weekly.md
   ```

13. Return only the final selected projects, up to 15, plus the required issue statistics. If none pass, publish zero and explain only the aggregate shortfall; do not add rejected projects to the final list.

## Non-negotiable behavior

- Treat physical outcome as mandatory; software, AI, and code may only support the physical build.
- Treat platform heat thresholds as hard gates. Unknown, private, conflicting, or post-window metrics do not pass.
- Permit only `first_release`, backed by an original-page or official-feed timestamp inside the target week. Do not support a breakout category.
- For GitHub, search by repository `created` time. A current-week push, release, Star increase, or README update does not make an old repository eligible.
- For YouTube and Reddit, apply project-intent filters and verified heat gates before selecting the platform Top 5; exclude questions, generic discussions, material tests, and unverifiable metrics.
- Merge cross-platform duplicates and retain all primary evidence links.
- Exclude mature-company official mass-market products, ads, product marketing, pure tutorials, replicas, kit assemblies, routine repairs, concepts, renders, food, and AI-only output.
- Preserve raw candidates and snapshots for audit. Do not rewrite observed metrics during editorial ranking.
- Never bypass Cloudflare, CAPTCHAs, login walls, rate limits, or platform access controls. A public-page collector must fail closed and preserve the source failure status when the page does not expose candidates or metrics.
