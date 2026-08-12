# Maker Weekly Radar

Maker Weekly Radar is a Codex Skill and Plugin for producing a rigorously sourced weekly Top 15 of physical Maker Projects.

It searches up to 13 public platforms, keeps only projects first published in the target natural week, takes each platform's strongest five eligible candidates, verifies platform-specific heat thresholds, applies five mandatory review gates and three red lines, and ranks the survivors on a 30-point editorial score. Fewer than 15 projects are returned when the evidence is insufficient.

## What Codex can do with it

- Build a global Maker, DIY hardware, or 3D-printing project weekly.
- Collect from Kickstarter, Indiegogo, GitHub, Hackaday, Hackster, Instructables, YouTube, Reddit, X, Instagram, Make Magazine, The Verge, and Tom's Hardware.
- Use public no-key collection where it is reliable, with optional official API providers.
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
python3 skills/curate-maker-weekly/scripts/maker_weekly.py collect \
  --config maker-weekly.json \
  --output output/candidates.json
```

The collector fails closed when a platform blocks anonymous access or does not expose verifiable metrics. It does not bypass CAPTCHAs, login walls, rate limits, or Cloudflare challenges. See `skills/curate-maker-weekly/references/providers.md` for provider behavior and optional credentials.

## Validate

```bash
python3 -m unittest discover -s skills/curate-maker-weekly/tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/curate-maker-weekly
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
```

## License

MIT
