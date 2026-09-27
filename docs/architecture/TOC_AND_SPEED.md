# 目录与轻量提速（2026-09-27）

基于 integration/production-baseline-v01 / 2fd5547，沿用现有渲染器、题库和八册入口。

## 本次实现

- 八册默认启用章/节两级目录，含纸面页码、PDF内部链接及分层书签。
- 目录使用罗马页码，正文从1开始；学生和教师册各自排版计算页码。
- 章节顺序直接取 book manifest，不增加独立目录库。旧样章不设置 table_of_contents 时保持无目录行为。
- XeLaTeX 根据 aux/toc/out 是否稳定决定是否再编译，上限5遍，不稳定则阻断；不再盲目固定编译两遍。
- 复用题目 schema validator；按来源、章节、题号预先分组，避免逐题重新检查schema和反复扫描完整题库/答案证据。
- 不删除完整性、答案冲突、重复题和缺解析检查。

## 性能证据与限制

同一环境、同一800道自编基准题、同一输入：原校验/编排8.144秒，修改后0.5818秒，约14.0倍。
对比八册清单（除新增目录开关）完全相同。单次观测，不是OCR、PDF编译或全库吞吐承诺。
原始基线为2fd5547；基准将4科样例每题扩展200个不同题干的自编变式，保留每题来源和答案核验证据。

## 可借鉴项目，不整体搬迁

- Quarto Books：https://quarto.org/docs/books/book-structure.html
  借鉴一份章节配置驱动章、节及导航。当前已有book manifest，无需引入Quarto重写。
- latexmk：https://ctan.org/pkg/latexmk
  借鉴自动重跑直到引用稳定。当前仅用XeLaTeX，用小型有界循环即可，暂不增加依赖。
- OCRmyPDF：https://ocrmypdf.readthedocs.io/en/stable/performance.html
  后续OCR优先处理确有需要的页；关闭非必要文件优化/PDF-A生成，限制并发，保留所有原始页。
  不能为提速使用skip-big把含题页静默漏掉。混合页仍需检查，不能仅凭存在文本就判定完整。
- Docling：https://docling-project.github.io/docling/usage/supported_formats/
  可作为困难PDF/表格的候选适配器，先用真实代表页比较时间、公式和阅读顺序，再决定是否接入。

## 暂不增加

不增加微服务、消息队列、向量数据库、额外目录管理后台，也不切换排版引擎。
先补真实题源到题库的闭环；接入已有预构建出版镜像应在稳定主线发布可复用镜像之后进行。

## 边界

本次上传的单招教研.zip未成功提供，因此未重新运行全库，也未给真实题库分类准确率。
真实题目OCR、公式转换、题组渲染、全量分章和解析核验仍不是本次目录改造已完成的内容。
