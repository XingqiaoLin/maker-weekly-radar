# Maker Weekly Radar

Maker Weekly Radar is a Codex Skill and Plugin for producing a rigorously sourced weekly Top 15 of physical Maker Projects.

It searches 13 public platforms, preserves raw discoveries for audit, requires direct evidence of a real physical build before time/heat ranking, then takes each platform's strongest five eligible candidates. Five mandatory review gates, three red lines, and a 30-point editorial score determine the final list. Fewer than 15 projects are returned when the evidence is insufficient.

## What Codex can do with it

- Build a global Maker, DIY hardware, or 3D-printing project weekly.
- Collect from Kickstarter, Indiegogo, GitHub, Hackaday, Hackster, Instructables, YouTube, Reddit, X, Instagram, Make Magazine, The Verge, and Tom's Hardware.
- Use public no-key collection where it is reliable, with optional official API providers.
- Avoid per-repository GitHub README API calls, use 29+ verified YouTube channel feeds, cover 20+ Reddit communities through rate-limit-friendly bundles, and use official Kickstarter update feeds when campaign pages are challenged.
- Accept project media plus documented multi-step fabrication as built-result evidence, and verify Reddit heat through Unicode-safe old-page/JSON fallback paths.
- Bound eligibility by the project's first-publication week while observing heat at report execution time, with the real metric capture timestamp preserved.
- Verify public heat metrics instead of treating feed position as popularity.
- Reject old projects even when they were updated, resurfaced, or crossed a heat threshold this week.
- Merge cross-platform duplicates and render at most 15 evidence-backed winners.

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
cp skills/curate-maker-weekly/assets/config.example.json maker-weekly.json
python3 skills/curate-maker-weekly/scripts/maker_weekly.py run \
  --config maker-weekly.json \
  --output-dir output
```

This writes `raw-discoveries.json`, `physical-candidates.json`, `researched.json`, and an explicitly non-publishable raw audit report. Only strict validated selections may become `final.json`.

The collector fails closed when a platform blocks anonymous access or does not expose verifiable metrics. It does not bypass CAPTCHAs, login walls, rate limits, or Cloudflare challenges. See `skills/curate-maker-weekly/references/providers.md` for provider behavior and optional credentials.

`--as-of` is the target publication cutoff. It is not a historical heat cutoff: metrics collected after that date remain eligible when the project's original publication date is inside the target week, and every metric keeps its actual `metrics_captured_at`.

## Validate

```bash
python3 -m unittest discover -s skills/curate-maker-weekly/tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/curate-maker-weekly
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
```

## License

MIT
