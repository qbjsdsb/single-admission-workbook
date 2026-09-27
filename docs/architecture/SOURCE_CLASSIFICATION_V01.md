# Source classification v0.1

## 两层分类，不搬原文件

原始资料保持只读和原路径不变。系统通过私有 `source-manifest.json` 给每个文件加元数据；真正成书时使用的是题目级分类，而不是原文件夹位置。

### A. 文件级 Source Manifest

每个文件记录：

- subject：四科
- source_class：past_exam / mock_exam / study_note / reference / syllabus / mind_map / other
- role：student / teacher / solution / answer / mixed / standalone
- year
- parser_lane：docx / legacy_doc / pdf_probe / image_ocr
- SHA-256：增量处理与去重
- pair_key：自动寻找学生版↔教师版、原卷↔解析版
- rights_status：版权/再分发边界
- import_status：处理进度

完整 manifest 属于 **private Source Vault**，不进入公开出版层。

### B. 题目级 Canonical Question Bank

文件被解析后，每道题重新分类：

- chapter / section：最终教学章节
- kind：选择、填空、材料、解答、作文、阅读组等
- knowledge tags：知识点可多标签
- difficulty：基础 / 标准 / 提升
- score
- answer / analysis / teacher notes
- duplicate cluster：相同或近似题
- review state（内部）

因此“2024真题里的病句题”和“模拟卷里的病句题”最后可以进入同一个“语言文字运用 → 病句”章节。来源只做内部溯源，不决定成书章节。

## 自动化流程

1. Inventory：只读扫描 ZIP，生成文件级 manifest。
2. Probe：对 PDF 判断 text / scan / mixed；DOC/DOCX 检查公式、图片、加点等能力需求。
3. Pair：依据名称和内容指纹建立原卷↔解析、学生↔教师候选关系。
4. Parse：按 parser lane 并行提取。
5. Question split：拆成候选题。
6. Classify：先规则分类，再由 AI 辅助知识点/题型分类。
7. Deduplicate：精确哈希 + 文本相似度 + 结构相似度。
8. Review gate：低置信、答案冲突、版式复杂、疑似重复进入人工复核队列。
9. Freeze：练习册 manifest 冻结题目顺序和章节。
10. Render：同一题库生成学生版 / 教师版。

## 效率原则

- 不重复 OCR：SHA-256 + parser version 未变化则跳过。
- 不先处理所有扫描件：DOCX、旧 DOC 转换、文本 PDF 走 fast lane；扫描 PDF 走 slow lane。
- 不人工整理文件夹：只修正 manifest 中的分类。
- 不让 AI 直接覆盖原资料：所有提取物都是派生数据，可随时重建。
- 不把来源字段带进成书：出版 renderer 只读取 canonical question + frozen book manifest。
