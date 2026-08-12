# Provider configuration

## Core behavior

Every enabled `sources[]` entry is an independent platform source and contributes at most `top_per_source` discovery candidates. Use one bundled source for multiple channels or subreddits when they share one platform-level Top 5. All lookbacks are calculated in UTC from `--as-of` or the current time.

Credentials are read only from environment variables named in the config. The collector records missing credentials as `skipped` and continues with other sources.

## Provider types

### `github`

Use GitHub's repository search API. `GITHUB_TOKEN` is optional but recommended for higher rate limits. Configure `queries` as several narrow searches and set `date_qualifier` to `created`, `pushed`, or `updated`. The collector merges results and keeps only repositories whose visible name, description, or topics match `required_terms`. A repository is only a discovery candidate until its physical core, 1,000-Star heat gate, creator, build process, and actual result are verified.

### `youtube`

Use YouTube Data API v3 `search.list`, followed by `videos.list` for public statistics. Set `YOUTUBE_API_KEY`. API mode supplies video views but the current collector does not supply channel subscriber counts; verify the channel threshold separately when a video is below 200,000 views.

### `reddit`

Use Reddit OAuth client credentials and the authenticated `/top` listing. Set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`, use a truthful `user_agent`, and obtain approval for the intended Data API use. This remains the broadest discovery mode. The no-account RSS mode described below can verify a bounded shortlist on public old-Reddit post pages without bypassing a challenge.

### `instagram`

Use the Instagram Graph API hashtag discovery and top-media endpoints. Set `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_USER_ID`. Access depends on account type, permissions, API version, and Meta review status. If access is unavailable, use an authorized `manual` export.

### `kickstarter_kicktraq`

Use public Kicktraq category pages only to discover Kickstarter project slugs. Interleave configured categories, bound the detail pool with `detail_candidate_limit`, then fetch each project's official Kickstarter `widget/card.html?v=2` page. Record launch time, creator, USD-equivalent pledged amount, backers, state, category, and deadline only from the official widget. Rank within Kickstarter by `usd_pledged/20000 + backers/200`. Keep both the original Kickstarter URL and the widget URL as primary evidence; retain Kicktraq only as discovery provenance. If the official widget fails, do not create a candidate from Kicktraq's copied metrics.

### `indiegogo_public`

Use Indiegogo's documented, no-key `GET /api/public/projects/getActiveCrowdfundingProjects` endpoint. It returns active projects ordered by campaign start date with creator, original project URL, start/end dates, campaign currency, funds gathered, and backer count. Set `usd_pledged` only when `currencyShortName` is USD; never relabel or silently convert another currency. A non-USD campaign can still pass via the independently verified 200-backer threshold.

### `instructables_web`

Fetch an Instructables category page, read the public search configuration that the page itself sends to anonymous visitors, and request Featured projects from that same public web endpoint. No account credential is stored in config. Configure `bootstrap_url` and optional category names. The collector records `featureFlag`, favorites, views, I Made It count, author, and publication time; `featureFlag=true` supplies the hard heat-gate evidence. If the page stops exposing its search configuration, fail the source instead of reusing an old token.

### `web_html`

Attempt anonymous discovery from one or more official listing pages, extract only links matching `link_pattern`, then fetch the official detail pages. Configure narrow `metric_patterns`; values are recorded only when their labels and numbers are visible in the returned page. This provider remains appropriate for X, Instagram, and other anonymous public-page attempts; prefer the dedicated Kickstarter and Indiegogo providers above. It deliberately does not execute JavaScript or defeat access controls. Cloudflare, CAPTCHA, login challenges, HTTP 401/403/429, empty JavaScript shells, and hidden metrics become `blocked` or `error`, never zero engagement and never a pass.

### `rss`

Use RSS or Atom without secrets. Set `feed_url` for one feed or `feed_urls` to merge several feeds into one platform-level source before applying the Top 5 limit. `static_metrics` may be used only when the feed URL itself proves the property—for example Hackster's `by=featured` feed may set `featured: true`. This supports discovery from Hackster Featured, curated YouTube channels, subreddit feeds, and editorial publications.

For no-account YouTube, set `detail_enrichment: youtube_public`. The collector normalizes video and Shorts links to the public watch page, records visible video views and channel subscribers, and ranks the shortlist by `views/200000 + channel_subscribers/50000`. For no-account Reddit, set `detail_enrichment: reddit_old`; the collector reads the public old-Reddit post's score and comment count and ranks by their exact sum. `detail_candidate_limit` bounds the discovery shortlist before detail requests, and `detail_workers` controls concurrency. A failed or challenged detail request remains auditable with `metric_verification.status: error`, ranks behind verified candidates, and cannot pass the strict heat gate.

A formal article on Hackaday, Make Magazine, The Verge, or Tom’s Hardware satisfies that platform's reporting heat gate but still must pass every other gate. Public endpoint availability does not override platform terms; never bypass a rejected feed.

### `manual`

Read a local JSON array or an object containing `items`. Use it for web-researched Kickstarter, Indiegogo, Hackster.io, Instructables, X, Instagram, or any approved source without a stable public API. Required item fields are `title` and `url`; optional fields include `summary`, `author`, `published_at`, `metrics`, `metrics_captured_at`, `tags`, and `evidence`. Record only observed public metrics and primary URLs.

## Commands

```bash
python3 scripts/maker_weekly.py collect --config maker-weekly.json --output output/candidates.json
python3 scripts/maker_weekly.py collect --config maker-weekly.json --source instructables --output output/instructables.json
python3 scripts/maker_weekly.py editorial --input output/candidates.json --decisions output/decisions.json --output output/ranked.json
python3 scripts/maker_weekly.py baseline --input output/candidates.json --output output/ranked.json
python3 scripts/maker_weekly.py validate-ranking --input output/ranked.json
python3 scripts/maker_weekly.py render --input output/ranked.json --output output/maker-weekly.md
python3 scripts/strict_weekly.py window
python3 scripts/strict_weekly.py prepare --input output/candidates.json --output output/researched.json --week-start YYYY-MM-DD --week-end YYYY-MM-DD
python3 scripts/strict_weekly.py snapshot --input output/researched.json --output snapshots/YYYY-MM-DD.json
```

Use `--as-of 2026-08-12T00:00:00Z` for reproducible runs.

## Weekly scheduling

The plugin itself does not own a scheduler. Invoke `run` from the user's cron, CI, or automation service. Run from a dedicated working directory, inject secrets through that service, and retain `candidates.json` as an audit artifact. Interactive Codex use should replace the heuristic ranking with the AI comparison described in `SKILL.md`.
