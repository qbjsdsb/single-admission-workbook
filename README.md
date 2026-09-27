# 四科八册自动成书工程

目标：从私有原始资料生成语文、数学、英语、政治四本练习册与四本教师解析册。

**当前：全库提取、证据配对、逐题核验、分值/分类Gate、Canonical晋升、双版样章与八册严格编排已接通；真实全库保真解析、异常复核和四科内容生产仍未完成，不能视为八本正式成品。**

```bash
pip install -r requirements-pipeline.txt
python scripts/workbook.py intake /path/to/sources.zip
python scripts/workbook.py build examples/eight-books/dataset.json --compile
```

第二条构建命令只生成自编验证样例，需 XeLaTeX 和中文字体。真实资料在 `build/private/` 处理，不进入 Git。
详见 [八册流水线与剩余工作](docs/architecture/EIGHT_BOOK_PIPELINE.md)。

---

# 体育单招文化课习题册 LaTeX 模板

这是一个面向体育单招文化课语文、政治习题册的公开工程骨架。

本仓库关注的是：

- A4 书芯与中文教辅版式；
- LaTeX / XeLaTeX 的可重复编译；
- 语文、政治题目组件的统一管理；
- 学生版与教师版的分离；
- 编译日志、PDF 和逐页视觉检查。

## 内容边界

本仓库不收录：

- 未经授权的真题、扫描件和网络资料；
- 邮箱附件、调查报告原件和个人信息；
- 尚未完成教师审核的正式题目；
- 任何应当留在本地或私有仓库中的材料。

当前内容只是公开模板和空白样章，不代表官方考纲、官方真题或任何考试机构。

## 目录

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
