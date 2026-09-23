# 体育单招文化考试四科习题册基础设施

这是面向普通高等学校运动训练、武术与民族传统体育专业招生文化考试的公开出版基础设施。当前范围覆盖语文、数学、政治、英语四科，重点是来源可追溯、内容与排版分离、学生版与教师版同源、可重复构建和可验证发布。

本仓库保存规范、Schema、LaTeX/XeLaTeX 公共层与学科层、构建工具、QA、少量自拟 fixtures 和脱敏研究结果。它不是公开题库，也不是官方真题仓库。

## 公开边界

禁止提交：

- 未经授权的真题、扫描书籍、商业教辅正文或大段转载内容；
- 私人邮箱附件、原始教研资料、个人信息和本地绝对路径；
- 来源、版权或审核状态不清的正式题目。

本地历史资料通过 `config/local-sources.yml` 接入，文件被 `.gitignore` 忽略。公开仓库只保留字段、规则、脱敏元数据和自拟结构测试，不复制本地原始资料。

## 当前入口

```text
config/exam-scope-register.yml       # 版本化考试范围与试卷结构
config/standards-register.yml        # 出版、语言、数学和印制标准
schemas/question.schema.json         # 题目语义模型的机器契约
fixtures/<subject>/                  # 四科自拟结构压力测试
src/workbook.cls                     # 公共 B5/print-profile 层
src/common/                          # 公共题目、材料、答案组件
src/subjects/                        # 四科学科排版 profile
scripts/build_content.py             # 同源数据生成学生/教师 TeX
scripts/build.ps1                    # 本地构建入口
scripts/validate_content.py          # Schema 级静态检查
scripts/qa_pdf.py                    # PDF、日志和页面尺寸检查
.github/workflows/qa.yml             # 推送/PR 自动复现构建
docs/                                # 审计、研究索引、迁移和 QA 规则
```

## 构建与验收

本地需要 XeLaTeX、Python 和 Poppler（`pdfinfo`、`pdftotext`、`pdftoppm`）。构建前会验证四科 JSON fixtures，再从同一份数据生成学生版、教师版和字下点回归页；构建会核对题目 ID、PDF 尺寸、教师答案标记和文本提取，并输出彩色/灰度页面，所有产物写入 `build/`：

```powershell
Set-Location .\single-admission-workbook
python -m pip install --requirement requirements-build.txt
.\scripts\build.ps1
```

构建生成四科各一张单页学生样张和对应教师版，另有四科整合样册作组合回归。通过编译不等于版面通过；正式样章还要检查日志、页数、缺字、overfull、彩色渲染、灰度渲染和关键页人工查看。XeLaTeX 支持 PATH 自动发现，也可通过 `XELATEX` 指定可执行文件；CI 配置位于 `.github/workflows/qa.yml`。

## 证据原则

题源按 `source_type`、`verification_status` 和 `allowed_usage` 分开管理。回忆版不能标成 `official_exam`，模拟题不能标成真题，教师审核稿仍须保留二手来源身份。题面、答案、解析和时效性分别记录；任何修正都保留原值、问题、建议修正和证据链。

当前考试范围以国家体育总局发布的 2023 版文化考试大纲及 2026 年招生管理办法为依据，见 `config/exam-scope-register.yml`。标准会过期或替代，不能用一个没有日期的“现行”标签覆盖历史版本。

## 许可证

仓库尚未附加开源许可证。许可证确定前，其他人可以查看和讨论代码，但请勿直接复制、再发布或用于商业出版。


