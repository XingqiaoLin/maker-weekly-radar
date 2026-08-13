# Maker 周报严格评审标准

## 目录

0. Make Something Gate 与数据阶段
1. 时间门
2. Maker Project 定义
3. 平台范围与热度门槛
4. 五关判定
5. 三条红线与直接排除项
6. 评分、排序与去重
7. 决策数据结构
8. 最终输出结构
9. 证据纪律

## 0. Make Something Gate 与数据阶段

严格区分 `raw_discoveries`、`physical_prefilter_passed`、`editorial_candidates`、`final_selections`。Raw 只供审计，不得显示成候选榜或周报。

在时间、热度和全局候选排序之前，每条内容必须同时证明：创作者亲自制作/改造/建造物理实体；实体是核心成果；页面直接显示成品、原型或实质进展；页面直接显示设计、加工、装配、测试或迭代投入。至少记录一条原始页面上的照片、运行视频、制作过程、测试、结构/材料/电子系统或迭代证据。仅凭标题、关键词、标签和 Topic 不得通过。

成品或实质原型证据不依赖特定英文结果词。原始项目媒体与至少两个结构化制作步骤同时存在，或原始项目媒体与多项明确加工/装配/测试过程同时存在，即可将 `built_result_visible` 判为通过；Logo、徽章、普通页面链接和软件截图仍不算实体媒体。

任一项无法核验时必须记录 `physical_gate.status = "fail"` 和 `rejection_reason = "未找到真实物理造物证据"`。纯软件、性能测试、SDK/API/Yocto 集成、教程/知识库、电子书/工具包、音乐/故事、游戏、概念/渲染/预告、产品营销、套件复刻、修复、食物及仅有周边的内容在此直接排除。

固定流水线为：平台抓取 → raw 审计 → Make Something Gate → 时间门 → 热度门 → 跨平台去重与统一候选评分 → 来源软配额混排候选 Top 15 → 五关三红线 → 最终 Top 15。候选最低目标为 YouTube 至少 5、Reddit 至少 4、Kickstarter 与 Indiegogo 合并众筹池至少 1、Hackaday 至少 1，另为其余平台初始轮转 4 个名额；任一池不足或仍有剩余名额时按全局分数自动回填，所有来源组（包括众筹和 Hackaday）都可以超过最低目标。不降门槛、不凑数，最终编辑评分仍以质量为准。

`editorial_candidates` 只是中间态。完整周报任务只要产生候选，就必须继续完成人工证据核验、五关、三条红线、卓越度和评分，直到生成并验证 `final.json`；仅当用户明确要求只做采集或候选池时才可停下。硬门失败者不评分，只在编辑审计中记录淘汰原因。

## 1. 时间门

- 使用完整自然周：周一 `00:00:00` 至周日 `23:59:59`，明确时区。
- 记录周开始、周结束、当前执行日期和时区。
- 只允许 `first_release`：项目、帖子、视频、代码仓库或众筹页必须在目标周首次上线。
- 不设“翻红”通道。旧项目本周更新、重新传播、增加 Stars、重新 Featured 或热度越线，均不得入选。
- 原始发布时间不可见、只有更新时间、或日期来源冲突时，时间门失败。
- 时间门必须在全局候选排名之前执行，避免旧项目占用候选名额。
- 快照仅可用于审计，不得用于放行目标周以前发布的项目。
- 目标周结束时间和 `--as-of` 只约束首次发布日期，不约束热度采集时间。周报可在周末之后执行并使用执行时看到的真实公开指标；必须记录真实 `captured_at`，不得把它表述为周末历史快照。

## 2. Maker Project 定义

Maker Project 必须由个人或小团队主导，经过实际设计、制作、测试或迭代，形成有一定项目体量的原创物理成果。必须看到：

- 清晰制作目标；
- 可见创造过程；
- 实际时间、精力或技术投入；
- 制作挑战及解决过程；
- 已完成成果或可验证的实质进展。

软件、AI、代码只能辅助；核心结果必须是现实世界中的物理造物。

## 3. 平台范围与热度门槛

重点检索：Kickstarter、Indiegogo、GitHub、Hackaday、Hackster.io、Instructables、YouTube、Reddit、X/Twitter、Instagram、Make Magazine、The Verge、Tom’s Hardware。Reddit 至少覆盖 `r/maker`、`r/functionalprint`、`r/somethingimade`、`r/engineering` 和相关 Maker 社区。

硬性门槛：

| 平台 | 必须可核验的最低门槛 |
|---|---|
| Kickstarter | 可审计的 `≥ US$5,000` 或 `≥ 40` 支持者；非美元 Widget 换算值默认不可用于金额放行 |
| Indiegogo | `≥ US$20,000` 或 `≥ 200` 支持者 |
| GitHub | `≥ 1,000` Stars |
| Hackaday | 精选、编辑推荐或正式报道 |
| Hackster.io | 精选或编辑推荐 |
| Instructables | Featured |
| YouTube | 单视频 `≥ 25,000` 播放，或频道 `≥ 10,000` 订阅 |
| Reddit | 单帖公开点赞/分数与评论合计 `≥ 500`；精确互动不可见时可使用官方合并 `top/week` RSS 前 50 名代理 |
| X / Twitter | 单帖公开互动 `≥ 5,000` |
| Instagram | 单帖公开互动 `≥ 5,000` |
| Make Magazine | 正式报道 |
| The Verge | 正式报道 |
| Tom’s Hardware | 正式报道 |

数据不可见、不可核验、币种无法可靠换算或来源冲突时，热度门失败。除已明确标注的 Reddit 官方合并周榜代理外，RSS 顺序不是热度数据。热度使用执行周报时的真实公开观测值；`captured_at` 可以晚于目标周结束，但项目首次发布日期必须仍在目标周内。降低 Kickstarter、YouTube 和 Reddit 的入池门槛只用于扩大严格编辑候选；物理造物门、时间门、五关、三条红线、卓越度和证据要求不得随之降低。

明确排除：中国大陆平台、Thingiverse、Printables、MakerWorld、纯模型上传、参数分享和素材下载页。

## 4. 五关判定

按顺序执行；任一必需项失败立即淘汰。

### 第一关：品类门

核心必须是已经做出的物理实体，如硬件、机械、电子设备、3D 打印作品、可穿戴、服装、家具、装置、机器人、艺术装置或实体改造。

排除纯软件、App、网站、代码、游戏、桌游、卡牌、纯数字艺术、素材、剧本、知识内容、效果图、渲染、预告、概念，以及物理物品仅为赠品或周边的项目。

### 第二关：热度门

严格使用平台表。每个数字记录真实抓取时间和原始页面。执行日期晚于目标周结束不是拒绝理由；不得用估算、伪造的周末快照、第三方声量或跨平台热度替代所属平台门槛。

### 第三关：项目门

以下四项至少三项有具体证据：

1. `multi_stage`：设计、制作、测试、迭代等多步骤流程；
2. `significant_investment`：数天、数周或数月投入；
3. `real_challenge`：技术、材料、结构或实现难点及解决；
4. `real_motivation`：明确为什么做以及解决/实现什么。

数小时一步完成、照教程拼装、无挑战的单点制作不通过。

### 第四关：必要条件

以下三项全部通过：

1. `small_team_led`：个人或小团队真实主导并亲手创造；
2. `what_and_why`：清楚说明做了什么、为什么做；
3. `built_or_substantive_progress`：已有实物或可验证实质进展。

必须核对内容发布者是否就是实际创作者。测评、探店、开箱、媒体报道或第三方演示即使展示了真实实体，也不能证明发布者亲手创造；除非与目标周内合格的原作者页面合并并重新核验时间和热度，否则 `small_team_led` 失败。

### 第五关：卓越度

至少一个方向形成具体同赛道差异，并写出可证实的对标话术：

- `technical_engineering`：同类已有 X、Y，但该项目实现了它们未做到的具体结构、路径、复杂度、精度或功能。
- `creative_play`：同类通常采用某方式，而它采用另一具体方式，形成少见体验或表达。
- `value_resonance`：同类通常帮助某群体，而它通过具体方法更直接影响另一具体对象或痛点。

“更好”“很创新”“性能不错”不构成卓越差异。

## 5. 三条红线与直接排除项

三条红线必须全部通过并给证据：

1. `original_creation`：有原创创造投入；复制、照搬、纯修复、原样还原、套件拼装和纯 AI 输出失败。
2. `actually_built`：已经实际做出；概念、渲染、预告、效果图和口头设想失败。
3. `not_mature_mass_product`：不是成熟大公司的官方工业化量产产品。个人、小团队、小创业公司或大公司员工的独立副业可保留。

同时直接排除：大公司营销/广告/带货、纯成品展示、纯教程、简单模型、无原创复刻、恢复原状的维修翻新、模板化作业、食物料理烘焙、无法验证的数据或证据。

## 6. 评分、排序与去重

仅对全部硬门通过者评分。六项各 `1–5` 分，总分 `6–30`：

1. `creation_investment`：原创/改造程度与投入规模；
2. `process_visibility`：设计制作过程是否清楚；
3. `impact_resonance`：讨论传播、痛点或情感价值；
4. `completion`：是否真正可用或有实质进展；
5. `cross_platform_continuity`：跨平台证据与持续更新；
6. `diversity_breakout`：是否突破典型 Maker 刻板印象。

按总分降序；同分依次比较创造投入、完成度、卓越差异、过程证据质量、热度。同一项目跨平台出现时合并为一项并保留主要证据链接。

## 7. 决策数据结构

`decisions.json`：

```json
{
  "selection_method": "maker-weekly-strict-v1",
  "items": [
    {
      "id": "candidate-id",
      "category": "社会价值",
      "entry_type": "first_release",
      "first_seen_date": "YYYY-MM-DD",
      "heat_gate": {
        "status": "pass",
        "observed": "公开可读的原始数值或编辑状态",
        "threshold": "对应平台门槛",
        "captured_at": "ISO-8601",
        "evidence_url": "https://primary.example/project"
      },
      "creator": {
        "name": "姓名或团队",
        "background": "可验证背景",
        "evidence_urls": ["https://primary.example/creator"]
      },
      "project_description": "外观、功能、用户和效果",
      "build_path": "技术、材料、工艺、设计、测试和迭代",
      "category_gate": {"passed": true, "evidence": "物理核心证据", "evidence_url": "https://..."},
      "project_gate_evidence": {
        "multi_stage": {"passed": true, "evidence": "设计、制作、测试与迭代证据", "evidence_url": "https://...", "evidence_locator": "步骤、章节或视频时间戳"},
        "significant_investment": {"passed": true, "evidence": "数天、数周或数月投入证据", "evidence_url": "https://...", "evidence_locator": "步骤、章节或视频时间戳"},
        "real_challenge": {"passed": true, "evidence": "具体难点及解决证据", "evidence_url": "https://...", "evidence_locator": "步骤、章节或视频时间戳"},
        "real_motivation": {"passed": true, "evidence": "为什么做及目标证据", "evidence_url": "https://...", "evidence_locator": "步骤、章节或视频时间戳"}
      },
      "necessary_conditions": {
        "small_team_led": {"passed": true, "evidence": "..."},
        "what_and_why": {"passed": true, "evidence": "..."},
        "built_or_substantive_progress": {"passed": true, "evidence": "..."}
      },
      "excellence": {
        "direction": "technical_engineering",
        "benchmark_statement": "同类已有……，但它做到了……",
        "evidence_url": "https://..."
      },
      "red_lines": {
        "original_creation": {"passed": true, "evidence": "..."},
        "actually_built": {"passed": true, "evidence": "..."},
        "not_mature_mass_product": {"passed": true, "evidence": "..."}
      },
      "scores": {
        "creation_investment": 5,
        "process_visibility": 5,
        "impact_resonance": 4,
        "completion": 4,
        "cross_platform_continuity": 3,
        "diversity_breakout": 4
      },
      "selection_reason": "两到三句具体理由",
      "auxiliary_evidence": ["https://..."]
    }
  ]
}
```

`category` 只能是：`社会价值`、`极客硬核`、`艺术科技交互`、`生活方式社群`。`entry_type` 只能是 `first_release`。仅当创作者明确寻求资金、合作、设备或资源时，增加 `invitation_signal`，并附原始证据 URL。

## 8. 最终输出结构

开头列出：时间范围、检索平台数、初始候选数、通过数和本周首发数。

每项依次输出：原始链接、辅助证据、类别、入选类型、原始发布日期、热度（执行时观测，含真实抓取时间）、创作者、项目简介、制作与技术路径、项目门至少三项证据、卓越方向、卓越对标话术、三条红线检查、六项评分、总分、两到三句入选理由，以及有证据时才出现的邀约信号。

## 9. 证据纪律

- 每项关键事实附原始链接或可信来源；优先原始页面。
- 所有链接可打开；记录热度抓取时间。
- 不捏造金额、支持者、播放、互动、发布时间、作者背景或制作过程。
- 数据冲突时优先平台原始页面并标明冲突。
- 无法验证即写入研究记录并淘汰，不进入最终输出。
- 不因名气、偏好或故事感放宽门槛。
- 描述具体、客观、有画面，避免空泛赞美。
