# Provider configuration

## Core behavior

Every enabled `sources[]` entry is an independent platform source. Its bounded fetch results first enter `raw-discoveries.json`; they do not count as Maker candidates. Run the Make Something Gate, time gate, and heat gate before applying `top_per_source`. Use one bundled source for multiple channels or subreddits when they share one platform-level Top 5. All publication lookbacks are calculated in UTC from `--as-of` or the current time. `--as-of` is the publication cutoff, not a heat-observation cutoff; public heat is collected at execution time and keeps its real `metrics_captured_at`.

The bundled formal profile requires no credentials and runs directly without `--config`. Do not ask users to configure provider APIs before the first run. Dedicated credentialed providers remain optional enhancements; they read only environment variables named in a custom config, record missing credentials as `skipped`, and never stop other sources.

## Provider types

### `github`

Use GitHub's repository search API. Resolve authentication in this order: `GITHUB_TOKEN`, `GH_TOKEN`, an existing local `gh auth token` session, then anonymous access. Never print or persist a discovered CLI token. All credentials are optional; anonymous exhaustion becomes `blocked` while other platforms continue. In strict weekly mode, set `date_qualifier` to `created`; `pushed` and `updated` are invalid editorial substitutes for first publication. Reuse `default_branch` from the search response and fetch README evidence from `raw.githubusercontent.com`; do not issue one REST README request per repository. This avoids turning a large raw pool into an anonymous API-rate-limit failure. A repository is only a discovery candidate until its physical core, 1,000-Star heat gate, creator, build process, and actual result are verified.

### `youtube`

Use YouTube Data API v3 `search.list`, followed by `videos.list` for public statistics. Set `YOUTUBE_API_KEY`. API mode supplies video views but the current collector does not supply channel subscriber counts; verify the channel threshold separately when a video is below 25,000 views.

### `reddit`

Use Reddit OAuth client credentials and the authenticated `/top` listing. Set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`, use a truthful `user_agent`, and obtain approval for the intended Data API use. For public desktop distribution, prefer an approved Installed App: put its non-secret client ID in `installed_client_id` or `REDDIT_INSTALLED_CLIENT_ID`; the collector requests application-only OAuth and batches shortlisted post IDs through `oauth.reddit.com/api/info`. Never commit a confidential client secret. The formal RSS profile treats anonymous pages as discovery-only.

### `instagram`

Use the Instagram Graph API hashtag discovery and top-media endpoints. Set `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_USER_ID`. The formal `instagram_fallback` provider tries direct Graph access, an optional evidence relay, audited browser evidence, then anonymous HTML discovery. Configure a relay with `MAKER_WEEKLY_SOCIAL_RELAY_URL` and optionally `MAKER_WEEKLY_SOCIAL_RELAY_TOKEN`; it accepts a JSON request containing `platform`, `since`, `as_of`, `limit`, `urls`, and `hashtags`, and returns `{ "items": [...] }` in the browser-evidence shape below. Access depends on account type, permissions, API version, and Meta review status.

### Audited browser evidence

Set `MAKER_WEEKLY_BROWSER_EVIDENCE` to an absolute JSON path after Codex has opened an original Reddit or Instagram post in a browser. This bridge is for visible original-platform facts, not search snippets or estimates:

```json
{
  "items": [{
    "platform": "Reddit",
    "title": "I built a physical machine",
    "url": "https://www.reddit.com/r/maker/comments/POST_ID/project/",
    "source_url": "https://www.reddit.com/r/maker/comments/POST_ID/project/",
    "provenance": "browser_visible",
    "published_at": "2026-08-07T10:00:00Z",
    "captured_at": "2026-08-12T10:00:00Z",
    "metrics": {"score": 480, "comments": 30},
    "author": "actual_maker"
  }]
}
```

Instagram records require numeric `likes` and `comments`; Reddit records require numeric `score` and `comments`. `url` and `source_url` must be hosted by the original platform. Allowed provenance values are `browser_visible`, `instagram_graph`, `reddit_oauth`, and `official_api`. Hidden or missing metrics fail validation. Include `physical_evidence` when the browser also captured direct build proof.

### `kickstarter_kicktraq`

Use public Kicktraq category pages only to discover Kickstarter project slugs. Interleave configured categories, bound the detail pool with `detail_candidate_limit`, then fetch each project's official Kickstarter `widget/card.html?v=2` page. Record launch time, creator, native pledged amount, backers, state, category, deadline, and currency only from the official widget. Set `usd_pledged` only when the campaign currency itself is USD. For non-USD campaigns, preserve the widget's USD-equivalent as `reported_usd_pledged` and attach `currency_conversion.status=unverified` plus `admissible_for_heat_gate=false`; the widget does not expose an auditable exchange-rate source and conversion timestamp. A non-USD amount may become eligible only through separately supplied conversion evidence containing `status=verified`, `admissible_for_heat_gate=true`, matching `source_currency`, `target_currency=USD`, `source_amount`, `rate`, `converted_amount_usd`, an authoritative `source_url`, and `captured_at`; the collector verifies both multiplication and agreement with `usd_pledged`. Backers remain an independent heat path. For the Make Something Gate, prefer the project's official `/posts.atom` feed when the main campaign page is challenged; updates may directly document prototypes, generations, fabrication, tests, images, and build videos. If neither the official page nor official posts feed proves human making, fail the physical gate. Keep Kicktraq only as discovery provenance.

### `indiegogo_public`

Use Indiegogo's documented, no-key `GET /api/public/projects/getActiveCrowdfundingProjects` endpoint. It returns active projects ordered by campaign start date with creator, original project URL, start/end dates, campaign currency, funds gathered, and backer count. Set `usd_pledged` only when `currencyShortName` is USD; never relabel or silently convert another currency. A non-USD campaign can still pass via the independently verified 200-backer threshold.

### `instructables_web`

Fetch an Instructables category page, read the public search configuration that the page itself sends to anonymous visitors, and request Featured projects from that same public web endpoint. No account credential is stored in config. Configure `bootstrap_url` and optional category names. The collector records `featureFlag`, favorites, views, I Made It count, author, and publication time; `featureFlag=true` supplies the hard heat-gate evidence. If the page stops exposing its search configuration, fail the source instead of reusing an old token.

### `web_html`

Attempt anonymous discovery from one or more official listing pages, extract only links matching `link_pattern`, then fetch the official detail pages. Configure narrow `metric_patterns`; values are recorded only when their labels and numbers are visible in the returned page. This provider remains appropriate for X, Instagram, and other anonymous public-page attempts; prefer the dedicated Kickstarter and Indiegogo providers above. It deliberately does not execute JavaScript or defeat access controls. Cloudflare, CAPTCHA, login challenges, HTTP 401/403/429, empty JavaScript shells, and hidden metrics become `blocked` or `error`, never zero engagement and never a pass.

### `rss`

Use RSS or Atom without secrets. Set `feed_url` for one feed or `feed_urls` to merge several feeds into one platform-level source before applying the Top 5 limit. `static_metrics` may be used only when the feed URL itself proves the property—for example Hackster's `by=featured` feed may set `featured: true`. This supports discovery from Hackster Featured, curated YouTube channels, subreddit feeds, and editorial publications.

Every configured feed is an explicit coverage target. The source status is `ok`/`empty` only when all feeds fetched and parsed; a partial result is `error` and still retains discoveries from successful feeds. `source_status[].coverage.feed_coverage` records total, successful, failed, ratio, failed URL, failure category, and HTTP status. HTTP 500/502/503/504, read timeouts, and incomplete response bodies receive two bounded retries after the initial request. Because YouTube can transiently return 404 for valid channel feeds, retry that exact Feed once after a short delay; a repeated 404 is stale/missing. Do not retry ordinary 404s. Detail enrichment has separate attempted/success/blocked/error counts, and any partial metric verification also prevents an `ok` status.

Do not turn a platform-level partial failure into an item-level rejection. Keep the platform `error`/`blocked`, exclude it from the completed-platform count, and warn that coverage is incomplete. Independently verified items from successful feeds remain eligible for physical, time, heat, and editorial gates and carry `source_coverage.scope=partial_platform_coverage`. An item with missing or failed own evidence remains ineligible; this rule does not infer metrics or relax any item gate.

For multi-feed social bundles, use `feed_pause_seconds` between requests, `feed_recovery_rounds` for failed-feed-only recovery, and `feed_recovery_pause_seconds` between rounds. Honor a provider's `Retry-After` up to the bounded collector maximum. Record `recovery_rounds` and `recovered_feeds`. The default uses slower Reddit pacing and lower detail concurrency than YouTube because Reddit applies tighter anonymous rate limits. Recovery improves transient coverage but does not bypass a persistent 429 or access challenge.

The default YouTube profile favors desktop stability over speed: 1.5 seconds between feeds, two recovery rounds separated by 20 seconds, and two detail workers. After those RSS attempts, `youtube_channel_page_fallback=true` permits a bounded fallback to the same channel's official `/videos` page. It extracts recent video IDs and opens official watch pages to require exact `publishDate`/`uploadDate` and visible metrics. Missing exact dates fail closed. The collector reuses those watch observations for metric and physical enrichment and reports RSS versus page-fallback counts separately.

For no-account YouTube, set `detail_enrichment: youtube_public`. The formal default bundles at least 29 verified Maker/engineering channel feeds, normalizes video and Shorts links, and records visible video views and channel subscribers. For Reddit, use `detail_enrichment: reddit_fallback` with one official combined `top/.rss?t=week` feed covering at least 20 communities. It preserves RSS author, text, image/video URLs, process language, exact feed position, and feed URL, then tries Installed-App OAuth and audited browser evidence for exact heat. When exact interactions remain unavailable and `weekly_rss_rank_fallback.enabled=true`, ranks 1–10 may pass only as `reddit_weekly_rss_rank` proxy evidence with `exact_score_available=false`. Exact score/comments always take precedence; a verified total below 500 fails even at RSS rank 1. Other RSS feeds and hand-entered ranks are ineligible. The legacy `reddit_old` mode retains bounded Unicode-safe old-page/JSON diagnostics for custom profiles but is not formal heat evidence. Respect HTTP 429 and `Retry-After`; never bypass limits. The formal default deliberately does not use title-only Maker filters.

Use the expanded default: YouTube reaches 25,000 views or 10,000 channel subscribers; Reddit score plus comments reaches 500, or uses official combined weekly RSS rank 1–10 only when exact interactions are unavailable; Kickstarter reaches US$5,000 or 50 backers. These gates expand editorial research only; keep all physical, time, authorship, process, and final editorial gates unchanged.

A formal article on Hackaday, Make Magazine, The Verge, or Tom’s Hardware satisfies that platform's reporting heat gate but still must pass every other gate. Public endpoint availability does not override platform terms; never bypass a rejected feed.

### `manual`

Read a local JSON array or an object containing `items`. Use it for web-researched Kickstarter, Indiegogo, Hackster.io, Instructables, X, Instagram, or any approved source without a stable public API. Required item fields are `title` and `url`; optional fields include `summary`, `author`, `published_at`, `metrics`, `metrics_captured_at`, `tags`, and `evidence`. Record only observed public metrics and primary URLs.

## Commands

```bash
python3 scripts/maker_weekly.py collect --output output/raw-discoveries.json
python3 scripts/maker_weekly.py run --output-dir output --as-of WEEK_END
python3 scripts/maker_weekly.py baseline --input output/raw-discoveries.json --output output/raw-audit.json
python3 scripts/maker_weekly.py render --input output/raw-audit.json --output output/raw-discoveries-audit.md
python3 scripts/strict_weekly.py window
python3 scripts/strict_weekly.py prepare --input output/researched.json --output output/researched-strict.json --week-start YYYY-MM-DD --week-end YYYY-MM-DD
python3 scripts/strict_weekly.py snapshot --input output/researched-strict.json --output snapshots/YYYY-MM-DD.json
```

Use `--as-of 2026-08-12T00:00:00Z` for reproducible runs.

## Weekly scheduling

The plugin itself does not own a scheduler. Invoke `run` from the user's cron, CI, or automation service. Run from a dedicated working directory, inject secrets through that service, and retain all four stage artifacts. Only `final.json`, created after strict editorial decisions and validation, may be rendered as a publishable Maker 周报.
