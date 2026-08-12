#!/usr/bin/env python3
"""Collect and render a weekly global physical Maker Project shortlist.

The module intentionally uses only Python's standard library. Platform
credentials are read from environment variables referenced by the config.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable


USER_AGENT = "maker-weekly-radar/0.2"
SUPPORTED_TYPES = {
    "github", "youtube", "reddit", "instagram", "rss", "manual", "web_html", "instructables_web",
    "kickstarter_kicktraq", "indiegogo_public",
}
TRACKING_PARAMS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source", "utm_campaign",
    "utm_content", "utm_medium", "utm_source", "utm_term",
}


class ConfigError(ValueError):
    pass


class MissingCredential(RuntimeError):
    pass


class AccessBlocked(RuntimeError):
    """A provider explicitly denied public, non-authenticated collection."""

    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if abs(timestamp) >= 100_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: Any, limit: int = 1000) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def canonical_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except ValueError:
        return value.strip()
    host = (parsed.hostname or "").lower()
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = sorted((k, v) for k, v in query if k.lower() not in TRACKING_PARAMS)
    if host == "youtu.be" and path != "/":
        host, path = "youtube.com", "/watch"
        query.append(("v", parsed.path.strip("/")))
        query.sort()
    return urllib.parse.urlunsplit((parsed.scheme.lower() or "https", host, path, urllib.parse.urlencode(query), ""))


def normalized_title(value: str) -> str:
    words = re.findall(r"[a-z0-9\u3400-\u9fff]+", value.lower())
    stop = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    return " ".join(word for word in words if word not in stop)


def stable_id(source_id: str, url: str, title: str) -> str:
    payload = f"{source_id}\n{canonical_url(url)}\n{normalized_title(title)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def request_bytes(
    url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> bytes:
    request_headers = {"Accept": "application/json, application/rss+xml, application/xml;q=0.9, */*;q=0.5", "User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    last_connection_error: urllib.error.URLError | None = None
    for _attempt in range(3):
        request = urllib.request.Request(url, headers=request_headers, data=data)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403, 429}:
                raise AccessBlocked(f"HTTP {exc.code} from provider; public collection was blocked or rate-limited") from exc
            raise RuntimeError(f"HTTP {exc.code} from provider") from exc
        except urllib.error.URLError as exc:
            last_connection_error = exc
    assert last_connection_error is not None
    raise RuntimeError(f"provider connection failed after 3 attempts: {last_connection_error.reason}") from last_connection_error


def request_json(
    url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> dict[str, Any]:
    raw = request_bytes(url, timeout, headers=headers, data=data)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("provider returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("provider returned a non-object JSON response")
    return payload


def require_env(source: dict[str, Any], field: str, default_name: str) -> str:
    env_name = str(source.get(field) or default_name)
    value = os.environ.get(env_name)
    if not value:
        raise MissingCredential(f"missing environment variable {env_name}")
    return value


def candidate(
    source: dict[str, Any],
    title: Any,
    url: Any,
    *,
    summary: Any = "",
    author: Any = "",
    published_at: Any = None,
    metrics: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    evidence: list[str] | None = None,
    raw_score: float = 0.0,
    metrics_captured_at: Any = None,
) -> dict[str, Any] | None:
    title_text, url_text = clean_text(title, 300), str(url or "").strip()
    if not title_text or not url_text.startswith(("http://", "https://")):
        return None
    source_id = str(source["id"])
    return {
        "id": stable_id(source_id, url_text, title_text),
        "source_id": source_id,
        "platform": str(source.get("platform") or source_id),
        "title": title_text,
        "url": url_text,
        "summary": clean_text(summary),
        "author": clean_text(author, 200),
        "published_at": iso_z(parse_datetime(published_at)),
        "metrics": metrics or {},
        "metrics_captured_at": iso_z(parse_datetime(metrics_captured_at)) or (iso_z(now_utc()) if metrics else None),
        "tags": sorted({clean_text(tag, 80) for tag in (tags or []) if clean_text(tag, 80)}),
        "evidence": [str(item) for item in (evidence or []) if item],
        "also_seen_on": [],
        "_raw_score": float(raw_score),
    }


def cap_and_rank(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda item: (item.get("_raw_score", 0.0), item.get("published_at") or ""), reverse=True)[:limit]
    count = len(ordered)
    for index, item in enumerate(ordered, 1):
        item["source_rank"] = index
        item["source_percentile"] = round(1.0 if count == 1 else 1.0 - ((index - 1) / (count - 1)), 4)
        item.pop("_raw_score", None)
    return ordered


def collect_github(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token_name = str(source.get("token_env") or "GITHUB_TOKEN")
    if os.environ.get(token_name):
        headers["Authorization"] = f"Bearer {os.environ[token_name]}"
    queries = source.get("queries") or [source.get("query") or "topic:3d-printing"]
    if not isinstance(queries, list) or not queries:
        raise ConfigError("github source requires a non-empty queries array")
    required_terms = [
        str(term).lower()
        for term in source.get("required_terms")
        or ["3d print", "3d-print", "3d printer", "openscad", "stl", "additive manufacturing"]
    ]
    repositories: dict[Any, dict[str, Any]] = {}
    date_qualifier = str(source.get("date_qualifier") or "created")
    if date_qualifier not in {"created", "pushed", "updated"}:
        raise ConfigError("github date_qualifier must be created, pushed, or updated")
    for raw_query in queries:
        date_range = f"{context['since'].date().isoformat()}..{context['as_of'].date().isoformat()}"
        query = f"{raw_query} {date_qualifier}:{date_range}"
        params = urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": min(50, context["limit"] * 5)})
        payload = request_json(f"https://api.github.com/search/repositories?{params}", context["timeout"], headers=headers)
        for repo in payload.get("items", []):
            if isinstance(repo, dict):
                repositories[repo.get("id") or repo.get("html_url")] = repo
    results = []
    for repo in repositories.values():
        visible_text = " ".join([
            str(repo.get("full_name") or ""), str(repo.get("description") or ""),
            " ".join(str(topic) for topic in repo.get("topics") or []),
        ]).lower()
        if required_terms and not any(term in visible_text for term in required_terms):
            continue
        stars, forks, watchers = int(repo.get("stargazers_count") or 0), int(repo.get("forks_count") or 0), int(repo.get("subscribers_count") or 0)
        item = candidate(
            source, repo.get("full_name"), repo.get("html_url"), summary=repo.get("description"),
            author=(repo.get("owner") or {}).get("login"), published_at=repo.get("created_at"),
            metrics={"stars": stars, "forks": forks, "watchers": watchers, "open_issues": int(repo.get("open_issues_count") or 0), "updated_at": repo.get("updated_at"), "pushed_at": repo.get("pushed_at")},
            tags=list(repo.get("topics") or []), evidence=[repo.get("html_url")], raw_score=stars + forks * 2 + watchers,
        )
        if item:
            results.append(item)
    return results


def collect_youtube(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    api_key = require_env(source, "api_key_env", "YOUTUBE_API_KEY")
    params = {
        "part": "snippet", "type": "video", "maxResults": min(50, context["limit"] * 5),
        "order": "viewCount", "publishedAfter": iso_z(context["since"]), "publishedBefore": iso_z(context["as_of"]),
        "q": str(source.get("query") or "3D printing project"), "key": api_key,
    }
    if source.get("region_code"):
        params["regionCode"] = str(source["region_code"])
    if source.get("relevance_language"):
        params["relevanceLanguage"] = str(source["relevance_language"])
    search = request_json(f"https://www.googleapis.com/youtube/v3/search?{urllib.parse.urlencode(params)}", context["timeout"])
    search_items = [item for item in search.get("items", []) if isinstance(item, dict) and (item.get("id") or {}).get("videoId")]
    if not search_items:
        return []
    ids = [item["id"]["videoId"] for item in search_items]
    stat_params = urllib.parse.urlencode({"part": "snippet,statistics", "id": ",".join(ids), "key": api_key})
    details = request_json(f"https://www.googleapis.com/youtube/v3/videos?{stat_params}", context["timeout"])
    results = []
    for video in details.get("items", []):
        if not isinstance(video, dict):
            continue
        snippet, stats = video.get("snippet") or {}, video.get("statistics") or {}
        views, likes, comments = int(stats.get("viewCount") or 0), int(stats.get("likeCount") or 0), int(stats.get("commentCount") or 0)
        url = f"https://www.youtube.com/watch?v={video.get('id')}"
        item = candidate(
            source, snippet.get("title"), url, summary=snippet.get("description"), author=snippet.get("channelTitle"),
            published_at=snippet.get("publishedAt"), metrics={"views": views, "likes": likes, "comments": comments},
            tags=list(snippet.get("tags") or []), evidence=[url], raw_score=views + likes * 20 + comments * 30,
        )
        if item:
            results.append(item)
    return results


def reddit_token(source: dict[str, Any], timeout: int) -> str:
    client_id = require_env(source, "client_id_env", "REDDIT_CLIENT_ID")
    client_secret = require_env(source, "client_secret_env", "REDDIT_CLIENT_SECRET")
    user_agent = str(source.get("user_agent") or USER_AGENT)
    if "YOUR_REDDIT_USERNAME" in user_agent:
        raise ConfigError("reddit user_agent still contains YOUR_REDDIT_USERNAME")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    payload = request_json(
        "https://www.reddit.com/api/v1/access_token", timeout,
        headers={"Authorization": f"Basic {basic}", "User-Agent": user_agent, "Content-Type": "application/x-www-form-urlencoded"}, data=data,
    )
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Reddit did not return an access token")
    return str(token)


def collect_reddit(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    token = reddit_token(source, context["timeout"])
    user_agent = str(source.get("user_agent") or USER_AGENT)
    headers = {"Authorization": f"Bearer {token}", "User-Agent": user_agent}
    results = []
    subreddits = source.get("subreddits") or ["3Dprinting"]
    for subreddit in subreddits:
        params = urllib.parse.urlencode({"t": "week", "limit": min(100, context["limit"] * 5), "raw_json": 1})
        payload = request_json(f"https://oauth.reddit.com/r/{urllib.parse.quote(str(subreddit))}/top?{params}", context["timeout"], headers=headers)
        for child in (payload.get("data") or {}).get("children", []):
            post = child.get("data") or {}
            created = parse_datetime(post.get("created_utc"))
            if created and not (context["since"] <= created <= context["as_of"]):
                continue
            score, comments, ratio = int(post.get("score") or 0), int(post.get("num_comments") or 0), float(post.get("upvote_ratio") or 0)
            permalink = f"https://www.reddit.com{post.get('permalink')}"
            item = candidate(
                source, post.get("title"), permalink, summary=post.get("selftext"), author=post.get("author"), published_at=created,
                metrics={"score": score, "comments": comments, "upvote_ratio": ratio, "subreddit": str(subreddit)},
                tags=[str(subreddit), post.get("link_flair_text") or ""], evidence=[permalink, post.get("url_overridden_by_dest")],
                raw_score=score + comments * 3,
            )
            if item:
                results.append(item)
    return results


def collect_instagram(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    token = require_env(source, "access_token_env", "INSTAGRAM_ACCESS_TOKEN")
    user_id = require_env(source, "user_id_env", "INSTAGRAM_USER_ID")
    version = str(source.get("api_version") or "v23.0")
    results = []
    for hashtag in source.get("hashtags") or ["3dprinting"]:
        lookup_params = urllib.parse.urlencode({"user_id": user_id, "q": str(hashtag), "access_token": token})
        lookup = request_json(f"https://graph.facebook.com/{version}/ig_hashtag_search?{lookup_params}", context["timeout"])
        data = lookup.get("data") or []
        if not data:
            continue
        tag_id = data[0].get("id")
        fields = "id,caption,media_type,permalink,timestamp,like_count,comments_count,username"
        media_params = urllib.parse.urlencode({"user_id": user_id, "fields": fields, "limit": min(50, context["limit"] * 5), "access_token": token})
        media = request_json(f"https://graph.facebook.com/{version}/{tag_id}/top_media?{media_params}", context["timeout"])
        for post in media.get("data", []):
            published = parse_datetime(post.get("timestamp"))
            if published and not (context["since"] <= published <= context["as_of"]):
                continue
            likes, comments = int(post.get("like_count") or 0), int(post.get("comments_count") or 0)
            caption = clean_text(post.get("caption"), 1000)
            item = candidate(
                source, caption[:160] or f"#{hashtag} Instagram post", post.get("permalink"), summary=caption,
                author=post.get("username"), published_at=published, metrics={"likes": likes, "comments": comments},
                tags=[str(hashtag), str(post.get("media_type") or "")], evidence=[post.get("permalink")], raw_score=likes + comments * 4,
            )
            if item:
                results.append(item)
    return results


class PublicPageParser(HTMLParser):
    """Extract conservative metadata and links from a public HTML response."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.jsonld: list[str] = []
        self.visible_parts: list[str] = []
        self.time_datetimes: list[str] = []
        self._in_title = False
        self._ignored_depth = 0
        self._anchor: dict[str, Any] | None = None
        self._script_type = ""
        self._script_id = ""
        self._script_parts: list[str] = []
        self.scripts_by_id: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            if key and values.get("content"):
                self.meta.setdefault(key, values["content"])
        elif tag == "a" and values.get("href"):
            self._anchor = {"href": values["href"], "title": values.get("title", ""), "parts": []}
        elif tag == "time" and values.get("datetime"):
            self.time_datetimes.append(values["datetime"])
        elif tag == "script":
            self._script_type = values.get("type", "").lower()
            self._script_id = values.get("id", "")
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor is not None:
            self.links.append({
                "href": str(self._anchor["href"]),
                "title": clean_text(self._anchor.get("title") or " ".join(self._anchor["parts"]), 300),
            })
            self._anchor = None
        elif tag == "script":
            script_text = "".join(self._script_parts).strip()
            if self._script_type == "application/ld+json" and script_text:
                self.jsonld.append(script_text)
            if self._script_id and script_text:
                self.scripts_by_id[self._script_id] = script_text
            self._script_type = ""
            self._script_id = ""
            self._script_parts = []
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._anchor is not None:
            self._anchor["parts"].append(data)
        if self._script_type or self._script_id:
            self._script_parts.append(data)
        elif not self._ignored_depth and data.strip():
            self.visible_parts.append(data)


def parse_public_page(raw: bytes) -> tuple[PublicPageParser, str]:
    text = raw.decode("utf-8", errors="replace")
    lowered = text.lower()
    blocked_markers = (
        "just a moment...", "cf-chl-", "challenge-platform", "enable javascript and cookies to continue",
        "please verify you are a human", "automated access to our data", "login to continue",
    )
    marker = next((value for value in blocked_markers if value in lowered), None)
    if marker:
        raise AccessBlocked(f"provider returned an access/login challenge ({marker})")
    parser = PublicPageParser()
    parser.feed(text)
    return parser, text


def jsonld_nodes(values: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for raw in values:
        try:
            walk(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return found


def author_name(value: Any) -> str:
    if isinstance(value, str):
        return clean_text(value, 200)
    if isinstance(value, dict):
        return clean_text(value.get("name") or value.get("alternateName"), 200)
    if isinstance(value, list):
        names = [author_name(item) for item in value]
        return ", ".join(name for name in names if name)[:200]
    return ""


def public_page_metadata(parser: PublicPageParser, page_url: str) -> dict[str, Any]:
    nodes = jsonld_nodes(parser.jsonld)
    primary = next(
        (node for node in nodes if str(node.get("@type") or "").lower() in {"article", "newsarticle", "product", "creativework", "project", "howto"}),
        nodes[0] if nodes else {},
    )
    title = (
        parser.meta.get("og:title") or parser.meta.get("twitter:title") or primary.get("headline")
        or primary.get("name") or clean_text(" ".join(parser.title_parts), 300)
    )
    description = (
        parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description")
        or primary.get("description") or ""
    )
    published = (
        parser.meta.get("article:published_time") or parser.meta.get("datepublished") or primary.get("datePublished")
        or primary.get("dateCreated") or (parser.time_datetimes[0] if parser.time_datetimes else None)
    )
    author = parser.meta.get("author") or author_name(primary.get("author") or primary.get("creator") or primary.get("contributor"))
    canonical = parser.meta.get("og:url") or primary.get("url") or page_url
    return {
        "title": clean_text(title, 300), "summary": clean_text(description), "published_at": published,
        "author": clean_text(author, 200), "url": str(canonical or page_url),
        "visible_text": clean_text(" ".join(parser.visible_parts), 20000),
    }


def compact_number(value: str) -> float | None:
    text = value.strip().strip(".,").replace("\u00a0", "").replace(" ", "").replace(",", "")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([kKmMbB]?)", text)
    if not match:
        return None
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[match.group(2).lower()]
    return float(match.group(1)) * multiplier


def configured_metrics(source: dict[str, Any], visible_text: str, raw_text: str) -> dict[str, Any]:
    configured = source.get("metric_patterns") or {}
    if not isinstance(configured, dict):
        raise ConfigError("web_html metric_patterns must be an object")
    metrics: dict[str, Any] = {}
    for name, patterns in configured.items():
        pattern_list = patterns if isinstance(patterns, list) else [patterns]
        for pattern in pattern_list:
            try:
                match = re.search(str(pattern), visible_text, flags=re.IGNORECASE)
                if match is None:
                    match = re.search(str(pattern), raw_text, flags=re.IGNORECASE)
            except re.error as exc:
                raise ConfigError(f"invalid metric pattern for {name}: {exc}") from exc
            if match:
                parsed = compact_number(match.group(1))
                if parsed is not None:
                    metrics[str(name)] = int(parsed) if parsed.is_integer() else parsed
                    break
    return metrics


def collect_web_html(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    listing_urls = source.get("listing_urls") or [source.get("listing_url")]
    if not isinstance(listing_urls, list) or not listing_urls or any(not str(url or "").startswith(("http://", "https://")) for url in listing_urls):
        raise ConfigError("web_html source requires valid listing_url or listing_urls")
    try:
        link_pattern = re.compile(str(source["link_pattern"]))
    except KeyError as exc:
        raise ConfigError("web_html source requires link_pattern") from exc
    except re.error as exc:
        raise ConfigError(f"invalid web_html link_pattern: {exc}") from exc
    discovered: dict[str, dict[str, str]] = {}
    listing_failures: list[str] = []
    blocked = False
    for listing_url in [str(value) for value in listing_urls]:
        try:
            parser, _ = parse_public_page(request_bytes(listing_url, context["timeout"], headers={"Accept": "text/html,application/xhtml+xml"}))
        except AccessBlocked as exc:
            blocked = True
            listing_failures.append(f"{urllib.parse.urlsplit(listing_url).hostname}: {exc}")
            continue
        except RuntimeError as exc:
            listing_failures.append(f"{urllib.parse.urlsplit(listing_url).hostname}: {exc}")
            continue
        for link in parser.links:
            absolute = urllib.parse.urljoin(listing_url, link["href"])
            normalized = canonical_url(absolute)
            if link_pattern.search(normalized):
                discovered.setdefault(normalized, {"url": absolute, "title": link["title"], "listing_url": listing_url})
    if not discovered:
        detail = "; ".join(listing_failures) or "listing returned no matching public project links; it may require JavaScript or login"
        if blocked:
            raise AccessBlocked(detail)
        raise RuntimeError(detail)
    results: list[dict[str, Any]] = []
    required_keywords = [str(value).lower() for value in source.get("keywords") or []]
    max_details = min(50, int(source.get("max_details") or context["limit"] * 5))
    for discovered_item in list(discovered.values())[:max_details]:
        page_url = discovered_item["url"]
        try:
            parser, raw_text = parse_public_page(request_bytes(page_url, context["timeout"], headers={"Accept": "text/html,application/xhtml+xml"}))
        except (AccessBlocked, RuntimeError):
            continue
        metadata = public_page_metadata(parser, page_url)
        title = metadata["title"] or discovered_item["title"]
        haystack = f"{title} {metadata['summary']} {metadata['visible_text']}".lower()
        if required_keywords and not any(keyword in haystack for keyword in required_keywords):
            continue
        published = parse_datetime(metadata["published_at"])
        if published and not (context["since"] <= published <= context["as_of"]):
            continue
        metrics = configured_metrics(source, metadata["visible_text"], raw_text)
        raw_score = sum(float(value) for value in metrics.values() if isinstance(value, (int, float)))
        item = candidate(
            source, title, metadata["url"] or page_url, summary=metadata["summary"], author=metadata["author"],
            published_at=published, metrics=metrics, tags=source.get("tags") or [],
            evidence=[page_url, discovered_item["listing_url"]], raw_score=raw_score,
        )
        if item:
            results.append(item)
    if not results:
        raise RuntimeError("public listing links were found, but no detail page produced a candidate inside the target window")
    return results


def parse_kickstarter_widget(raw: bytes) -> dict[str, Any]:
    """Read the official Kickstarter card payload without treating bundled JS as a challenge."""

    text = raw.decode("utf-8", errors="replace")
    match = re.search(r'window\.current_project\s*=\s*"(.*?)";', text, flags=re.DOTALL)
    if match is None:
        # Detect a real Cloudflare page only when the project payload is absent.
        parse_public_page(raw)
        raise RuntimeError("Kickstarter widget did not expose window.current_project")
    serialized = html.unescape(match.group(1))
    attempts = (serialized, serialized.replace("\\\\", "\\"))
    for value in attempts:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("name") and payload.get("urls"):
            return payload
    raise RuntimeError("Kickstarter widget exposed invalid project JSON")


def collect_kickstarter_kicktraq(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Discover on Kicktraq, then verify every fact on Kickstarter's public card."""

    listing_urls = source.get("listing_urls") or [source.get("listing_url")]
    if not isinstance(listing_urls, list) or not listing_urls:
        raise ConfigError("kickstarter_kicktraq requires listing_url or listing_urls")
    listing_groups: list[list[dict[str, str]]] = []
    listing_failures: list[str] = []
    for raw_url in listing_urls:
        listing_url = str(raw_url or "")
        if not listing_url.startswith(("http://", "https://")):
            raise ConfigError("kickstarter_kicktraq listing URLs must use http(s)")
        try:
            parser, _ = parse_public_page(request_bytes(listing_url, context["timeout"], headers={"Accept": "text/html"}))
        except (AccessBlocked, RuntimeError) as exc:
            listing_failures.append(f"{urllib.parse.urlsplit(listing_url).hostname}: {exc}")
            continue
        group: list[dict[str, str]] = []
        seen_in_group: set[str] = set()
        for link in parser.links:
            absolute = urllib.parse.urljoin(listing_url, link["href"])
            parsed = urllib.parse.urlsplit(absolute)
            if (parsed.hostname or "").lower() not in {"kicktraq.com", "www.kicktraq.com"}:
                continue
            parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
            if len(parts) != 3 or parts[0] != "projects":
                continue
            creator, slug = parts[1], parts[2]
            project_url = f"https://www.kickstarter.com/projects/{urllib.parse.quote(creator)}/{urllib.parse.quote(slug)}"
            if project_url in seen_in_group:
                continue
            seen_in_group.add(project_url)
            group.append({"url": project_url, "listing_url": listing_url, "kicktraq_url": absolute})
        if group:
            listing_groups.append(group)
    if not listing_groups:
        raise RuntimeError("Kicktraq discovery failed: " + ("; ".join(listing_failures) or "no project links"))

    # Interleave categories so one busy category cannot consume the whole detail budget.
    discovered: list[dict[str, str]] = []
    seen_projects: set[str] = set()
    max_group_size = max(len(group) for group in listing_groups)
    for index in range(max_group_size):
        for group in listing_groups:
            if index >= len(group):
                continue
            item = group[index]
            if item["url"] not in seen_projects:
                seen_projects.add(item["url"])
                discovered.append(item)
    detail_limit = int(source.get("detail_candidate_limit") or max(35, context["limit"] * 7))
    if detail_limit < 1:
        raise ConfigError("kickstarter_kicktraq detail_candidate_limit must be at least 1")
    discovered = discovered[:detail_limit]

    required_keywords = [str(value).lower() for value in source.get("keywords") or []]
    excluded_keywords = [str(value).lower() for value in source.get("exclude_keywords") or []]
    captured_at = iso_z(now_utc())

    def load_project(discovered_item: dict[str, str]) -> tuple[dict[str, str], dict[str, Any] | None]:
        widget_url = discovered_item["url"] + "/widget/card.html?v=2"
        try:
            payload = parse_kickstarter_widget(request_bytes(widget_url, context["timeout"], headers={"Accept": "text/html"}))
        except (AccessBlocked, RuntimeError):
            return discovered_item, None
        payload["_widget_url"] = widget_url
        return discovered_item, payload

    workers = max(1, min(8, int(source.get("detail_workers") or 4), len(discovered)))
    if workers == 1:
        loaded = [load_project(item) for item in discovered]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="kickstarter-card") as executor:
            loaded = list(executor.map(load_project, discovered))

    results: list[dict[str, Any]] = []
    parsed_details = 0
    for discovered_item, project in loaded:
        if project is None:
            continue
        parsed_details += 1
        title, summary = clean_text(project.get("name"), 300), clean_text(project.get("blurb"))
        category = project.get("category") if isinstance(project.get("category"), dict) else {}
        category_text = " ".join(str(category.get(key) or "") for key in ("name", "parent_name"))
        haystack = f"{title} {summary} {category_text}".lower()
        if required_keywords and not any(keyword in haystack for keyword in required_keywords):
            continue
        if excluded_keywords and any(keyword in haystack for keyword in excluded_keywords):
            continue
        launched = parse_datetime(project.get("launched_at"))
        if launched and not (context["since"] <= launched <= context["as_of"]):
            continue
        backers = int(project.get("backers_count") or 0)
        usd_pledged = float(project.get("usd_pledged") or 0)
        web_urls = project.get("urls") if isinstance(project.get("urls"), dict) else {}
        web_urls = web_urls.get("web") if isinstance(web_urls.get("web"), dict) else {}
        project_url = str(web_urls.get("project") or discovered_item["url"])
        metrics = {
            "backers": backers, "usd_pledged": usd_pledged, "goal": float(project.get("goal") or 0),
            "currency": str(project.get("currency") or ""), "state": str(project.get("state") or ""),
            "staff_pick": bool(project.get("staff_pick")), "deadline": iso_z(parse_datetime(project.get("deadline"))),
        }
        creator = project.get("creator") if isinstance(project.get("creator"), dict) else {}
        tags = [str(category.get(key) or "") for key in ("parent_name", "name")]
        item = candidate(
            source, title, project_url, summary=summary, author=creator.get("name"), published_at=launched,
            metrics=metrics, metrics_captured_at=captured_at, tags=tags,
            evidence=[project_url, project["_widget_url"], discovered_item["kicktraq_url"], discovered_item["listing_url"]],
            raw_score=usd_pledged / 20_000 + backers / 200,
        )
        if item:
            item["metric_verification"] = {
                "status": "ok", "source_url": project["_widget_url"], "captured_at": captured_at,
                "ranking_basis": "usd_pledged/20000 + backers/200",
            }
            results.append(item)
    if parsed_details == 0:
        raise RuntimeError("Kicktraq found projects, but every official Kickstarter widget failed")
    return results


def collect_indiegogo_public(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    endpoint = str(source.get("endpoint") or "https://www.indiegogo.com/api/public/projects/getActiveCrowdfundingProjects")
    raw = request_bytes(endpoint, context["timeout"], headers={"Accept": "application/json"})
    try:
        projects = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Indiegogo public API returned invalid JSON") from exc
    if not isinstance(projects, list):
        raise RuntimeError("Indiegogo public API returned a non-list response")
    required_keywords = [str(value).lower() for value in source.get("keywords") or []]
    excluded_keywords = [str(value).lower() for value in source.get("exclude_keywords") or []]
    captured_at = iso_z(now_utc())
    results: list[dict[str, Any]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        title = clean_text(project.get("projectName"), 300)
        summary = clean_text(project.get("shortDescription"))
        haystack = f"{title} {summary}".lower()
        if required_keywords and not any(keyword in haystack for keyword in required_keywords):
            continue
        if excluded_keywords and any(keyword in haystack for keyword in excluded_keywords):
            continue
        launched = parse_datetime(project.get("campaignStartDate"))
        if launched and not (context["since"] <= launched <= context["as_of"]):
            continue
        currency = str(project.get("currencyShortName") or "").upper()
        pledged = float(project.get("fundsGathered") or 0)
        backers = int(project.get("backerCount") or 0)
        metrics: dict[str, Any] = {
            "backers": backers, "pledged": pledged, "currency": currency,
            "goal": float(project.get("campaignGoal") or 0),
            "comments": int(project.get("commentCount") or 0), "updates": int(project.get("updateCount") or 0),
            "deadline": iso_z(parse_datetime(project.get("campaignEndDate"))),
        }
        # Do not pretend a local-currency amount is USD. The backer threshold
        # remains independently verifiable for every currency.
        if currency == "USD":
            metrics["usd_pledged"] = pledged
        project_url = str(project.get("projectHomeUrl") or "")
        item = candidate(
            source, title, project_url, summary=summary, author=project.get("creatorName"), published_at=launched,
            metrics=metrics, metrics_captured_at=captured_at, tags=["crowdfunding", currency],
            evidence=[project_url, endpoint], raw_score=backers / 200 + float(metrics.get("usd_pledged") or 0) / 20_000,
        )
        if item:
            item["metric_verification"] = {
                "status": "ok", "source_url": endpoint, "captured_at": captured_at,
                "ranking_basis": "usd_pledged/20000 + backers/200; non-USD amount is not converted",
            }
            results.append(item)
    return results


def collect_instructables_web(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    bootstrap_url = str(source.get("bootstrap_url") or "https://www.instructables.com/circuits/projects/")
    parser, _ = parse_public_page(request_bytes(bootstrap_url, context["timeout"], headers={"Accept": "text/html,application/xhtml+xml"}))
    raw_context = parser.scripts_by_id.get("js-page-context")
    if not raw_context:
        raise RuntimeError("Instructables page did not expose js-page-context")
    try:
        page_context = json.loads(raw_context)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Instructables page context was invalid JSON") from exc
    proxy, public_key = page_context.get("typesenseProxy"), page_context.get("typesenseApiKey")
    if not proxy or not public_key:
        raise RuntimeError("Instructables page did not expose its public search configuration")
    endpoint = urllib.parse.urljoin(bootstrap_url, str(proxy).rstrip("/") + "/collections/projects/documents/search")
    fields = "title,urlString,screenName,favorites,views,primaryClassification,featureFlag,prizeLevel,IMadeItCount,publishDate"
    categories = source.get("categories") or ["Circuits", "Workshop", "Design", "Craft", "Living", "Outside"]
    if not isinstance(categories, list) or not categories:
        raise ConfigError("instructables_web categories must be a non-empty array")
    projects: dict[str, dict[str, Any]] = {}
    per_page = min(60, int(source.get("per_page") or context["limit"] * 5))
    headers = {"Accept": "application/json", "x-typesense-api-key": str(public_key)}
    category_filter = ",".join(str(category) for category in categories)
    query = urllib.parse.urlencode({
        "q": "*", "query_by": "title,stepBody,screenName", "page": 1,
        "sort_by": "publishDate:desc", "include_fields": fields,
        "filter_by": f"status:=PUBLISHED && featureFlag:=true && category:=[{category_filter}] && indexTags:!=external",
        "per_page": per_page,
    })
    payload = request_json(f"{endpoint}?{query}", context["timeout"], headers=headers)
    for hit in payload.get("hits") or []:
        document = hit.get("document") if isinstance(hit, dict) else None
        if not isinstance(document, dict) or not document.get("urlString"):
            continue
        projects[str(document["urlString"])] = document
    results = []
    for document in projects.values():
        published = parse_datetime(document.get("publishDate"))
        if published and not (context["since"] <= published <= context["as_of"]):
            continue
        url_string = str(document.get("urlString") or "").strip("/")
        project_url = f"https://www.instructables.com/{url_string}/"
        metrics = {
            "featured": bool(document.get("featureFlag")), "favorites": int(document.get("favorites") or 0),
            "views": int(document.get("views") or 0), "i_made_it_count": int(document.get("IMadeItCount") or 0),
        }
        classification = document.get("primaryClassification") or {}
        tags = [str(value) for value in classification.values()] if isinstance(classification, dict) else [str(classification)]
        item = candidate(
            source, document.get("title"), project_url, author=document.get("screenName"), published_at=published,
            metrics=metrics, tags=tags, evidence=[project_url, bootstrap_url],
            raw_score=metrics["views"] + metrics["favorites"] * 10 + metrics["i_made_it_count"] * 20,
        )
        if item:
            results.append(item)
    return results


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_value(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def youtube_watch_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    path_parts = [part for part in parsed.path.split("/") if part]
    video_id = ""
    if parsed.hostname in {"youtu.be", "www.youtu.be"} and path_parts:
        video_id = path_parts[0]
    elif path_parts[:1] in (["shorts"], ["embed"]) and len(path_parts) > 1:
        video_id = path_parts[1]
    elif parsed.path == "/watch":
        video_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
        raise RuntimeError("YouTube candidate URL does not contain a valid video id")
    return f"https://www.youtube.com/watch?v={video_id}"


def enrich_youtube_public(item: dict[str, Any], timeout: int) -> None:
    detail_url = youtube_watch_url(str(item.get("url") or ""))
    raw = request_bytes(detail_url, timeout, headers={"Accept": "text/html,application/xhtml+xml"})
    _, page = parse_public_page(raw)
    video_details = re.search(r'"videoDetails":\{.*?"viewCount":"([0-9]+)"', page, flags=re.DOTALL)
    if video_details is None:
        video_details = re.search(r'"viewCount":"([0-9]+)"', page)
    subscriber_text = re.search(
        r'"subscriberCountText":\{.*?"simpleText":"([0-9][0-9.,]*\s*[KMB]?)\s+subscribers?"',
        page, flags=re.IGNORECASE | re.DOTALL,
    )
    if video_details is None and subscriber_text is None:
        raise RuntimeError("YouTube page exposed neither video views nor channel subscribers")
    metrics = item.setdefault("metrics", {})
    if video_details is not None:
        metrics["views"] = int(video_details.group(1))
    if subscriber_text is not None:
        subscribers = compact_number(subscriber_text.group(1))
        if subscribers is not None:
            metrics["channel_subscribers"] = int(subscribers)
    item["metrics_captured_at"] = iso_z(now_utc())
    item["metric_verification"] = {
        "status": "ok", "source_url": detail_url, "captured_at": item["metrics_captured_at"],
        "ranking_basis": "views/200000 + channel_subscribers/50000",
    }
    item["evidence"] = list(dict.fromkeys((item.get("evidence") or []) + [detail_url]))
    # Normalize both public signals by the editorial heat thresholds. This keeps
    # a subscriber-qualified video comparable with a view-qualified video while
    # preserving views as a useful tie-breaker between videos on one channel.
    item["_raw_score"] = (
        float(metrics.get("views") or 0) / 200_000
        + float(metrics.get("channel_subscribers") or 0) / 50_000
    )


def reddit_old_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if "reddit.com" not in (parsed.hostname or ""):
        raise RuntimeError("Reddit candidate URL is not hosted on reddit.com")
    return urllib.parse.urlunsplit(("https", "old.reddit.com", parsed.path, "", ""))


def enrich_reddit_public(item: dict[str, Any], timeout: int) -> None:
    detail_url = reddit_old_url(str(item.get("url") or ""))
    raw = request_bytes(detail_url, timeout, headers={"Accept": "text/html,application/xhtml+xml"})
    _, page = parse_public_page(raw)
    post_id_match = re.search(r"/comments/([A-Za-z0-9]+)/", detail_url)
    post_id = post_id_match.group(1) if post_id_match else ""
    opening_tag = re.search(rf'<div\b[^>]*\bid="thing_t3_{re.escape(post_id)}"[^>]*>', page, flags=re.IGNORECASE)
    if opening_tag is None:
        opening_tag = re.search(r'<div\b[^>]*\bdata-type="link"[^>]*\bdata-score="[0-9]+"[^>]*>', page, flags=re.IGNORECASE)
    score: int | None = None
    comments: int | None = None
    if opening_tag is not None:
        attributes = dict(re.findall(r'([A-Za-z0-9_-]+)="([^"]*)"', opening_tag.group(0)))
        if str(attributes.get("data-score") or "").isdigit():
            score = int(attributes["data-score"])
        if str(attributes.get("data-comments-count") or "").isdigit():
            comments = int(attributes["data-comments-count"])
    if score is None or comments is None:
        description = re.search(
            r'<meta\s+property="og:description"\s+content="[^"]*?•\s*([0-9,]+)\s+points?\s+and\s+([0-9,]+)\s+comments?',
            page, flags=re.IGNORECASE,
        )
        if description:
            score = int(description.group(1).replace(",", ""))
            comments = int(description.group(2).replace(",", ""))
    if score is None or comments is None:
        raise RuntimeError("Reddit old page exposed neither a complete score nor comment count")
    metrics = item.setdefault("metrics", {})
    metrics.update({"score": score, "comments": comments})
    item["metrics_captured_at"] = iso_z(now_utc())
    item["metric_verification"] = {
        "status": "ok", "source_url": detail_url, "captured_at": item["metrics_captured_at"],
        "ranking_basis": "score + comments",
    }
    item["evidence"] = list(dict.fromkeys((item.get("evidence") or []) + [detail_url]))
    item["_raw_score"] = float(score + comments)


def enrich_rss_details(source: dict[str, Any], results: list[dict[str, Any]], timeout: int) -> None:
    mode = str(source.get("detail_enrichment") or "").strip().lower()
    if not mode:
        return
    enrichers: dict[str, Callable[[dict[str, Any], int], None]] = {
        "youtube_public": enrich_youtube_public,
        "reddit_old": enrich_reddit_public,
    }
    enricher = enrichers.get(mode)
    if enricher is None:
        raise ConfigError(f"unsupported rss detail_enrichment: {mode}")
    def enrich_one(item: dict[str, Any]) -> None:
        try:
            enricher(item, timeout)
        except Exception as exc:
            # Keep the discovery candidate for audit, but place unverifiable
            # metrics behind every successfully verified heat score.
            item["_raw_score"] = -1.0
            item["metric_verification"] = {
                "status": "error", "captured_at": iso_z(now_utc()), "detail": clean_text(str(exc), 300),
            }

    worker_count = max(1, min(8, int(source.get("detail_workers") or 4), len(results)))
    if worker_count == 1:
        for item in results:
            enrich_one(item)
        return
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="maker-detail") as executor:
        list(executor.map(enrich_one, results))


def collect_rss(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    feed_urls = source.get("feed_urls") or [source.get("feed_url")]
    if not isinstance(feed_urls, list) or not feed_urls:
        raise ConfigError("rss source requires feed_url or a non-empty feed_urls array")
    urls = [str(value or "") for value in feed_urls]
    if any(not value.startswith(("http://", "https://")) for value in urls):
        raise ConfigError("rss feed URLs must use http(s)")
    required_keywords = [str(word).lower() for word in source.get("keywords") or []]
    static_metrics = source.get("static_metrics") or {}
    if not isinstance(static_metrics, dict):
        raise ConfigError("rss static_metrics must be an object")
    results = []
    failures = []
    for feed_url in urls:
        try:
            raw = request_bytes(feed_url, context["timeout"])
            root = ET.fromstring(raw)
        except (RuntimeError, ET.ParseError) as exc:
            failures.append(f"{urllib.parse.urlsplit(feed_url).hostname}: {exc}")
            continue
        entries = [entry for entry in root.iter() if local_name(entry.tag) in {"item", "entry"}]
        for feed_position, entry in enumerate(entries):
            title = child_value(entry, {"title"})
            summary = child_value(entry, {"description", "summary", "content", "encoded"})
            haystack = f"{clean_text(title)} {clean_text(summary)}".lower()
            if required_keywords and not any(word in haystack for word in required_keywords):
                continue
            link = child_value(entry, {"link"})
            if not link:
                for child in list(entry):
                    if local_name(child.tag) == "link" and child.attrib.get("href"):
                        link = child.attrib["href"]
                        break
            published = child_value(entry, {"pubdate", "published", "updated", "date"})
            parsed = parse_datetime(published)
            if parsed and not (context["since"] <= parsed <= context["as_of"]):
                continue
            author = child_value(entry, {"author", "creator"})
            keyword_hits = sum(1 for word in context["keywords"] if word in haystack)
            age_days = max(0.0, (context["as_of"] - parsed).total_seconds() / 86400) if parsed else context["lookback_days"]
            feed_order_score = max(0, 25 - feed_position)
            item = candidate(
                source, title, link, summary=summary, author=author, published_at=parsed,
                metrics={"keyword_hits": keyword_hits, "feed_host": urllib.parse.urlsplit(feed_url).hostname, **static_metrics}, evidence=[link, feed_url],
                raw_score=keyword_hits * 10 + max(0, context["lookback_days"] - age_days) + feed_order_score,
            )
            if item:
                results.append(item)
    if failures and not results:
        raise RuntimeError("all RSS feeds failed: " + "; ".join(failures))
    if source.get("detail_enrichment"):
        detail_limit = int(source.get("detail_candidate_limit") or max(20, int(context.get("limit") or 5) * 4))
        if detail_limit < 1:
            raise ConfigError("rss detail_candidate_limit must be at least 1")
        results = sorted(
            results,
            key=lambda item: (item.get("_raw_score", 0.0), item.get("published_at") or ""),
            reverse=True,
        )[:detail_limit]
    enrich_rss_details(source, results, context["timeout"])
    return results


def collect_manual(source: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    raw_path = source.get("path")
    if not raw_path:
        raise ConfigError("manual source requires path")
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = context["config_dir"] / path
    if not path.exists():
        raise ConfigError(f"manual source file not found: {path}")
    payload = read_json(path)
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ConfigError("manual source must be a JSON array or object with items array")
    results = []
    for rank, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        published = parse_datetime(raw.get("published_at"))
        if published and not (context["since"] <= published <= context["as_of"]):
            continue
        metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
        raw_score = float(raw.get("source_score") or max(0, len(items) - rank))
        item = candidate(
            source, raw.get("title"), raw.get("url"), summary=raw.get("summary"), author=raw.get("author"),
            published_at=published, metrics=metrics, tags=raw.get("tags") or [], evidence=raw.get("evidence") or [raw.get("url")], raw_score=raw_score,
            metrics_captured_at=raw.get("metrics_captured_at"),
        )
        if item:
            results.append(item)
    return results


COLLECTORS: dict[str, Callable[[dict[str, Any], dict[str, Any]], list[dict[str, Any]]]] = {
    "github": collect_github,
    "youtube": collect_youtube,
    "reddit": collect_reddit,
    "instagram": collect_instagram,
    "rss": collect_rss,
    "manual": collect_manual,
    "web_html": collect_web_html,
    "instructables_web": collect_instructables_web,
    "kickstarter_kicktraq": collect_kickstarter_kicktraq,
    "indiegogo_public": collect_indiegogo_public,
}


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("sources"), list):
        raise ConfigError("config.sources must be an array")
    top_per_source = int(config.get("top_per_source", 5))
    final_top = int(config.get("final_top", 15))
    if not 1 <= top_per_source <= 50:
        raise ConfigError("top_per_source must be between 1 and 50")
    if not 1 <= final_top <= 100:
        raise ConfigError("final_top must be between 1 and 100")
    seen = set()
    for source in config["sources"]:
        if not isinstance(source, dict) or not source.get("id"):
            raise ConfigError("every source requires a non-empty id")
        if source["id"] in seen:
            raise ConfigError(f"duplicate source id: {source['id']}")
        seen.add(source["id"])
        if source.get("type") not in SUPPORTED_TYPES:
            raise ConfigError(f"unsupported source type for {source['id']}: {source.get('type')}")


def load_config(path: Path) -> dict[str, Any]:
    config = read_json(path)
    if not isinstance(config, dict):
        raise ConfigError("config root must be an object")
    validate_config(config)
    return config


def merge_duplicate(primary: dict[str, Any], duplicate: dict[str, Any]) -> None:
    if duplicate["url"] != primary["url"]:
        primary["also_seen_on"].append({"platform": duplicate["platform"], "source_id": duplicate["source_id"], "url": duplicate["url"]})
    primary["evidence"] = list(dict.fromkeys(primary.get("evidence", []) + duplicate.get("evidence", [])))
    primary["tags"] = sorted(set(primary.get("tags", []) + duplicate.get("tags", [])))
    if len(duplicate.get("summary", "")) > len(primary.get("summary", "")):
        primary["summary"] = duplicate["summary"]


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    by_url: dict[str, dict[str, Any]] = {}
    for item in sorted(items, key=lambda row: (row.get("source_percentile", 0), len(row.get("evidence", []))), reverse=True):
        url_key = canonical_url(item["url"])
        duplicate = by_url.get(url_key)
        if duplicate is None:
            title_key = normalized_title(item["title"])
            for existing in unique:
                existing_key = normalized_title(existing["title"])
                if min(len(title_key), len(existing_key)) >= 16 and SequenceMatcher(None, title_key, existing_key).ratio() >= 0.9:
                    duplicate = existing
                    break
        if duplicate is not None:
            merge_duplicate(duplicate, item)
        else:
            unique.append(item)
            by_url[url_key] = item
    return unique


def heuristic_components(item: dict[str, Any], as_of: datetime, keywords: list[str]) -> dict[str, float]:
    text = f"{item.get('title', '')} {item.get('summary', '')} {' '.join(item.get('tags', []))}".lower()
    relevance_hits = sum(1 for word in keywords if word.lower() in text)
    relevance = min(25.0, 8.0 + relevance_hits * 4.0)
    engagement = 5.0 + 20.0 * float(item.get("source_percentile", 0.0))
    published = parse_datetime(item.get("published_at"))
    if published:
        age_days = max(0.0, (as_of - published).total_seconds() / 86400)
        freshness = max(0.0, 15.0 * (1.0 - age_days / 14.0))
    else:
        freshness = 5.0
    evidence = min(15.0, 5.0 + len(item.get("evidence", [])) * 3.0 + (2.0 if item.get("summary") else 0.0))
    maker_terms = ["stl", "step", "cad", "openscad", "build", "tutorial", "printable", "open source", "how to", "files"]
    maker_value = min(20.0, 5.0 + sum(3.0 for term in maker_terms if term in text))
    return {
        "relevance": round(relevance, 2),
        "engagement_within_source": round(engagement, 2),
        "freshness": round(freshness, 2),
        "evidence_quality": round(evidence, 2),
        "maker_value": round(maker_value, 2),
    }


def collect_envelope(config_path: Path, as_of: datetime, source_ids: set[str] | None = None) -> dict[str, Any]:
    config = load_config(config_path)
    lookback_days = int(config.get("lookback_days", 7))
    limit = int(config.get("top_per_source", 5))
    keywords = [str(word) for word in config.get("keywords") or []]
    context = {
        "as_of": as_of, "since": as_of - timedelta(days=lookback_days), "lookback_days": lookback_days,
        "limit": limit, "timeout": int(config.get("request_timeout_seconds", 20)), "keywords": [word.lower() for word in keywords],
        "config_dir": config_path.resolve().parent,
    }
    collected, statuses = [], []
    for source in config["sources"]:
        if source_ids and str(source["id"]) not in source_ids:
            continue
        if not source.get("enabled", True):
            statuses.append({"source_id": source["id"], "platform": source.get("platform", source["id"]), "status": "disabled", "count": 0})
            continue
        try:
            raw_items = COLLECTORS[source["type"]](source, context)
            items = cap_and_rank(raw_items, limit)
            collected.extend(items)
            statuses.append({"source_id": source["id"], "platform": source.get("platform", source["id"]), "status": "ok", "count": len(items)})
        except MissingCredential as exc:
            statuses.append({"source_id": source["id"], "platform": source.get("platform", source["id"]), "status": "skipped", "count": 0, "detail": str(exc)})
        except AccessBlocked as exc:
            statuses.append({"source_id": source["id"], "platform": source.get("platform", source["id"]), "status": "blocked", "count": 0, "detail": str(exc)})
        except Exception as exc:  # isolate provider failures so partial reports remain useful
            statuses.append({"source_id": source["id"], "platform": source.get("platform", source["id"]), "status": "error", "count": 0, "detail": str(exc)})
    unique = deduplicate(collected)
    for item in unique:
        components = heuristic_components(item, as_of, keywords)
        item["heuristic_score"] = round(sum(components.values()), 2)
        item["heuristic_breakdown"] = components
    unique.sort(key=lambda item: (item["heuristic_score"], item.get("published_at") or ""), reverse=True)
    return {
        "schema_version": 1,
        "generated_at": iso_z(now_utc()),
        "as_of": iso_z(as_of),
        "window_start": iso_z(context["since"]),
        "selection_method": "unranked-candidates",
        "config_summary": {"lookback_days": lookback_days, "top_per_source": limit, "final_top": int(config.get("final_top", 15)), "keywords": keywords},
        "source_status": statuses,
        "items": unique,
    }


def baseline_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    limit = int((payload.get("config_summary") or {}).get("final_top", 15))
    items = sorted(payload.get("items", []), key=lambda item: item.get("heuristic_score", 0), reverse=True)[:limit]
    for index, item in enumerate(items, 1):
        item["rank"] = index
        item["ai_score"] = item.get("heuristic_score", 0)
        item["score_breakdown"] = item.get("heuristic_breakdown", {})
        item["why_selected"] = "Deterministic baseline based on relevance, same-source engagement, freshness, evidence, and maker value."
        item["risks_or_unknowns"] = ["Not yet reviewed by the AI editorial comparison."]
    result = dict(payload)
    result["selection_method"] = "heuristic-v1"
    result["items"] = items
    return result


def editorial_envelope(payload: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    source_items = {item.get("id"): item for item in payload.get("items", []) if isinstance(item, dict)}
    decision_items = decisions.get("items")
    if not isinstance(decision_items, list):
        raise ConfigError("decisions.items must be an array")
    limit = int((payload.get("config_summary") or {}).get("final_top", 15))
    if len(decision_items) > limit:
        raise ConfigError(f"decisions has {len(decision_items)} items but final_top is {limit}")
    selected, seen = [], set()
    editorial_fields = ("ai_score", "score_breakdown", "why_selected", "risks_or_unknowns")
    for rank, decision in enumerate(decision_items, 1):
        if not isinstance(decision, dict) or not decision.get("id"):
            raise ConfigError(f"decision {rank} requires an id")
        candidate_id = decision["id"]
        if candidate_id in seen:
            raise ConfigError(f"duplicate decision id: {candidate_id}")
        if candidate_id not in source_items:
            raise ConfigError(f"decision references unknown candidate id: {candidate_id}")
        missing = [field for field in editorial_fields if field not in decision]
        if missing:
            raise ConfigError(f"decision {candidate_id} missing: {', '.join(missing)}")
        merged = dict(source_items[candidate_id])
        merged.update({field: decision[field] for field in editorial_fields})
        merged["rank"] = rank
        selected.append(merged)
        seen.add(candidate_id)
    result = dict(payload)
    result["selection_method"] = str(decisions.get("selection_method") or "codex-ai-rubric-v1")
    result["items"] = selected
    errors = validate_ranking(result)
    if errors:
        raise ConfigError("editorial ranking validation failed: " + "; ".join(errors))
    return result


def validate_ranking(payload: dict[str, Any]) -> list[str]:
    errors = []
    items = payload.get("items")
    if not isinstance(items, list):
        return ["items must be an array"]
    limit = int((payload.get("config_summary") or {}).get("final_top", 15))
    if len(items) > limit:
        errors.append(f"ranking has {len(items)} items but final_top is {limit}")
    ids, ranks = set(), []
    for index, item in enumerate(items, 1):
        label = f"item {index}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in ("id", "title", "url", "platform", "rank", "ai_score", "score_breakdown", "why_selected", "risks_or_unknowns"):
            if field not in item:
                errors.append(f"{label} missing {field}")
        if item.get("id") in ids:
            errors.append(f"duplicate candidate id {item.get('id')}")
        ids.add(item.get("id"))
        if isinstance(item.get("rank"), int):
            ranks.append(item["rank"])
        score = item.get("ai_score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            errors.append(f"{label} ai_score must be between 0 and 100")
    if ranks and sorted(ranks) != list(range(1, len(items) + 1)):
        errors.append("ranks must be unique and contiguous starting at 1")
    return errors


def metric_text(metrics: dict[str, Any]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in metrics.items() if value not in (None, "")) or "无公开指标"


def render_markdown(payload: dict[str, Any]) -> str:
    items = sorted(payload.get("items", []), key=lambda item: item.get("rank", 9999))
    as_of = payload.get("as_of", "unknown")
    lines = [
        f"# 3D 打印 Maker 周报 · Top {len(items)}",
        "",
        f"统计截止：{as_of}  ",
        f"评选方式：`{payload.get('selection_method', 'unknown')}`",
        "",
        "## 来源覆盖",
        "",
        "| 来源 | 状态 | 候选数 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for status in payload.get("source_status", []):
        detail = str(status.get("detail", "")).replace("|", "\\|")
        lines.append(f"| {status.get('platform', status.get('source_id'))} | {status.get('status')} | {status.get('count', 0)} | {detail} |")
    lines.extend(["", "## 本周项目", ""])
    for index, item in enumerate(items, 1):
        rank = item.get("rank", index)
        score = item.get("ai_score", item.get("heuristic_score", 0))
        lines.extend([
            f"### {rank}. [{item.get('title', 'Untitled')}]({item.get('url', '')})",
            "",
            f"- 平台：{item.get('platform', '')}",
            f"- 评分：{score}/100",
            f"- 发布：{item.get('published_at') or '未知'}",
            f"- 指标：{metric_text(item.get('metrics') or {})}",
            f"- 入选理由：{item.get('why_selected') or item.get('summary') or '待编辑'}",
        ])
        risks = item.get("risks_or_unknowns") or []
        if risks:
            lines.append(f"- 待核实：{'；'.join(str(value) for value in risks)}")
        if item.get("also_seen_on"):
            links = ", ".join(f"[{seen.get('platform')}]({seen.get('url')})" for seen in item["also_seen_on"])
            lines.append(f"- 其他来源：{links}")
        lines.append("")
    if len(items) < int((payload.get("config_summary") or {}).get("final_top", 15)):
        lines.extend(["> 本期可信候选不足 15 条，因此没有用低质量条目补位。", ""])
    lines.extend(["## 方法说明", "", "各来源先独立取 Top 5，再进行跨平台去重与统一评选。平台热度只在同一来源内比较；评分同时考虑可复现性、创新、证据、时效和社区价值。", ""])
    return "\n".join(lines)


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return now_utc()
    parsed = parse_datetime(value)
    if parsed is None:
        raise ConfigError("--as-of must be ISO 8601, for example 2026-08-12T00:00:00Z")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="collect and normalize source candidates")
    collect.add_argument("--config", required=True, type=Path)
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument("--as-of")
    collect.add_argument("--source", action="append", help="collect only this source id; repeat for multiple sources")
    baseline = sub.add_parser("baseline", help="create a deterministic non-AI ranking")
    baseline.add_argument("--input", required=True, type=Path)
    baseline.add_argument("--output", required=True, type=Path)
    editorial = sub.add_parser("editorial", help="merge compact AI decisions with collected candidates")
    editorial.add_argument("--input", required=True, type=Path)
    editorial.add_argument("--decisions", required=True, type=Path)
    editorial.add_argument("--output", required=True, type=Path)
    validate = sub.add_parser("validate-ranking", help="validate a ranked JSON envelope")
    validate.add_argument("--input", required=True, type=Path)
    render = sub.add_parser("render", help="render ranked JSON as Markdown")
    render.add_argument("--input", required=True, type=Path)
    render.add_argument("--output", required=True, type=Path)
    run = sub.add_parser("run", help="collect, heuristic-rank, and render")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--as-of")
    run.add_argument("--source", action="append", help="collect only this source id; repeat for multiple sources")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "collect":
            payload = collect_envelope(args.config, parse_as_of(args.as_of), set(args.source or []))
            write_json(args.output, payload)
            print(f"collected {len(payload['items'])} unique candidates -> {args.output}")
        elif args.command == "baseline":
            payload = baseline_envelope(read_json(args.input))
            write_json(args.output, payload)
            print(f"ranked {len(payload['items'])} candidates with heuristic-v1 -> {args.output}")
        elif args.command == "editorial":
            payload = editorial_envelope(read_json(args.input), read_json(args.decisions))
            write_json(args.output, payload)
            print(f"merged {len(payload['items'])} AI editorial decisions -> {args.output}")
        elif args.command == "validate-ranking":
            errors = validate_ranking(read_json(args.input))
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 2
            print(f"ranking is valid: {args.input}")
        elif args.command == "render":
            payload = read_json(args.input)
            errors = validate_ranking(payload)
            if errors:
                raise ConfigError("ranking validation failed: " + "; ".join(errors))
            write_text(args.output, render_markdown(payload))
            print(f"rendered report -> {args.output}")
        elif args.command == "run":
            collected = collect_envelope(args.config, parse_as_of(args.as_of), set(args.source or []))
            ranked = baseline_envelope(collected)
            candidates_path = args.output_dir / "candidates.json"
            ranked_path = args.output_dir / "ranked.json"
            report_path = args.output_dir / "maker-weekly.md"
            write_json(candidates_path, collected)
            write_json(ranked_path, ranked)
            write_text(report_path, render_markdown(ranked))
            print(f"wrote candidates, baseline ranking, and report to {args.output_dir}")
        return 0
    except (ConfigError, json.JSONDecodeError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
