# 题源与核验模型

## 1. 目标

题源模型要同时回答四个问题：这是什么材料、它从哪里来、哪些地方被谁核验过、现在允许怎么用。文件名、目录名和“老师看过”一句话都不能替代结构化记录。

## 2. 记录层级

### Source：材料级

一个 PDF、DOCX、扫描件、网页导出或本地整理文件对应一个 `source_id`。材料级记录至少包含：

- `source_id`、标题、科目、年份/周期、来源机构或作者、格式、语言；
- `source_type`、`verification_status`、`allowed_usage`；
- 私有路径别名、公开 URL（如有）、SHA-256、文件大小、取得/检查日期；
- 审核报告引用、审核人、审核日期、版权/公开范围说明；
- 时效起止、已知问题、置信度、备注。

### Question：题目级

题目使用不可因换章节或换版式而改变的 `question_id`。题目在某一份材料、某一年、某一页或某一段的出现使用 `occurrence_id`。题目修订使用递增 `revision_id`，不能覆盖原记录。

### Verification event：事件级

题面、答案、解析、分值、考点、时效和排版可分别核验。每次核验记录检查对象、观察值、结论、证据、核验人、时间、下一步和状态。

### Correction event：修订级

发现错误时至少保存：

```yaml
original_value: "观察到的原值"
observed_issue: "具体问题"
proposed_correction: "建议值"
evidence_refs: ["source-or-report-id"]
verification_status: disputed
```

只有在证据和审核事件满足门槛后，修订值才可进入发布视图；原值和问题仍保留。

## 3. 受控枚举

### `source_type`

`official_exam`, `official_syllabus`, `teacher_reviewed_transcription`, `secondary_transcription`, `recall`, `mock`, `lecture_note`, `textbook_note`, `knowledge_summary`, `derived_exercise`, `self_authored`

### `verification_status`

`unknown`, `inventoried`, `reviewed`, `teacher_reviewed`, `cross_checked`, `verified`, `disputed`, `rejected`

### `allowed_usage`

`research_only`, `structure_reference`, `knowledge_reference`, `transformation_source`, `exercise_candidate`, `student_release`, `teacher_release`

## 4. 使用门槛

| 状态/材料类型 | 可做什么 | 不可做什么 |
|---|---|---|
| `unknown` / `inventoried` | 目录、哈希、结构研究 | 学生发布 |
| `reviewed` | 章节研究、教师内部候选 | 宣称答案已证实 |
| `teacher_reviewed` | 进入教师版候选、抽样学生版 | 忽略未核验题目级问题 |
| `cross_checked` | 交叉核验后的题目进入发布候选 | 把二手来源变成官方来源 |
| `verified` | 满足题目、答案、解析和版式门槛时可发布 | 超出原材料或时效范围 |
| `disputed` / `rejected` | 保留问题、研究和反例 | 学生发布 |

## 5. 公开与私有分离

公开仓库只存 schema、匿名化 fixture、来源类型、公开 URL 和不含隐私的证据说明。真实路径、完整私有文件名、审核人隐私信息和本地哈希清单由 `config/local-sources.yml`（被 gitignore）及本地台账管理。
