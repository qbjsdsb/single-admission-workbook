---
name: latex-workbook
description: Build and review a Chinese sports-admissions culture-course workbook with XeLaTeX. Use for chapter samples, question blocks, student/teacher variants, compilation diagnostics, and color/grayscale PDF QA.
---

# LaTeX 习题册工作流

## 适用范围

用于语文、政治习题册的公开模板和经过授权的正式项目。不要把未经授权的原始题库、扫描件或个人资料放进公开仓库。

## 工作顺序

1. 只读盘点源文件、题型、章节和版式约束。
2. 先生成小样章，不直接扩展全书。
3. 用 XeLaTeX 编译，并保留可定位的日志。
4. 检查页数、乱码、缺字、溢出、空白页和题号连续性。
5. 生成彩色与灰度渲染图，实际逐页查看。
6. 优先修改组件和模板，再重新编译样章。

## 学生版硬约束

- 题目中的括号直接承担答题功能。
- 不额外生成底部答题区域。
- 不添加“先读句意”“自查”等解释性文案，除非项目明确要求。
- 加点字、划线句子和题号必须与源稿语义一致。

## 完成条件

只有在编译成功、结构检查通过、彩色与灰度页面都完成实际查看后，才能说样章完成。自动检查不能替代视觉验收。


