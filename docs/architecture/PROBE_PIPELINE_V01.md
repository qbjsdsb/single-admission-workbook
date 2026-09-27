# Probe pipeline v0.1

Inventory只回答“这是什么文件”；Probe回答“这个文件应该怎样解析”。

## PDF

只抽样前若干页，记录：

- 总页数
- 抽样页数
- 可提取文本字符量
- 文本块数量
- 图片数量
- 模式：text / scan / mixed / sparse

Probe阶段绝不做OCR。OCR只在后续slow lane对scan/mixed页触发。

## DOCX

直接读取OOXML包，不把正文压成纯文本。记录：

- 段落、表格
- 着重号
- 下划线
- OMML公式
- 图片
- 嵌入对象

这些能力标记用于选择解析器，并防止语文加点、数学公式和插图在后续转换时丢失。

## Legacy DOC

Probe只标记needs_conversion，后续统一通过LibreOffice headless转换到DOCX，然后走同一OOXML管线。

## 设计原则

Probe结果是可重建的派生数据；缓存键应包含source SHA-256 + probe/parser version。
