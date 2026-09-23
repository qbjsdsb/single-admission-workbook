\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{workbook}[2026/09/22 Single-admission workbook public class]

\newif\ifworkbookteacher
\workbookteacherfalse
\DeclareOption{teacher}{\workbookteachertrue}
\DeclareOption{student}{\workbookteacherfalse}
\ExecuteOptions{student}
\ProcessOptions\relax

\newcommand{\workbookedition}{学生版}
\ifworkbookteacher
  \renewcommand{\workbookedition}{教师版}
\fi

\LoadClass[UTF8,zihao=-4]{ctexart}
\RequirePackage[b5paper,margin=17mm,top=18mm,bottom=18mm]{geometry}
\RequirePackage{xcolor}
\RequirePackage{amsmath}
\RequirePackage{amssymb}
\RequirePackage{array}
\RequirePackage{enumitem}
\RequirePackage{needspace}
\RequirePackage{setspace}
\RequirePackage{xeCJKfntef}
\RequirePackage{ulem}
\normalem

\definecolor{workbookink}{HTML}{242424}
\definecolor{workbookmuted}{HTML}{626262}
\definecolor{workbookrule}{HTML}{B9B9B9}
\definecolor{workbookpale}{HTML}{F3F3F1}
\definecolor{workbookteacher}{HTML}{5B6E63}

\pagecolor{white}
\color{workbookink}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.35em}
\setstretch{1.28}
\setlength{\emergencystretch}{1.5em}
\pagestyle{empty}
