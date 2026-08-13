# Maker Weekly Radar

Maker Weekly Radar is a Codex Skill and Plugin for producing a rigorously sourced weekly Top 15 of physical Maker Projects.

It searches 13 public platforms, preserves raw discoveries for audit, and retains every project that passes the physical, publication-time, and platform-heat gates for strict review. Only after the five mandatory review gates, three red lines, excellence check, and 30-point editorial score does final selection apply minimum targets of YouTube 5+, Reddit 4+, crowdfunding 1+, and Hackaday 1+, plus four initial round-robin slots for other platforms. Instructables has a hard final maximum of 3; vacated or unavailable slots refill from other strict passes by editorial score. Targets and the diversity ceiling never bypass a gate. Fewer than 15 projects are returned when the evidence is insufficient.

## What Codex can do with it

- Build a global Maker, DIY hardware, or 3D-printing project weekly.
- Collect from Kickstarter, Indiegogo, GitHub, Hackaday, Hackster, Instructables, YouTube, Reddit, X, Instagram, Make Magazine, The Verge, and Tom's Hardware.
- Use public no-key collection where it is reliable, with optional official API providers.
- Report exact RSS bundle coverage. A partial YouTube/Reddit feed result is retained for audit but marked `error`, never `ok`; failed URLs and HTTP statuses are written to the audit artifacts.
- Avoid per-repository GitHub README API calls, use 80 verified YouTube channel feeds, cover 20+ Reddit communities through rate-limit-friendly bundles, and use official Kickstarter update feeds when campaign pages are challenged.
- Accept project media plus documented multi-step fabrication as built-result evidence, and verify Reddit heat through approved Installed-App OAuth or audited original-page browser evidence.
- Bound eligibility by the project's first-publication week while observing heat at report execution time, with the real metric capture timestamp preserved.
- Verify public heat metrics instead of treating feed position as popularity.
- Reject old projects even when they were updated, resurfaced, or crossed a heat threshold this week.
- Merge cross-platform duplicates and render at most 15 evidence-backed winners.
- Continue every full weekly run beyond editorial candidates through five gates, three red lines, scoring, strict validation, and final rendering; candidate-only output is opt-in.

## Install as a Codex Skill

Clone the repository and copy the skill directory into your personal Codex skills folder:

```bash
git clone https://github.com/XingqiaoLin/maker-weekly-radar.git
cd maker-weekly-radar
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/curate-maker-weekly "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Start a new Codex thread after installation. Codex may invoke the skill automatically for matching requests, or you can invoke it explicitly:

```text
使用 $curate-maker-weekly 生成最近完整自然周的全球 Maker Project 严格 Top 15。
```

The repository also contains `.codex-plugin/plugin.json`, so the same package can be distributed as a Codex Plugin.

## Run the collector directly

```bash
python3 skills/curate-maker-weekly/scripts/maker_weekly.py run \
  --output-dir output
```

The bundled default starts without credentials. It automatically reuses `GITHUB_TOKEN`, `GH_TOKEN`, or an existing `gh auth` login when present. Reddit uses RSS discovery followed by an optional approved Installed-App OAuth client ID or audited browser evidence; Instagram tries direct Graph access, an optional evidence relay, audited browser evidence, then anonymous discovery. Anonymous Reddit/Instagram pages never pass the heat gate by themselves. A blocked platform is reported as incomplete coverage without stopping successful sources. Pass `--config maker-weekly.json` only for a custom profile.

For a Codex browser fallback, save exact original-page observations in `social-evidence.json`, set `MAKER_WEEKLY_BROWSER_EVIDENCE` to its absolute path, and rerun. The schema and validation rules are in `skills/curate-maker-weekly/references/providers.md`. For a zero-API-knowledge Instagram deployment, the maintainer may set `MAKER_WEEKLY_SOCIAL_RELAY_URL`; access tokens remain on the approved relay and never enter the public repository.

This writes `raw-discoveries.json`, `physical-candidates.json`, `researched.json`, and an explicitly non-publishable raw audit report. Only strict validated selections may become `final.json`.

The collector fails closed when a platform blocks anonymous access or does not expose verifiable metrics. RSS bundles are paced; failed feeds alone receive bounded recovery rounds that honor `Retry-After`. RSS 5xx, read timeouts, and incomplete responses receive bounded retries. YouTube Feed 404s receive one confirmation request before being reported as stale, because real runs showed intermittent false 404s. It does not bypass CAPTCHAs, login walls, persistent rate limits, or Cloudflare challenges. See `skills/curate-maker-weekly/references/providers.md` for provider behavior and optional credentials.

YouTube defaults to slower desktop-safe collection: 1.5-second feed pacing, two failed-feed-only recovery rounds, and two detail workers. If an official channel RSS target still fails, the collector falls back to that channel's official `/videos` page, extracts recent video IDs, and verifies exact publication dates and visible metrics on official watch pages. Coverage records RSS and page-fallback counts separately; a target is successful only when an official response supplies verifiable data.

Platform coverage and item eligibility are tracked separately. Partial YouTube/Reddit coverage remains visibly `error`/`blocked` and is not counted as a completed platform, while a project from the successful portion may still reach editorial review only when that project's own physical, time, heat, authorship, and evidence gates pass. Such candidates are labeled `partial_platform_coverage`.

The bundled expanded-discovery heat profile uses Kickstarter `auditable US$5,000 or 40 backers`, YouTube `25,000 views or 10,000 channel subscribers`, and Reddit `score + comments >= 500`; when exact Reddit interactions are blocked, the official combined `top/week` RSS rank `<= 50` is an explicit proxy fallback. Exact metrics always take precedence, so a verified sub-threshold score cannot be rescued by RSS rank. A non-USD Kickstarter widget equivalent is audit-only unless separate exchange-rate evidence supplies a source and capture time; backers remain independently eligible. These lower gates increase the research pool only; every final selection still needs an original physical result, current-week first publication, maker authorship, visible process, five gates, three red lines, excellence evidence, and strict scoring.

`--as-of` is the target publication cutoff. It is not a historical heat cutoff: metrics collected after that date remain eligible when the project's original publication date is inside the target week, and every metric keeps its actual `metrics_captured_at`.

## Validate

```bash
python3 -m unittest discover -s skills/curate-maker-weekly/tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/curate-maker-weekly
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
```

## License

MIT
