#!/usr/bin/env python3
"""Enforce Maker Weekly natural-week, first-publication, gate, and report rules."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import maker_weekly


CATEGORIES = {"社会价值", "极客硬核", "艺术科技交互", "生活方式社群"}
ENTRY_TYPES = {"first_release"}
EXCELLENCE_DIRECTIONS = {"technical_engineering", "creative_play", "value_resonance"}
PROJECT_GATE_KEYS = {"multi_stage", "significant_investment", "real_challenge", "real_motivation"}
NECESSARY_KEYS = {"small_team_led", "what_and_why", "built_or_substantive_progress"}
RED_LINE_KEYS = {"original_creation", "actually_built", "not_mature_mass_product"}
SCORE_KEYS = {
    "creation_investment", "process_visibility", "impact_resonance", "completion",
    "cross_platform_continuity", "diversity_breakout",
}
EDITORIAL_MEDIA = {"hackaday", "make magazine", "the verge", "tom's hardware", "tom’s hardware"}


class StrictError(ValueError):
    pass


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise StrictError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def week_bounds(start_text: str, end_text: str) -> tuple[datetime, datetime]:
    start_day, end_day = parse_date(start_text), parse_date(end_text)
    if start_day.weekday() != 0:
        raise StrictError("week-start must be a Monday")
    if end_day.weekday() != 6 or end_day - start_day != timedelta(days=6):
        raise StrictError("week-end must be the Sunday six days after week-start")
    start = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(end_day, time.max.replace(microsecond=0), tzinfo=timezone.utc)
    return start, end


def last_complete_week(today: date) -> dict[str, str]:
    current_monday = today - timedelta(days=today.weekday())
    end_day = current_monday - timedelta(days=1)
    start_day = end_day - timedelta(days=6)
    return {
        "week_start": start_day.isoformat(),
        "week_end": end_day.isoformat(),
        "execution_date": today.isoformat(),
        "timezone": "UTC",
    }


def number(metrics: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = metrics.get(name)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", "").replace("$", ""))
            except ValueError:
                pass
    return None


def heat_gate(item: dict[str, Any]) -> dict[str, Any]:
    platform = str(item.get("platform") or "").lower().strip()
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    result: dict[str, Any] = {"status": "unknown", "observed": "无法从候选数据核验", "threshold": "平台未映射", "evidence_url": item.get("url")}
    if "kickstarter" in platform or "indiegogo" in platform:
        pledged, backers = number(metrics, "usd_pledged", "pledged_usd"), number(metrics, "backers")
        result.update(threshold="US$20,000 或 200 名支持者", observed=f"USD={pledged}; backers={backers}")
        if pledged is not None or backers is not None:
            result["status"] = "pass" if (pledged or 0) >= 20000 or (backers or 0) >= 200 else "fail"
    elif "github" in platform:
        stars = number(metrics, "stars")
        result.update(threshold="1,000 Stars", observed=f"stars={stars}")
        if stars is not None:
            result["status"] = "pass" if stars >= 1000 else "fail"
    elif "youtube" in platform:
        views, subscribers = number(metrics, "views"), number(metrics, "channel_subscribers", "subscribers")
        result.update(threshold="200,000 播放或频道 50,000 订阅", observed=f"views={views}; subscribers={subscribers}")
        if views is not None or subscribers is not None:
            result["status"] = "pass" if (views or 0) >= 200000 or (subscribers or 0) >= 50000 else "fail"
    elif "reddit" in platform:
        score, comments = number(metrics, "upvotes", "score"), number(metrics, "comments")
        result.update(threshold="公开点赞/分数与评论合计 5,000", observed=f"score={score}; comments={comments}")
        if score is not None and comments is not None:
            result["status"] = "pass" if score + comments >= 5000 else "fail"
    elif platform in {"x", "x / twitter", "twitter", "instagram"}:
        interactions = number(metrics, "interactions")
        if interactions is None:
            values = [number(metrics, key) for key in ("likes", "comments", "reposts", "replies", "quotes")]
            interactions = sum(value or 0 for value in values) if any(value is not None for value in values) else None
        result.update(threshold="公开互动 5,000", observed=f"interactions={interactions}")
        if interactions is not None:
            result["status"] = "pass" if interactions >= 5000 else "fail"
    elif platform in EDITORIAL_MEDIA:
        result.update(status="pass", threshold="平台正式报道", observed="候选来自该媒体的正式文章")
    elif "hackster" in platform:
        featured = metrics.get("featured")
        result.update(threshold="精选或编辑推荐", observed=f"featured={featured}")
        if isinstance(featured, bool):
            result["status"] = "pass" if featured else "fail"
    elif "instructables" in platform:
        featured = metrics.get("featured")
        result.update(threshold="Featured", observed=f"featured={featured}")
        if isinstance(featured, bool):
            result["status"] = "pass" if featured else "fail"
    result["captured_at"] = item.get("metrics_captured_at")
    return result


def annotate_time(item: dict[str, Any], start: datetime, end: datetime) -> dict[str, Any]:
    published = maker_weekly.parse_datetime(item.get("published_at"))
    if published and start <= published <= end:
        return {"status": "pass", "entry_type": "first_release", "reason": "原始页面发布时间位于目标自然周"}
    if published:
        return {"status": "fail", "entry_type": None, "reason": "原始发布时间不在目标自然周；旧项目本周更新或重新传播也不接受"}
    return {"status": "fail", "entry_type": None, "reason": "无法核验原始发布时间；严格本周首发规则下淘汰"}


def prepare_payload(payload: dict[str, Any], start: datetime, end: datetime) -> dict[str, Any]:
    result = deepcopy(payload)
    for item in result.get("items", []):
        item["canonical_url"] = maker_weekly.canonical_url(str(item.get("url") or ""))
        item["heat_gate"] = maker_weekly.evaluate_heat_gate(item, end)
        item["time_gate"] = annotate_time(item, start, end)
    statuses = result.get("source_status") or []
    stage_counts = result.get("stage_counts") if isinstance(result.get("stage_counts"), dict) else {}
    covered = {str(status.get("platform") or "").lower(): status.get("status") for status in statuses}
    missing_social = [name for name in ("YouTube", "Reddit") if covered.get(name.lower()) not in {"ok", "empty"}]
    result["week"] = {
        "start": maker_weekly.iso_z(start), "end": maker_weekly.iso_z(end),
        "execution_date": datetime.now(timezone.utc).date().isoformat(), "timezone": "UTC",
        "strict_current_week_only": True,
    }
    result["issue_stats"] = {
        "platforms_attempted": len(statuses),
        "platforms_searched": len([status for status in statuses if status.get("status") in {"ok", "empty"}]),
        "platforms_failed": len([status for status in statuses if status.get("status") in {"blocked", "error", "skipped"}]),
        "raw_discoveries": int(stage_counts.get("raw_discoveries", len(result.get("items", [])))),
        "physical_prefilter_passed": int(stage_counts.get("physical_prefilter_passed", len(result.get("items", [])))),
        "heat_gate_passed": int(stage_counts.get("heat_gate_passed", len(result.get("items", [])))),
        "initial_candidates": int(stage_counts.get("editorial_candidates", len(result.get("items", [])))),
        "coverage_warning": f"本期平台覆盖不完整：{'/'.join(missing_social)} 未检索" if missing_social else "",
    }
    result["selection_method"] = "strict-research-pending"
    return result


def make_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    week = payload.get("week") or {}
    items = []
    for item in payload.get("items", []):
        captured_at = maker_weekly.iso_z(datetime.now(timezone.utc))
        gate = deepcopy(item.get("heat_gate") or heat_gate(item))
        if not gate.get("captured_at"):
            gate["captured_at"] = captured_at
        items.append({
            "id": item.get("id"), "url": item.get("url"), "canonical_url": item.get("canonical_url") or maker_weekly.canonical_url(str(item.get("url") or "")),
            "platform": item.get("platform"), "title": item.get("title"), "published_at": item.get("published_at"),
            "metrics": item.get("metrics") or {}, "heat_gate": gate,
            "captured_at": captured_at,
        })
    return {"schema_version": 1, "snapshot_date": str(week.get("end", ""))[:10], "week": week, "items": items}


def is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def passed_evidence_map(value: Any, required: set[str], label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    for key in required:
        entry = value.get(key)
        if not isinstance(entry, dict) or entry.get("passed") is not True or not str(entry.get("evidence") or "").strip():
            errors.append(f"{label}.{key} must pass with concrete evidence")


def validate_decision(decision: dict[str, Any], candidate: dict[str, Any], start: datetime, end: datetime) -> list[str]:
    errors: list[str] = []
    if candidate.get("physical_gate", {}).get("status") != "pass":
        errors.append("candidate must pass Make Something Gate before editorial review")
    if candidate.get("time_gate", {}).get("status") != "pass":
        errors.append("candidate must pass the pipeline time gate")
    if candidate.get("heat_gate", {}).get("status") != "pass":
        errors.append("candidate must pass the pipeline platform heat gate")
    if decision.get("category") not in CATEGORIES:
        errors.append("invalid category")
    entry_type = decision.get("entry_type")
    if entry_type not in ENTRY_TYPES:
        errors.append("entry_type must be first_release")
    published = maker_weekly.parse_datetime(candidate.get("published_at"))
    if entry_type == "first_release" and not (published and start <= published <= end):
        errors.append("first_release requires an original publication date inside the target week")
    gate = decision.get("heat_gate")
    if not isinstance(gate, dict) or gate.get("status") != "pass" or not gate.get("observed") or not gate.get("threshold") or not gate.get("captured_at") or not is_http_url(gate.get("evidence_url")):
        errors.append("heat_gate must pass with observed value, threshold, capture time, and evidence URL")
    elif maker_weekly.parse_datetime(gate.get("captured_at")) is None:
        errors.append("heat_gate capture time must be a valid ISO-8601 observation time")
    category_gate = decision.get("category_gate")
    if not isinstance(category_gate, dict) or category_gate.get("passed") is not True or not category_gate.get("evidence") or not is_http_url(category_gate.get("evidence_url")):
        errors.append("category_gate must prove a physical core with an evidence URL")
    project_gate = decision.get("project_gate_evidence")
    if not isinstance(project_gate, dict):
        errors.append("project_gate_evidence must be an object")
    else:
        satisfied = sum(bool(str(project_gate.get(key) or "").strip()) for key in PROJECT_GATE_KEYS)
        if satisfied < 3:
            errors.append("project gate requires evidence for at least three of four dimensions")
    passed_evidence_map(decision.get("necessary_conditions"), NECESSARY_KEYS, "necessary_conditions", errors)
    passed_evidence_map(decision.get("red_lines"), RED_LINE_KEYS, "red_lines", errors)
    excellence = decision.get("excellence")
    if not isinstance(excellence, dict) or excellence.get("direction") not in EXCELLENCE_DIRECTIONS or len(str(excellence.get("benchmark_statement") or "").strip()) < 20 or not is_http_url(excellence.get("evidence_url")):
        errors.append("excellence requires a valid direction, concrete benchmark statement, and evidence URL")
    creator = decision.get("creator")
    if not isinstance(creator, dict) or not creator.get("name") or not creator.get("background") or not any(is_http_url(url) for url in creator.get("evidence_urls") or []):
        errors.append("creator requires name, verifiable background, and evidence URL")
    for field in ("first_seen_date", "project_description", "build_path", "selection_reason"):
        if not str(decision.get(field) or "").strip():
            errors.append(f"missing {field}")
    scores = decision.get("scores")
    if not isinstance(scores, dict) or set(scores) != SCORE_KEYS:
        errors.append("scores must contain exactly the six required dimensions")
    else:
        for key, value in scores.items():
            if not isinstance(value, int) or not 1 <= value <= 5:
                errors.append(f"scores.{key} must be an integer from 1 to 5")
    invitation = decision.get("invitation_signal")
    if invitation is not None and (not isinstance(invitation, dict) or not invitation.get("text") or not is_http_url(invitation.get("evidence_url"))):
        errors.append("invitation_signal requires explicit text and evidence URL")
    return errors


def select_payload(researched: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    week = researched.get("week") or {}
    start = maker_weekly.parse_datetime(week.get("start"))
    end = maker_weekly.parse_datetime(week.get("end"))
    if not start or not end:
        raise StrictError("researched input is missing valid week bounds")
    source = {item.get("id"): item for item in researched.get("items", []) if isinstance(item, dict)}
    decision_items = decisions.get("items")
    if not isinstance(decision_items, list):
        raise StrictError("decisions.items must be an array")
    if len(decision_items) > 15:
        raise StrictError("final selection cannot exceed 15 projects")
    selected, seen_ids, seen_urls, all_errors = [], set(), set(), []
    for index, decision in enumerate(decision_items, 1):
        candidate_id = decision.get("id") if isinstance(decision, dict) else None
        candidate = source.get(candidate_id)
        if candidate is None:
            all_errors.append(f"decision {index}: unknown candidate id {candidate_id}")
            continue
        if candidate_id in seen_ids:
            all_errors.append(f"decision {index}: duplicate candidate id {candidate_id}")
            continue
        canonical = candidate.get("canonical_url") or maker_weekly.canonical_url(str(candidate.get("url") or ""))
        if canonical in seen_urls:
            all_errors.append(f"decision {index}: duplicate canonical project URL")
            continue
        errors = validate_decision(decision, candidate, start, end)
        if errors:
            all_errors.extend(f"decision {candidate_id}: {error}" for error in errors)
            continue
        merged = deepcopy(candidate)
        merged.update(deepcopy(decision))
        merged["total_score"] = sum(decision["scores"].values())
        selected.append(merged)
        seen_ids.add(candidate_id)
        seen_urls.add(canonical)
    if all_errors:
        raise StrictError("\n".join(all_errors))
    selected.sort(key=lambda item: (
        item["total_score"], item["scores"]["creation_investment"], item["scores"]["completion"],
        len(item["excellence"]["benchmark_statement"]), len(item.get("evidence", [])),
    ), reverse=True)
    for rank, item in enumerate(selected, 1):
        item["rank"] = rank
    stats = dict(researched.get("issue_stats") or {})
    stats.update({
        "selected_projects": len(selected),
        "first_release_count": sum(item["entry_type"] == "first_release" for item in selected),
    })
    return {
        "schema_version": 1, "selection_method": "maker-weekly-strict-v1", "week": week,
        "issue_stats": stats, "source_status": researched.get("source_status") or [], "items": selected,
    }


def validate_final(payload: dict[str, Any]) -> list[str]:
    errors = []
    if payload.get("selection_method") != "maker-weekly-strict-v1":
        errors.append("selection_method must be maker-weekly-strict-v1")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > 15:
        errors.append("items must be an array with at most 15 projects")
        return errors
    totals = [item.get("total_score") for item in items if isinstance(item, dict)]
    if any(not isinstance(total, int) or not 6 <= total <= 30 for total in totals):
        errors.append("every total_score must be an integer from 6 to 30")
    if totals != sorted(totals, reverse=True):
        errors.append("items must be sorted by total_score descending")
    if [item.get("rank") for item in items] != list(range(1, len(items) + 1)):
        errors.append("ranks must be contiguous from 1")
    for index, item in enumerate(items, 1):
        if item.get("physical_gate", {}).get("status") != "pass" or item.get("time_gate", {}).get("status") != "pass" or item.get("heat_gate", {}).get("status") != "pass":
            errors.append(f"item {index} must retain passing physical, time, and heat gates")
    stats = payload.get("issue_stats") or {}
    if stats.get("selected_projects") != len(items):
        errors.append("issue_stats.selected_projects does not match items")
    return errors


def direction_label(value: str) -> str:
    return {"technical_engineering": "技术工程", "creative_play": "创意玩法", "value_resonance": "价值共鸣"}.get(value, value)


def entry_label(value: str) -> str:
    return {"first_release": "本周首发"}.get(value, value)


def render(payload: dict[str, Any]) -> str:
    errors = validate_final(payload)
    if errors:
        raise StrictError("; ".join(errors))
    week, stats = payload.get("week") or {}, payload.get("issue_stats") or {}
    lines = [
        "# Maker 周报：全球 Maker Project Top {}".format(len(payload.get("items", []))), "",
        f"- 本期时间范围：{week.get('start')} 至 {week.get('end')}（{week.get('timezone', 'UTC')}）",
        f"- 共检索平台：{stats.get('platforms_searched', 0)}",
        f"- 尝试平台：{stats.get('platforms_attempted', stats.get('platforms_searched', 0))}；失败或受限：{stats.get('platforms_failed', 0)}",
        f"- 初始候选数量：{stats.get('initial_candidates', 0)}",
        f"- 原始发现：{stats.get('raw_discoveries', stats.get('initial_candidates', 0))}；通过物理预筛：{stats.get('physical_prefilter_passed', stats.get('initial_candidates', 0))}；通过热度门：{stats.get('heat_gate_passed', stats.get('initial_candidates', 0))}",
        f"- 通过全部标准：{stats.get('selected_projects', 0)}",
        f"- 本周首发：{stats.get('first_release_count', 0)}", "",
    ]
    if stats.get("coverage_warning"):
        lines.insert(2, f"> **{stats['coverage_warning']}**")
        lines.insert(3, "")
    for item in payload.get("items", []):
        decision = item
        creator, gate, excellence = decision["creator"], decision["heat_gate"], decision["excellence"]
        lines.extend([
            f"## {decision['rank']:02d}. {decision['title']}", "",
            f"- 原始链接：{decision['url']}",
            f"- 辅助证据：{', '.join(decision.get('auxiliary_evidence') or decision.get('evidence') or []) or '无'}",
            f"- 类别：{decision['category']}",
            f"- 入选类型：{entry_label(decision['entry_type'])}",
            f"- 首次发现日期：{decision['first_seen_date']}",
            f"- 热度（执行时观测）：{gate['observed']}；门槛：{gate['threshold']}；抓取：{gate['captured_at']}；证据：{gate['evidence_url']}",
        ])
        lines.extend([
            f"- 创作者：{creator['name']}；{creator['background']}；证据：{', '.join(creator['evidence_urls'])}",
            f"- 项目简介：{decision['project_description']}",
            f"- 制作与技术路径：{decision['build_path']}",
            "- 项目门证据：",
        ])
        labels = {"multi_stage": "多步骤多阶段", "significant_investment": "投入大耗时长", "real_challenge": "真实挑战", "real_motivation": "真实命题驱动"}
        for key, value in decision["project_gate_evidence"].items():
            if value:
                lines.append(f"  - {labels.get(key, key)}：{value}")
        lines.extend([
            f"- 卓越方向：{direction_label(excellence['direction'])}",
            f"- 卓越对标话术：“{excellence['benchmark_statement']}”",
            "- 三条红线检查：",
            f"  - 原创投入：通过；{decision['red_lines']['original_creation']['evidence']}",
            f"  - 已经落地：通过；{decision['red_lines']['actually_built']['evidence']}",
            f"  - 非成熟大公司量产：通过；{decision['red_lines']['not_mature_mass_product']['evidence']}",
            "- 评分：",
            f"  - 创造投入：{decision['scores']['creation_investment']}/5",
            f"  - 过程可见性：{decision['scores']['process_visibility']}/5",
            f"  - 影响与共鸣：{decision['scores']['impact_resonance']}/5",
            f"  - 完成与落地：{decision['scores']['completion']}/5",
            f"  - 跨平台与持续性：{decision['scores']['cross_platform_continuity']}/5",
            f"  - 多元与破圈：{decision['scores']['diversity_breakout']}/5",
            f"  - 总分：{decision['total_score']}/30",
            f"- 入选理由：{decision['selection_reason']}",
        ])
        if decision.get("invitation_signal"):
            signal = decision["invitation_signal"]
            lines.append(f"- 邀约信号：{signal['text']}；证据：{signal['evidence_url']}")
        lines.append("")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    window = sub.add_parser("window")
    window.add_argument("--today")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--input", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--week-start", required=True)
    prepare.add_argument("--week-end", required=True)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--input", required=True, type=Path)
    snapshot.add_argument("--output", required=True, type=Path)
    select = sub.add_parser("select")
    select.add_argument("--input", required=True, type=Path)
    select.add_argument("--decisions", required=True, type=Path)
    select.add_argument("--output", required=True, type=Path)
    validate = sub.add_parser("validate")
    validate.add_argument("--input", required=True, type=Path)
    render_cmd = sub.add_parser("render")
    render_cmd.add_argument("--input", required=True, type=Path)
    render_cmd.add_argument("--output", required=True, type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "window":
            today = parse_date(args.today) if args.today else datetime.now(timezone.utc).date()
            print(json.dumps(last_complete_week(today), ensure_ascii=False, indent=2))
        elif args.command == "prepare":
            start, end = week_bounds(args.week_start, args.week_end)
            payload = prepare_payload(maker_weekly.read_json(args.input), start, end)
            maker_weekly.write_json(args.output, payload)
            print(f"prepared {len(payload.get('items', []))} candidates -> {args.output}")
        elif args.command == "snapshot":
            payload = make_snapshot(maker_weekly.read_json(args.input))
            maker_weekly.write_json(args.output, payload)
            print(f"saved {len(payload['items'])} snapshot candidates -> {args.output}")
        elif args.command == "select":
            payload = select_payload(maker_weekly.read_json(args.input), maker_weekly.read_json(args.decisions))
            maker_weekly.write_json(args.output, payload)
            print(f"selected {len(payload['items'])} strict projects -> {args.output}")
        elif args.command == "validate":
            errors = validate_final(maker_weekly.read_json(args.input))
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 2
            print(f"strict weekly report is valid: {args.input}")
        elif args.command == "render":
            payload = maker_weekly.read_json(args.input)
            errors = validate_final(payload)
            if errors:
                raise StrictError("; ".join(errors))
            maker_weekly.write_text(args.output, render(payload))
            print(f"rendered strict report -> {args.output}")
        return 0
    except (StrictError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
