# Content Model v0.1

## 目标

题库是内容真源，LaTeX/XeLaTeX 只是当前 PDF 渲染器。未来即使增加 Typst、DOCX 或网页预览，也不改变题库数据。

系统分为四层：

1. **Source Vault**：原始 PDF/DOC/DOCX、扫描件、来源台账。默认私有。
2. **Canonical Question Bank**：规范化题目内容。
3. **Frozen Book Manifest**：一本书实际使用哪些题、章节顺序、版本和 edition。
4. **Renderer**：将同一 manifest 渲染为学生版或教师版。

## 关键原则

### 1. 出版内容与内部溯源隔离

题目可有内部来源、页码、解析置信度、审核记录，但 renderer 的公开输入接口不允许读取这些字段。成书不显示：

- source / source_id / page
- question_id
- parser / confidence
- review_status
- GitHub / commit / build
- copyright_status
- AI 生成或模型信息

### 2. 行内内容不是纯字符串

语文加点、下划线、数学公式、图片必须是结构化节点，而不是先转纯文本再猜回来。

示例：

```json
[
  {"type":"text","text":"对下列"},
  {"type":"emphasis_dot","children":[{"type":"text","text":"加点字"}]},
  {"type":"text","text":"的注音判断……"}
]
```

### 3. 教师版与学生版同源

学生版隐藏答案、解析、评分点；教师版显示它们。不得维护两份题目正文。

### 4. 章节结构独立于来源

原始资料可能按年份、试卷、机构排列；最终书按教学逻辑排列。四科各自定义 chapter/section，不把来源名称当默认章节。

### 5. 发布可重复

筛题可以使用规则，但 Release 前必须冻结成 `question_ids` 有序列表。相同 manifest + renderer version + seed 应得到相同内容与页脚古诗词选择。

### 6. 布局允许自动判断，也允许少量人工覆盖

选择题默认由 renderer 根据实际宽度决定四列/两列/单列；必要时题目可以声明 `layout.choice_mode` 覆盖自动判断。

数学解答空间默认由题型、分值和小问数估算；必要时允许 `answer_space_mm` 精确覆盖。

## 版本边界

v0.1 先支持：

- single_choice
- multiple_choice
- fill_blank
- short_answer
- material_question
- solution
- composition
- reading_group

后续再增加特殊题型，不在初版过度抽象。
