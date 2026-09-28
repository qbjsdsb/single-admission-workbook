# 四科八册自动成书工程

目标：从私有原始资料生成语文、数学、英语、政治四本练习册与四本教师解析册。

**当前：全库提取、证据配对、逐题核验、分值/分类Gate、Canonical晋升、双版样章与八册严格编排已接通；真实英语已进入业务生产循环。真实全库保真解析、异常复核和四科内容生产仍未完成，不能视为八本正式成品。**

```bash
pip install -r requirements-pipeline.txt
python scripts/workbook.py intake /path/to/sources.zip
python scripts/workbook.py build examples/eight-books/dataset.json --compile
```

第二条构建命令只生成自编验证样例，需 XeLaTeX 和中文字体。真实资料在 `build/private/` 处理，不进入 Git。
详见 [八册流水线与剩余工作](docs/architecture/EIGHT_BOOK_PIPELINE.md)。

---

## 静态 LaTeX 样张与兼容构建

仓库早期从语文、政治静态样张起步；当前项目已扩展为四科八册生产流水线。以下目录和脚本只说明静态样张入口，完整生产流程见上方的流水线文档。

本仓库关注的是：

- A4 书芯与中文教辅版式；
- LaTeX / XeLaTeX 的可重复编译；
- 四科学科题目组件与学生/教师同源管理；
- 学生版与教师版的分离；
- 编译日志、PDF 和逐页视觉检查。

## 内容边界

本仓库不收录：

- 未经授权的真题、扫描件和网络资料；
- 邮箱附件、调查报告原件和个人信息；
- 尚未完成教师审核的正式题目；
- 任何应当留在本地或私有仓库中的材料。

公开仓库包含代码、Schema、自拟样例和不含真实题文的汇总记录，不存放私有原题、答案、教师解析或题目图片。示例不代表官方考纲、官方真题或任何考试机构。

## 静态样张目录

```text
AGENTS.md                         # Codex 项目规则
.agents/skills/latex-workbook/    # 习题册构建与验收流程
src/main.tex                      # 不含真实题库的公开样章
scripts/build.ps1                 # 本地 XeLaTeX 构建入口
docs/                             # 项目范围与后续计划
```

## 本地构建

需要本机已安装 XeLaTeX，并且 `xelatex` 已加入 PATH：

```powershell
Set-Location .\single-admission-workbook-public
.\scripts\build.ps1
```

生成文件会放在 `build/`，不会覆盖源文件。

## 使用原则

1. 先做少量样章，再扩展整册。
2. 每次修改先编译，再检查日志和页数。
3. PDF 必须同时检查彩色渲染和灰度渲染。
4. 学生版只保留学生需要看到的内容；答案和解析进入教师版。
5. 原始资料与公开模板分离保存。

## 授权说明

本仓库暂未附加开源许可证。许可证确定前，其他人可以查看和讨论代码，但请勿直接复制、再发布或用于商业出版。

## 目录与速度优化

八册构建默认生成章/节两级目录、独立页码与PDF书签；目录复用章节清单，无需另填。
保留原校验要求，并减少重复schema检查与全库扫描。详见 [目录与轻量提速](docs/architecture/TOC_AND_SPEED.md)。

### 一条命令预检原卷与解析版

```bash
python scripts/review_docx_pair.py build/private/student.docx build/private/teacher.docx \
  --subject english --out build/private/review
```

支持已归一化的英语、政治 DOCX。复用现有提取、答案配对、分值、分类建议、
教师解析和编辑队列，输出九份 JSON；不会自动批准答案或生成可出版状态。
原卷、解析版及包含题文的结果必须保存在私有目录，不能提交到公开仓库。

### 一条命令把可自动化生产步骤跑到底

对已经完成 intake 的私有缓存，英语/政治可以同时跑“配对来源”和“未配对同源证据”两条线；配对组再自动进入严格验证与计分。互不依赖的来源组使用有界并行，不降低任何答案/分值 Gate：

```bash
python scripts/run_fast_production.py build/private/intake \
  --subject english \
  --out build/private/production/english \
  --workers 4
```

输出 `fast-production-summary.json`。如果只是存在内容歧义、缺分值或待复核题，命令仍保存完整 checkpoint 并标记 `complete_with_content_blockers`；只有缓存损坏、Schema/进程失败等基础设施问题才标记 `hard_failure`。真实题文仍只存在私有输出中。

整体并行成书路线见 [八册高速生产路线](docs/architecture/EIGHT_BOOK_FAST_TRACK.md)。

### 按科目批量预检 intake 配对

已有 `workbook.py intake` 缓存后，可以一次复核全部精确配对而不重新解析源文件：

```bash
python scripts/review_intake_pairs.py build/private/intake \
  --subject english --out build/private/review-english
```

批量命令复用 `sources.private.json`、`pairs.private.json` 与 Document AST 缓存，输出每套卷的私有复核结果、总摘要和 UTF-8-BOM 教研队列 CSV；不会自动批准答案或生成可出版状态。

### 把真实 Canonical 样章走正式 XeLaTeX 路径

完成核验、分值、分类和 Canonical 晋升后，可以直接把私有样章交给正式 A4 出版器：

```bash
python scripts/render_private_sample.py \
  build/private/english/canonical-draft.json \
  build/private/english/curriculum.json \
  --out build/private/english-xelatex-sample \
  --compile
python scripts/check_pdf_navigation.py build/private/english-xelatex-sample
```

该命令只选择通过现有样章 Gate 的题目，生成同源学生版和教师版，并检查 A4 页面、空页、溢出、缺字和学生版教师内容泄漏。输出仍是私有样章，必须完成视觉复核后才能继续扩成整册。


### 冻结真实生产进度快照

批量预检后，不必再人工翻整份 CSV 才知道下一步处理什么。可以从私有 Batch Review 结果生成不含题文和源路径的生产摘要：

```bash
python scripts/build_production_snapshot.py \
  build/private/review-english \
  --out build/private/english-snapshot
```

输出 `production-snapshot.json` 和 `production-snapshot.md`，汇总各优先级、阻断项、可进样章题量和下一批应处理的 source IDs。它只是生产调度视图，不会自动核验答案，也不会授予出版状态。

### 来源缺解析时的补全边界

来源本身没有教师解析时，不把 AI 文本伪装成 source evidence。先生成独立的 supplement manifest，明确标记来源为 generated/editorial 和审核决定；只有 `approve` 且带审核说明的条目才能在 Canonical 晋升前补入教师解析：

```bash
python scripts/build_canonical_draft.py \
  build/private/verified-scored.json \
  build/private/classification.json \
  --teacher-enrichment build/private/teacher-enrichment.json \
  --analysis-supplement build/private/reviewed-analysis-supplement.json \
  --candidate-bank build/private/candidate-bank.json \
  --out build/private/canonical-draft.json
```

补充解析只能填空，不能覆盖不同的来源原解析；未审核、延期或拒绝的 AI 草稿不会进入成书输入。
