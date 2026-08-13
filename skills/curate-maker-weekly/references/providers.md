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

Use Reddit OAuth client credentials and the authenticated `/top` listing. Set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`, use a truthful `user_agent`, and obtain approval for the intended Data API use. This remains the broadest discovery mode. The no-account RSS mode described below can verify a bounded shortlist on public old-Reddit post pages without bypassing a challenge.

### `instagram`

Use the Instagram Graph API hashtag discovery and top-media endpoints. Set `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_USER_ID`. Access depends on account type, permissions, API version, and Meta review status. If access is unavailable, use an authorized `manual` export.

### `kickstarter_kicktraq`

Use public Kicktraq category pages only to discover Kickstarter project slugs. Interleave configured categories, bound the detail pool with `detail_candidate_limit`, then fetch each project's official Kickstarter `widget/card.html?v=2` page. Record launch time, creator, USD-equivalent pledged amount, backers, state, category, and deadline only from the official widget. For the Make Something Gate, prefer the project's official `/posts.atom` feed when the main campaign page is challenged; updates may directly document prototypes, generations, fabrication, tests, images, and build videos. If neither the official page nor official posts feed proves human making, fail the physical gate. Keep Kicktraq only as discovery provenance.

### `indiegogo_public`

Use Indiegogo's documented, no-key `GET /api/public/projects/getActiveCrowdfundingProjects` endpoint. It returns active projects ordered by campaign start date with creator, original project URL, start/end dates, campaign currency, funds gathered, and backer count. Set `usd_pledged` only when `currencyShortName` is USD; never relabel or silently convert another currency. A non-USD campaign can still pass via the independently verified 200-backer threshold.

### `instructables_web`

Fetch an Instructables category page, read the public search configuration that the page itself sends to anonymous visitors, and request Featured projects from that same public web endpoint. No account credential is stored in config. Configure `bootstrap_url` and optional category names. The collector records `featureFlag`, favorites, views, I Made It count, author, and publication time; `featureFlag=true` supplies the hard heat-gate evidence. If the page stops exposing its search configuration, fail the source instead of reusing an old token.

### `web_html`

Attempt anonymous discovery from one or more official listing pages, extract only links matching `link_pattern`, then fetch the official detail pages. Configure narrow `metric_patterns`; values are recorded only when their labels and numbers are visible in the returned page. This provider remains appropriate for X, Instagram, and other anonymous public-page attempts; prefer the dedicated Kickstarter and Indiegogo providers above. It deliberately does not execute JavaScript or defeat access controls. Cloudflare, CAPTCHA, login challenges, HTTP 401/403/429, empty JavaScript shells, and hidden metrics become `blocked` or `error`, never zero engagement and never a pass.

### `rss`

Use RSS or Atom without secrets. Set `feed_url` for one feed or `feed_urls` to merge several feeds into one platform-level source before applying the Top 5 limit. `static_metrics` may be used only when the feed URL itself proves the property—for example Hackster's `by=featured` feed may set `featured: true`. This supports discovery from Hackster Featured, curated YouTube channels, subreddit feeds, and editorial publications.

For no-account YouTube, set `detail_enrichment: youtube_public`. The formal default bundles at least 29 verified Maker/engineering channel feeds, normalizes video and Shorts links, and records visible video views and channel subscribers. For no-account Reddit, set `detail_enrichment: reddit_old`; use a small number of multi-subreddit RSS bundles to cover at least 20 communities without triggering one anonymous request per community. Preserve the RSS-embedded author, post text, image/video URLs, and process language. Percent-encode Unicode post paths before public requests. Verify score and comments on old Reddit first; when either value is missing or the HTML path fails, try the canonical post JSON, old-host JSON, short `/comments/ID.json`, and `api.reddit.com/comments/ID` public representations. Mark the item failed only when all bounded public representations fail. Respect HTTP 429 and `Retry-After`; use bounded retries and a small configured pause rather than bypassing limits. The formal default deliberately does not use title-only Maker filters.

Use the expanded verified default: YouTube reaches 25,000 views or 10,000 channel subscribers; Reddit score plus comments reaches 500; Kickstarter reaches US$5,000 or 50 backers. These gates expand editorial research only; keep all physical, time, authorship, process, and final editorial gates unchanged.

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
