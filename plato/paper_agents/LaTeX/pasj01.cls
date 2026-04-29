%% =============================================
%% pasj01.cls - version 2.0
%% (Based on pasj00.cls)
%%
%% Aptara Inc., dated 25th Nov. 2014
%%
%% Version 1.0 (History)
%% ---------------------
%% 1) Updated for margins to closely match the 
%%    final composition output.
%% 2) Used the Times for normal text and 
%%    Helvetica for display heads.
%%
%% Version 1.1 (2018 Feb 6) 
%% ---------------------
%% 1) Deleted dvips option   
%% 2) Deleted unnecessary commands 
%% 
%% Version 1.2 (2018 May 15) 
%% ---------------------
%% 1) Change default font to "Computer Modern" 
%%    for normal text  
%% 
%% =============================================
%%
%% This is file `pasj01.cls',
%% generated with the docstrip utility.
%%
%% The original source files were:
%%
%% pasj.dtx  (with options: `cls,distribution')
%% 
%% IMPORTANT NOTICE:
%% 
%% The contents of this file is originally managed by GlobalTeX Co., Ltd.
%% 
%% Any modified versions of this file must be renamed
%% with new filenames distinct from its original name.
%% 
%% You must not distribute this generated file without written permission
%% of the Astronomical Society of Japan and of GlobalTeX Co., Ltd.
\NeedsTeXFormat{LaTeX2e}[1995/12/01]
%% \ProvidesClass{pasj00}[2013/12/04 v.5.1 Simplified document class for PASJ^^J%
%% \@spaces\@spaces\@spaces(C) 2008 Astronomical Society of Japan]
\ProvidesClass{pasj01}[2018/05/15 v.1.2 Simplified document class for PASJ^^J%
\@spaces\@spaces\@spaces(C) 2018 Astronomical Society of Japan]
\DeclareOption{draft}{\setlength\overfullrule{5pt}}
\DeclareOption{final}{\setlength\overfullrule{0pt}}
\newif\if@restonecol
\DeclareOption{onecolumn}{\@twocolumnfalse}
\DeclareOption{twocolumn}{\@twocolumntrue}
\newif\if@openright
\DeclareOption{openright}{\@openrighttrue}
\DeclareOption{openany}{\@openrightfalse}
\newif\if@proofread
\@proofreadfalse
\DeclareOption{proof}{\@proofreadtrue}
\newif\if@useamsfonts
\@useamsfontsfalse
\DeclareOption{useamsfonts}{\@useamsfontstrue}
\newif\if@pasj@usefigure
\@pasj@usefiguretrue
\DeclareOption{nofigure}{\@pasj@usefigurefalse}
\newif\if@mfastrosym
\@mfastrosymfalse
\DeclareOption{mfastrosym}{\@mfastrosymtrue}
\ExecuteOptions{final,twocolumn,openright}
\ProcessOptions
\@twosidetrue
\def\SetVolumeData#1#2#3{%
   \@tempcnta\year
   \afterassignment\remove@to@nnil
   \count@0#1\relax\@nnil
   \ifnum\count@>\z@ \year\count@ \else \year\@tempcnta \fi
   \def\no{#3}%
   \def\@@vol{#2}}
\def\SetRunningHead#1#2{%
   \def\@Author{#1}%
   \def\@runninghead{#2}}
\def\SetContentsData#1#2{%
   \if@filesw
         \begingroup
         \let\break\robustbreak
         \addcontentsline{toc}{article}{{#1}{#2}{\lett}}%
         \endgroup
   \fi}
\edef\robustbreak{%
   {\noexpand\protect
   \expandafter\noexpand\csname break \endcsname}}
\long\def\title#1{\def\@title{#1}}
\def\author{\@add@author*\relax{}}
\def\@affil{}
\def\affil#1{\xdef\@affil{\ifx\@affil\@empty#1\else\@affil\par#1\fi}}
%%%
%%
\typeout{ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! }
\typeout{  For LETTER article, be sure to compile with  "Computer Modern (defalt font)".  }
\typeout{  fonts to estimate page numbers. Do NOT use "Times" font. }
\typeout{  (defalt font setting in pasj01.cls: Computer Modern)  } 
\typeout{ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! } 
%%
\newcount\aucnt
\newcount\tempcount
\newcount\@tempcnta
\def\author#1{\global\advance\aucnt\@ne\expandafter\gdef\csname author\romannumeral\the\aucnt\endcsname{#1}}
\def\printauthor{%
\ifnum\aucnt>\z@%
    \tempcount\z@%
    \@tempcnta=\aucnt%%
    \loop%
    \ifnum\@tempcnta>\z@%
     \advance\tempcount\@ne%
     \csname author\romannumeral\the\tempcount\endcsname%
         \ifnum\aucnt>2%%
	   \ifnum\@tempcnta>\@ne\ifnum\@tempcnta=2\ and\ %%
	   \else, \fi\fi%%
       \else%%
	   \ifnum\@tempcnta>\@ne\ifnum\@tempcnta=2\ and\ %%
	   \else, \fi\fi%%
       \fi%%
       \global\advance\@tempcnta\m@ne%%
    \repeat%
\fi%
}
%%%
\def\@email{}
\def\email#1{\xdef\@email{\ifx\@email\@empty $^{\ast}$E-mail: #1\else\@email,\ #1\fi}}
%% \def\email{\@ifnextchar[\@email\@@email}
%% \def\@email[#1]{\@add@author{\small\itshape}{E-mail(#1):~}}
%% \def\@@email{\@add@author{\small\itshape}{}}
\def\altaffilmark#1{\textsuperscript{\normalfont#1}}
\def\altaffiltext#1#2{\protected@xdef\@affil{\ifx\@affil\@empty\@hangfrom{\protect\textsuperscript{#1}}#2\else\@affil\par\@hangfrom{\protect\textsuperscript{#1}}#2\fi}}
%%
\def\and{\@add@author\relax{}{and}}
\def\@add@author{%
   \@ifstar
      {\let\@affil@curr@prefix\@empty
       \let\@affil@curr@break\@affil@break
       \@add@author@}%
      {\let\@affil@curr@prefix\@affil@prefix
       \let\@affil@curr@break\@empty
       \@add@author@}}
\long\def\@add@author@#1#2#3{%
   \let\@tempa\@empty
   \def\@add@author@font{#1}%
   \expandafter\@add@author@loop\@affil@curr@prefix#2#3\\\@nil\\\@gobble\\%
   \@csc@t\@author\@author\@tempa
   \def\@affil@prefix{\\}%
   \let\@affil@break\@affil@break@}
\def\@affil@break@{\@@par}
\long\def\@add@author@loop#1\\#2\\{%
   \def\@tempb{#1}%
   \def\@tempc{#2}%
   \ifx\@tempb\@nnil
      \expandafter\@gobbletwo
   \else
      \expandafter\def\expandafter\@tempb\expandafter{%
         \expandafter\ignorespaces\@tempb\unskip}%
      \@csc@t\@tempb\@add@author@font\@tempb
      \expandafter\def\expandafter\@tempb\expandafter{%
         \expandafter{\@tempb}}%
      \@csc@t\@tempb\@affil@curr@break\@tempb
      \let\@affil@curr@break\@empty
      \ifx\@tempc\@nnil\else
         \def\@tempd{\\}%
         \@csc@t\@tempb\@tempb\@tempd
      \fi
      \@csc@t\@tempa\@tempa\@tempb
      \expandafter\@add@author@loop
   \fi
   #2\\}
\def\Received#1{\def\rdate{#1}}
\def\Accepted#1{\def\adate{#1}}
\def\Published#1{\def\pdate{#1}}
\long\def\KeyWords#1{\def\@keywords{#1}}
\let\kword\KeyWords
%
%%% initialize some commands used for producing head/foot
\let\@Author\relax
\let\@runninghead\relax
\let\@keywords\@empty
\let\@title\@empty
\let\@author\@empty
\let\@affil@prefix\@empty
\let\@affil@break\@empty
\let\@@vol\@empty
\let\no\@empty
\let\rdate\@empty
\let\adate\@empty
\let\pdate\@empty
\def\pageSTART{\thepage}
\def\pageEND{{\bfseries??}}
\def\@@pageEND{10000}
\let\@plateno\@empty
\let\@firstplate\@empty
\let\@lastplate\@empty
\edef\plateid{\string\plateid}
\def\@ptsize{0}
%
%%% font setting (optional)
\openin\@inputcheck pasjfont.sty\relax
\ifeof\@inputcheck \let\@tempa\relax
\else              \def\@tempa{\@@input pasjfont.sty\relax}\fi
\closein\@inputcheck
\@tempa
\@ifundefined{@astrofont}{\let\@astrofont\@empty}{}
%
%%% font size
\newdimen\defaultbaselineskip
\defaultbaselineskip 13\p@
\DeclareRobustCommand*\normalsize{%
   \@setfontsize\normalsize\@size@for@normalsize\defaultbaselineskip
   \abovedisplayskip 6\p@ \@plus2\p@ \@minus5\p@
   \belowdisplayskip \abovedisplayskip
   \abovedisplayshortskip \z@ \@plus3\p@
   \belowdisplayshortskip 6\p@ \@plus3\p@ \@minus3\p@
   \let\@listi\@listI}
\DeclareRobustCommand*\small{%
   \@setfontsize\small\@size@for@small{10.5}%
   \abovedisplayskip 5.5\p@ \@plus3\p@ \@minus4\p@
   \belowdisplayskip \abovedisplayskip
   \abovedisplayshortskip \z@ \@plus2\p@
   \belowdisplayshortskip 4\p@ \@plus2\p@ \@minus2\p@
   \def\@listi{%
      \leftmargin\leftmargini
      \topsep 6\p@ \@plus\p@ \@minus\p@
      \parsep  \z@ \@plus\p@ \@minus\p@
      \itemsep \parsep}}
\DeclareRobustCommand*\footnotesize{%
   \@setfontsize\footnotesize\@size@for@footnotesize{9.5}%
   \abovedisplayskip 4.75\p@ \@plus2\p@ \@minus4\p@
   \belowdisplayskip \abovedisplayskip
   \abovedisplayshortskip \z@ \@plus\p@
   \belowdisplayshortskip 3\p@ \@plus\p@ \@minus2\p@
   \def\@listi{%
      \leftmargin\leftmargini
      \topsep 6\p@ \@plus\p@ \@minus\p@
      \parsep  \z@ \@plus\p@ \@minus\p@
      \itemsep \parsep}}
\DeclareRobustCommand*\scriptsize{%
   \@setfontsize\scriptsize\@size@for@scriptsize\@viiipt}
\DeclareRobustCommand*\tiny{\@setfontsize\tiny\@size@for@tiny\@vipt}
\DeclareRobustCommand*\large{\@setfontsize\large\@size@for@large{14}}
\DeclareRobustCommand*\Large{\@setfontsize\Large\@size@for@Large{18}}
\DeclareRobustCommand*\LARGE{\@setfontsize\LARGE\@size@for@LARGE{22}}
\DeclareRobustCommand*\huge{\@setfontsize\huge\@size@for@huge{25}}
\DeclareRobustCommand*\Huge{\@setfontsize\Huge\@size@for@Huge{30}}
%
%%% page size/margins etc.
\paperwidth     210mm
\paperheight    276mm
\textheight     55.0pc %%% previous value: 655.5pt, 55.5pc
\textwidth      40.5pc
\columnsep       18pt
\columnseprule    \z@
\def\@set@sidemargins{%
   \@ifstar{\@tempswafalse\@set@sidemargins@}%
           {\@tempswatrue\@set@sidemargins@}}
\def\@set@sidemargins@#1{%
   \dimen@#1\relax
   \ifdim\dimen@>\z@
      \evensidemargin\dimen@
      \if@tempswa
         \oddsidemargin\paperwidth
         \advance\oddsidemargin-\textwidth
         \advance\oddsidemargin-\evensidemargin
      \else
         \oddsidemargin\evensidemargin
      \fi
   \else
      \dimen@\paperwidth
      \advance\dimen@-\textwidth
      \divide\dimen@\tw@
      \oddsidemargin\dimen@
      \evensidemargin\dimen@
   \fi
   \advance\oddsidemargin  -1in
   \advance\evensidemargin -1in
   \relax}
%% \@set@sidemargins{55.7756pt}
%% \advance\topmargin -1in
%%%

\setlength\topmargin{28pt}
\setlength\oddsidemargin   {55.7756pt}
\setlength\evensidemargin\paperwidth
\addtolength\evensidemargin{-\textwidth}
\addtolength\evensidemargin{-\oddsidemargin}
%
\setlength\headheight{5.5\p@}% 
\setlength\headsep   {21.15pt}% \typeheight - \textheight - \headheight
\setlength\topskip   {7.15\p@}
%%  
\advance\oddsidemargin  -1in
\advance\evensidemargin -1in
\advance\topmargin  -1in
%%%
\@ifundefined{mathindent}{\newskip\mathindent}{}
\def\usetenpoint{%
   \def\@ptsize{0}%
   \def\@size@for@tiny{\@vpt}%
   \def\@size@for@scriptsize{\@viipt}%
   \def\@size@for@footnotesize{\@viiipt}%
   \def\@size@for@small{\@ixpt}%
   \def\@size@for@normalsize{9.25}%
   \def\@size@for@large{\@xiipt}%
   \def\@size@for@Large{\@xivpt}%
   \def\@size@for@LARGE{\@xviipt}%
   \def\@size@for@huge{\@xxpt}%
   \def\@size@for@Huge{\@xxvpt}%
   \normalsize}
\def\tenpoint{%
   \usetenpoint
   %\headsep .8pc \advance\headsep 10\p@ \advance\headsep-\topskip
   \parindent  12pt
   \mathindent 0pc
   \relax}
\def\useelevenpoint{%
   \def\@ptsize{1}%
   \def\@size@for@tiny{\@vipt}%
   \def\@size@for@scriptsize{\@viiipt}%
   \def\@size@for@footnotesize{\@ixpt}%
   \def\@size@for@small{\@xpt}%
   \def\@size@for@normalsize{\@xipt}%
   \def\@size@for@large{\@xiipt}%
   \def\@size@for@Large{\@xivpt}%
   \def\@size@for@LARGE{\@xviipt}%
   \def\@size@for@huge{\@xxpt}%
   \def\@size@for@Huge{\@xxvpt}%
   \normalsize}
\def\elevenpoint{%
   \useelevenpoint
   \headsep 35\p@ \advance\headsep 10\p@ \advance\headsep-\topskip
   \footskip    40\p@
   \footnotesep 12\p@
   \parindent  3em
   \mathindent 5em
   \relax}
\def\usetwelvepoint{%
   \def\@ptsize{2}%
   \def\@size@for@tiny{\@vipt}%
   \def\@size@for@scriptsize{\@viiipt}%
   \def\@size@for@footnotesize{\@xpt}%
   \def\@size@for@small{\@xipt}%
   \def\@size@for@normalsize{\@xiipt}%
   \def\@size@for@large{\@xivpt}%
   \def\@size@for@Large{\@xviipt}%
   \def\@size@for@LARGE{\@xxpt}%
   \def\@size@for@huge{\@xxvpt}%
   \def\@size@for@Huge{\@xxvpt}%
   \normalsize}
\def\twelvepoint{%
   \usetwelvepoint
   \headsep 35\p@ \advance\headsep 10\p@ \advance\headsep-\topskip
   \footskip    40\p@
   \footnotesep 12\p@
   \parindent  3em
   \mathindent 5em
   \relax}
\def\draft{%
   \@proofreadtrue
   \twelvepoint
   \def\ps@draft{%
      \let\@mkboth\@gobbletwo
      \def\@oddfoot{\hfil{\normalsize\normalfont\lett\thepage}\hfil}%
      \def\@evenfoot{\hfil{\normalsize\normalfont\lett\thepage}\hfil}%
      \def\@oddhead{\@set@proofmark\hfil}%
      \let\@evenhead\@oddhead}%
   \pagestyle{draft}%
   \let\ps@firstpage\ps@draft
   \textwidth  170mm
   \topmargin  -5.4mm %%% 20mm - 1in
   \advance\topmargin-\headheight \advance\topmargin-\headsep
   \textheight 237mm
   \@set@sidemargins\z@ %%% \z@ ==> left margin = right margin
   \onecolumn
   \linespread{1.5}%
   \normalsize
   \footskip\baselineskip\relax
   \advance\textheight-\footskip}
\usetenpoint

%% \headsep .8pc \advance\headsep 10\p@ \advance\headsep-\topskip
\parindent  12pt
\mathindent 0pc
%% \topskip         \defaultbaselineskip
%% \advance\topskip-.05\p@
%% \headsep         .8pc
%% \headheight      12\p@
%% \advance\headsep 10\p@
%% \advance\headsep-\topskip %%% \headsep + \topskip = .8pc + 10pt
%% \footskip       .35in
%% \maxdepth        4\p@
%% \marginparwidth  48\p@
%% \marginparsep    10\p@
%% \marginparpush    5\p@
%% \footnotesep   6.65\p@
%% \skip\footins     9\p@ \@plus 4\p@ \@minus 2\p@
%% \skip\@mpfootins = \skip\footins
\arraycolsep      5\p@
\tabcolsep        6\p@
\arrayrulewidth  .4\p@
\doublerulesep    2\p@
\tabbingsep        \labelsep
%% \fboxsep          3\p@
%% \fboxrule        .4\p@
%% \floatsep        12\p@ \@plus 2\p@ \@minus 2\p@
%% \textfloatsep    12\p@ \@plus 2\p@ \@minus 4\p@
%% \intextsep       12\p@ \@plus 2\p@ \@minus 2\p@
%% \dblfloatsep     12\p@ \@plus 2\p@ \@minus 2\p@
%% \dbltextfloatsep 12\p@ \@plus 2\p@ %%% \@minus 4\p@
%% \@fptop            \z@
%% \@fpsep           8\p@ \@plus 2fil
%% \@fpbot            \z@ \@plus 1fil
%% \@dblfptop         \z@ \@plus 1fil
%% \@dblfpsep        8\p@ \@plus 2fil
%% \@dblfpbot         \z@ \@plus 1fil
%% \lineskip          \p@
%% \normallineskip    \p@
%% \parskip           \z@ \@plus \p@
%% \def\baselinestretch{}%%% empty ==> single space
%% \dimen@\defaultbaselineskip\relax
%% \smallskipamount .25\dimen@ \@plus 1\p@ \@minus 1\p@
%% \medskipamount    .5\dimen@ \@plus 2\p@ \@minus 2\p@
%% \bigskipamount      \dimen@ \@plus 4\p@ \@minus 4\p@
%% \@lowpenalty   51
%% \@medpenalty  151
%% \@highpenalty 301
%
%%% lists
\def\@listi{%
   \leftmargin\leftmargini
   \labelwidth\leftmargini
   \advance\labelwidth-\labelsep
   \parsep   \z@ \@plus \p@
   \topsep  .5\defaultbaselineskip \@plus \p@ \@minus \p@
   \itemsep  \z@ \@plus \p@ \@minus \p@}
\let\@listI\@listi
\@listi
\def\@listii{%
   \leftmargin\leftmarginii
   \labelwidth\leftmarginii
   \advance\labelwidth-\labelsep
   \topsep  .5\defaultbaselineskip \@plus \p@ \@minus \p@
   \parsep   \z@ \@plus \p@
   \itemsep  \parsep}
\def\@listiii{%
   \leftmargin\leftmarginiii
   \labelwidth\leftmarginiii
   \advance\labelwidth-\labelsep
   \topsep     \z@ \@plus \p@ \@minus \p@
   \parsep     \z@ \@plus \p@
   \partopsep  \z@ \@plus \z@ \@minus \p@
   \itemsep    \topsep}
\def\@listiv{%
   \leftmargin\leftmarginiv
   \labelwidth\leftmarginiv
   \advance\labelwidth-\labelsep}
\def\@listv{%
   \leftmargin\leftmarginv
   \labelwidth\leftmarginv
   \advance\labelwidth-\labelsep}
\def\@listvi{%
   \leftmargin\leftmarginvi
   \labelwidth\leftmarginvi
   \advance\labelwidth-\labelsep}
\@beginparpenalty -\@lowpenalty
\@endparpenalty   -\@lowpenalty
\@itempenalty     -\@lowpenalty
\partopsep         \z@ \@plus 1\p@ \@minus 1\p@
\leftmargini     25\p@
\leftmarginii    22\p@
\leftmarginiii 18.7\p@
\leftmarginiv    17\p@
\leftmarginv     10\p@
\leftmarginvi    10\p@
\leftmargin\leftmargini
\labelsep         5\p@
\labelwidth\leftmargini
\advance\labelwidth-\labelsep
%
\def\itemize{\setlength\leftmargini{1em}\labelsep5pt%
  \ifnum \@itemdepth >\thr@@\@toodeep\else
    \advance\@itemdepth\@ne
    \edef\@itemitem{labelitem\romannumeral\the\@itemdepth}%
    \expandafter
    \list
      \csname\@itemitem\endcsname
      {\setlength\leftmarginii{1.1em}\itemsep0pt\ifnum \@listdepth >1\topsep0pt\else\topsep3pt\fi\parsep0pt\parskip0pt\def\makelabel##1{\hss\llap{##1}}}%
  \fi}
%%
\def\enumerate{\setlength\leftmargini{1.25em}%
  \ifnum \@enumdepth >\thr@@\@toodeep\else
    \advance\@enumdepth\@ne
    \edef\@enumctr{enum\romannumeral\the\@enumdepth}%
      \expandafter
      \list
        \csname label\@enumctr\endcsname
        {\setlength\leftmarginii{1.7em}\itemsep0pt\ifnum \@listdepth >1\topsep0pt\else\topsep3pt\fi\parsep0pt\parskip0pt\usecounter\@enumctr\def\makelabel##1{\hss\llap{##1}}}%
  \fi}
%%
\newenvironment{unnumlist}{\list{}{\itemsep0pt\parsep0pt\parskip0pt\partopsep0pt\leftmargin4mm\itemindent-4mm}}{\endlist}%
%%% itemize/enumerate
\def\theenumi{\@arabic\c@enumi}
\def\labelenumi{\theenumi.}
\def\theenumii{\@alph\c@enumii}
\def\labelenumii{(\theenumii)}
\def\p@enumii{\theenumi}
\def\theenumiii{\@roman\c@enumiii}
\def\labelenumiii{\theenumiii.}
\def\p@enumiii{\theenumi(\theenumii)}
\def\theenumiv{\@Alph\c@enumiv}
\def\labelenumiv{\theenumiv.}
\def\p@enumiv{\p@enumiii\theenumiii}
\def\labelitemi{\textbullet}
\def\labelitemii{\normalfont\bfseries \textendash}
\def\labelitemiii{\textasteriskcentered}
\def\labelitemiv{\textperiodcentered}
\def\@doendpe{%
   \@endpetrue
   \def\par{%
      \@restorepar
      \everypar{%
         \if@nobreak\else \clubpenalty\@clubpenalty \fi
         \everypar{}}%
      \par\@endpefalse}%
   \everypar{%
      {\setbox\z@\lastbox}%
      \if@nobreak\else \clubpenalty\@clubpenalty \fi
      \everypar{}%
      \@endpefalse}}
\def\verse{%
   \let\\\@centercr
   \list{}{%
      \itemsep      \z@
      \itemindent   -1.5em
      \listparindent\itemindent
      \rightmargin  \leftmargin
      \advance\leftmargin 1.5em}%
   \item\relax}
\def\endverse{\endlist}
\def\quotation{%
   \list{}{%
      \listparindent 1.5em
      \itemindent    \listparindent
      \rightmargin   \leftmargin
      \parsep        \z@ \@plus\p@}%
   \item\relax}
\def\endquotation{\endlist}
\def\quote{\list{}{}\item\relax}
\def\endquote{\endlist}
\def\description{%
   \list{}{%
      \labelwidth\z@
      \itemindent-\leftmargin
      \let\makelabel\descriptionlabel}}
\def\enddescription{\endlist}
\def\descriptionlabel#1{\hspace\labelsep\normalfont\bfseries #1}
%
%%% titlepage
\def\titlepage{%
   \cleardoublepage
   \if@twocolumn \@restonecoltrue\onecolumn
   \else         \@restonecolfalse          \fi
   \thispagestyle{empty}%
   \setcounter{page}\z@}%
\def\endtitlepage{\if@restonecol \twocolumn \else \newpage \fi}
\let\@saved@minipage\minipage
\def\minipage{\let\footnoterule\@empty\@saved@minipage}
%
%%% sectioning
\setcounter{secnumdepth}{4}
\global\let\cl@@article\@empty
\newcounter{part}
\@addtoreset{part}{@article}
\newcounter{chapter}
\@addtoreset{chapter}{@article}
\newcounter{section}[chapter]
\@addtoreset{section}{@article}
\newcounter{subsection}[section]
\@addtoreset{subsection}{@article}
\newcounter{subsubsection}[subsection]
\@addtoreset{subsubsection}{@article}
\newcounter{paragraph}[subsubsection]
\@addtoreset{paragraph}{@article}
\newcounter{subparagraph}[paragraph]
\@addtoreset{subparagraph}{@article}
\def\thepart{\@Roman\c@part}
\def\thechapter{\@arabic\c@chapter}
\def\thesection{\@arabic\c@section}
\def\thesubsection{\thesection.\@arabic\c@subsection}
\def\thesubsubsection{\thesubsection.\@arabic\c@subsubsection}
\def\theparagraph{\thesubsubsection.\@arabic\c@paragraph}
\def\thesubparagraph{\theparagraph.\@arabic\c@subparagraph}
\def\@chapapp{\chaptername}
\def\part{%
   \@startsection{part}{-1}{\z@}%
      {\defaultbaselineskip \@plus  1ex \@minus .2ex}%
      {\defaultbaselineskip \@plus .2ex}%
      {\normalfont\large\bfseries\boldmath}}
\let\partmark\@gobble
\def\chapter{%
   \@startsection{chapter}{0}{\z@}%
      {\defaultbaselineskip \@plus 1ex \@minus .2ex}%
      {\defaultbaselineskip \@plus .2ex}%
      {\normalfont\large\bfseries\boldmath}}
\let\chaptermark\@gobble
\def\section{%
   \@startsection{section}{1}{\z@}%
      {-22pt \@plus -.2pt \@minus -.2pt}%
      {4pt}%
      {\sectionfont\boldmath}}
\let\sectionmark\@gobble
\def\subsection@old{%
   \if@aftersection
      \if@twocolumn \vspace{-.5\defaultbaselineskip}\fi
      \expandafter\subsection@a
   \else
      \if@noskipsec \leavevmode \fi
      \ifhmode \unskip\par \fi
      \if@nobreak \nobreak \else \penalty-\@lowpenalty \fi
      \if@twocolumn
         \@nobreaktrue
         \vspace{.5\defaultbaselineskip}%%% modified 2003/7/16
      \else
         \addvspace{.5\defaultbaselineskip}%
      \fi
      \expandafter\subsection@b
   \fi}
\newcommand\subsection{\@startsection{subsection}{2}{\z@}{-20pt \@plus -.2pt \@minus -.2pt}{4pt}{\subsectionfont}}%
\def\subsection@a{%
   \@startsection{subsection}{2}{\z@}%
      {.5\defaultbaselineskip \@minus .1ex}%
      {.5\defaultbaselineskip \@minus .1ex}%
      {\normalfont\normalsize\itshape}}
\def\subsection@b{%
   \@startsection{subsection}{2}{\z@}%
      {1sp}%
      {.5\defaultbaselineskip \@minus .1ex}%
      {\subsectionfont}}
\let\subsectionmark\@gobble
\def\subsubsection{%
   \@startsection{subsubsection}{3}{\z@}%
      {-13pt \@plus -.2pt \@minus -.2pt}%%% modified
      {.00001pt}%
      {\subsubsectionfont}}
\let\subsubsectionmark\@gobble
\def\paragraph{%
   \@startsection{paragraph}{4}{\z@}%
      {13pt \@plus 2pt \@minus .2pt}%{\defaultbaselineskip \@minus .1ex}%
      {-.5em}{\paragraphfont}}
\let\paragraphmark\@gobble
\def\subparagraph{%
   \@startsection{subparagraph}{5}{\z@}%
      {13pt \@plus 2pt \@minus .2pt}%
      {-.5em}{\subparagraphfont}}
\let\subparagraphmark\@gobble
\def\@startsection#1#2#3#4#5#6{%
   \if@noskipsec \leavevmode \fi
   \par
   \@tempskipa #4\relax
   \@afterindenttrue
   \ifdim \@tempskipa <\z@
      \@tempskipa -\@tempskipa \@afterindentfalse
   \fi
   \if@nobreak
      \everypar{}%
   \else
      \addpenalty\@secpenalty\addvspace\@tempskipa
   \fi
   \@ifstar
     {\@ssect{#1}{#3}{#4}{#5}{#6}}%
     {\@dblarg{\@sect{#1}{#2}{#3}{#4}{#5}{#6}}}}
\def\@sect#1#2#3#4#5#6[#7]#8{%
   \if@in@appendix
      \ifnum#2>\@ne %%% subsection, subsubsection, ...
         \def\@sectitle@prefix{A.}%
      \else
         \def\@sectitle@prefix{\appendixname\space}%
      \fi
   \else
      \let\@sectitle@prefix\@empty
   \fi
   \ifnum #2>\c@secnumdepth
      \let\@svsec\@empty
      \let\@seccnt@suffix\@empty
   \else
      \refstepcounter{#1}%
      \ifnum#2<\z@%%% \part
         \let\@seccnt@suffix\@empty
      \else       %%% otherwise
         \def\@seccnt@suffix{}%
      \fi
      \protected@edef\@svsec{\@seccntformat{#1}\relax}%
   \fi
   \@tempskipa #5\relax
   \ifdim \@tempskipa>\z@
      \begingroup
         #6{\if@in@appendix
               \@hangfrom{\hskip #3\relax}%
               \@sectitle@prefix\@svsec
            \else
               \@hangfrom{\hskip #3\relax\@svsec}%
            \fi
            \interlinepenalty \@M #8\@@par}%
      \endgroup
%%%      \csname #1mark\endcsname{#7}%
      \addcontentsline{toc}{#1}{%
         \protect\numberline{%
            \@sectitle@prefix
            \csname the#1\endcsname\@seccnt@suffix}%
            #7}%
   \else
      \def\@svsechd{%
         #6{\hskip #3\relax \@svsec #8.}%
%%%         \csname #1mark\endcsname{#7}%
         \addcontentsline{toc}{#1}{%
            \protect\numberline{%
               \@sectitle@prefix
               \csname the#1\endcsname\@seccnt@suffix}%
               #7}%
      }%
   \fi
   \ifnum#2<\tw@ \@aftersectiontrue \else \@aftersectionfalse \fi
   \@xsect{#5}}
\def\@ssect#1#2#3#4#5#6{%
   \@tempskipa #4\relax
   \let\@sectitle@prefix\@empty
   \if@in@appendix
      \def\@tempa{#1}%
      \def\@tempb{section}%
      \ifx\@tempa\@tempb \def\@sectitle@prefix{\appendixname.\quad}\fi%%% modified 2003/7/16
   \fi
   \ifdim \@tempskipa>\z@
      \begingroup
         #5{\@hangfrom{\hskip #2}%
            \interlinepenalty \@M
            \if@in@appendix \@sectitle@prefix \fi
            #6\@@par}%
      \endgroup
      \addcontentsline{toc}{#1}{%
         \ifx\@sectitle@prefix\@empty\else
            \protect\numberline{\@sectitle@prefix}%
         \fi
         #6}%
   \else
      \def\@svsechd{%
         #5{\hskip #2\relax
            \if@in@appendix \@sectitle@prefix \fi
            #6}%
         \addcontentsline{toc}{#1}{%
            \ifx\@sectitle@prefix\@empty\else
               \protect\numberline{\@sectitle@prefix}%
            \fi
            #6}%
      }%
   \fi
   \def\@tempa{#1}%
   \def\@tempb{section}%
   \ifx\@tempa\@tempb \@aftersectiontrue \else \@aftersectionfalse \fi
   \@xsect{#4}}
\def\@seccntformat#1{\csname the#1\endcsname\@seccnt@suffix\enspace}
\def\@aftersectiontrue{\global\let\if@aftersection\iftrue}
\def\@aftersectionfalse{\global\let\if@aftersection\iffalse}
\@aftersectionfalse
\def\@afterheading{%
   \@nobreaktrue
   \everypar{%
      \@aftersectionfalse
      \if@nobreak
         \@nobreakfalse
         \clubpenalty \@M
         \if@afterindent \else
           {\setbox\z@\lastbox}%
         \fi
      \else
         \clubpenalty \@clubpenalty
         \everypar{}%
      \fi}}
%
%%% appendix
\newif\if@in@appendix
\global\@in@appendixfalse
\def\appendix{%
   \par
   \@in@appendixtrue
   \setcounter{chapter}{0}%
   \setcounter{section}{0}%
   \setcounter{equation}{0}%
   \def\@chapapp{\appendixname}%
   \def\thechapter{\@Alph\c@chapter}%
   \def\theequation{A\@arabic\c@equation}}
%
%%% equation number
\@addtoreset{equation}{@article}
\def\theequation{\@arabic\c@equation}
%
%%% float placement parameters
\setcounter{topnumber}{2}
\def\topfraction{.9}
\setcounter{bottomnumber}{1}
\def\bottomfraction{.3}
\setcounter{totalnumber}{3}
\def\textfraction{.1}
\def\floatpagefraction{.7}
\setcounter{dbltopnumber}{2}
\def\dbltopfraction{.9}
\def\dblfloatpagefraction{.7}
%
%%% floats
%%% floats
\newcounter{figure}
\@addtoreset{figure}{@article}
\def\thefigure{\@arabic\c@figure}
\def\fps@figure{tbp}
\def\ftype@figure{1}
\def\ext@figure{lof}
\def\fnum@figure{\figurename~\thefigure}
\def\figure@caption@shape{\bfseries}
\def\figure{\@float{figure}}
\def\endfigure{\end@float}
\@namedef{figure*}{\@dblfloat{figure}}
\@namedef{endfigure*}{\end@dblfloat}
\newcounter{table}
\@addtoreset{table}{@article}
\def\thetable{\@arabic\c@table}
\def\fps@table{tbp}
\def\ftype@table{2}
\def\ext@table{lot}
\def\fnum@table{\tablename~\thetable}
\def\table@caption@shape{\bfseries}
\def\table{\@float{table}}
\def\endtable{\end@float}
\@namedef{table*}{\@dblfloat{table}}
\@namedef{endtable*}{\end@dblfloat}
\let\@@dblfloat\@dblfloat
\def\@xfloat#1[#2]{%
   \@nodocument
   \def\@captype{#1}%
   \csname @set@captionskip@for@\@captype\endcsname
   \def\@fps{#2}%
   \@onelevel@sanitize\@fps
   \def\reserved@b{!}%
   \ifx\reserved@b\@fps
      \@fpsadddefault
   \else
      \ifx\@fps\@empty \@fpsadddefault \fi
   \fi
   \ifhmode
      \@bsphack
      \@floatpenalty -\@Mii
   \else
      \@floatpenalty-\@Miii
   \fi
   \ifinner
      \@parmoderr\@floatpenalty\z@
   \else
      \@next\@currbox\@freelist
        {\@read@fps@position
         \global \count\@currbox \@tempcnta}%
         \@fltovf
   \fi
   \global\setbox\@currbox
      \color@vbox
         \normalcolor
         \vbox \bgroup
            \hsize\columnwidth
            \@parboxrestore
            \@floatboxreset}
\def\@read@fps@position{%
   \@tempcnta \sixt@@n
   \expandafter\@tfor\expandafter\reserved@a\expandafter:\expandafter=%
      \@fps\do{%
         \if \reserved@a h%
            \ifodd\@tempcnta\else \advance\@tempcnta\@ne \fi
         \fi
         \if \reserved@a t%
            \@setfpsbit \tw@
         \fi
         \if \reserved@a b%
            \@setfpsbit 4%
         \fi
         \if \reserved@a p%
            \@setfpsbit 8%
         \fi
         \if \reserved@a !%
            \ifnum \@tempcnta>15
               \advance\@tempcnta -\sixt@@n\relax
            \fi
         \fi}%
   \@tempcntb\csname ftype@\@captype\endcsname
   \multiply \@tempcntb \@xxxii
   \advance \@tempcnta \@tempcntb}
\let\end@@dblfloat\end@dblfloat
\def\@extrafloats{48}
\count@\z@
\@whilenum\@extrafloats>\count@\do{%
   \advance\count@\@ne
   \expandafter\newinsert\csname bx@\romannumeral\count@\endcsname
   \expandafter\@cons\expandafter\@freelist
      \csname bx@\romannumeral\count@\endcsname}%
%
%%% \@makecaption
\newlength\abovecaptionskip
\newlength\belowcaptionskip
\def\@set@captionskip@for@figure{%
   \abovecaptionskip -.5\p@
   \belowcaptionskip   \z@}
\def\@set@captionskip@for@table{%
   \abovecaptionskip   \z@
   \belowcaptionskip  0\p@
   \if@proofread \usetenpoint \fi}
\def\captionsidemargin{12pt}
\def\caption{%
   \ifx\@captype\@undefined
      \@latex@error{\noexpand\caption outside float}\@ehd
      \expandafter\@gobble
   \else
      \expandafter\@firstofone
   \fi
   {\@ifnextchar[\@caption@with@option\@caption@without@option}}
\def\@caption@with@option[#1]{%
   \protected@edef\@currentlabel{#1}%
   \@makecaption{\csname\@captype name\endcsname~#1}}
\def\@caption@without@option{%
   \refstepcounter\@captype
   \@makecaption{\csname fnum@\@captype\endcsname}}
\long\def\@caption#1#2{%
   \par
   \begingroup
   \@parboxrestore
   \if@minipage \@setminipage \fi
   \@makecaption{#1}{\ignorespaces #2}\par
   \endgroup}
\long\def\@makecaption#1#2{%
   \ifhmode \unskip\par \fi
   \vskip\abovecaptionskip
   \begingroup
   \def\@tempa{table}%
   \dimen@\topskip
   \ifx\@captype\@tempa
      \edef\@caption@strut{%
         \noexpand\nobreak
         \noexpand\rule\z@{\the\dimen@}}%
   \else
      \let\@caption@strut\@empty
   \fi
   {\ifx\@captype\@tempa\tablecaptionfont\else\figcaptionfont\fi
      \mbox{\@nameuse{\@captype @caption@shape}#1. }%
      \@caption@strut\nobreak
      #2\par}%
%%    \@tempdima\captionsidemargin\relax
%%    \@tempdima-2\@tempdima \advance\@tempdima\hsize
%%    \ifdim \wd\@tempboxa>\@tempdima
%%      \leftskip\captionsidemargin\relax
%%      \rightskip\leftskip
%%      \noindent
%%      \unhbox\@tempboxa\par
%%   \else
%%      \global \@minipagefalse
%%      \hbox to\hsize{\hfil\box\@tempboxa\hfil}%
%%   \fi
  \endgroup
  \vskip\belowcaptionskip}
\let\@sharp\relax
\newdimen\@lt@hsize
\newdimen\@lt@caption@hsize
\newbox\@lt@currbox
\newbox\@lt@head
\newbox\@lt@firsthead
\newbox\@lt@foot
\newbox\@lt@lastfoot
\newbox\@lt@prevline
\newbox\@lt@captionbox
\newdimen\@lt@goalsize
\newdimen\@lt@doublerulesep
\newcount\@lt@id
\newcount\@lt@colcnt
\newcount\@lt@maxcols
\newif\if@lt@nocaption
\newif\if@lt@usecaption
\global\@lt@id\z@
\def\longtable{\@lt@usecaptiontrue\@longtable}
\@namedef{longtable*}{\@lt@usecaptionfalse\@longtable}
\def\@longtable{%
   \ifhmode \unskip\par \fi
   \global\advance\@lt@id\@ne
   \def\@captype{table}%
   \@ifnextchar[\@@longtable{\@@longtable[t]}}
\def\@@longtable[#1]#2{%
   \def\@lt@firstposition{#1}%
   \@lt@hsize\textwidth
   \@lt@caption@hsize\textwidth
   \@lt@doublerulesep\doublerulesep
   \advance\@lt@doublerulesep-\arrayrulewidth
   \let\@preamble\@empty
   \protected@edef\@tempa{#2}%
   \expandafter\@lt@expast\@tempa*0x\@nnil
   \expandafter\@lt@mkpream\@preamble\@nnil
   \@lt@init
   \let\@lt@preamble\@preamble
   \@lt@starttabular}

\def\endlongtable{%
   \@lt@endtabular\@empty
   \@lt@output@tabular\@lt@lastfoot
   \if@lt@usecaption
      \if@lt@nocaption
         \@lt@warning{There is no caption for this tabular.}%
      \fi
   \fi
   \@lt@write@boxsize}
\@namedef{endlongtable*}{%
   \@lt@endtabular\@empty
   \@lt@output@tabular\@lt@lastfoot
   \@lt@write@boxsize}
\def\@lt@warning#1{\typeout{^^JWarning [longtable:\the\@lt@id]: #1}}
\def\@lt@expast#1*#2#3{%
   \@lt@addtopream{#1}%
   \count@#2\relax
   \ifnum\count@>\z@
      \let\@tempa\@empty
      \@whilenum\count@>\z@\do{%
         \@lt@addtopream{#3}%
         \advance\count@\m@ne}%
      \expandafter\@lt@expast
   \else
      \expandafter\remove@to@nnil
   \fi}
\def\@lt@addtopream#1{%
   \expandafter\def\expandafter\@preamble\expandafter{\@preamble#1}}
\newif\if@lt@addcolsep
\def\@lt@mkpream{%
   \let\@preamble\@empty
   \let\@sharp\relax
   \let\@lt@start@entrybox\relax
   \let\@lt@end@entrybox\relax
   \let\@lt@start@pbox\relax
   \let\@lt@end@pbox\relax
   \let\@lt@putoption\relax
   \@chclass\m@ne
   \@firstamptrue
   \@lt@addcolseptrue
   \@tempcntb\z@
   \@lt@mkpream@loop}
\def\@lt@mkpream@loop#1{%
   \ifx#1\@nnil
      \let\@tempa\relax
   \else
      \@lastchclass\@chclass
      \def\@tempa{\@lt@addentry}%
      \if     #1l\relax
         \@chclass\z@
         \@tempcnta\@ne
      \else\if#1c\relax
         \@chclass\z@
         \@tempcnta\z@
      \else\if#1r\relax
         \@chclass\z@
         \@tempcnta\m@ne
      \else\if#1p\relax
         \@chclass\z@
         \def\@tempa{\@lt@addparbox}%
      \else\if#1|\relax
         \@chclass\@ne
         \def\@tempa{\@lt@addvrule}%
      \else\if#1@\relax
         \@chclass\tw@
         \def\@tempa{\@lt@readopt}%
      \else
         \def\@tempa{\@lt@mkpream@loop}%
      \fi\fi\fi\fi\fi\fi
   \fi
   \@tempa}
\def\@lt@addentry{%
   \edef\@tempa{%
      \ifnum\@tempcnta>\z@\else \hfil \fi
      \@lt@start@entrybox\ignorespaces\@sharp\unskip\@lt@end@entrybox
      \ifnum\@tempcnta<\z@\else \hfil \fi}%
   \ifnum\@lastchclass=\z@ \@lt@addcolsep \fi
   \if@firstamp \@firstampfalse \else \@lt@addtopream{&}\fi
   \@lt@addcolsep
   \@csc@t\@preamble\@preamble\@tempa
   \@lt@addcolseptrue
   \advance\@tempcntb\@ne
   \@lt@mkpream@loop}
\def\@lt@addparbox#1{%
   \edef\@tempa{\@lt@start@pbox{#1}\ignorespaces\@sharp\unskip\@lt@end@pbox}%
   \ifnum\@lastchclass=\z@ \@lt@addcolsep \fi
   \if@firstamp \@firstampfalse \else \@lt@addtopream{&}\fi
   \@lt@addcolsep
   \@csc@t\@preamble\@preamble\@tempa
   \@lt@addcolseptrue
   \advance\@tempcntb\@ne
   \@lt@mkpream@loop}
\def\@lt@addvrule{\@ifnextchar[\@lt@addvrule@{\@lt@addvrule@[\arrayrulewidth]}}
\def\@lt@addvrule@[#1]{%
   \dimen@#1\relax
   \edef\@tempa{\vrule width\the\dimen@\relax}%
   \ifcase\@lastchclass
      \@lt@addcolsep
   \or
      \@lt@addtopream{\hskip\@lt@doublerulesep}%
   \else
      \relax
   \fi
   \@csc@t\@preamble\@preamble\@tempa
   \@lt@mkpream@loop}
\def\@lt@readopt#1{%
   \@lt@addcolsepfalse
   \@lt@addtopream{\@lt@putoption{#1}}%
   \@lt@mkpream@loop}
\def\@lt@addcolsep{\if@lt@addcolsep \@lt@addtopream{\hskip\tabcolsep}\fi}
\def\@lt@init{%
   \global\@lt@maxcols\@tempcntb
   \@whilenum\@tempcntb>\z@\do{%
      \@ifundefined{@lt@wd@\the\@lt@id @\the\@tempcntb}{%
         \@namedef{@lt@wd@\the\@lt@id @\the\@tempcntb}{\z@}}{}%
      \global\@namedef{@lt@maxwd@\the\@tempcntb}{\z@}%
      \advance\@tempcntb\m@ne}%
   \gdef\@lt@maxht{\z@}%
   \gdef\@lt@maxdp{\z@}%
   \let\@lt@firstline\@empty
   \count@\z@
   \@whilenum\count@<\@lt@maxcols\do{%
      \advance\count@\@ne
      \edef\@tempa{%
         \ifnum\count@>\@ne &\fi
         \vrule \@width\@nameuse{@lt@wd@\the\@lt@id @\the\count@}%
                \@height\z@ \@depth\z@}%
      \edef\@lt@firstline{\@lt@firstline\@tempa}}%
   \def\@tempa{\tabskip\z@skip}%
   \@csc@t\@preamble\@tempa\@preamble
   \edef\@lt@firstline{%
      &########\tabskip\@centering\cr
       \global\noexpand\@lt@wdcheckfalse
       \@lt@firstline
      &\global\@lt@colcnt\z@
       \global\noexpand\@lt@wdchecktrue\cr}%
   \@csc@t\@preamble\@preamble\@lt@firstline
   \baselineskip\z@skip
   \lineskip\z@skip
   \lineskiplimit\maxdimen
   \setbox\@arstrutbox\hbox{%
      \vrule \@height\arraystretch\ht\strutbox
             \@depth\arraystretch \dp\strutbox
             \@width\z@}%
   \setbox\@lt@head\box\voidb@x
   \setbox\@lt@firsthead\box\voidb@x
   \setbox\@lt@foot\box\voidb@x
   \setbox\@lt@lastfoot\box\voidb@x
   \global\setbox\@lt@prevline\box\voidb@x
   \global\@lt@colcnt\z@
   \let\par\@empty
   \let\@sharp##%
   \let\@lt@start@entrybox\@lt@start@entrybox@
   \let\@lt@end@entrybox\@lt@end@entrybox@
   \let\@lt@start@pbox\@lt@start@pbox@
   \let\@lt@end@pbox\@lt@end@pbox@
   \let\@lt@putoption\@lt@putoption@
   \def\@lt@headbox{%
      \ifvoid\@lt@firsthead \@lt@head
      \else                 \@lt@firsthead \fi}%
   \let\\\@lt@cr
   \let\cline\@lt@cline
   \let\hline\@lt@hline
   \let\multicolumn\@lt@multicolumn
   \let\caption\@lt@setcaption
   \let\@@label\label
   \let\label\@lt@label
   \let\newpage\tabularbreak
   \global\@lt@nocaptiontrue
   \global\let\@lt@makecaption@stepcounter\@lt@makecaption@stepcounter@
   \global\let\@lt@caption\@empty
   \global\let\@lt@captionnumber\@empty
   \gdef\@lt@optional@vspace{\z@}}
\def\@lt@start@entrybox@{\setbox\z@\hbox\bgroup}
\newif\if@lt@wdcheck
\global\@lt@wdchecktrue
\def\@lt@end@entrybox@{\@lt@end@entrybox@@\@ne}
\def\@lt@end@entrybox@@#1{%
   \egroup
   \ifdim\@lt@maxht<\ht\z@ \xdef\@lt@maxht{\the\ht\z@}\fi
   \ifdim\@lt@maxdp<\dp\z@ \xdef\@lt@maxdp{\the\dp\z@}\fi
   \count@#1\relax \ifnum\count@<\@ne \count@\@ne \fi
   \dimen@\wd\z@ \divide\dimen@\count@
   \if@lt@wdcheck
      \@whilenum\count@>\z@\do{%
         \global\advance\@lt@colcnt\@ne
         \advance\count@\m@ne
         \ifdim\csname @lt@maxwd@\the\@lt@colcnt\endcsname<\dimen@
            \expandafter\xdef\csname @lt@maxwd@\the\@lt@colcnt\endcsname{%
               \the\dimen@}%
         \fi}%
   \fi
   \unhbox\z@}
\def\@lt@start@pbox@#1{\setbox\z@\hbox\bgroup
   \vtop\bgroup\hsize#1\relax\@arrayparboxrestore}
\def\@lt@end@pbox@{%
   \if@lt@wdcheck \@finalstrut\@arstrutbox\par \fi
   \egroup\@lt@end@entrybox@@\@ne}
\def\@lt@putoption@{%
   \if@lt@wdcheck \expandafter\@firstofone
   \else          \expandafter\hphantom    \fi}
\def\@lt@cr{%
   &%%% terminate the entry in the last column
   {\ifnum0=`}\fi
   \@ifstar\@lt@cr@\@lt@cr@}
\def\@lt@cr@{\@ifnextchar[\@lt@cr@@{\@lt@cr@@[\z@]}}
\def\@lt@cr@@[#1]{%
   \ifdim#1<\z@ \expandafter\@lt@ncr
   \else        \expandafter\@lt@pcr \fi
   {#1}}
\def\@lt@pcr#1{\ifnum0=`{\fi}%
   \gdef\@lt@optional@vspace{\z@}%
   \@tempdima\ht\@arstrutbox
   \@tempdimb\dp\@arstrutbox \advance\@tempdimb#1\relax
   \vrule\@height\@tempdima \@depth\@tempdimb \@width\z@
   \dimen@
      \ifdim\@lt@maxht<\@tempdima \@tempdima
      \else                       \@lt@maxht \fi
   \advance\dimen@
      \ifdim\@lt@maxdp<\@tempdimb \@tempdimb
      \else                       \@lt@maxdp \fi
   \@tempdima\@lt@goalsize \advance\@tempdima-\dimen@
   \ifdim\@tempdima<\z@
      \gdef\@lt@next{\@lt@breaktabular}%
   \else
      \global\@lt@goalsize\@tempdima
      \global\let\@lt@next\@empty
   \fi
   \global\@lt@colcnt\z@
   \gdef\@lt@maxht{\z@}%
   \gdef\@lt@maxdp{\z@}%
   \cr
   \@lt@next}
\def\@lt@ncr#1{\ifnum0=`{\fi}%
   \xdef\@lt@optional@vspace{#1}%
   \copy\@arstrutbox
   \dimen@
      \ifdim\@lt@maxht<\ht\@arstrutbox \ht\@arstrutbox
      \else                            \@lt@maxht     \fi
   \advance\dimen@
      \ifdim\@lt@maxdp<\dp\@arstrutbox \dp\@arstrutbox
      \else                            \@lt@maxdp     \fi
   \@tempdima\@lt@goalsize \advance\@tempdima-\dimen@
   \ifdim\@tempdima<\z@
      \gdef\@lt@next{\@lt@breaktabular}%
   \else
      \@tempdimb\@lt@optional@vspace\relax
      \advance\@tempdima-\@tempdimb
      \global\@lt@goalsize\@tempdima
      \gdef\@lt@next{\noalign{\vskip\@lt@optional@vspace}}%
   \fi
   \global\@lt@colcnt\z@
   \gdef\@lt@maxht{\z@}%
   \gdef\@lt@maxdp{\z@}%
   \cr
   \@lt@next}
\newdimen\@@arrayrulewidth
\global\@@arrayrulewidth\arrayrulewidth
\global\@@arrayrulewidth\arrayrulewidth
\def\@lt@hline{%
   \noalign{\ifnum0=`}\fi
   \@ifnextchar[\@lt@hline@{\@lt@hline@[\arrayrulewidth]}}
\def\@lt@hline@[#1]{%
   \dimen@#1\relax \ifdim\dimen@<\z@ \dimen@\z@ \fi
   \global\@@arrayrulewidth\dimen@
   \hrule height\z@
   \global\advance\@lt@goalsize-\dimen@
   \@ifnextchar[\@lt@hline@@\@lt@hline@@}%%% skip redundant spaces
\def\@lt@hline@@{\futurelet\@tempa\@lt@hline@@@}
\def\@lt@hline@@@{%
   \ifx\@tempa\hline
      \global\advance\@lt@goalsize-\@lt@doublerulesep
   \fi
   \xdef\@lt@gtempa{%
      \noexpand\@@cline@{1}{\the\@lt@maxcols}%
      \noalign{%
         \ifx\@tempa\hline \vskip\@lt@doublerulesep \fi
         \global\@@arrayrulewidth\arrayrulewidth}}%
   \ifnum0=`{\fi}%
   \@lt@gtempa}
\def\@lt@cline{%
   \noalign{\ifnum0=`}\fi
   \@ifnextchar[\@lt@cline@{\@lt@cline@[\arrayrulewidth]}}
\def\@lt@cline@[#1]{%
   \global\@@arrayrulewidth#1\relax
   \ifnum0=`{\fi}%
   \@lt@cline@@}
\def\@lt@cline@@#1{\@cline#1\@nil}
\def\@cline#1-#2\@nil{%
   \@@cline@{#1}{#2}%
   \noalign{%
      \vskip-\@@arrayrulewidth
      \global\@@arrayrulewidth\arrayrulewidth}}
\def\@@cline@#1#2{%
   \omit
   \@multicnt#1%
   \advance\@multispan\m@ne
   \ifnum\@multicnt=\@ne\@firstofone{&\omit}\fi
   \@multicnt#2%
   \advance\@multicnt-#1%
   \advance\@multispan\@ne
   \leaders\hrule\@height\@@arrayrulewidth\hfill
   \cr}
\def\@lt@starttabular{\@tempdimb\z@\@lt@starttabular@}
\def\@lt@starttabular@{%
   \@set@captionskip@for@table
   \ifx\@lt@caption\@empty
      \setbox\@lt@captionbox\box\voidb@x
   \else
      \if@lt@usecaption
         \setbox\@lt@captionbox\vbox{%
            \hsize\@lt@caption@hsize \linewidth\hsize
            \@lt@makecaption\@lt@caption}%
      \else
         \setbox\@lt@captionbox\box\voidb@x
      \fi
   \fi
   \dimen@\z@
   \@for\@tempa:=\@lt@captionbox,\@lt@headbox,\@lt@foot\do{%
      \advance\dimen@\ht\@tempa\relax
      \advance\dimen@\dp\@tempa\relax}%
   \@tempdima\textheight \advance\@tempdima-\dimen@
   \advance\@tempdima-\@tempdimb
   \global\@lt@goalsize\@tempdima
   \global\@lt@colcnt\z@
   \gdef\@lt@maxht{\z@}%
   \gdef\@lt@maxdp{\z@}%
   \setbox\@lt@currbox\vbox\bgroup
      \hsize\@lt@hsize \tabskip\@centering
      \def\@tempa{\halign to\@lt@hsize}%
      \expandafter\@tempa\expandafter\bgroup\@lt@preamble}
\def\@lt@endtabular#1{%
   \crcr\egroup\egroup
   \ifx#1\@empty\relax \else
      \setbox#1\box\@lt@currbox
      \expandafter\@lt@starttabular
   \fi}
\def\endhead{\@lt@endtabular\@lt@head}
\def\endfirsthead{\@lt@endtabular\@lt@firsthead}
\def\endfoot{\@lt@endtabular\@lt@foot}
\def\endlastfoot{\@lt@endtabular\@lt@lastfoot}
\def\@lt@setcaption{%
   \noalign{\ifnum0=`}\fi
   \@ifstar\@lt@setcaption@\@lt@setcaption@}
\def\@lt@setcaption@{\@ifnextchar[\@lt@setcaption@@{\@lt@setcaption@@[]}}
\long\def\@lt@setcaption@@[#1]#2{%
   \global\@lt@nocaptionfalse
   \gdef\@lt@captionnumber{#1}%
   \gdef\@lt@caption{#2}%
   \@lt@remove@cr}
\def\@lt@remove@cr{\@ifnextchar[\@lt@remove@cr@\@lt@remove@cr@}
\def\@lt@remove@cr@{\futurelet\let@token\@lt@remove@cr@@}
\def\@lt@remove@cr@@{%
   \ifx\let@token\\%
      \def\@tempa{\@gobble}%
   \else
      \let\@tempa\@empty
   \fi
   \ifnum0=`{\fi\expandafter}\@tempa}
\def\@lt@label#1{%
   \noalign{\ifnum0=`}\fi
   \def\@tempa{#1}%
   \@onelevel@sanitize\@tempa
   \edef\@tempa{\noexpand\label{\@tempa}}%
   \@csc@t\@tempa\@lt@caption\@tempa
   \global\let\@lt@caption\@tempa
   \@lt@remove@cr}
\def\@lt@makecaption{%
   \@lt@makecaption@stepcounter
   \global\let\@lt@makecaption@stepcounter\relax
   \@dblarg\@lt@makecaption@}
\def\@lt@makecaption@stepcounter@{%
   \ifx\@lt@captionnumber\@empty
      \refstepcounter{table}%
      \global\let\@lt@currentlabel\@currentlabel
      \gdef\@lt@currnumber{\fnum@table}%
   \else
      \global\let\@lt@currentlabel\@lt@captionnumber
      \gdef\@lt@currnumber{\tablename~\@lt@captionnumber}%
   \fi}%
\global\let\@lt@currentlabel\@empty
\long\def\@lt@makecaption@[#1]#2{%
   \par
   \begingroup
   \@parboxrestore
   \if@minipage \@setminipage \fi
   \let\label\@@label
   \let\@currentlabel\@lt@currentlabel
   \normalsize
   \@makecaption\@lt@currnumber{\ignorespaces #2}\par
   \endgroup}
\def\@lt@breaktabular{%
   \egroup\egroup
   \setbox\@lt@currbox\vbox{%
      \unvbox\@lt@currbox
      \global\setbox\@ne\lastbox}%
   \@lt@output@tabular\voidb@x
   \global\setbox\@lt@prevline\box\@ne
   \@tempdimb\ht\@lt@prevline \advance\@tempdimb\dp\@lt@prevline
   \@lt@starttabular@}
\def\tabularbreak{%
   \egroup\egroup
   \@lt@output@tabular\voidb@x
   \global\setbox\@lt@prevline\box\voidb@x
   \@tempdimb\z@
   \@lt@starttabular@}
\def\@lt@output@tabular#1{%
   \ifnum#1<\z@\else
      \setbox\@lt@currbox\vbox{%
         \box\@lt@captionbox
         \copy\@lt@headbox
         \box\@lt@prevline
         \vskip\@lt@optional@vspace
         \box\@lt@currbox
         \def\@tempa{\@lt@foot}%
         \ifnum#1=\@lt@lastfoot \ifvoid\@lt@lastfoot\else
            \def\@tempa{\@lt@lastfoot}%
         \fi\fi
         \copy\@tempa}%
   \fi
   \def\@lt@headbox{\@lt@head}%
   \@lt@output@tabular@}
\def\@lt@output@tabular@{%
   \ifx\@lt@firstposition\@empty
      \def\@tempa{\relax}%
   \else
      \edef\@tempa{[\@lt@firstposition]}%
      \let\@lt@firstposition\@empty
   \fi
   \edef\@tempa{\noexpand\@dblfloat{table}\@tempa}%
   \@tempa\box\@lt@currbox\end@dblfloat
   \if@lt@usecaption \gdef\@lt@caption{(Continued)}\fi} %%%08D14
\def\@lt@write@boxsize{%
   \if@filesw
      \count@\z@
      \@tempswafalse
      \@whilenum\count@<\@lt@maxcols\do{%
         \advance\count@\@ne
         \@tempdima\csname @lt@maxwd@\the\count@\endcsname\relax
         \@tempdimb\csname @lt@wd@\the\@lt@id @\the\count@\endcsname\relax
         \advance\@tempdima-\@tempdimb
         \ifdim\@tempdima<\z@ \@tempdima-\@tempdima \fi
         \ifdim\@lt@colwd@fuzz<\@tempdima \@tempswatrue \fi
         \immediate\write\@auxout{%
            \string\@set@ltdata{\the\@lt@id}{\the\count@}{%
               \csname @lt@maxwd@\the\count@\endcsname}}}%
   \else
      \@tempswafalse
   \fi
   \if@tempswa
      \@lt@warning{The width of each column may have changed.}%
   \fi}
\def\@lt@colwd@fuzz{.1\p@}
\def\@set@ltdata#1#2#3{\expandafter\gdef\csname @lt@wd@#1@#2\endcsname{#3}}
\long\def\@lt@multicolumn#1#2#3{%
   \multispan{#1}\begingroup
   \let\@preamble\@empty
   \protected@edef\@tempa{#2}%
   \expandafter\@lt@expast\@tempa*0x\@nnil
   \expandafter\@lt@mkpream\@preamble\@nnil
   \def\@sharp{#3}\set@typeset@protect
   \let\@lt@start@entrybox\@lt@start@entrybox@
   \def\@lt@end@entrybox{\@lt@end@entrybox@@{#1}}%
   \let\@lt@start@pbox\@lt@start@pbox@
   \def\@lt@end@pbox{%
      \@finalstrut\@arstrutbox\par\egroup\@lt@end@entrybox@@{#1}}%
   \let\@lt@putoption\@lt@putoption@
   \@arstrut\@preamble\hbox{}\endgroup\ignorespaces}
%
%%% make a slight change to array/tabular environment
\def\@array[#1]#2{%
   \if #1t\vtop \else \if#1b\vbox \else \vcenter \fi\fi
   \bgroup
   \setbox\@arstrutbox\hbox{%
      \vrule \@height\arraystretch\ht\strutbox
             \@depth\arraystretch \dp\strutbox
             \@width\z@}%
   \@mkpream{#2}%
   \edef\@preamble{%
      \ialign \noexpand\@halignto
         \bgroup \@arstrut \@preamble \tabskip\z@skip \cr}%
   \let\@startpbox\@@startpbox \let\@endpbox\@@endpbox
   \let\tabularnewline\\%
   \let\par\@empty
   \let\multicolumn\@@multicolumn
   \let\cline\@@cline
   \let\hline\@@hline
   \let\@sharp##%
   \set@typeset@protect
   \lineskip\z@skip\baselineskip\z@skip
   \ifhmode \@preamerr\z@ \@@par\fi
   \@preamble}
\let\@@cline\cline
\let\@@hline\hline
\let\@@multicolumn\multicolumn
%
%%% page styles
\let\lett\@empty
\def\ps@myheadings{%
   \let\@oddfoot\@empty\let\@evenfoot\@empty
   \def\@evenhead{%
      \@set@proofmark
      \thepage\hfil\slshape\leftmark}%
   \def\@oddhead{%
      \@set@proofmark
      {\slshape\rightmark}\hfil\thepage}%
   \let\@mkboth\@gobbletwo}
\def\@sidelabelsep{13pt}
\def\ps@firstpage{%
   \def\@oddhead{\hbox to \textwidth{\hphantom{\fboxsep=0pt\fbox{\vbox to 54pt{\hbox to 46pt{}}}}\hfill\hspace*{-6pt}\vbox to 54pt{\hsize250pt{\raggedleft\rhfont{\itshape Publ. Astron. Soc. Japan}\ (\@jyear)\ \@jvol(\@Issue),\ \thepage--\@endpage\par%
\@doi\par}\vfill}\hspace*{6pt}\hspace*{1.5pc}\hphantom{\fboxsep=0pt\fbox{\vbox to 54pt{\hbox to 46pt{}}}}}\rlap{\hspace*{10pt}\vbox to 54pt{\foliofont\thepage}}}%
   \let\@evenhead\@oddhead
   \def\@oddfoot{\hbox to \textwidth{%
     \vbox to 5pt{{\hsize\textwidth{\rffont\copyright\ \@jyear.\ Astronomical Society of Japan.\par}}}}}%
   \def\@evenfoot{}%
   \let\@mkboth\@gobbletwo}
%%
\def\oddfolio{{\foliofont\thepage}}
\def\evenfolio{{\foliofont\thepage}}
%%
\def\ps@headings{%
   \def\@evenhead{\vbox{\hsize\textwidth%
{\evenfolio}\hfill{\rhhfont{\itshape Publications of the Astronomical Society of Japan},\ (\@jyear),\ Vol.\ \@jvol,\ No.\ \@Issue}\par\vspace*{5.5pt}
{\vrule width\textwidth height1pt}}}%
   \def\@oddhead{\vbox{\hsize\textwidth%
{\rhhfont{\itshape Publications of the Astronomical Society of Japan},\ (\@jyear),\ Vol.\ \@jvol,\ No.\ \@Issue}\hfill{\oddfolio}\par\vspace*{5.5pt}
{\vrule width\textwidth height1pt}}}%%%
   \def\@oddfoot{%
      \hfill
      \rlap{%
         \kern\@sidelabelsep
         \@put@sidelabel\@oddsidelabel}}%
   \def\@evenfoot{%
      \llap{%
         \@put@sidelabel\@evensidelabel
         \kern\@sidelabelsep}%
      \hfill}%
   \let\@mkboth\@gobbletwo}
\def\@put@sidelabel#1{%
   \vbox to\z@{\hsize\evensidemargin
      \vss
      \vbox to\textheight{\vss#1}%
      \vskip\footskip}}
\let\@oddsidelabel\@empty
\let\@evensidelabel\@empty
\def\@@Author{\ifx\@Author\relax \leftmark \else \@Author \fi}
\def\@@runninghead{\ifx\@runninghead\relax \rightmark \else \@runninghead \fi}
\def\ps@headnombre{%
   \def\@oddhead{%
      \@set@proofmark
      \hfill{\slshape\thepage}}%
   \def\@evenhead{%
      \@set@proofmark
      {\slshape\thepage}\hfill}%
   \let\@oddfoot\@empty
   \let\@evenfoot\@empty
   \let\@mkboth\@gobbletwo}
\def\ps@sample{%
   \let\ps@firstpage\ps@plain
   \def\@evenhead{\normalsize\normalfont
      \rlap{\lett\thepage}\hfill\@@Author\hfill}%
   \def\@oddhead{\normalsize\normalfont
      \hfill\@@runninghead\hfill\llap{\lett\thepage}}%
   \let\@oddfoot\@empty
   \let\@evenfoot\@empty
   \let\@mkboth\@gobbletwo}
\let\@set@proofmark\relax
%
%%% bibliography
\def\etal{et~al.}
\newdimen\bibindent
\setlength\bibindent{1.5em}
\def\newblock{\hskip .11em\@plus.33em\@minus.07em}
\let\@openbib@code\@empty
%%%\let\@biblabel\@firstofone
\let\ADSentry\@secondoftwo
\def\bibsectionfont{\fontfamily{\sfdefault}\if@proofread\fontsize{12}{14}\else\fontsize{11}{13}\fi\selectfont\bfseries\rightskip0pt plus1fill}
%%
\def\thebibliography#1{\let\sectionfont\bibsectionfont%
   \if@twocolumn
      \let\@tempa\relax
   \else
      \if@noskipsec \leavevmode \fi
      \ifhmode \unskip\par \fi
      \addvspace\defaultbaselineskip
      \nobreak
      \if@proofread \let\@tempa\relax
      \else         \def\@tempa{\@init@twocolbib}%
      \fi
   \fi
   \@tempa
   \global\@in@appendixfalse
   \bibliofont%
   \section*{\bibname}%
   \list{}%
      {\leftmargin 15pt
       \itemindent-\leftmargin
       \labelwidth\z@
       \itemsep\z@}%
   \let\@prev@author\@empty
   \let\@bib@year\@empty
   \sloppy \sfcode`\.=\@m \hyphenpenalty\@M
   \bibliofont}
\def\endthebibliography{%
   \def\@noitemerr{\@latex@warning{Empty `thebibliography' environment}}%
   \@topsepadd\z@
   \endlist
   \let\@tempa\relax
   \if@twocolumn\else \if@proofread\else
      \def\@tempa{\@close@twocolbib}%
   \fi\fi
   \@tempa}
\def\bibitem{\@ifnextchar[\@lbibitem\@bibitem}
\def\@bibitem{%
   \let\@bib@author\@prev@author
   \@set@biblabel}
\def\@lbibitem[#1]{%
   \@bib@parse#1()\@nil
   \@set@biblabel}
\def\@bib@parse#1(#2)#3\@nil{%
   \def\@bib@author{#1}%
   \protected@edef\@bib@year{\zap@space#2 \@empty}}
\def\@set@biblabel#1{%
   \ifx\@bib@author\@empty
      \@latex@warning{Author name should be given
         for reference entry ``#1''}%
   \fi
   \ifx\@bib@year\@empty
      \@latex@warning{Publication year should be given
         for reference entry ``#1''}%
   \fi
   \if@filesw
      \begingroup
      \let\protect\noexpand
      \immediate\write\@auxout{%
         \string\bibcite{\@ref@prefix#1}{{\@bib@author}{\@bib@year}}}%
      \endgroup
   \fi
   \let\@prev@author\@bib@author
   \item[]}
\def\bysame{\ifvmode\leavevmode\fi \hbox to3em{\hrulefill}\thinspace}
\newbox\@bib@textbox
\def\textminimum{3}
\def\@init@twocolbib{%
   \dimen@\textwidth \advance\dimen@-\columnsep \divide\dimen@\tw@
   \columnwidth\dimen@
   \global\setbox\@bib@textbox\vbox\bgroup
      \hsize\dimen@
      \@parboxrestore
      \@setminipage}
\def\@close@twocolbib{%
      \ifhmode \unskip\par \fi
      \vskip-\lastskip
      \global\@minipagefalse
      \egroup
   \@twocolbib@sizecheck}
\def\@twocolbib@sizecheck{%
   \ifdim\pagegoal>\textheight
      \dimen@\@colroom
   \else
      \dimen@\pagegoal \advance\dimen@-\pagetotal
   \fi
   \@tempdima\defaultbaselineskip\relax \@tempdima\textminimum\@tempdima
   \ifdim\dimen@<\@tempdima
      \ifdim\dimen@>\z@
         \def\@tempa{\vbox{}\newpage\@twocolbib@sizecheck}%
      \else
         \def\@tempa{\vbox{}\@twocolbib@sizecheck}%
      \fi
   \else
      \def\@tempa{\@twocolbib@splitbox}%
   \fi
   \@tempa}
\def\@twocolbib@htfuzz{\p@}
\def\@twocolbib@splitbox{%
   \begingroup
   \vbadness\@M \vfuzz\maxdimen
   \ifdim.5\ht\@bib@textbox<\dimen@
      \dimen\tw@\defaultbaselineskip\relax
      \@tempdima.5\ht\@bib@textbox
      \dimen@\@tempdima
      \@tempdimb\maxdimen
      \setbox4\box\@bib@textbox
      \@whiledim\@tempdima<\@tempdimb\do{%
         \setbox6=\copy4\relax
         \setbox\z@\vsplit6 to\dimen@
         \setbox\z@\vbox{\unvbox\z@\vskip-\lastskip}%
         \setbox\tw@\vbox{\unvbox6\vskip-\lastskip}%
         \@tempdima\ht\z@  \advance\@tempdima\dp\z@
         \@tempdimb\ht\tw@ \advance\@tempdimb\dp\tw@
         \advance\@tempdima\@twocolbib@htfuzz\relax
         \advance\dimen@.5\dimen\tw@}%
   \else
      \setbox\z@ \vsplit\@bib@textbox to\dimen@
      \setbox\z@\vbox{\unvbox\z@}%
      \setbox\tw@\vsplit\@bib@textbox to\dimen@
      \setbox\tw@\vbox{\unvbox\tw@}%
   \fi
   \@tempdima\ht\z@
   \@tempdimb\ht\tw@
   \dimen@ \ifdim\@tempdima>\@tempdimb \@tempdima \else \@tempdimb \fi
   \@tempdima \ifdim\dp\z@<\dp\tw@ \dp\tw@ \else \dp\z@ \fi
   \hbox to\textwidth{%
      \hbox to\columnwidth{%
         \vbox to\dimen@{\unvbox\z@\vfill\hrule\@height\z@}%
         \hss}%
      \hss
      \hbox to\columnwidth{%
         \vbox to\dimen@{\unvbox\tw@\vfill\hrule\@height\z@}%
         \hss}}%
   \endgroup
   \ifvoid\@bib@textbox \let\@tempa\@empty
   \else                \def\@tempa{\newpage\@twocolbib@sizecheck}%
   \fi
   \@tempa}
\DeclareRobustCommand\cite{\@cite@\@empty\@empty\@citeform@both}
\DeclareRobustCommand\yearcite{\@cite@\@empty\@empty\@citeform@year}
\DeclareRobustCommand\authorcite{\@cite@\@empty\@empty\@citeform@author}
\DeclareRobustCommand\citep{\@cite@()\@citeform@both}
\DeclareRobustCommand\citet{\@cite@\@empty\@empty\@citeform@text}
\def\@cite@#1#2#3{%
   \def\@cite@prefix{#1}%
   \def\@cite@suffix{#2}%
   \@ifnextchar[%
      {\@tempswatrue\let\@citeform#3\@citex}%
      {\@tempswafalse\let\@citeform#3\@citex[]}}
\def\@citex[#1]#2{%
   \let\@citea\@empty
   \@cite{\@for\@citeb:=#2\do{%
      \@citea\def\@citea{;\penalty\@m\ }%
      \edef\@citeb{\expandafter\@firstofone\@citeb\@empty}%
      \if@filesw\immediate\write\@auxout{\string\citation{\@citeb}}\fi
      \@ifundefined{b@\@ref@prefix\@citeb}%
         {\mbox{\reset@font\bfseries ?}%
          \G@refundefinedtrue
         \@latex@warning{Citation `\@citeb' on page \thepage\space undefined}}%
         {\@citeform\@citeb}}}{#1}}
\def\@citeform@both#1{%
   \expandafter\expandafter\expandafter\@citeform@both@
   \csname b@\@ref@prefix#1\endcsname\@empty\@empty}
\def\@citeform@both@#1#2{#1\penalty0\ #2}
\def\@citeform@year#1{%
   \expandafter\expandafter\expandafter\@secondoftwo
   \csname b@\@ref@prefix#1\endcsname\@empty\@empty}
\def\@citeform@author#1{%
   \expandafter\expandafter\expandafter\@firstoftwo
   \csname b@\@ref@prefix#1\endcsname\@empty\@empty}
\def\@citeform@text#1{%
   \expandafter\expandafter\expandafter\@firstoftwo
   \csname b@\@ref@prefix#1\endcsname\@empty\@empty
   \penalty0\ (%
   \expandafter\expandafter\expandafter\@secondoftwo
   \csname b@\@ref@prefix#1\endcsname\@empty\@empty)}
\def\nocite#1{\@bsphack
   \@for\@citeb:=#1\do{%
      \edef\@citeb{\expandafter\@firstofone\@citeb}%
      \if@filesw\immediate\write\@auxout{\string\citation{\@citeb}}\fi
      \@ifundefined{b@\@ref@prefix\@citeb}%
         {\G@refundefinedtrue
          \@latex@warning{Citation `\@citeb' undefined}}{}}%
   \@esphack}
\def\@cite#1#2{{\@cite@prefix#1\if@tempswa , #2\fi\@cite@suffix}}
\let\@cite@prefix\@empty
\let\@cite@suffix\@empty
\def\article{\@ifnextchar[\@article{\@article[]}}
\def\@article[#1]#2{%
   \IfFileExists{#2}%
      {\begingroup
       \global\advance\@articleid\@ne
       \if@filesw
          \immediate\write\@auxout{%
             \string\@articledata{#2}%
                {{\the\@articleid}{\the\@lt@id}{\the\c@page}}}%
       \else
          \expandafter\ifx\csname @articledata@for@#2\endcsname\relax\else
             \expandafter\expandafter\expandafter\@split@articledata
                \csname @articledata@for@#2\endcsname\@empty\@empty\@empty
          \fi
       \fi
       \begingroup
       \let\@elt\@stpelt
       \cl@@article
       \endgroup
       \@aftersectionfalse
       \let\label\@article@label
       \let\ltx@label\@article@label%%% for amsmath package
       \let\ref\@article@ref
       \edef\@ref@prefix{\the\@articleid:}%
       \let\pageref\@article@pageref
       \let\@Author\relax
       \let\@runninghead\relax
       \let\@keywords\@empty
       \let\@title\@empty
       \let\@author\@empty
       \let\@affil@prefix\@empty
       \let\@affil@break\@empty
       \let\rdate\@empty
       \let\adate\@empty
       \let\pdate\@empty
       \let\@abstract\@empty
       \@skip@abstractfalse
       \let\@thanks\@empty
       \setbox\@abstract@textbox\box\voidb@x
       \let\@post@abstract\relax
       \edef\pageSTART{\thepage}%
       \edef\@tempa{r@\@ref@prefix @article:\the\@articleid:@}%
       \expandafter\ifx\csname\@tempa\endcsname\relax
          \typeout{Warning [pasj]: Last page for article `#2' is unknown.}%
          \def\pageEND{{\bfseries??}}%
          \def\@@pageEND{10000}%
       \else
          \edef\pageEND{%
             \expandafter\expandafter\expandafter
             \@secondoftwo\csname\@tempa\endcsname}%
          \let\@@pageEND\pageEND
       \fi
       \let\@plateno\@empty
       \def\theequation{\@arabic\c@equation}%
       \@in@appendixfalse
       \@@input\@filef@und
       \ifvmode \vskip-\lastskip \fi
       \edef\@tempa{\noexpand\label{@article:\the\@articleid:@}}%
       \@tempa
       #1%
       \if@openright \cleardoublepage \else \clearpage \fi
       \if@twocolumn\else \twocolumn \fi
       \endgroup}%
      {\typeout{No file #2.}}}
\def\@split@articledata#1#2#3{%
   \afterassignment\remove@to@nnil
   \global\@articleid 0#1\relax\@nnil
   \afterassignment\remove@to@nnil
   \global\@lt@id 0#2\relax\@nnil
   \afterassignment\remove@to@nnil
   \global\c@page 0#3\relax\@nnil}
\newcount\@articleid
\global\@articleid\z@
\def\@articledata#1#2{%
   \expandafter\gdef\csname @articledata@for@#1\endcsname{#2}}
\let\@ref@prefix\@empty
\def\@article@ref#1{%
   \expandafter\@setref\csname r@\@ref@prefix#1\endcsname
   \@firstoftwo{#1}}
\def\@article@pageref#1{%
   \expandafter\@setref\csname r@\@ref@prefix#1\endcsname
   \@secondoftwo{#1}}
\def\@article@label#1{%
   \@bsphack
   \protected@write\@auxout{}%
      {\string\newlabel{\@ref@prefix#1}{{\@currentlabel}{\thepage}}}%
   \@esphack}
\def\papers{\@ifnextchar[\@papers{\@papers[\papersname]}}
\def\@papers[#1]{%
   \if@filesw
      \immediate\write\@auxout{\string\@writefile{toc}%
         {\string\contentsline{block}{#1}{}}}%
   \fi
   \let\@oddsidelabel\@empty
   \let\@evensidelabel\@empty
   \let\lett\@empty}
\def\letters{\@ifnextchar[\@letters{\@letters[\lettersname]}}
\def\@letters[#1]{%
   \if@filesw
      \immediate\write\@auxout{\string\@writefile{toc}%
         {\string\contentsline{block}{#1}{}}}%
   \fi
   \def\@oddsidelabel{\Loddsidelabel}%
   \def\@evensidelabel{\Levensidelabel}%
   \def\lett{L}}
\def\Loddsidelabel{%
   \setbox\z@\hbox{%
      {\color[gray]{.8}%
       \dimen@\topmargin \advance\dimen@\headheight
       \advance\dimen@\headsep \advance\dimen@ 1in\relax
       \advance\dimen@.05\paperheight
       \@tempdima1.1\paperheight \advance\@tempdima-\dimen@
       \vrule\@width 10mm \@height\dimen@ \@depth\@tempdima}}%
   \ht\z@\z@ \dp\z@\z@ \wd\z@\z@ \box\z@
   \nointerlineskip
   \hbox{%
      \if@pasj@usefigure
         \kern 5\p@
         \vbox to\z@{%
            \vss\kern-15\p@
            \hbox{\rotatebox{90}{\sffamily
               \@makeoutline{L\,E\,T\,T\,E\,R}}}%
            \vss}%
      \else
         \tiny\sffamily LETTER
      \fi}%
   \vfill}
\let\Levensidelabel\@empty
\def\@makeoutline#1{%
   \mbox{%
      \setbox\z@\hbox{{\color{white}#1}}%
      \setbox\tw@\hbox{{\color{black}#1}}%
      \wd\tw@\z@
      \dimen@.2\p@
      \kern-\dimen@\copy\tw@\@@makeoutline\kern\dimen@
      \@@makeoutline
      \kern\dimen@\copy\tw@\@@makeoutline\kern-\dimen@
      \box\z@}}
\def\@@makeoutline{\raise\dimen@\copy\tw@\lower\dimen@\copy\tw@}
%
%%% \maketitle
\def\maketitle{%
   \def\@tempa{\@maketitle}%
   \ifx\@abstract\@empty
      \if@skip@abstract
         \def\@post@abstract{%
            \ifhmode \unskip\par \fi
            \addvspace\topsep
            \unvbox\@abstract@textbox}%
      \else
         \def\@post@abstract{\@maketitle}%
         \let\@tempa\relax
      \fi
   \else
      \def\@post@abstract{%
         \typeout{Notice: There is a redundant abstract environment.}%
         \setbox\@abstract@textbox\box\voidb@x}%
   \fi
   \@tempa}
\newskip\@saved@topsep
\let\@thanks\@empty
\def\@maketitle{%
   \thispagestyle{firstpage}%
   \begingroup
   \def\thefootnote{\fnsymbol{footnote}}%
   \def\@makefnmark{%
      {\normalfont\mathversion{normal}%
       $\m@th{}^{\@thefnmark}$}}%
   \if@twocolumn
      \@@maketitle
      \ifvoid\z@\else
         \@topnewpage[\box\z@]%
      \fi
   \else
      \newpage
      \@@maketitle
      \box\z@
   \fi
   \@thanks
   \endgroup
   \setcounter{footnote}{0}}
\def\@@maketitle{%
   \@saved@topsep\topsep
   \topsep\z@ \partopsep\z@
   \setbox\z@\vbox{\hsize\textwidth \linewidth\textwidth
\vspace*{50pt}%
\parindent0pt%
\begingroup
{\vrule width34.5pc height2pt depth0pt\par\vspace*{.6pt}}%
{\titlefont\@title\par\vspace*{8.5pt}}%
{\authorfont \printauthor\par\vspace*{7pt}}%
{\affilfont\@affil\par\vspace*{6pt}}%
{\corfont\@email\par\vspace*{6pt}}%
\endgroup
\begingroup\historyfont
Received   \@make@formatted@date\rdate
 ; Accepted  \@make@formatted@date\adate\par\vspace*{8.5pt}%
\endgroup
      \smallskip
      \if@skip@abstract\else
         \ifx\@abstract\@empty
            \vspace\@saved@topsep
            \unvbox\@abstract@textbox
            \vspace{-\@saved@topsep}%
         \else
              {\abstractheadfont \abstractname\par}%
              \vspace\@saved@topsep
              {\abstractfont\@abstract\par}\strut
              \@@par
              \vspace{-\@saved@topsep}%
         \fi
      \fi
      \ifx\@keywords\@empty\else\vspace*{11.6pt}%
            {\keywordheadfont Key words:}~{\keywordfont\@keywords\par}
      \fi%
\par\vspace*{3pt}%
{\vrule width34.5pc height2pt depth0pt}
      \par%
      \vspace*{15.5pt}}%
   \dimen@\ht\z@ \advance\dimen@\dp\z@
   \@whiledim\dimen@>\textheight\do{%
      \setbox\tw@\vsplit\z@ to\textheight
      \global\setbox\@outputbox\vbox to\textheight{\unvbox\tw@\vss}%
      \@outputpage
      \ifvoid\z@
         \dimen@\z@
      \else
         \setbox\z@\vbox{\unvbox\z@}%
         \dimen@\ht\z@ \advance\dimen@\dp\z@
      \fi}%
   \ifvoid\z@\else
      \dimen@\ht\z@ \advance\dimen@\dp\z@
      \@tempdima\defaultbaselineskip
      \advance\dimen@.8\@tempdima
      \divide\dimen@\@tempdima \count@\dimen@
      \dimen@\count@\@tempdima
      \setbox\z@\vbox to\dimen@{\box\z@\vss\hrule\@height\z@}%
   \fi}
\def\@gobbled@thanks#1#{\@gobbled@thanks@}
\let\@gobbled@thanks@\@gobble
\def\@make@formatted@date#1{%
   \expandafter\@make@formatted@date@#1///\@nil
   \@tempa}
\def\@make@formatted@date@#1/#2/#3/#4\@nil{%
   \def\@tempa{#1}%
   \def\@tempb{#2}%
   \def\@tempc{#3}%
   \def\@tempd{#4}%
   \global\let\@curr@year\@empty
   \ifx\@tempd\@empty\else
      \begingroup
      \afterassignment\remove@to@nnil
      \@tempcnta 0\@tempa\relax\@nnil
      \ifnum\@tempcnta>\z@\else \@tempcnta\z@ \fi
      \year\@tempcnta
      \xdef\@curr@year{\number\year}%
      \afterassignment\remove@to@nnil
      \@tempcnta 0\@tempb\relax\@nnil
      \ifnum\@tempcnta>\z@\else \@tempcnta\z@ \fi
      \month\@tempcnta
      \afterassignment\remove@to@nnil
      \@tempcnta 0\@tempc\relax\@nnil
      \ifnum\@tempcnta>\z@\else \@tempcnta\z@ \fi
      \day\@tempcnta
      \edef\@tempa{\def\noexpand\@tempa{\today}}%
      \expandafter\endgroup\@tempa
   \fi}
\def\thanks{\@ifnextchar[\@othanks\@nthanks}
\def\@othanks[#1]#2{%
   \footnotemark[\ensuremath{#1}]%
   \protected@xdef\@thanks{%
      \@thanks
      \protect\footnotetext[\ensuremath{#1}]{#2}}}
\def\@nthanks#1{%
   \footnotemark
   \protected@xdef\@thanks{%
      \@thanks
      \protect\footnotetext[\thefootnote]{#1}}}
\let\@post@abstract\relax
\newbox\@abstract@textbox
\def\abstract{%
   \global\setbox\@abstract@textbox\vbox\bgroup\parindent0pt%
      \hsize\textwidth \linewidth\hsize
      \topsep\z@ \partopsep\z@
      {\abstractheadfont\abstractname\par\vspace*{3pt}}%
      \abstractfont}
\def\endabstract{%
      \setbox\z@\hbox{g}%
      \ifhmode
         \unskip\nobreak
         \vrule \@width\z@ \@depth\dp\z@
         \par
      \else
         \dimen@\dp\z@
         \advance\dimen@-\prevdepth
         \ifdim\dimen@>\z@ \kern\dimen@ \fi
      \fi
      \vskip-\lastskip\kern\z@
   \egroup
   \aftergroup\@post@abstract}
\newif\if@skip@abstract
\global\@skip@abstractfalse
\def\noabstract{\@skip@abstracttrue}
\let\@abstract\@empty
\long\def\abst#1{\def\@abstract{#1}}
%
%%% old style font-change commands
\DeclareOldFontCommand{\rm}{\normalfont\rmfamily}{\mathrm}
\DeclareOldFontCommand{\sf}{\normalfont\sffamily}{\mathsf}
\DeclareOldFontCommand{\tt}{\normalfont\ttfamily}{\mathtt}
\DeclareOldFontCommand{\bf}{\normalfont\bfseries}{\mathbf}
\DeclareOldFontCommand{\it}{\normalfont\itshape}{\mathit}
\DeclareOldFontCommand{\sl}{\normalfont\slshape}{\@nomath\sl}
\DeclareOldFontCommand{\sc}{\normalfont\scshape}{\@nomath\sc}
\DeclareRobustCommand*\cal{\@fontswitch\relax\mathcal}
\DeclareRobustCommand*\mit{\@fontswitch\relax\mathnormal}
%
%%% tableofcontents
\def\@tocrmarg{50pt}
\def\@toclmarg{3em}
\def\@tocloffset{0pt}
\def\@tocroverfull{0pt}
\def\@dotsep{2}
\setcounter{tocdepth}{2}
\def\tableofcontents{%
   \if@twocolumn
      \@restonecolfalse\onecolumn
   \else
      \@restonecoltrue
   \fi
   \begingroup
   \normalfont
   \@tableofcontents@setup
   \centerline{\bfseries \contentsname}%
   \@starttoc{toc}%
   \newpage
   \if@openright \cleardoublepage \fi
   \endgroup
   \if@restonecol\else\twocolumn\fi}
\def\@tableofcontents@setup{%
   \leftskip\@tocloffset\relax \advance\leftskip\@toclmarg\relax
   \rightskip\@tocrmarg\relax
   \parfillskip-\rightskip \advance\parfillskip-\@tocroverfull\relax
   \dimen@-\parfillskip \edef\@pnumwidth{\the\dimen@}%
   \tolerance3000 \hyphenpenalty\@M}
\def\l@block#1#2{%
   \ifhmode \unskip\par \fi
   \noindent\kern-\@toclmarg{\bfseries#1}%
   \par}
\def\l@misc#1#2{%
   \ifhmode \unskip\par \fi
   \noindent\kern-\@toclmarg{\bfseries#1}%
   \nobreak\hfill\nobreak
   \setbox\z@\hbox{#2}%
   \ifdim\@pnumwidth>\wd\z@ \hbox to\@pnumwidth{\hss\unhbox\z@}%
   \else                    \box\z@                              \fi
   \par}
\def\l@article#1#2{%
   \@toc@get@articledata#1\relax\relax\relax
   \@toc@split@authorlist%%% \count@ := number of authors
   \@toc@rewrite@authorlist
   \ifhmode \unskip\par \fi
   \begingroup
   \begingroup
   \dimen@\@toclmarg\relax \advance\leftskip-\dimen@
   \noindent
   \@toc@title
   \nobreak
   \hfill\nobreak
   \setbox\z@\hbox{\@toc@prefix#2}%
   \ifdim\@pnumwidth>\wd\z@ \hbox to\@pnumwidth{\hss\unhbox\z@}%
   \else                    \box\z@                              \fi
   \par\nobreak
   \endgroup
   \@toc@addbreakfalse
   \parfillskip\z@\@plus 1fil
   \noindent
   {\itshape\@toc@authors}%
   \par\endgroup
   \addvspace{.5\defaultbaselineskip}}
\def\@toc@get@articledata#1#2#3{%
   \def\@toc@authorlist{#1}%
   \def\@toc@title{#2}%
   \def\@toc@prefix{#3}}
\def\@toc@split@authorlist{%
   \let\@toc@templist\@empty
   \count@\z@
   \expandafter\@toc@split@authorlist@\@toc@authorlist\@nil}
\def\@toc@split@authorlist@{%
   \@ifnextchar\bgroup
      \@toc@split@authorlist@loop
      \@toc@split@authorlist@@}
\def\@cs@break{\break}
\def\@toc@split@authorlist@loop#1{%
   \def\@toc@tempa{#1}%
   \ifx\@toc@tempa\@nnil
      \let\@toc@authorlist\@toc@templist
   \else
      \ifx\@toc@tempa\@cs@break\else \advance\count@\@ne \fi
      \def\@toc@tempa{\@toc@elt{#1}}%
      \@csc@t\@toc@templist\@toc@templist\@toc@tempa
      \expandafter\@toc@split@authorlist@loop
   \fi}
\def\@toc@split@authorlist@@#1\@nil{%
   \count@\@ne
   \def\@toc@authorlist{\@toc@elt{#1}}}
\def\@toc@rewrite@authorlist{%
   \let\@toc@authors\@empty
   \@toc@leaderskip\z@
   \let\@set@toc@leaderskip\@set@toc@leaderskip@
   \@tempcnta\count@
   \let\@toc@elt\@toc@rewrite@authorlist@elt
   \@toc@addbreakfalse
   \let\@toc@separator\@empty
   \def\@toc@break@separator{\unskip\break\null\tocleader}%
   \@toc@authorlist}
\newif\if@toc@addbreak
\def\@toc@rewrite@authorlist@elt#1{%
   \def\@tempa{#1}%
   \ifx\@tempa\@cs@break
      \@toc@addbreaktrue
   \else
      \@set@toc@leaderskip{#1}%
      \if@toc@addbreak
         \let\@toc@tempb\@toc@break@separator
         \@toc@addbreakfalse
      \else
         \let\@toc@tempb\@toc@separator
      \fi
      \expandafter\def\expandafter\@toc@tempa\expandafter{%
         \@toc@tempb\hbox{#1}}%
      \@csc@t\@toc@authors\@toc@authors\@toc@tempa
      \advance\@tempcnta\m@ne
      \ifnum\@tempcnta>\@ne%%% \@tempcnta: number of remaining author(s)
         \def\@toc@separator{, }%
         \def\@toc@break@separator{,\hfil\break}%
      \else
         \edef\@toc@separator{%
            \ifnum\count@>\tw@ ,\fi%%% This comma should be removed.
            \ and }%
         \edef\@toc@break@separator{%
            \ifnum\count@>\tw@ ,\fi%%% This comma should be removed.
            \hfil\break and }%
      \fi
   \fi}
\newdimen\@toc@leaderskip
\def\@set@toc@leaderskip@#1{%
   \setbox\z@\hbox{#1}%
   \@toc@leaderskip\wd\z@
   \let\@set@toc@leaderskip\@gobble}
\def\@toc@leader{%
   \hskip \z@ \@plus 3em \penalty-\@medpenalty
   \hskip \z@ \@plus-3em
   \ifdim\@toc@leaderskip>\z@
      \leaders
         \copy\@toc@leader@dot
         \hskip 6\wd\@toc@leader@dot\@plus\@toc@leaderskip
      \penalty-\@lowpenalty
      \hskip -\wd\@toc@leader@dot \@plus-\@toc@leaderskip\null
   \fi
   \leaders\copy\@toc@leader@dot\hfill
   \nobreak
   \@toc@leaderskip\z@}
\newbox\@toc@leader@dot
\normalfont
\setbox\z@\hbox{$\m@th\mkern \@dotsep mu\hbox{.}\mkern \@dotsep mu$}
\@tempdima\textwidth \@tempdimb\wd\z@
\advance\@tempdima.5\@tempdimb
\divide\@tempdima\@tempdimb
\count@\@tempdima
\@tempdima\textwidth \divide\@tempdima\count@
\setbox\@toc@leader@dot\hbox to\@tempdima{\hss\unhbox\z@\hss}
\def\tocleader{%
   \null\nobreak
   \leaders\copy\@toc@leader@dot\hfill
   \nobreak\null}
\def\@csc@t#1#2#3{%
   \expandafter\expandafter\expandafter\def
   \expandafter\expandafter\expandafter#1%
   \expandafter\expandafter\expandafter{\expandafter#2#3}}
\let\@@lineno\@empty
\expandafter\ifx\csname inputlineno\endcsname\relax\else
   \ifnum\inputlineno<\z@\else
      \def\@@lineno{l.\the\inputlineno\space}
   \fi
\fi
\def\l@section{\@dottedtocline{1}{20pt}{18pt}}
\def\l@subsection{\@dottedtocline{2}{-38pt}{20pt}}
\def\l@subsubsection{\@dottedtocline{3}{-58pt}{20pt}}
\def\l@paragraph{\@dottedtocline{4}{-78pt}{20pt}}
\def\l@subparagraph{\@dottedtocline{5}{-98pt}{20pt}}
\def\@localtoc@pnumwidth{12pt}
\def\@dottedtocline#1#2#3#4#5{%
   \ifnum#1>\c@tocdepth\else
      \ifhmode \unskip\par \fi
      \ifnum#1=\@ne%%% section
         \medskip
      \fi
      \begingroup
      \@tempdimb#2\relax
      \ifdim\@tempdimb<\z@
         \def\@numberline@adjust{\hfill}%
         \@tempdimb-\@tempdimb
      \else
         \let\@numberline@adjust\@empty
      \fi
      \@tempdima#3\relax
      \leftskip\@tempdima \advance\leftskip\@tempdimb
      \rightskip\@localtoc@pnumwidth\relax
      \parfillskip-\rightskip \advance\rightskip 20\p@
      \noindent
      \hskip-\@tempdima
      #4\nobreak\tocleader\nobreak
      \setbox\z@\hbox{#5}%
      \ifdim\@localtoc@pnumwidth<\wd\z@\else
         \setbox\z@\hbox to\@localtoc@pnumwidth{\hss\unhbox\z@}%
      \fi
      \box\z@
      \par
      \endgroup
   \fi}
\def\numberline#1{%
   \setbox\z@\hbox{\@numberline@adjust#1}%
   \advance\@tempdima -1em\relax
   \ifdim\wd\z@>\@tempdima\else
      \setbox\z@\hbox to\@tempdima{\unhbox\z@\hss}%
   \fi
   \box\z@\kern1em\relax}
\def\footnoterule{}
\@addtoreset{footnote}{@article}
\long\def\@makefntext#1{%
    \par
     \fontfamily{\sfdefault}\fontsize{7}{10.25}\selectfont %%%08D14
    \noindent\@hangfrom{\hbox to5\p@{\@makefnmark\hss}}#1}
\def\footnotemark{%
   \@ifnextchar[%
      \@xfootnotemark
     {\stepcounter{footnote}%
      \protected@xdef\@thefnmark{\thefootnote}%
      \@footnotemark}}
\def\@xfootnotemark[#1]{%
   \protected@edef\@thefnmark{#1}%
   \@footnotemark}
\def\@footnotemark{%
   \ifvmode \leavevmode \fi
   \edef\@x@sf{\the\spacefactor}\nobreak
   \@makefnmark
   \spacefactor\@x@sf
   \relax}
\def\footnotetext{%
   \@ifnextchar[%
      \@xfootnotenext
     {\protected@xdef\@thefnmark{\thempfn}%
      \@footnotetext}}
\def\@xfootnotenext[#1]{%
   \protected@edef\@thefnmark{#1}%
   \@footnotetext}
%
%%% leaders
\def\hrulefill{\leaders\hrule\hfill\kern\z@}
\def\dotfill{\cleaders\hbox{$\m@th \mkern1.5mu.\mkern1.5mu$}\hfill\kern\z@}
%
%%% astronomical symbols
\def\useastrosym{%
   \relax
   \ifmmode
      \expandafter\@use@astrosym@in@math
   \else
      \expandafter\@use@astrosym@in@text
   \fi}
\def\@use@astrosym@in@text#1{%
   \ifvmode \leavevmode \fi
   \begingroup
   \@use@astrosym@\@find@astrosym@text@offset{1}{#1}%
   \endgroup}
\def\@use@astrosym@in@math#1{%
   \mathchoice
      {\@use@astrosym@\@find@astrosym@math@offset{1}{#1}}%
      {\@use@astrosym@\@find@astrosym@math@offset{1}{#1}}%
      {\@use@astrosym@\@find@astrosym@math@offset\defaultscriptratio{#1}}%
      {\@use@astrosym@\@find@astrosym@math@offset
                      \defaultscriptscriptratio{#1}}}
\def\@use@astrosym@#1#2#3{%
   \hbox{%
      #1%
      \advance\count@#3\relax
      \edef\@astro@symbolcode{\the\count@}%
      \dimen@\f@size\p@ \dimen@#2\dimen@
      \@astrosym@getchar}}
\def\@find@astrosym@text@offset{%
   \edef\@tempa{\expandafter\@car\bfdefault\@empty\@nil}%
   \edef\@tempb{\expandafter\@car\f@series\@empty\@nil}%
   \ifx\@tempa\@tempb
      \count@100\relax
   \else
      \edef\@tempa{\sfdefault}%
      \ifx\@tempa\f@family
         \count@200\relax
      \else
         \count@\z@
      \fi
   \fi}
\def\@find@astrosym@math@offset{%
   \def\@tempa{bold}%
   \ifx\@tempa\math@version \count@100\relax
   \else                    \count@\z@        \fi}
\DeclareRobustCommand*\Sol{\ensuremath{\@solar}}
\def\@solar{\mathbin{\mathchoice{\@@solar}{\@@solar}{\odot}{\odot}}}
\def\@@solar{%
   \hbox{%
      \dimen@\f@size\p@
      \@tempdima.6\dimen@ \@tempdimb.4667\dimen@
      \advance\@tempdima.5\p@ \advance\@tempdimb.5\p@
      \divide\@tempdima\p@ \divide\@tempdimb\p@
      \@tempcnta\@tempdima \@tempcntb\@tempdimb
      \ifnum\@tempcnta<\@ne \@tempcnta\@ne \fi
      \ifnum\@tempcnta>15   \@tempcnta15  \fi
      \advance\@tempcnta95\relax
      \ifnum\@tempcntb<\@ne \@tempcntb\@ne \fi
      \ifnum\@tempcntb>15   \@tempcntb15  \fi
      \advance\@tempcntb111\relax
      \kern.5\dimen@
      \raise.2\dimen@\hbox to\z@{\tencirc\char\@tempcnta\hss}%
      \raise.2\dimen@\hbox to\z@{\fivecirc\char\@tempcntb\hss}%
      \kern.5\dimen@}}
\edef\@tempa{\fontname\tencirc\space at5pt}
\font\fivecirc\@tempa\relax
\DeclareRobustCommand*\Mercurius{\useastrosym{1}}
\DeclareRobustCommand*\Venus{\useastrosym{2}}
\DeclareRobustCommand*\Terra{\useastrosym{3}}
\DeclareRobustCommand*\Mars{\useastrosym{4}}
\DeclareRobustCommand*\Jupiter{\useastrosym{5}}
\DeclareRobustCommand*\Saturnus{\useastrosym{6}}
\DeclareRobustCommand*\varSaturnus{\useastrosym{23}}
\DeclareRobustCommand*\Uranus{\useastrosym{7}}
\DeclareRobustCommand*\Neptunus{\useastrosym{8}}
\DeclareRobustCommand*\varNeptunus{\useastrosym{24}}
\DeclareRobustCommand*\Pluto{\useastrosym{9}}
\DeclareRobustCommand*\varPluto{\useastrosym{25}}
\DeclareRobustCommand*\Luna{\useastrosym{10}}
\DeclareRobustCommand*\Aries{\useastrosym{11}}
\DeclareRobustCommand*\Taurus{\useastrosym{12}}
\DeclareRobustCommand*\Gemini{\useastrosym{13}}
\DeclareRobustCommand*\Cancer{\useastrosym{14}}
\DeclareRobustCommand*\Leo{\useastrosym{15}}
\DeclareRobustCommand*\Virgo{\useastrosym{16}}
\DeclareRobustCommand*\Libra{\useastrosym{17}}
\DeclareRobustCommand*\varLibra{\useastrosym{26}}
\DeclareRobustCommand*\Scorpio{\useastrosym{18}}
\DeclareRobustCommand*\Sagittarius{\useastrosym{19}}
\DeclareRobustCommand*\Capriconus{\useastrosym{20}}
\DeclareRobustCommand*\Aquarius{\useastrosym{21}}
\DeclareRobustCommand*\varAquarius{\useastrosym{27}}
\DeclareRobustCommand*\VarAquarius{\useastrosym{28}}
\DeclareRobustCommand*\Pisces{\useastrosym{22}}
\if@mfastrosym %%% use METAFONT version
\DeclareFontFamily{U}{astro}{}
\begingroup
\nfss@catcodes
\ifx\@astrofont\@empty \def\@astrofont{astrosym}\fi
\edef\x{\noexpand\DeclareFontShape{U}{astro}{m}{n}%
   {<-> s * [.9] \@astrofont}{}}
\expandafter\endgroup\x
\def\@astrosym@getchar{%
   \fontsize\dimen@\z@
   \usefont{U}{astro}{m}{n}%
   \char\@astro@symbolcode}
\else
\def\@astrosym@getchar{%
   \@tempdima.01875\dimen@ %%% \f@size = 10 ==> 1dot = 3/16 pt
   \dimen@1.5\@tempdima
   \setbox\z@\hbox{%
      \setbox\z@\hbox{%
         \let\@\@foc@ \def\@@##1{\gdef\@astrosym@shift{##1}}%
         \@nameuse{@astrosym@\@astro@symbolcode}}%
      \lower\@astrosym@shift\dimen@\box\z@}%
   \dp\z@\z@ \box\z@}
\def\@foc@#1{%
   \@tempcnta\z@
   \hbox to \@tempdima\bgroup\vbox\bgroup\@@foc@loop#1,-1,}
\def\@@foc@loop#1,{%
   \ifnum#1<\z@
      \let\@tempa\@@foc@end
   \else
      \ifodd\@tempcnta \let\@tempa\@@foc@
      \else            \let\@tempa\@@foc@blank \fi
   \fi
   \@tempa{#1}}
\def\@@foc@end#1{%
   \hrule\@width\@tempdima\@height\z@
   \egroup\egroup\ignorespaces}
\def\@@foc@#1{%
   \hrule\@height#1\@tempdima
   \advance\@tempcnta\@ne
   \@@foc@loop}
\def\@@foc@blank#1{%
   \kern#1\@tempdima
   \advance\@tempcnta\@ne
   \@@foc@loop}
\fi
%
%%% font data of astrosym (about 1000 lines)
\@namedef{@astrosym@0}{\@@{0}%
   \@{21,9,19}\@{18,15,16}\@{16,19,14}\@{14,23,12}\@{13,25,11}%
   \@{11,29,9}\@{10,12,7,12,8}\@{9,10,13,10,7}\@{8,9,17,9,6}%
   \@{7,8,21,8,5}\@{6,8,23,8,4}\@{6,7,25,7,4}\@{5,7,27,7,3}%
   \@{5,6,29,6,3}\@{4,7,29,7,2}\@{4,6,31,6,2}\@{3,7,31,7,1}%
   \@{3,6,33,6,1}\@{3,6,33,6,1}\@{2,6,35,6}\@{2,6,16,3,16,6}%
   \@{2,6,15,1,3,1,15,6}\@{2,6,14,1,5,1,14,6}\@{2,6,14,1,5,1,14,6}%
   \@{2,6,14,1,5,1,14,6}\@{2,6,15,1,3,1,15,6}\@{2,6,16,3,16,6}%
   \@{2,6,35,6}\@{3,6,33,6,1}\@{3,6,33,6,1}\@{3,7,31,7,1}\@{4,6,31,6,2}%
   \@{4,7,29,7,2}\@{5,6,29,6,3}\@{5,7,27,7,3}\@{6,7,25,7,4}\@{6,8,23,8,4}%
   \@{7,8,21,8,5}\@{8,9,17,9,6}\@{9,10,13,10,7}\@{10,12,7,12,8}\@{11,29,9}%
   \@{13,25,11}\@{14,23,12}\@{16,19,14}\@{18,15,16}\@{21,9,19}\@{49}}
\@namedef{@astrosym@1}{\@@{8}%
   \@{3,9,20,9,32}\@{1,14,15,13,30}\@{2,15,11,17,28}\@{3,16,7,21,26}%
   \@{3,17,5,23,25}\@{4,17,3,25,11,6,7}\@{11,11,1,10,7,10,10,6,7}%
   \@{14,17,11,9,9,6,7}\@{15,14,15,7,9,6,7}\@{16,12,17,7,8,6,7}%
   \@{16,11,19,6,8,6,7}\@{17,10,19,7,7,6,7}\@{17,9,21,6,7,6,7}%
   \@{18,8,21,7,6,6,7}\@{18,7,23,24,1}\@{18,7,23,24,1}\@{18,7,23,24,1}%
   \@{18,7,23,24,1}\@{18,7,23,24,1}\@{18,7,23,24,1}\@{18,8,21,7,6,6,7}%
   \@{17,9,21,6,7,6,7}\@{17,10,19,7,7,6,7}\@{16,11,19,6,8,6,7}%
   \@{16,12,17,7,8,6,7}\@{15,14,15,7,9,6,7}\@{14,17,11,9,9,6,7}%
   \@{11,11,1,10,7,10,10,6,7}\@{4,17,3,25,11,6,7}\@{3,17,5,23,25}%
   \@{3,16,7,21,26}\@{2,15,11,17,28}\@{1,14,15,13,30}\@{3,9,20,9,32}\@{73}}
\@namedef{@astrosym@2}{\@@{0}%
   \@{16,8,37}\@{13,14,34}\@{11,18,32}\@{10,20,31}\@{8,24,29}\@{7,26,28}%
   \@{6,11,6,11,12,6,9}\@{5,9,12,9,11,6,9}\@{4,8,16,8,10,6,9}%
   \@{4,7,18,7,10,6,9}\@{3,7,20,7,9,6,9}\@{3,6,22,6,9,6,9}%
   \@{2,7,22,7,8,6,9}\@{2,6,24,6,8,6,9}\@{2,6,24,6,8,6,9}%
   \@{1,6,26,6,7,6,9}\@{1,6,26,27,1}\@{1,6,26,27,1}\@{1,6,26,27,1}%
   \@{1,6,26,27,1}\@{1,6,26,27,1}\@{1,6,26,27,1}\@{1,6,26,6,7,6,9}%
   \@{2,6,24,6,8,6,9}\@{2,6,24,6,8,6,9}\@{2,7,22,7,8,6,9}%
   \@{3,6,22,6,9,6,9}\@{3,7,20,7,9,6,9}\@{4,7,18,7,10,6,9}%
   \@{4,8,16,8,10,6,9}\@{5,9,12,9,11,6,9}\@{6,11,6,11,12,6,9}%
   \@{7,26,28}\@{8,24,29}\@{10,20,31}\@{11,18,32}\@{13,14,34}\@{16,8,37}\@{61}}
\@namedef{@astrosym@3}{\@@{0}%
   \@{37,8,16}\@{34,14,13}\@{32,18,11}\@{31,20,10}\@{29,24,8}\@{28,26,7}%
   \@{27,11,6,11,6}\@{26,9,12,9,5}\@{25,8,16,8,4}\@{8,6,11,7,18,7,4}%
   \@{8,6,10,7,20,7,3}\@{8,6,10,6,22,6,3}\@{8,6,9,7,22,7,2}%
   \@{8,6,9,6,24,6,2}\@{8,6,9,6,24,6,2}\@{8,6,8,6,26,6,1}%
   \@{1,27,26,6,1}\@{1,27,26,6,1}\@{1,27,26,6,1}\@{1,27,26,6,1}%
   \@{1,27,26,6,1}\@{1,27,26,6,1}\@{8,6,8,6,26,6,1}\@{8,6,9,6,24,6,2}%
   \@{8,6,9,6,24,6,2}\@{8,6,9,7,22,7,2}\@{8,6,10,6,22,6,3}%
   \@{8,6,10,7,20,7,3}\@{8,6,11,7,18,7,4}\@{8,6,11,8,16,8,4}%
   \@{26,9,12,9,5}\@{27,11,6,11,6}\@{28,26,7}\@{29,24,8}\@{31,20,10}%
   \@{32,18,11}\@{34,14,13}\@{37,8,16}\@{61}}
\@namedef{@astrosym@4}{\@@{0}%
   \@{43,8,16}\@{40,14,13}\@{38,18,11}\@{37,20,10}\@{35,24,8}\@{34,26,7}%
   \@{33,11,6,11,6}\@{32,9,12,9,5}\@{31,8,16,8,4}\@{31,7,18,7,4}%
   \@{30,7,20,7,3}\@{30,6,22,6,3}\@{29,7,22,7,2}\@{29,6,24,6,2}%
   \@{29,6,24,6,2}\@{28,6,26,6,1}\@{28,6,26,6,1}\@{28,6,26,6,1}%
   \@{28,6,26,6,1}\@{28,6,26,6,1}\@{28,6,26,6,1}\@{26,8,26,6,1}%
   \@{12,1,11,10,26,6,1}\@{11,2,9,13,24,6,2}\@{11,2,7,15,24,6,2}%
   \@{10,3,5,18,22,7,2}\@{10,4,2,13,1,6,22,6,3}\@{9,18,3,7,20,7,3}%
   \@{8,17,6,7,18,7,4}\@{8,15,8,8,16,8,4}\@{7,14,11,9,12,9,5}%
   \@{6,13,14,11,6,11,6}\@{6,11,17,26,7}\@{5,12,18,24,8}%
   \@{4,14,19,20,10}\@{3,16,19,18,11}\@{2,18,20,14,13}\@{1,4,38,8,16}\@{67}}
\@namedef{@astrosym@5}{\@@{0}%
   \@{5,1,35,1,12}\@{4,4,31,3,12}\@{2,9,26,5,12}\@{1,13,20,8,12}%
   \@{1,17,12,12,12}\@{3,39,12}\@{5,37,12}\@{7,35,12}\@{10,32,12}%
   \@{13,21,2,6,12}\@{18,12,6,6,12}\@{36,6,12}\@{36,6,12}\@{36,6,12}%
   \@{36,6,12}\@{36,6,12}\@{36,6,12}\@{36,6,12}\@{36,6,12}\@{11,42,1}%
   \@{11,42,1}\@{11,42,1}\@{11,42,1}\@{11,42,1}\@{11,42,1}\@{36,6,12}%
   \@{36,6,12}\@{36,6,12}\@{36,6,12}\@{36,6,12}\@{36,6,12}\@{36,6,12}\@{54}}
\@namedef{@astrosym@6}{\@@{6}%
   \@{9,6,49}\@{9,6,49}\@{9,6,49}\@{9,6,49}\@{2,53,9}\@{2,53,9}\@{2,53,9}%
   \@{2,53,9}\@{2,53,9}\@{2,53,9}\@{9,6,7,6,36}\@{9,6,7,6,36}\@{9,6,6,6,37}%
   \@{9,6,6,6,37}\@{9,6,6,6,37}\@{21,6,37}\@{20,6,38}\@{20,6,27,4,7}%
   \@{20,6,25,8,5}\@{20,6,23,11,4}\@{20,6,20,16,2}\@{20,6,18,20}%
   \@{20,6,16,22}\@{20,6,14,14,2,7,1}\@{20,6,11,15,5,6,1}%
   \@{21,6,6,17,9,3,2}\@{21,26,14,1,2}\@{21,24,19}\@{22,21,21}%
   \@{23,18,23}\@{24,14,26}\@{26,8,30}\@{64}}
\@namedef{@astrosym@7}{\@@{5}%
   \@{40,8,16}\@{37,14,13}\@{35,18,11}\@{34,20,10}\@{32,24,8}\@{31,26,7}%
   \@{30,11,6,11,6}\@{29,9,12,9,5}\@{28,8,16,8,4}\@{18,1,9,7,18,7,4}%
   \@{17,2,8,7,20,7,3}\@{15,4,8,6,22,6,3}\@{14,5,7,7,22,7,2}%
   \@{12,6,8,6,24,6,2}\@{11,7,8,6,24,6,2}\@{9,9,7,6,26,6,1}%
   \@{7,24,11,4,11,6,1}\@{4,27,10,6,10,6,1}\@{1,30,10,6,10,6,1}%
   \@{1,30,10,6,10,6,1}\@{4,27,10,6,10,6,1}\@{7,24,11,4,11,6,1}%
   \@{9,9,7,6,26,6,1}\@{11,7,8,6,24,6,2}\@{12,6,8,6,24,6,2}%
   \@{14,5,7,7,22,7,2}\@{15,4,8,6,22,6,3}\@{17,2,8,7,20,7,3}%
   \@{18,1,9,7,18,7,4}\@{28,8,16,8,4}\@{29,9,12,9,5}\@{30,11,6,11,6}%
   \@{31,26,7}\@{32,24,8}\@{34,20,10}\@{35,18,11}\@{37,14,13}\@{40,8,16}\@{64}}
\@namedef{@astrosym@8}{\@@{0}%
   \@{18,2,41}\@{16,3,42}\@{14,4,43}\@{11,7,43}\@{8,41,12}\@{5,44,12}%
   \@{1,48,12}\@{2,47,12}\@{6,43,12}\@{9,40,12}\@{11,7,25,6,12}%
   \@{14,5,24,6,12}\@{16,3,24,6,12}\@{19,1,23,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{17,3,23,6,12}%
   \@{15,4,24,6,12}\@{13,5,25,6,12}\@{10,8,25,6,12}\@{7,53,1}\@{3,57,1}%
   \@{1,59,1}\@{3,57,1}\@{7,53,1}\@{10,50,1}\@{13,5,25,6,12}%
   \@{15,4,24,6,12}\@{17,3,23,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{19,1,23,6,12}\@{16,3,24,6,12}%
   \@{14,5,24,6,12}\@{11,7,25,6,12}\@{9,40,12}\@{6,43,12}\@{2,47,12}%
   \@{1,48,12}\@{5,44,12}\@{8,41,12}\@{11,7,43}\@{14,4,43}\@{16,3,42}%
   \@{18,2,41}\@{61}}
\@namedef{@astrosym@9}{\@@{0}%
   \@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,59,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{2,6,24,6,16,6,1}\@{2,6,24,6,16,6,1}\@{2,7,22,7,16,6,1}%
   \@{3,6,22,6,24}\@{3,7,20,7,24}\@{4,7,18,7,25}\@{4,9,14,9,25}%
   \@{5,11,8,11,26}\@{6,28,27}\@{7,26,28}\@{8,24,29}\@{10,20,31}%
   \@{12,16,33}\@{15,10,36}\@{61}}
\@namedef{@astrosym@10}{\@@{0}%
   \@{20,11,18}\@{17,17,15}\@{15,21,13}\@{13,25,11}\@{11,29,9}%
   \@{10,31,8}\@{9,12,9,12,7}\@{8,11,13,11,6}\@{7,10,17,10,5}%
   \@{6,9,21,9,4}\@{6,8,23,8,4}\@{5,8,25,8,3}\@{5,7,27,7,3}%
   \@{4,7,29,7,2}\@{4,7,10,9,10,7,2}\@{3,7,8,15,8,7,1}%
   \@{3,7,6,19,6,7,1}\@{3,6,6,21,6,6,1}\@{3,6,4,25,4,6,1}%
   \@{2,6,4,10,7,10,4,6}\@{2,6,3,8,13,8,3,6}\@{2,6,2,7,17,7,2,6}%
   \@{2,6,1,7,19,7,1,6}\@{2,13,21,13}\@{2,12,23,12}\@{2,11,25,11}%
   \@{2,11,25,11}\@{2,10,27,10}\@{2,10,27,10}\@{3,8,29,8,1}%
   \@{3,8,29,8,1}\@{3,7,31,7,1}\@{4,6,31,6,2}\@{4,6,31,6,2}%
   \@{5,5,31,5,3}\@{5,5,31,5,3}\@{6,4,31,4,4}\@{6,4,31,4,4}%
   \@{7,4,29,4,5}\@{8,3,29,3,6}\@{9,3,27,3,7}\@{10,2,27,2,8}%
   \@{11,2,25,2,9}\@{49}}
\@namedef{@astrosym@11}{\@@{1}%
   \@{7,6,43}\@{5,3,48}\@{4,3,49}\@{3,4,49}\@{3,3,50}\@{2,4,50}%
   \@{2,4,50}\@{2,4,50}\@{2,5,49}\@{2,6,48}\@{2,10,44}\@{3,8,1,3,41}%
   \@{3,16,37}\@{4,14,1,3,34}\@{5,21,30}\@{7,22,27}\@{10,23,23}%
   \@{13,23,20}\@{17,23,16}\@{20,23,13}\@{24,23,9}\@{28,22,6}%
   \@{31,23,2}\@{35,21}\@{31,23,2}\@{28,22,6}\@{24,23,9}\@{20,23,13}%
   \@{17,3,1,19,16}\@{13,23,20}\@{10,3,1,19,23}\@{7,22,27}\@{5,21,30}%
   \@{4,18,34}\@{3,16,37}\@{3,12,41}\@{2,10,44}\@{2,6,48}\@{2,5,49}%
   \@{2,4,50}\@{2,4,50}\@{2,4,50}\@{3,3,50}\@{3,3,50}\@{4,3,49}%
   \@{5,3,48}\@{7,6,43}\@{56}}
\@namedef{@astrosym@12}{\@@{4}%
   \@{10,7,44}\@{8,11,42}\@{7,13,41}\@{6,15,40}\@{5,17,39}%
   \@{4,4,7,8,16,9,13}\@{3,3,11,6,14,14,10}\@{2,2,14,6,11,17,9}%
   \@{19,6,8,21,7}\@{19,6,7,23,6}\@{20,6,5,25,5}\@{20,6,4,10,6,11,4}%
   \@{21,5,3,9,10,10,3}\@{21,6,1,8,14,8,3}\@{21,6,1,7,16,8,2}%
   \@{22,12,18,7,2}\@{22,11,20,7,1}\@{22,11,20,7,1}\@{23,9,22,6,1}%
   \@{23,9,22,7}\@{23,8,24,6}\@{23,8,24,6}\@{24,6,25,6}\@{24,6,25,6}%
   \@{24,6,25,6}\@{23,8,24,6}\@{23,8,24,6}\@{23,9,22,7}\@{23,9,22,6,1}%
   \@{22,11,20,7,1}\@{22,11,20,7,1}\@{22,12,18,7,2}\@{21,6,1,7,16,8,2}%
   \@{21,6,1,8,14,8,3}\@{21,5,3,9,10,10,3}\@{20,6,4,10,6,11,4}%
   \@{20,6,5,25,5}\@{19,6,7,23,6}\@{19,6,8,21,7}\@{2,2,14,6,11,17,9}%
   \@{3,3,11,6,14,14,10}\@{4,4,7,8,16,9,13}\@{5,17,39}\@{6,15,40}%
   \@{7,13,41}\@{8,11,42}\@{10,7,44}\@{61}}
\@namedef{@astrosym@13}{\@@{4}%
   \@{2,1,57,1}\@{3,2,53,2,1}\@{3,3,51,3,1}\@{4,3,49,3,2}\@{4,4,47,4,2}%
   \@{5,4,45,4,3}\@{5,5,43,5,3}\@{6,4,43,4,4}\@{6,5,41,5,4}\@{6,51,4}%
   \@{7,49,5}\@{7,49,5}\@{7,49,5}\@{7,49,5}\@{7,49,5}\@{8,6,35,6,6}%
   \@{8,6,35,6,6}\@{8,6,35,6,6}\@{8,6,35,6,6}\@{8,6,35,6,6}%
   \@{8,6,35,6,6}\@{8,6,35,6,6}\@{8,6,35,6,6}\@{8,6,35,6,6}%
   \@{8,6,35,6,6}\@{8,6,35,6,6}\@{7,49,5}\@{7,49,5}\@{7,49,5}%
   \@{7,49,5}\@{7,49,5}\@{6,51,4}\@{6,5,41,5,4}\@{6,4,43,4,4}%
   \@{5,5,43,5,3}\@{5,4,45,4,3}\@{4,4,47,4,2}\@{4,3,49,3,2}%
   \@{3,3,51,3,1}\@{3,2,53,2,1}\@{2,1,57,1}\@{61}}
\@namedef{@astrosym@14}{\@@{0}%
   \@{22,8,22}\@{18,14,20}\@{16,18,18}\@{15,20,5,1,11}\@{13,23,5,1,10}%
   \@{12,24,5,2,9}\@{11,14,4,8,5,2,8}\@{10,13,8,6,5,3,7}%
   \@{9,13,10,6,5,2,7}\@{8,14,10,6,5,3,6}\@{8,7,1,6,10,6,5,4,5}%
   \@{7,7,2,6,10,6,6,3,5}\@{6,7,3,6,10,6,6,4,4}\@{6,6,5,6,8,6,7,4,4}%
   \@{5,7,5,8,4,8,8,4,3}\@{5,6,7,18,9,4,3}\@{4,6,8,18,9,5,2}%
   \@{4,6,9,16,11,4,2}\@{4,5,11,14,12,4,2}\@{3,6,13,10,14,5,1}%
   \@{3,6,15,6,16,5,1}\@{3,5,38,5,1}\@{3,5,39,4,1}\@{2,6,39,5}%
   \@{2,5,40,5}\@{2,5,40,5}\@{2,5,40,5}\@{2,5,40,5}\@{2,5,40,5}%
   \@{2,5,40,5}\@{2,5,40,5}\@{2,5,40,5}\@{2,5,40,5}\@{2,5,40,5}%
   \@{2,5,40,5}\@{2,5,39,6}\@{3,4,39,5,1}\@{3,5,38,5,1}%
   \@{3,5,16,6,15,6,1}\@{3,5,14,10,13,6,1}\@{4,4,12,14,11,5,2}%
   \@{4,4,11,16,9,6,2}\@{4,5,9,18,8,6,2}\@{5,4,9,18,7,6,3}%
   \@{5,4,8,8,4,8,5,7,3}\@{6,4,7,6,8,6,5,6,4}\@{6,4,6,6,10,6,3,7,4}%
   \@{7,3,6,6,10,6,2,7,5}\@{7,4,5,6,10,6,1,7,6}\@{8,3,5,6,10,14,6}%
   \@{9,2,5,6,10,13,7}\@{9,3,5,6,8,13,8}\@{10,2,5,8,4,14,9}%
   \@{11,2,5,24,10}\@{12,1,5,23,11}\@{13,1,5,20,13}\@{20,18,14}%
   \@{22,14,16}\@{24,8,20}\@{52}}
\@namedef{@astrosym@15}{\@@{5}%
   \@{46,7,15}\@{44,10,14}\@{43,13,12}\@{42,15,11}\@{41,17,10}%
   \@{41,17,10}\@{40,7,5,7,9}\@{40,5,8,6,9}\@{13,10,17,4,10,6,8}%
   \@{11,16,13,4,10,6,8}\@{10,20,10,3,11,6,8}\@{8,24,8,3,11,6,8}%
   \@{7,28,5,3,11,6,8}\@{6,32,3,2,11,6,8}\@{5,9,8,22,9,6,9}%
   \@{4,8,14,19,7,7,9}\@{4,7,18,29,10}\@{3,7,21,27,10}\@{3,6,25,23,11}%
   \@{2,7,28,19,12}\@{2,6,32,14,14}\@{2,6,36,9,15}\@{1,6,61}\@{1,6,61}%
   \@{1,6,61}\@{1,6,61}\@{1,6,61}\@{1,6,61}\@{1,6,61}\@{1,6,61}\@{1,6,61}%
   \@{2,6,60}\@{2,6,60}\@{2,6,60}\@{3,6,59}\@{3,6,42,11,6}\@{3,7,34,20,4}%
   \@{4,7,27,27,3}\@{4,8,20,34,2}\@{5,9,11,41,2}\@{6,61,1}\@{7,45,9,6,1}%
   \@{8,37,18,4,1}\@{10,29,25,3,1}\@{11,22,31,3,1}\@{13,13,38,3,1}%
   \@{64,2,2}\@{63,3,2}\@{62,3,3}\@{60,3,5}\@{68}}
\@namedef{@astrosym@16}{\@@{5}%
   \@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{11,1,47}%
   \@{10,2,47}\@{9,2,48}\@{8,2,49}\@{8,1,50}\@{7,2,50}\@{6,2,51}\@{6,2,51}%
   \@{5,2,52}\@{5,2,52}\@{4,2,53}\@{4,2,53}\@{3,3,53}\@{3,3,53}\@{3,3,53}%
   \@{3,4,52}\@{3,6,50}\@{3,49,7}\@{3,49,7}\@{4,48,7}\@{5,47,7}%
   \@{6,46,7}\@{9,43,7}\@{10,2,47}\@{10,1,48}\@{9,2,48}\@{8,2,49}%
   \@{7,2,50}\@{7,1,51}\@{6,2,51}\@{5,2,52}\@{5,2,47,2,3}\@{4,2,47,2,4}%
   \@{4,2,45,3,5}\@{4,2,44,3,6}\@{3,3,43,4,6}\@{3,3,42,5,6}\@{3,4,40,6,6}%
   \@{3,6,38,5,7}\@{3,56}\@{3,56}\@{3,56}\@{4,55}\@{5,54}\@{8,51}%
   \@{11,2,33,6,7}\@{10,2,34,6,7}\@{9,2,35,6,7}\@{8,2,36,6,7}\@{7,2,37,6,7}%
   \@{6,2,38,6,7}\@{6,2,38,6,7}\@{5,2,39,6,7}\@{4,2,40,6,7}\@{4,2,40,6,7}%
   \@{3,2,41,6,7}\@{3,2,41,6,7}\@{3,2,41,6,7}\@{2,3,41,6,7}\@{2,3,40,6,8}%
   \@{2,4,38,7,8}\@{2,6,35,8,8}\@{2,48,9}\@{2,47,10}\@{2,46,11}\@{3,44,12}%
   \@{4,41,14}\@{7,37,15}}
\@namedef{@astrosym@17}{\@@{0}%
   \@{17,9,5,6,6}\@{19,7,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}%
   \@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}%
   \@{12,7,1,6,5,6,6}\@{10,16,5,6,6}\@{8,18,5,6,6}\@{7,19,5,6,6}%
   \@{6,20,5,6,6}\@{5,21,5,6,6}\@{4,9,5,8,5,6,6}\@{4,7,9,6,5,6,6}%
   \@{3,7,21,6,6}\@{3,6,22,6,6}\@{3,6,22,6,6}\@{2,6,23,6,6}\@{2,6,23,6,6}%
   \@{2,6,23,6,6}\@{2,6,23,6,6}\@{2,6,23,6,6}\@{3,6,22,6,6}\@{3,6,22,6,6}%
   \@{3,7,21,6,6}\@{4,7,9,6,5,6,6}\@{4,9,5,8,5,6,6}\@{5,21,5,6,6}%
   \@{6,20,5,6,6}\@{7,19,5,6,6}\@{8,18,5,6,6}\@{10,16,5,6,6}%
   \@{12,7,1,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}%
   \@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}%
   \@{19,7,5,6,6}\@{17,9,5,6,6}\@{43}}
\@namedef{@astrosym@18}{\@@{5}%
   \@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{11,1,47}%
   \@{10,2,47}\@{9,2,48}\@{8,2,49}\@{7,2,50}\@{7,2,50}\@{6,2,51}\@{5,3,51}%
   \@{5,2,52}\@{4,3,52}\@{4,3,52}\@{3,4,52}\@{3,4,52}\@{3,5,51}\@{3,5,51}%
   \@{3,6,50}\@{3,9,47}\@{3,49,7}\@{4,48,7}\@{5,47,7}\@{6,46,7}\@{8,44,7}%
   \@{10,42,7}\@{11,1,47}\@{10,1,48}\@{9,2,48}\@{8,2,49}\@{7,2,50}%
   \@{6,3,50}\@{6,2,51}\@{5,3,51}\@{5,2,52}\@{4,3,52}\@{4,3,52}%
   \@{3,4,52}\@{3,4,52}\@{3,5,51}\@{3,5,51}\@{3,6,50}\@{3,9,2,39,6}%
   \@{4,51,4}\@{4,52,3}\@{5,52,2}\@{6,52,1}\@{8,50,1}\@{10,5,38,6}%
   \@{55,4}\@{56,3}\@{56,3}\@{56,3}\@{50,1,4,4}\@{50,1,4,3,1}%
   \@{49,2,3,3,2}\@{48,3,2,3,3}\@{48,7,4}\@{47,7,5}\@{46,7,6}%
   \@{46,10,3}\@{45,11,3}\@{44,6,9}\@{43,3,13}}
\@namedef{@astrosym@19}{\@@{4}%
   \@{62,1,4}\@{48,2,10,4,3}\@{47,4,8,5,3}\@{45,6,6,8,2}\@{45,7,3,11,1}%
   \@{46,6,2,11,2}\@{46,18,3}\@{47,15,5}\@{47,13,7}\@{47,12,8}\@{45,12,10}%
   \@{44,12,11}\@{42,15,10}\@{41,16,10}\@{39,11,1,7,9}\@{37,12,3,7,8}%
   \@{36,11,5,7,8}\@{34,11,8,4,10}\@{32,12,9,3,11}\@{31,11,25}\@{29,11,27}%
   \@{17,1,9,12,28}\@{17,1,8,11,30}\@{16,2,6,11,32}\@{15,2,5,12,33}%
   \@{14,3,4,11,35}\@{14,3,2,11,37}\@{13,16,38}\@{12,15,40}\@{11,14,42}%
   \@{10,14,43}\@{9,13,45}\@{9,12,46}\@{8,13,46}\@{7,19,41}\@{6,20,41}%
   \@{5,14,48}\@{4,10,53}\@{3,7,57}\@{2,4,61}\@{1,2,64}\@{0,1,66}}
\@namedef{@astrosym@20}{\@@{0}%
   \@{27,1,21}\@{26,1,22}\@{25,2,22}\@{24,2,23}\@{24,1,24}\@{23,2,24}%
   \@{22,2,25}\@{2,6,14,2,25}\@{2,6,13,2,26}\@{2,6,12,3,26}\@{2,6,12,3,26}%
   \@{2,6,11,3,7,8,12}\@{2,6,11,3,5,13,9}\@{2,6,11,3,3,17,7}%
   \@{2,6,10,3,2,20,6}\@{2,6,10,3,1,22,5}\@{2,6,10,27,4}%
   \@{2,6,9,8,1,3,7,10,3}\@{2,6,9,6,1,2,13,7,3}\@{2,6,9,7,16,7,2}%
   \@{2,6,9,5,19,7,1}\@{2,6,8,4,21,7,1}\@{2,6,8,4,22,6,1}\@{2,6,7,5,22,7}%
   \@{2,6,6,6,23,6}\@{2,6,5,7,23,6}\@{2,6,5,2,1,4,23,6}\@{2,6,4,2,2,4,23,6}%
   \@{2,6,3,2,3,5,22,6}\@{2,6,2,3,3,5,21,7}\@{2,6,1,3,4,6,20,7}%
   \@{2,9,6,6,18,7,1}\@{2,8,7,7,16,8,1}\@{2,7,9,8,12,9,2}%
   \@{2,6,10,11,7,11,2}\@{2,6,11,27,3}\@{2,5,13,25,4}\@{2,4,15,23,5}%
   \@{2,3,18,19,7}\@{2,2,21,16,8}\@{2,1,25,10,11}\@{49}}
\@namedef{@astrosym@21}{\@@{0}%
   \@{45}\@{45}\@{11,1,18,1,14}\@{9,2,17,2,15}\@{7,2,17,2,17}\@{6,1,18,1,19}%
   \@{4,4,15,4,18}\@{2,8,11,8,16}\@{1,10,9,10,15}\@{3,10,9,10,13}%
   \@{5,9,10,9,12}\@{6,10,9,10,10}\@{8,10,9,10,8}\@{9,10,9,10,7}%
   \@{11,9,10,9,6}\@{13,5,14,5,8}\@{14,3,16,3,9}\@{13,2,17,2,11}%
   \@{12,1,18,1,13}\@{10,2,17,2,14}\@{8,2,17,2,16}\@{7,2,17,2,17}%
   \@{5,2,17,2,19}\@{4,4,15,4,18}\@{2,8,11,8,16}\@{2,10,9,10,14}%
   \@{3,10,9,10,13}\@{5,10,9,10,11}\@{7,10,9,10,9}\@{8,10,9,10,8}%
   \@{10,10,9,10,6}\@{12,8,11,8,6}\@{13,5,14,5,8}\@{15,1,18,1,10}%
   \@{13,2,17,2,11}\@{11,2,17,2,13}\@{10,1,18,1,15}\@{8,2,17,2,16}%
   \@{6,2,17,2,18}\@{5,2,17,2,19}\@{3,6,13,6,17}\@{1,9,10,9,16}%
   \@{2,10,9,10,14}\@{4,10,9,10,12}\@{5,10,9,10,11}\@{7,10,9,10,9}%
   \@{9,10,9,10,7}\@{10,10,9,10,6}\@{12,7,12,7,7}\@{14,3,16,3,9}%
   \@{14,2,17,2,10}\@{12,2,17,2,12}\@{11,1,18,1,14}\@{9,2,17,2,15}%
   \@{45}\@{45}\@{45}}
\@namedef{@astrosym@22}{\@@{4}%
   \@{2,2,55,2}\@{3,3,51,3,1}\@{4,4,47,4,2}\@{5,6,41,6,3}\@{6,8,35,8,4}%
   \@{7,11,27,11,5}\@{9,15,15,15,7}\@{10,43,8}\@{12,39,10}\@{14,35,12}%
   \@{16,31,14}\@{18,27,16}\@{21,21,19}\@{25,13,23}\@{28,6,27}\@{28,6,27}%
   \@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}%
   \@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{25,13,23}%
   \@{21,21,19}\@{18,27,16}\@{16,31,14}\@{14,35,12}\@{12,39,10}\@{10,43,8}%
   \@{9,15,15,15,7}\@{7,11,27,11,5}\@{6,8,35,8,4}\@{5,6,41,6,3}%
   \@{4,4,47,4,2}\@{3,3,51,3,1}\@{2,2,55,2}\@{60,1}}
\@namedef{@astrosym@23}{\@@{6}%
   \@{10,6,48}\@{10,6,48}\@{10,6,48}\@{10,6,48}\@{10,6,48}\@{10,6,40,5,3}%
   \@{10,6,38,9,1}\@{10,6,36,12}\@{10,6,35,12,1}\@{10,6,34,13,1}%
   \@{10,6,33,14,1}\@{10,6,32,9,3,2,2}\@{2,21,24,8,9}\@{2,21,24,7,10}%
   \@{2,21,23,7,11}\@{2,21,22,7,12}\@{2,21,21,8,12}\@{2,21,21,7,13}%
   \@{10,6,1,6,20,7,14}\@{10,6,1,6,19,7,15}\@{10,6,2,6,17,8,15}%
   \@{10,6,2,6,16,8,16}\@{10,6,2,6,15,8,17}\@{10,6,2,7,12,9,18}%
   \@{10,6,3,6,10,10,19}\@{10,6,3,7,6,12,20}\@{10,6,4,23,21}%
   \@{10,6,4,21,23}\@{10,6,5,19,24}\@{22,16,26}\@{23,13,28}%
   \@{25,8,31}\@{64}}
\@namedef{@astrosym@24}{\@@{0}%
   \@{18,2,41}\@{16,3,42}\@{14,4,43}\@{11,7,43}\@{8,15,38}\@{5,21,35}%
   \@{1,28,32}\@{2,29,30}\@{6,26,29}\@{9,25,27}\@{11,7,4,13,26}%
   \@{14,5,6,11,25}\@{16,3,9,9,24}\@{19,1,10,8,23}\@{31,8,22}\@{32,8,21}%
   \@{33,7,21}\@{34,7,20}\@{35,6,20}\@{35,7,19}\@{36,6,19}\@{36,7,18}%
   \@{37,6,18}\@{37,6,7,6,5}\@{38,6,6,6,5}\@{38,6,6,6,5}\@{17,3,18,6,6,6,5}%
   \@{15,4,20,6,5,6,5}\@{13,5,21,6,5,6,5}\@{10,8,21,6,5,6,5}\@{7,53,1}%
   \@{3,57,1}\@{1,59,1}\@{3,57,1}\@{7,53,1}\@{10,50,1}\@{13,5,21,6,5,6,5}%
   \@{15,4,20,6,5,6,5}\@{17,3,18,6,6,6,5}\@{38,6,6,6,5}\@{38,6,6,6,5}%
   \@{37,6,7,6,5}\@{37,6,18}\@{36,7,18}\@{36,6,19}\@{35,7,19}\@{35,6,20}%
   \@{34,7,20}\@{33,7,21}\@{32,8,21}\@{31,8,22}\@{19,1,10,8,23}%
   \@{16,3,9,9,24}\@{14,5,6,11,25}\@{11,7,4,13,26}\@{9,25,27}%
   \@{6,26,29}\@{2,29,30}\@{1,28,32}\@{5,21,35}\@{8,15,38}\@{11,7,43}%
   \@{14,4,43}\@{16,3,42}\@{18,2,41}\@{61}}
\@namedef{@astrosym@25}{\@@{0}%
   \@{18,2,41}\@{16,3,42}\@{13,5,43}\@{10,39,12}\@{6,43,12}\@{2,47,12}%
   \@{1,48,12}\@{5,44,12}\@{9,40,12}\@{12,6,25,6,12}\@{15,4,24,6,12}%
   \@{17,3,23,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,17,1}%
   \@{43,17,1}\@{43,17,1}\@{43,17,1}\@{43,17,1}\@{43,17,1}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{17,3,23,6,12}\@{15,4,24,6,12}%
   \@{12,6,25,6,12}\@{9,40,12}\@{5,44,12}\@{1,48,12}\@{2,47,12}%
   \@{6,43,12}\@{10,39,12}\@{13,5,43}\@{16,3,42}\@{18,2,41}\@{61}}
\@namedef{@astrosym@26}{\@@{0}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{10,7,2,6,4,6,14}\@{8,17,4,6,14}\@{6,19,4,6,14}\@{5,20,4,6,14}%
   \@{4,21,4,6,14}\@{3,22,4,6,14}\@{3,8,5,9,4,6,14}\@{3,6,9,7,4,6,14}%
   \@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}%
   \@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}%
   \@{2,6,11,6,4,6,14}\@{3,6,9,7,4,6,14}\@{3,8,5,9,4,6,14}%
   \@{4,21,4,6,14}\@{4,21,4,6,14}\@{5,20,4,6,14}\@{6,19,4,6,14}%
   \@{8,17,4,6,14}\@{10,7,2,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{49}}
\@namedef{@astrosym@27}{\@@{0}%
   \@{10,2,8,2,17}\@{8,3,7,3,18}\@{7,3,7,3,19}\@{6,4,6,4,19}\@{5,4,6,4,20}%
   \@{4,5,5,5,20}\@{3,5,5,5,21}\@{3,5,5,5,21}\@{2,6,4,6,21}\@{2,5,5,5,22}%
   \@{2,5,5,5,22}\@{1,6,4,6,22}\@{1,6,4,6,22}\@{1,6,4,6,22}\@{1,6,4,6,22}%
   \@{1,6,4,6,22}\@{1,6,4,6,22}\@{1,6,4,6,22}\@{2,6,4,6,21}\@{2,6,4,6,21}%
   \@{3,5,5,5,21}\@{3,6,4,6,20}\@{4,5,5,5,20}\@{4,5,5,5,20}\@{5,5,5,5,19}%
   \@{5,5,5,5,19}\@{6,4,6,4,19}\@{6,5,5,5,18}\@{7,4,6,4,18}\@{7,4,6,4,18}%
   \@{8,4,6,4,17}\@{8,4,6,4,17}\@{8,4,6,4,17}\@{8,4,6,4,17}\@{8,4,6,4,17}%
   \@{8,4,6,4,17}\@{8,4,6,4,17}\@{8,3,7,3,18}\@{7,4,6,4,18}\@{7,3,7,3,19}%
   \@{7,3,7,3,19}\@{6,3,7,3,20}\@{5,3,7,3,21}\@{5,3,7,3,21}\@{3,6,4,6,20}%
   \@{1,9,1,9,19}\@{1,9,1,9,19}\@{3,8,2,8,18}\@{4,7,3,7,18}\@{4,8,2,8,17}%
   \@{5,7,3,7,17}\@{5,7,3,7,17}\@{6,6,4,6,17}\@{6,6,4,6,17}\@{6,5,5,5,18}%
   \@{6,3,7,3,20}\@{39}}
\@namedef{@astrosym@28}{\@@{0}%
   \@{8,3,14,3,15}\@{6,4,13,4,16}\@{5,4,13,4,17}\@{4,5,12,5,17}%
   \@{4,4,13,4,18}\@{3,5,12,5,18}\@{3,5,12,5,18}\@{3,5,12,5,18}%
   \@{3,6,11,6,17}\@{3,10,7,10,13}\@{4,11,6,11,11}\@{4,12,5,12,10}%
   \@{5,12,5,12,9}\@{6,12,5,12,8}\@{8,10,7,10,8}\@{12,7,10,7,7}%
   \@{13,6,11,6,7}\@{13,6,11,6,7}\@{13,6,11,6,7}\@{13,6,11,6,7}%
   \@{9,9,8,9,8}\@{7,11,6,11,8}\@{5,13,4,13,8}\@{4,13,4,13,9}%
   \@{3,13,4,13,10}\@{3,11,6,11,12}\@{2,8,9,8,16}\@{2,6,11,6,18}%
   \@{2,6,11,6,18}\@{2,6,11,6,18}\@{2,6,11,6,18}\@{2,8,9,8,16}%
   \@{3,11,6,11,12}\@{3,13,4,13,10}\@{4,13,4,13,9}\@{5,13,4,13,8}%
   \@{7,11,6,11,8}\@{9,9,8,9,8}\@{13,6,11,6,7}\@{13,6,11,6,7}%
   \@{13,6,11,6,7}\@{13,6,11,6,7}\@{12,7,10,7,7}\@{8,10,7,10,8}%
   \@{6,12,5,12,8}\@{5,12,5,12,9}\@{4,12,5,12,10}\@{4,11,6,11,11}%
   \@{3,10,7,10,13}\@{3,6,11,6,17}\@{3,5,12,5,18}\@{3,5,12,5,18}%
   \@{3,5,12,5,18}\@{4,4,13,4,18}\@{4,5,12,5,17}\@{5,4,13,4,17}%
   \@{6,4,13,4,16}\@{8,3,14,3,15}}
\@namedef{@astrosym@100}{\@@{0}%
   \@{21,9,19}\@{18,15,16}\@{16,19,14}\@{14,23,12}\@{13,25,11}\@{11,29,9}%
   \@{10,12,7,12,8}\@{9,10,13,10,7}\@{8,9,17,9,6}\@{7,8,21,8,5}%
   \@{6,8,23,8,4}\@{6,7,25,7,4}\@{5,7,27,7,3}\@{5,6,29,6,3}\@{4,7,29,7,2}%
   \@{4,6,31,6,2}\@{3,7,31,7,1}\@{3,6,33,6,1}\@{3,6,33,6,1}\@{2,6,15,5,15,6}%
   \@{2,6,14,7,14,6}\@{2,6,13,9,13,6}\@{2,6,13,4,1,4,13,6}%
   \@{2,6,13,3,3,3,13,6}\@{2,6,13,4,1,4,13,6}\@{2,6,13,9,13,6}%
   \@{2,6,14,7,14,6}\@{2,6,15,5,15,6}\@{3,6,33,6,1}\@{3,6,33,6,1}%
   \@{3,7,31,7,1}\@{4,6,31,6,2}\@{4,7,29,7,2}\@{5,6,29,6,3}\@{5,7,27,7,3}%
   \@{6,7,25,7,4}\@{6,8,23,8,4}\@{7,8,21,8,5}\@{8,9,17,9,6}\@{9,10,13,10,7}%
   \@{10,12,7,12,8}\@{11,29,9}\@{13,25,11}\@{14,23,12}\@{16,19,14}\@{18,15,16}%
   \@{21,9,19}\@{49}}
\@namedef{@astrosym@101}{\@@{8}%
   \@{3,9,20,9,32}\@{2,12,16,13,30}\@{1,15,12,17,28}\@{1,17,8,21,26}%
   \@{1,18,6,23,25}\@{2,18,4,25,12,4,8}\@{10,11,2,10,7,10,10,6,7}%
   \@{13,8,1,9,11,9,9,6,7}\@{14,15,15,7,9,6,7}\@{15,13,17,7,8,6,7}%
   \@{16,11,19,6,8,6,7}\@{16,11,19,7,7,6,7}\@{17,9,21,6,7,6,7}%
   \@{17,9,21,7,6,6,7}\@{18,7,23,22,3}\@{18,7,23,24,1}\@{18,7,23,24,1}%
   \@{18,7,23,24,1}\@{18,7,23,24,1}\@{18,7,23,22,3}\@{17,9,21,7,6,6,7}%
   \@{17,9,21,6,7,6,7}\@{16,11,19,7,7,6,7}\@{16,11,19,6,8,6,7}%
   \@{15,13,17,7,8,6,7}\@{14,15,15,7,9,6,7}\@{13,8,1,9,11,9,9,6,7}%
   \@{10,11,2,10,7,10,10,6,7}\@{2,18,4,25,12,4,8}\@{1,18,6,23,25}%
   \@{1,17,8,21,26}\@{1,15,12,17,28}\@{2,12,16,13,30}\@{3,9,20,9,32}\@{73}}
\@namedef{@astrosym@102}{\@@{0}%
   \@{16,8,37}\@{13,14,34}\@{11,18,32}\@{10,20,31}\@{8,24,29}\@{7,26,28}%
   \@{6,11,6,11,14,2,11}\@{5,9,12,9,11,6,9}\@{4,8,16,8,10,6,9}%
   \@{4,7,18,7,10,6,9}\@{3,7,20,7,9,6,9}\@{3,6,22,6,9,6,9}%
   \@{2,7,22,7,8,6,9}\@{2,6,24,6,8,6,9}\@{2,6,24,6,8,6,9}\@{1,6,26,6,7,6,9}%
   \@{1,6,26,25,3}\@{1,6,26,27,1}\@{1,6,26,27,1}\@{1,6,26,27,1}%
   \@{1,6,26,27,1}\@{1,6,26,25,3}\@{1,6,26,6,7,6,9}\@{2,6,24,6,8,6,9}%
   \@{2,6,24,6,8,6,9}\@{2,7,22,7,8,6,9}\@{3,6,22,6,9,6,9}\@{3,7,20,7,9,6,9}%
   \@{4,7,18,7,10,6,9}\@{4,8,16,8,10,6,9}\@{5,9,12,9,11,6,9}%
   \@{6,11,6,11,14,2,11}\@{7,26,28}\@{8,24,29}\@{10,20,31}\@{11,18,32}%
   \@{13,14,34}\@{16,8,37}\@{61}}
\@namedef{@astrosym@103}{\@@{0}%
   \@{37,8,16}\@{34,14,13}\@{32,18,11}\@{31,20,10}\@{29,24,8}\@{28,26,7}%
   \@{27,11,6,11,6}\@{26,9,12,9,5}\@{10,2,13,8,16,8,4}\@{9,4,12,7,18,7,4}%
   \@{8,6,10,7,20,7,3}\@{8,6,10,6,22,6,3}\@{8,6,9,7,22,7,2}\@{8,6,9,6,24,6,2}%
   \@{8,6,9,6,24,6,2}\@{8,6,8,6,26,6,1}\@{3,25,26,6,1}\@{1,27,26,6,1}%
   \@{1,27,26,6,1}\@{1,27,26,6,1}\@{1,27,26,6,1}\@{3,25,26,6,1}%
   \@{8,6,8,6,26,6,1}\@{8,6,9,6,24,6,2}\@{8,6,9,6,24,6,2}\@{8,6,9,7,22,7,2}%
   \@{8,6,10,6,22,6,3}\@{8,6,10,7,20,7,3}\@{9,4,12,7,18,7,4}%
   \@{10,2,13,8,16,8,4}\@{26,9,12,9,5}\@{27,11,6,11,6}\@{28,26,7}\@{29,24,8}%
   \@{31,20,10}\@{32,18,11}\@{34,14,13}\@{37,8,16}\@{61}}
\@namedef{@astrosym@104}{\@@{0}%
   \@{43,8,16}\@{40,14,13}\@{38,18,11}\@{37,20,10}\@{35,24,8}\@{34,26,7}%
   \@{33,11,6,11,6}\@{32,9,12,9,5}\@{31,8,16,8,4}\@{31,7,18,7,4}%
   \@{30,7,20,7,3}\@{30,6,22,6,3}\@{29,7,22,7,2}\@{29,6,24,6,2}%
   \@{29,6,24,6,2}\@{28,6,26,6,1}\@{28,6,26,6,1}\@{28,6,26,6,1}%
   \@{28,6,26,6,1}\@{28,6,26,6,1}\@{13,3,12,6,26,6,1}\@{12,5,9,8,26,6,1}%
   \@{11,6,7,10,26,6,1}\@{11,6,4,14,24,6,2}\@{10,7,2,16,24,6,2}%
   \@{9,7,1,19,22,7,2}\@{8,21,1,6,22,6,3}\@{8,19,3,7,20,7,3}%
   \@{7,18,6,7,18,7,4}\@{6,16,9,8,16,8,4}\@{5,15,12,9,12,9,5}%
   \@{4,16,13,11,6,11,6}\@{3,19,12,26,7}\@{2,21,12,24,8}\@{1,22,14,20,10}%
   \@{1,22,15,18,11}\@{1,21,18,14,13}\@{3,4,36,8,16}\@{67}}
\@namedef{@astrosym@105}{\@@{0}%
   \@{3,3,33,3,12}\@{1,7,30,6,10}\@{1,10,25,8,10}\@{1,13,19,11,10}%
   \@{1,17,11,15,10}\@{3,41,10}\@{5,39,10}\@{7,37,10}\@{10,27,1,6,10}%
   \@{13,21,4,6,10}\@{17,13,8,6,10}\@{38,6,10}\@{38,6,10}\@{38,6,10}%
   \@{38,6,10}\@{38,6,10}\@{38,6,10}\@{38,6,10}\@{38,6,10}\@{38,6,10}%
   \@{12,39,3}\@{11,42,1}\@{10,43,1}\@{10,43,1}\@{11,42,1}\@{12,39,3}%
   \@{38,6,10}\@{38,6,10}\@{38,6,10}\@{38,6,10}\@{38,6,10}\@{40,2,12}\@{54}}
\@namedef{@astrosym@106}{\@@{6}%
   \@{11,2,51}\@{9,6,49}\@{9,6,49}\@{9,6,49}\@{4,49,11}\@{2,53,9}\@{2,53,9}%
   \@{2,53,9}\@{2,53,9}\@{4,49,11}\@{9,6,7,6,36}\@{9,6,7,6,36}\@{9,6,6,6,37}%
   \@{10,4,7,6,37}\@{11,2,8,6,37}\@{21,6,37}\@{20,6,38}\@{20,6,25,5,8}%
   \@{20,6,23,9,6}\@{20,6,21,13,4}\@{20,6,19,17,2}\@{20,6,17,20,1}%
   \@{20,6,15,23}\@{20,6,12,14,3,9}\@{20,6,10,14,7,7}\@{21,6,6,15,11,4,1}%
   \@{21,25,18}\@{21,23,20}\@{22,20,22}\@{23,16,25}\@{24,13,27}%
   \@{26,8,30}\@{64}}
\@namedef{@astrosym@107}{\@@{5}%
   \@{40,8,16}\@{37,14,13}\@{35,18,11}\@{34,20,10}\@{32,24,8}\@{31,26,7}%
   \@{30,11,6,11,6}\@{19,2,8,9,12,9,5}\@{18,4,6,8,16,8,4}\@{16,7,5,7,18,7,4}%
   \@{15,8,4,7,20,7,3}\@{13,9,5,6,22,6,3}\@{12,10,4,7,22,7,2}%
   \@{10,10,6,6,24,6,2}\@{8,11,7,6,24,6,2}\@{5,12,8,6,26,6,1}%
   \@{3,28,11,4,11,6,1}\@{1,30,10,6,10,6,1}\@{1,30,10,6,10,6,1}%
   \@{1,30,10,6,10,6,1}\@{1,30,10,6,10,6,1}\@{3,28,11,4,11,6,1}%
   \@{5,12,8,6,26,6,1}\@{8,11,7,6,24,6,2}\@{10,10,6,6,24,6,2}%
   \@{12,10,4,7,22,7,2}\@{13,9,5,6,22,6,3}\@{15,8,4,7,20,7,3}%
   \@{16,7,5,7,18,7,4}\@{18,4,6,8,16,8,4}\@{19,2,8,9,12,9,5}%
   \@{30,11,6,11,6}\@{31,26,7}\@{32,24,8}\@{34,20,10}\@{35,18,11}%
   \@{37,14,13}\@{40,8,16}\@{64}}
\@namedef{@astrosym@108}{\@@{0}%
   \@{20,3,38}\@{17,7,37}\@{15,9,37}\@{12,12,37}\@{9,15,37}\@{6,17,38}%
   \@{3,45,13}\@{1,48,12}\@{1,48,12}\@{1,48,12}\@{1,48,12}\@{3,46,12}%
   \@{6,17,20,6,12}\@{9,15,19,6,12}\@{12,12,19,6,12}\@{15,9,19,6,12}%
   \@{17,7,19,6,12}\@{20,3,20,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{21,1,21,6,12}\@{19,5,19,6,12}\@{16,8,19,6,12}%
   \@{14,10,19,6,12}\@{11,13,19,6,12}\@{7,16,20,6,12}\@{3,19,21,6,12}%
   \@{2,56,3}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{3,55,3}%
   \@{8,15,20,6,12}\@{11,13,19,6,12}\@{14,10,19,6,12}\@{16,8,19,6,12}%
   \@{19,5,19,6,12}\@{21,1,21,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,6,12}\@{43,6,12}\@{20,3,20,6,12}\@{17,7,19,6,12}\@{15,9,19,6,12}%
   \@{12,12,19,6,12}\@{9,15,19,6,12}\@{6,17,20,6,12}\@{3,46,12}\@{1,48,12}%
   \@{1,48,12}\@{1,48,12}\@{1,48,12}\@{3,45,13}\@{6,17,38}\@{9,15,37}%
   \@{12,12,37}\@{15,9,37}\@{17,7,37}\@{20,3,38}\@{61}}
\@namedef{@astrosym@109}{\@@{0}%
   \@{3,55,3}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,59,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}\@{1,6,26,6,15,6,1}%
   \@{2,6,24,6,16,6,1}\@{2,6,24,6,16,6,1}\@{2,7,22,7,17,4,2}%
   \@{3,6,22,6,24}\@{3,7,20,7,24}\@{4,7,18,7,25}\@{4,9,14,9,25}%
   \@{5,11,8,11,26}\@{6,28,27}\@{7,26,28}\@{8,24,29}\@{10,20,31}%
   \@{12,16,33}\@{15,10,36}\@{61}}
\@namedef{@astrosym@110}{\@@{0}%
   \@{21,9,19}\@{18,15,16}\@{16,19,14}\@{14,23,12}\@{13,25,11}\@{11,29,9}%
   \@{10,12,7,12,8}\@{9,10,13,10,7}\@{8,9,17,9,6}\@{7,8,21,8,5}\@{6,8,23,8,4}%
   \@{6,7,25,7,4}\@{5,7,27,7,3}\@{5,6,10,9,10,6,3}\@{4,7,7,15,7,7,2}%
   \@{4,6,7,17,7,6,2}\@{3,7,5,21,5,7,1}\@{3,6,5,23,5,6,1}\@{3,6,4,25,4,6,1}%
   \@{2,6,4,10,7,10,4,6}\@{2,6,3,8,13,8,3,6}\@{2,6,3,7,15,7,3,6}%
   \@{2,6,2,7,17,7,2,6}\@{2,6,2,6,19,6,2,6}\@{2,6,1,7,19,7,1,6}%
   \@{2,6,1,6,21,6,1,6}\@{2,6,1,6,21,6,1,6}\@{2,12,23,12}\@{3,11,23,11,1}%
   \@{3,11,23,11,1}\@{3,11,23,11,1}\@{4,10,23,10,2}\@{4,10,23,10,2}%
   \@{4,10,23,10,2}\@{5,9,23,9,3}\@{5,9,23,9,3}\@{6,9,21,9,4}\@{7,8,21,8,5}%
   \@{7,9,19,9,5}\@{8,8,19,8,6}\@{9,7,19,7,7}\@{11,5,19,5,9}\@{12,3,21,3,10}%
   \@{49}}
\@namedef{@astrosym@111}{\@@{0}%
   \@{9,1,45}\@{7,4,44}\@{5,7,43}\@{4,8,43}\@{3,9,43}\@{3,8,44}\@{3,7,45}%
   \@{2,6,47}\@{2,6,47}\@{2,6,47}\@{2,6,47}\@{2,6,47}\@{3,6,46}\@{3,7,3,4,38}%
   \@{4,18,33}\@{4,23,28}\@{5,27,23}\@{6,31,18}\@{7,35,13}\@{9,5,2,31,8}%
   \@{21,32,2}\@{26,28,1}\@{31,24}\@{36,19}\@{31,24}\@{26,28,1}\@{21,32,2}%
   \@{9,5,2,31,8}\@{7,35,13}\@{6,31,18}\@{5,27,23}\@{4,23,28}\@{4,18,33}%
   \@{3,7,3,4,38}\@{3,6,46}\@{2,6,47}\@{2,6,47}\@{2,6,47}\@{2,6,47}%
   \@{2,6,47}\@{3,7,45}\@{3,8,44}\@{3,9,43}\@{4,8,43}\@{5,7,43}\@{7,4,44}%
   \@{9,1,45}\@{55}}
\@namedef{@astrosym@112}{\@@{4}%
   \@{12,7,42}\@{10,11,40}\@{8,15,38}\@{7,17,37}\@{5,20,36}\@{4,22,14,8,13}%
   \@{3,10,5,8,11,13,11}\@{2,9,9,7,9,16,9}\@{2,7,12,6,7,20,7}%
   \@{2,6,13,7,5,22,6}\@{4,2,16,6,4,24,5}\@{22,6,3,10,6,10,4}%
   \@{23,6,1,8,12,8,3}\@{23,6,1,7,14,7,3}\@{23,13,16,7,2}\@{24,11,18,6,2}%
   \@{24,11,18,7,1}\@{24,10,20,6,1}\@{24,9,21,6,1}\@{25,8,22,6}\@{25,7,23,6}%
   \@{25,7,23,6}\@{25,7,23,6}\@{26,6,23,6}\@{25,7,23,6}\@{25,7,23,6}%
   \@{25,7,23,6}\@{25,8,22,6}\@{24,9,21,6,1}\@{24,10,20,6,1}\@{24,11,18,7,1}%
   \@{24,11,18,6,2}\@{23,13,16,7,2}\@{23,6,1,7,14,7,3}\@{23,6,1,8,12,8,3}%
   \@{22,6,3,10,6,10,4}\@{4,2,16,6,4,24,5}\@{2,6,13,7,5,22,6}%
   \@{2,6,13,6,7,20,7}\@{2,8,10,7,9,16,9}\@{3,9,6,8,11,14,10}\@{3,23,14,8,13}%
   \@{4,21,36}\@{6,18,37}\@{7,16,38}\@{9,12,40}\@{11,8,42}\@{61}}
\@namedef{@astrosym@113}{\@@{4}%
   \@{4,2,51,2,2}\@{2,6,47,6}\@{2,7,45,7}\@{2,8,43,8}\@{2,8,43,8}%
   \@{4,7,41,7,2}\@{5,7,39,7,3}\@{5,7,39,7,3}\@{6,7,37,7,4}\@{7,6,37,6,5}%
   \@{7,49,5}\@{8,47,6}\@{8,47,6}\@{9,45,7}\@{9,45,7}\@{9,45,7}%
   \@{10,6,31,6,8}\@{10,6,31,6,8}\@{10,6,31,6,8}\@{10,6,31,6,8}%
   \@{10,6,31,6,8}\@{10,6,31,6,8}\@{10,6,31,6,8}\@{10,6,31,6,8}%
   \@{10,6,31,6,8}\@{9,45,7}\@{9,45,7}\@{9,45,7}\@{8,47,6}\@{8,47,6}%
   \@{7,49,5}\@{7,6,37,6,5}\@{6,7,37,7,4}\@{5,7,39,7,3}\@{5,7,39,7,3}%
   \@{4,7,41,7,2}\@{3,7,43,7,1}\@{2,8,43,8}\@{2,7,45,7}\@{2,6,47,6}%
   \@{4,2,51,2,2}\@{61}}
\@namedef{@astrosym@114}{\@@{0}%
   \@{22,9,21}\@{19,13,20}\@{17,17,18}\@{15,20,17}\@{13,23,4,3,9}%
   \@{12,24,3,5,8}\@{11,13,6,7,2,6,7}\@{10,13,8,6,2,6,7}\@{9,13,10,6,1,7,6}%
   \@{8,14,10,6,2,6,6}\@{8,7,1,6,10,6,2,7,5}\@{7,7,2,6,10,6,3,6,5}%
   \@{6,7,3,6,10,6,3,7,4}\@{6,7,3,6,10,6,4,6,4}\@{5,7,5,6,8,6,5,7,3}%
   \@{5,6,6,7,6,7,6,6,3}\@{4,7,7,18,7,6,3}\@{4,6,8,18,8,6,2}%
   \@{4,6,9,16,9,6,2}\@{3,6,11,14,10,6,2}\@{3,6,13,10,12,6,2}%
   \@{3,6,14,8,14,6,1}\@{3,6,36,6,1}\@{2,6,37,6,1}\@{2,6,37,6,1}%
   \@{2,6,37,6,1}\@{2,6,38,6}\@{2,6,38,6}\@{2,6,38,6}\@{2,6,38,6}%
   \@{2,6,38,6}\@{2,6,38,6}\@{2,6,38,6}\@{2,6,38,6}\@{2,6,38,6}\@{2,6,38,6}%
   \@{3,6,37,6}\@{3,6,37,6}\@{3,6,37,6}\@{3,6,36,6,1}\@{3,6,14,8,14,6,1}%
   \@{4,6,12,10,13,6,1}\@{4,6,10,14,11,6,1}\@{4,6,9,16,9,6,2}%
   \@{4,6,8,18,8,6,2}\@{5,6,7,18,7,7,2}\@{5,6,6,7,6,7,6,6,3}%
   \@{5,7,5,6,8,6,5,7,3}\@{6,6,4,6,10,6,3,7,4}\@{6,7,3,6,10,6,3,7,4}%
   \@{7,6,3,6,10,6,2,7,5}\@{7,7,2,6,10,6,1,7,6}\@{8,6,2,6,10,14,6}%
   \@{8,7,1,6,10,13,7}\@{9,6,2,6,8,13,8}\@{9,6,2,7,6,13,9}\@{10,5,3,24,10}%
   \@{11,3,4,23,11}\@{19,20,13}\@{20,17,15}\@{22,13,17}\@{23,9,20}\@{52}}
\@namedef{@astrosym@115}{\@@{5}%
   \@{46,7,15}\@{45,9,14}\@{43,13,12}\@{42,15,11}\@{41,17,10}\@{41,17,10}%
   \@{40,7,5,7,9}\@{14,9,17,6,7,6,9}\@{11,16,12,6,9,6,8}\@{10,20,9,6,9,6,8}%
   \@{8,25,6,6,9,6,8}\@{7,28,4,6,9,6,8}\@{6,32,1,6,9,6,8}\@{5,10,7,24,7,6,9}%
   \@{4,8,14,21,5,7,9}\@{4,7,18,29,10}\@{3,7,22,26,10}\@{3,6,25,23,11}%
   \@{2,7,28,19,12}\@{2,6,32,14,14}\@{2,6,36,9,15}\@{1,6,61}\@{1,6,61}%
   \@{1,6,61}\@{1,6,61}\@{1,6,61}\@{1,6,61}\@{1,6,61}\@{1,6,61}\@{2,6,60}%
   \@{2,6,42,11,7}\@{2,7,36,18,5}\@{3,6,32,23,4}\@{3,7,27,28,3}\@{4,7,22,33,2}%
   \@{4,8,17,37,2}\@{5,9,9,28,9,6,2}\@{6,40,15,6,1}\@{7,35,19,6,1}%
   \@{8,30,23,6,1}\@{10,24,27,6,1}\@{11,19,31,6,1}\@{13,11,37,6,1}%
   \@{60,6,2}\@{56,10,2}\@{55,11,2}\@{54,11,3}\@{54,10,4}\@{55,8,5}%
   \@{56,5,7}\@{68}}
\@namedef{@astrosym@116}{\@@{5}%
   \@{4,46,9}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{4,46,9}\@{10,7,42}%
   \@{9,7,43}\@{9,7,43}\@{8,7,44}\@{8,6,45}\@{7,7,45}\@{7,6,46}\@{7,6,46}%
   \@{6,6,47}\@{6,6,47}\@{6,6,47}\@{6,6,47}\@{5,6,48}\@{5,6,48}\@{5,6,48}%
   \@{5,6,48}\@{5,6,48}\@{5,45,9}\@{6,46,7}\@{6,46,7}\@{7,45,7}\@{8,44,7}%
   \@{10,40,9}\@{10,7,42}\@{9,7,43}\@{9,6,44}\@{8,7,44}\@{8,6,45}%
   \@{7,7,37,3,5}\@{7,6,37,5,4}\@{6,7,36,6,4}\@{6,6,36,7,4}\@{6,6,35,8,4}%
   \@{6,6,34,8,5}\@{5,6,35,7,6}\@{5,6,34,7,7}\@{5,6,34,6,8}\@{5,6,33,7,8}%
   \@{5,6,33,6,9}\@{5,52,2}\@{6,53}\@{6,53}\@{7,52}\@{8,51}\@{10,47,2}%
   \@{9,8,27,6,9}\@{9,7,28,6,9}\@{8,7,29,6,9}\@{7,7,30,6,9}\@{6,8,30,6,9}%
   \@{6,7,31,6,9}\@{5,7,32,6,9}\@{5,6,33,6,9}\@{4,7,34,6,8}\@{4,6,35,6,8}%
   \@{3,7,35,6,8}\@{3,6,36,6,8}\@{3,6,36,6,8}\@{2,6,37,6,8}\@{2,6,36,6,9}%
   \@{2,6,35,7,9}\@{2,6,33,8,10}\@{2,47,10}\@{2,46,11}\@{3,44,12}\@{3,43,13}%
   \@{4,40,15}\@{6,36,17}}
\@namedef{@astrosym@117}{\@@{0}%
   \@{16,8,9,2,8}\@{15,10,6,6,6}\@{15,11,5,6,6}\@{15,11,5,6,6}\@{15,11,5,6,6}%
   \@{16,10,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}%
   \@{12,6,2,6,5,6,6}\@{10,16,5,6,6}\@{8,18,5,6,6}\@{7,19,5,6,6}%
   \@{6,20,5,6,6}\@{5,21,5,6,6}\@{4,9,4,9,5,6,6}\@{4,7,8,5,7,6,6}%
   \@{3,7,21,6,6}\@{3,6,22,6,6}\@{3,6,22,6,6}\@{2,6,23,6,6}\@{2,6,23,6,6}%
   \@{2,6,23,6,6}\@{2,6,23,6,6}\@{2,6,23,6,6}\@{3,6,22,6,6}\@{3,6,22,6,6}%
   \@{3,7,21,6,6}\@{4,7,8,5,7,6,6}\@{4,9,4,8,6,6,6}\@{5,21,5,6,6}%
   \@{6,20,5,6,6}\@{7,19,5,6,6}\@{8,18,5,6,6}\@{10,16,5,6,6}%
   \@{12,6,2,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}\@{20,6,5,6,6}%
   \@{20,6,5,6,6}\@{16,10,5,6,6}\@{15,11,5,6,6}\@{15,11,5,6,6}%
   \@{15,11,5,6,6}\@{15,11,5,6,6}\@{16,8,9,2,8}\@{43}}
\@namedef{@astrosym@118}{\@@{5}%
   \@{4,46,9}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{2,50,7}\@{4,46,9}\@{10,7,42}%
   \@{9,7,43}\@{8,7,44}\@{8,7,44}\@{7,7,45}\@{7,6,46}\@{7,6,46}\@{6,6,47}%
   \@{6,6,47}\@{6,6,47}\@{5,6,48}\@{5,6,48}\@{5,6,48}\@{5,6,48}\@{5,6,48}%
   \@{5,7,47}\@{5,45,9}\@{6,46,7}\@{6,46,7}\@{7,45,7}\@{9,43,7}\@{11,39,9}%
   \@{10,7,42}\@{9,8,42}\@{9,7,43}\@{8,7,44}\@{8,6,45}\@{7,7,45}\@{7,6,46}%
   \@{7,6,46}\@{6,6,47}\@{6,6,47}\@{6,6,47}\@{5,6,48}\@{5,6,48}\@{5,6,48}%
   \@{5,6,48}\@{5,6,48}\@{5,8,46}\@{6,48,5}\@{6,50,3}\@{7,50,2}\@{8,50,1}%
   \@{10,48,1}\@{12,47}\@{53,6}\@{46,3,4,6}\@{45,5,3,6}\@{45,6,1,6,1}%
   \@{44,14,1}\@{44,14,1}\@{43,14,2}\@{43,13,3}\@{42,13,4}\@{42,14,3}%
   \@{41,16,2}\@{41,16,2}\@{40,16,3}\@{39,16,4}\@{39,14,6}\@{39,10,10}%
   \@{39,7,13}\@{40,3,16}\@{59}}
\@namedef{@astrosym@119}{\@@{4}%
   \@{62,2,3}\@{47,2,11,6,1}\@{45,5,8,8,1}\@{45,6,6,9,1}\@{45,6,4,11,1}%
   \@{45,7,1,11,3}\@{46,17,4}\@{46,15,6}\@{47,12,8}\@{46,12,9}\@{45,11,11}%
   \@{43,13,11}\@{41,15,11}\@{40,17,10}\@{38,11,2,6,10}\@{36,11,4,7,9}%
   \@{35,11,6,6,9}\@{33,11,8,5,10}\@{31,11,12,2,11}\@{30,11,26}\@{28,11,28}%
   \@{15,3,8,11,30}\@{14,5,6,11,31}\@{13,6,4,11,33}\@{12,7,2,11,35}%
   \@{12,7,1,11,36}\@{11,18,38}\@{10,17,40}\@{9,17,41}\@{8,16,43}%
   \@{7,15,45}\@{6,18,43}\@{6,19,42}\@{5,20,42}\@{4,21,42}\@{3,22,42}%
   \@{2,21,44}\@{1,18,48}\@{1,13,53}\@{1,9,57}\@{3,3,61}\@{67}}
\@namedef{@astrosym@120}{\@@{0}%
   \@{26,3,20}\@{25,5,19}\@{24,6,19}\@{23,7,19}\@{23,7,19}\@{22,7,20}%
   \@{21,7,21}\@{21,7,21}\@{20,7,22}\@{3,4,13,6,23}\@{2,6,11,7,23}%
   \@{2,6,11,6,24}\@{2,6,11,6,3,9,12}\@{2,6,10,6,1,14,10}\@{2,6,10,23,8}%
   \@{2,6,10,25,6}\@{2,6,9,27,5}\@{2,6,9,28,4}\@{2,6,9,12,7,10,3}%
   \@{2,6,9,9,12,9,2}\@{2,6,8,8,16,7,2}\@{2,6,7,8,18,7,1}\@{2,6,6,8,20,6,1}%
   \@{2,6,5,9,20,6,1}\@{2,6,5,9,21,6}\@{2,6,4,10,21,6}\@{2,6,3,11,21,6}%
   \@{2,6,2,12,21,6}\@{2,6,1,13,21,6}\@{2,6,1,7,1,6,19,6,1}%
   \@{2,13,2,6,19,6,1}\@{2,12,3,7,17,7,1}\@{2,12,4,7,15,7,2}%
   \@{2,11,5,9,11,9,2}\@{2,10,7,10,7,10,3}\@{2,9,9,25,4}\@{2,8,11,23,5}%
   \@{2,7,13,21,6}\@{2,7,15,17,8}\@{2,6,18,13,10}\@{4,2,22,9,12}\@{49}}
\@namedef{@astrosym@121}{\@@{0}%
   \@{9,3,16,3,14}\@{8,5,14,5,13}\@{6,8,11,8,12}\@{4,10,9,10,12}%
   \@{3,10,9,10,13}\@{2,10,9,10,14}\@{1,9,10,9,16}\@{1,9,10,9,16}%
   \@{1,11,8,11,14}\@{3,10,9,10,13}\@{4,11,8,11,11}\@{6,10,9,10,10}%
   \@{7,11,8,11,8}\@{9,11,8,11,6}\@{11,9,10,9,6}\@{12,9,10,9,5}%
   \@{10,10,9,10,6}\@{9,11,8,11,6}\@{7,11,8,11,8}\@{6,10,9,10,10}%
   \@{4,11,8,11,11}\@{2,11,8,11,13}\@{1,10,9,10,15}\@{1,9,10,9,16}%
   \@{1,9,10,9,16}\@{2,10,9,10,14}\@{3,11,8,11,12}\@{5,10,9,10,11}%
   \@{6,11,8,11,9}\@{8,11,8,11,7}\@{9,11,8,11,6}\@{11,9,10,9,6}%
   \@{12,8,11,8,6}\@{10,10,9,10,6}\@{8,11,8,11,7}\@{7,11,8,11,8}%
   \@{5,11,8,11,10}\@{3,11,8,11,12}\@{2,11,8,11,13}\@{1,10,9,10,15}%
   \@{1,8,11,8,17}\@{1,10,9,10,15}\@{2,11,8,11,13}\@{3,11,8,11,12}%
   \@{5,11,8,11,10}\@{7,10,9,10,9}\@{8,11,8,11,7}\@{10,10,9,10,6}%
   \@{12,8,11,8,6}\@{11,9,10,9,6}\@{10,10,9,10,6}\@{8,11,8,11,7}%
   \@{8,9,10,9,9}\@{8,7,12,7,11}\@{8,6,13,6,12}\@{9,3,16,3,14}\@{45}}
\@namedef{@astrosym@122}{\@@{4}%
   \@{4,2,51,2,2}\@{2,6,47,6}\@{2,9,41,9}\@{2,11,37,11}\@{2,14,31,14}%
   \@{4,15,25,15,2}\@{5,20,13,20,3}\@{7,49,5}\@{10,43,8}\@{12,39,10}%
   \@{15,33,13}\@{18,27,16}\@{24,15,22}\@{28,6,27}\@{28,6,27}\@{28,6,27}%
   \@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}%
   \@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}\@{28,6,27}%
   \@{24,15,22}\@{18,27,16}\@{15,33,13}\@{12,39,10}\@{10,43,8}\@{7,49,5}%
   \@{5,20,13,20,3}\@{4,15,25,15,2}\@{3,13,31,13,1}\@{2,11,37,11}%
   \@{2,9,41,9}\@{2,6,47,6}\@{4,2,51,2,2}\@{61}}
\@namedef{@astrosym@123}{\@@{6}%
   \@{12,2,50}\@{10,6,48}\@{10,6,48}\@{10,6,48}\@{10,6,48}\@{10,6,40,5,3}%
   \@{10,6,38,9,1}\@{10,6,36,12}\@{10,6,35,13}\@{10,6,34,14}\@{10,6,33,14,1}%
   \@{10,6,32,9,3,2,2}\@{4,18,25,8,9}\@{2,21,24,7,10}\@{2,21,23,7,11}%
   \@{2,21,22,7,12}\@{2,21,21,8,12}\@{4,19,21,7,13}\@{10,6,1,6,20,7,14}%
   \@{10,6,1,6,19,7,15}\@{10,6,2,6,17,8,15}\@{10,6,2,6,16,8,16}%
   \@{10,6,2,6,15,8,17}\@{10,6,2,7,12,9,18}\@{10,6,3,6,10,10,19}%
   \@{10,6,3,7,6,12,20}\@{10,6,4,23,21}\@{10,6,4,21,23}\@{12,2,7,19,24}%
   \@{22,16,26}\@{23,13,28}\@{25,8,31}\@{64}}
\@namedef{@astrosym@124}{\@@{0}%
   \@{20,3,38}\@{17,7,37}\@{15,9,37}\@{12,12,37}\@{9,15,37}\@{6,17,38}%
   \@{3,21,37}\@{1,27,33}\@{1,29,31}\@{1,31,29}\@{1,32,28}\@{3,32,26}%
   \@{6,30,25}\@{9,15,3,10,24}\@{12,12,5,9,23}\@{15,9,7,8,22}\@{17,7,8,8,21}%
   \@{20,3,10,7,21}\@{34,7,20}\@{35,7,19}\@{35,7,19}\@{36,7,18}\@{37,6,18}%
   \@{21,1,15,6,8,4,6}\@{19,5,14,6,6,6,5}\@{16,8,14,6,6,6,5}%
   \@{14,10,14,6,6,6,5}\@{11,13,14,6,6,6,5}\@{7,16,16,6,5,6,5}%
   \@{3,19,17,6,5,6,5}\@{2,56,3}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,59,1}%
   \@{3,55,3}\@{8,15,16,6,5,6,5}\@{11,13,14,6,6,6,5}\@{14,10,14,6,6,6,5}%
   \@{16,8,14,6,6,6,5}\@{19,5,14,6,6,6,5}\@{21,1,15,6,8,4,6}\@{37,6,18}%
   \@{36,7,18}\@{35,7,19}\@{35,7,19}\@{34,7,20}\@{20,3,10,7,21}%
   \@{17,7,8,8,21}\@{15,9,7,8,22}\@{12,12,5,9,23}\@{9,15,3,10,24}%
   \@{6,30,25}\@{3,32,26}\@{1,32,28}\@{1,31,29}\@{1,29,31}\@{1,27,33}%
   \@{3,21,37}\@{6,17,38}\@{9,15,37}\@{12,12,37}\@{15,9,37}\@{17,7,37}%
   \@{20,3,38}\@{61}}
\@namedef{@astrosym@125}{\@@{0}%
   \@{20,3,38}\@{17,7,37}\@{14,10,37}\@{10,14,37}\@{7,17,37}\@{3,45,13}%
   \@{1,48,12}\@{1,48,12}\@{1,48,12}\@{1,48,12}\@{2,47,12}\@{5,19,19,6,12}%
   \@{9,15,19,6,12}\@{13,11,19,6,12}\@{16,8,19,6,12}\@{19,4,20,6,12}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{43,15,3}\@{43,17,1}\@{43,17,1}\@{43,17,1}\@{43,17,1}\@{43,15,3}%
   \@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}\@{43,6,12}%
   \@{19,4,20,6,12}\@{16,8,19,6,12}\@{13,11,19,6,12}\@{9,15,19,6,12}%
   \@{5,19,19,6,12}\@{2,47,12}\@{1,48,12}\@{1,48,12}\@{1,48,12}\@{1,48,12}%
   \@{3,45,13}\@{7,17,37}\@{10,14,37}\@{14,10,37}\@{17,7,37}\@{20,3,38}\@{61}}
\@namedef{@astrosym@126}{\@@{0}%
   \@{21,2,8,2,16}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{10,7,2,6,4,6,14}\@{8,17,4,6,14}\@{6,19,4,6,14}\@{5,20,4,6,14}%
   \@{4,21,4,6,14}\@{3,22,4,6,14}\@{3,8,5,9,4,6,14}\@{3,6,9,7,4,6,14}%
   \@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}%
   \@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}\@{2,6,11,6,4,6,14}%
   \@{2,6,11,6,4,6,14}\@{3,6,9,7,4,6,14}\@{3,8,5,9,4,6,14}\@{4,21,4,6,14}%
   \@{4,21,4,6,14}\@{5,20,4,6,14}\@{6,19,4,6,14}\@{8,17,4,6,14}%
   \@{10,7,2,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}\@{19,6,4,6,14}%
   \@{21,2,8,2,16}\@{49}}
\@namedef{@astrosym@127}{\@@{0}%
   \@{7,3,7,3,19}\@{6,5,5,5,18}\@{5,6,4,6,18}\@{5,6,4,6,18}\@{4,7,3,7,18}%
   \@{4,6,4,6,19}\@{3,7,3,7,19}\@{3,6,4,6,20}\@{2,6,4,6,21}\@{2,6,4,6,21}%
   \@{2,6,4,6,21}\@{1,6,4,6,22}\@{1,6,4,6,22}\@{1,6,4,6,22}\@{1,6,4,6,22}%
   \@{1,6,4,6,22}\@{1,6,4,6,22}\@{1,6,4,6,22}\@{1,6,4,6,22}\@{2,6,4,6,21}%
   \@{2,6,4,6,21}\@{2,6,4,6,21}\@{3,6,4,6,20}\@{3,6,4,6,20}\@{3,7,3,7,19}%
   \@{4,6,4,6,19}\@{4,7,3,7,18}\@{5,6,4,6,18}\@{5,6,4,6,18}\@{6,6,4,6,17}%
   \@{6,6,4,6,17}\@{6,6,4,6,17}\@{6,6,4,6,17}\@{6,6,4,6,17}\@{6,6,4,6,17}%
   \@{6,6,4,6,17}\@{6,6,4,6,17}\@{5,6,4,6,18}\@{5,6,4,6,18}\@{5,6,4,6,18}%
   \@{4,6,4,6,19}\@{4,6,4,6,19}\@{2,8,2,8,19}\@{1,8,2,8,20}\@{1,8,2,8,20}%
   \@{1,8,2,8,20}\@{2,8,2,8,19}\@{3,7,3,7,19}\@{4,7,3,7,18}\@{5,6,4,6,18}%
   \@{5,7,3,7,17}\@{6,6,4,6,17}\@{6,6,4,6,17}\@{6,6,4,6,17}\@{6,6,4,6,17}%
   \@{8,2,8,2,19}\@{39}}
\@namedef{@astrosym@128}{\@@{0}%
   \@{7,5,12,5,14}\@{5,8,9,8,13}\@{4,9,8,9,13}\@{3,10,7,10,13}%
   \@{3,10,7,10,13}\@{2,10,7,10,14}\@{2,6,11,6,18}\@{2,6,11,6,18}%
   \@{2,6,11,6,18}\@{2,6,11,6,18}\@{2,10,7,10,14}\@{3,11,6,11,12}%
   \@{3,13,4,13,10}\@{4,13,4,13,9}\@{5,13,4,13,8}\@{7,11,6,11,8}%
   \@{11,8,9,8,7}\@{13,6,11,6,7}\@{13,6,11,6,7}\@{13,6,11,6,7}%
   \@{11,8,9,8,7}\@{7,11,6,11,8}\@{5,13,4,13,8}\@{4,13,4,13,9}%
   \@{3,13,4,13,10}\@{3,11,6,11,12}\@{2,10,7,10,14}\@{2,6,11,6,18}%
   \@{2,6,11,6,18}\@{2,6,11,6,18}\@{2,6,11,6,18}\@{2,10,7,10,14}%
   \@{3,11,6,11,12}\@{3,13,4,13,10}\@{4,13,4,13,9}\@{5,13,4,13,8}%
   \@{7,11,6,11,8}\@{11,8,9,8,7}\@{13,6,11,6,7}\@{13,6,11,6,7}%
   \@{13,6,11,6,7}\@{11,8,9,8,7}\@{7,11,6,11,8}\@{5,13,4,13,8}%
   \@{4,13,4,13,9}\@{3,13,4,13,10}\@{3,11,6,11,12}\@{2,10,7,10,14}%
   \@{2,6,11,6,18}\@{2,6,11,6,18}\@{2,6,11,6,18}\@{2,6,11,6,18}%
   \@{2,10,7,10,14}\@{3,10,7,10,13}\@{3,10,7,10,13}\@{4,9,8,9,13}%
   \@{5,8,9,8,13}\@{7,5,12,5,14}}
\@namedef{@astrosym@200}{\@@{0}%
   \@{21,9,19}\@{18,16,15}\@{15,21,13}\@{13,8,9,8,11}\@{11,6,17,6,9}%
   \@{10,5,21,5,8}\@{9,4,25,4,7}\@{8,4,27,4,6}\@{7,4,29,4,5}\@{6,4,31,4,4}%
   \@{6,3,33,3,4}\@{5,3,35,3,3}\@{5,3,35,3,3}\@{4,3,37,3,2}\@{4,3,37,3,2}%
   \@{3,3,39,3,1}\@{3,3,39,3,1}\@{3,3,39,3,1}\@{3,3,39,3,1}\@{2,3,41,3}%
   \@{2,3,41,3}\@{2,3,19,3,19,3}\@{2,3,18,5,18,3}\@{2,3,18,2,1,2,18,3}%
   \@{2,3,18,5,18,3}\@{2,3,19,3,19,3}\@{2,3,41,3}\@{2,3,41,3}\@{3,3,39,3,1}%
   \@{3,3,39,3,1}\@{3,3,39,3,1}\@{4,2,39,2,2}\@{4,3,37,3,2}\@{4,3,37,3,2}%
   \@{5,3,35,3,3}\@{5,3,35,3,3}\@{6,3,33,3,4}\@{6,4,31,4,4}\@{7,4,29,4,5}%
   \@{8,4,27,4,6}\@{9,4,25,4,7}\@{10,5,21,5,8}\@{11,6,17,6,9}%
   \@{13,8,9,8,11}\@{15,21,13}\@{18,16,15}\@{21,9,19}\@{49}}
\@namedef{@astrosym@201}{\@@{8}%
   \@{2,7,24,7,33}\@{1,10,19,13,30}\@{1,12,15,17,28}\@{9,6,11,7,7,7,26}%
   \@{11,5,9,5,13,5,13,3,9}\@{13,4,7,4,17,4,12,3,9}\@{14,4,5,4,19,4,11,3,9}%
   \@{15,4,3,4,21,4,10,3,9}\@{16,3,3,3,23,3,10,3,9}\@{17,3,1,3,25,3,9,3,9}%
   \@{17,3,1,3,25,3,9,3,9}\@{18,5,27,3,8,3,9}\@{18,5,27,3,8,3,9}%
   \@{19,3,29,3,7,3,9}\@{19,3,29,3,7,3,9}\@{19,3,29,3,7,3,9}%
   \@{19,3,29,21,1}\@{19,3,29,21,1}\@{19,3,29,21,1}\@{19,3,29,3,7,3,9}%
   \@{19,3,29,3,7,3,9}\@{18,5,27,3,8,3,9}\@{18,5,27,3,8,3,9}%
   \@{17,3,1,3,25,3,9,3,9}\@{17,3,1,3,25,3,9,3,9}\@{16,3,3,3,23,3,10,3,9}%
   \@{15,4,3,4,21,4,10,3,9}\@{14,4,5,4,19,4,11,3,9}\@{13,4,7,4,17,4,12,3,9}%
   \@{11,5,9,5,13,5,13,3,9}\@{9,6,11,7,7,7,26}\@{1,12,15,17,28}%
   \@{1,10,19,13,30}\@{2,7,24,7,33}\@{73}}
\@namedef{@astrosym@202}{\@@{0}%
   \@{16,8,37}\@{13,14,34}\@{11,18,32}\@{9,7,8,7,30}\@{8,5,14,5,29}%
   \@{7,4,18,4,16,1,11}\@{6,4,20,4,14,3,10}\@{5,4,22,4,13,3,10}%
   \@{4,4,24,4,12,3,10}\@{4,3,26,3,12,3,10}\@{3,3,28,3,11,3,10}%
   \@{3,3,28,3,11,3,10}\@{2,3,30,3,10,3,10}\@{2,3,30,3,10,3,10}%
   \@{2,3,30,3,10,3,10}\@{1,3,32,3,9,3,10}\@{1,3,32,3,9,3,10}%
   \@{1,3,32,3,9,3,10}\@{1,3,32,24,1}\@{1,3,32,24,1}\@{1,3,32,24,1}%
   \@{1,3,32,3,9,3,10}\@{1,3,32,3,9,3,10}\@{2,3,30,3,10,3,10}%
   \@{2,3,30,3,10,3,10}\@{2,3,30,3,10,3,10}\@{3,3,28,3,11,3,10}%
   \@{3,3,28,3,11,3,10}\@{4,3,26,3,12,3,10}\@{4,4,24,4,12,3,10}%
   \@{5,4,22,4,13,3,10}\@{6,4,20,4,14,3,10}\@{7,4,18,4,16,1,11}%
   \@{8,5,14,5,29}\@{9,7,8,7,30}\@{11,18,32}\@{13,14,34}\@{16,8,37}\@{61}}
\@namedef{@astrosym@203}{\@@{0}%
   \@{37,8,16}\@{34,14,13}\@{32,18,11}\@{30,7,8,7,9}\@{29,5,14,5,8}%
   \@{28,4,18,4,7}\@{27,4,20,4,6}\@{26,4,22,4,5}\@{11,1,13,4,24,4,4}%
   \@{10,3,12,3,26,3,4}\@{10,3,11,3,28,3,3}\@{10,3,11,3,28,3,3}%
   \@{10,3,10,3,30,3,2}\@{10,3,10,3,30,3,2}\@{10,3,10,3,30,3,2}%
   \@{10,3,9,3,32,3,1}\@{10,3,9,3,32,3,1}\@{10,3,9,3,32,3,1}%
   \@{1,24,32,3,1}\@{1,24,32,3,1}\@{1,24,32,3,1}\@{10,3,9,3,32,3,1}%
   \@{10,3,9,3,32,3,1}\@{10,3,10,3,30,3,2}\@{10,3,10,3,30,3,2}%
   \@{10,3,10,3,30,3,2}\@{10,3,11,3,28,3,3}\@{10,3,11,3,28,3,3}%
   \@{10,3,12,3,26,3,4}\@{11,1,13,4,24,4,4}\@{26,4,22,4,5}%
   \@{27,4,20,4,6}\@{28,4,18,4,7}\@{29,5,14,5,8}\@{30,7,8,7,9}%
   \@{32,18,11}\@{34,14,13}\@{37,8,16}\@{61}}
\@namedef{@astrosym@204}{\@@{0}%
   \@{43,8,16}\@{40,14,13}\@{38,18,11}\@{36,7,8,7,9}\@{35,5,14,5,8}%
   \@{34,4,18,4,7}\@{33,4,20,4,6}\@{32,4,22,4,5}\@{31,4,24,4,4}%
   \@{31,3,26,3,4}\@{30,3,28,3,3}\@{30,3,28,3,3}\@{29,3,30,3,2}%
   \@{29,3,30,3,2}\@{29,3,30,3,2}\@{28,3,32,3,1}\@{28,3,32,3,1}%
   \@{28,3,32,3,1}\@{28,3,32,3,1}\@{28,3,32,3,1}\@{28,3,32,3,1}%
   \@{13,2,13,3,32,3,1}\@{12,4,12,3,32,3,1}\@{12,3,11,6,30,3,2}%
   \@{11,3,10,8,30,3,2}\@{10,4,8,6,1,3,30,3,2}\@{10,3,7,6,4,3,28,3,3}%
   \@{9,3,6,6,6,3,28,3,3}\@{8,4,4,6,9,3,26,3,4}\@{7,4,3,6,11,4,24,4,4}%
   \@{7,3,2,6,14,4,22,4,5}\@{6,3,1,6,17,4,20,4,6}\@{5,9,20,4,18,4,7}%
   \@{4,8,23,5,14,5,8}\@{3,18,15,7,8,7,9}\@{2,20,16,18,11}%
   \@{1,21,18,14,13}\@{1,4,38,8,16}\@{67}}
\@namedef{@astrosym@205}{\@@{0}%
   \@{1,3,36,3,11}\@{1,4,34,4,11}\@{2,5,31,5,11}\@{3,7,26,7,11}%
   \@{5,8,20,10,11}\@{7,11,11,9,2,3,11}\@{10,26,4,3,11}\@{14,19,7,3,11}%
   \@{18,11,11,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}%
   \@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}%
   \@{40,3,11}\@{40,3,11}\@{11,42,1}\@{11,42,1}\@{11,42,1}\@{40,3,11}%
   \@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}\@{40,3,11}\@{54}}
\@namedef{@astrosym@206}{\@@{6}%
   \@{9,3,52}\@{9,3,52}\@{9,3,52}\@{9,3,52}\@{9,3,52}\@{2,53,9}\@{2,53,9}%
   \@{2,53,9}\@{9,3,12,3,37}\@{9,3,11,3,38}\@{9,3,11,3,38}\@{9,3,11,3,38}%
   \@{10,1,12,2,39}\@{22,3,39}\@{22,3,39}\@{22,3,39}\@{22,3,39}\@{21,3,40}%
   \@{21,3,40}\@{21,3,29,4,7}\@{21,3,27,8,5}\@{21,3,25,12,3}%
   \@{21,3,23,6,4,5,2}\@{21,3,21,6,8,5}\@{21,3,19,6,11,4}%
   \@{21,3,17,6,15,1,1}\@{22,3,14,6,19}\@{22,3,12,6,21}\@{22,4,7,8,23}%
   \@{23,16,25}\@{24,12,28}\@{26,7,31}\@{64}}
\@namedef{@astrosym@207}{\@@{5}%
   \@{40,8,16}\@{37,14,13}\@{35,18,11}\@{33,7,8,7,9}\@{32,5,14,5,8}%
   \@{31,4,18,4,7}\@{30,4,20,4,6}\@{29,4,22,4,5}\@{28,4,24,4,4}%
   \@{17,2,9,3,26,3,4}\@{16,4,7,3,28,3,3}\@{14,5,8,3,28,3,3}%
   \@{13,5,8,3,30,3,2}\@{11,5,10,3,30,3,2}\@{10,5,11,3,30,3,2}%
   \@{8,5,12,3,32,3,1}\@{5,7,13,3,32,3,1}\@{2,8,15,3,32,3,1}%
   \@{1,27,15,2,15,3,1}\@{1,27,15,2,15,3,1}\@{1,27,32,3,1}%
   \@{5,7,13,3,32,3,1}\@{8,5,12,3,32,3,1}\@{10,5,11,3,30,3,2}%
   \@{11,5,10,3,30,3,2}\@{13,5,8,3,30,3,2}\@{14,5,8,3,28,3,3}%
   \@{16,4,7,3,28,3,3}\@{17,2,9,3,26,3,4}\@{28,4,24,4,4}\@{29,4,22,4,5}%
   \@{30,4,20,4,6}\@{31,4,18,4,7}\@{32,5,14,5,8}\@{33,7,8,7,9}\@{35,18,11}%
   \@{37,14,13}\@{40,8,16}\@{64}}
\@namedef{@astrosym@208}{\@@{0}%
   \@{20,2,39}\@{17,5,39}\@{15,7,39}\@{12,8,41}\@{9,8,44}\@{6,9,46}%
   \@{1,47,13}\@{1,48,12}\@{1,48,12}\@{3,10,33,3,12}\@{7,9,30,3,12}%
   \@{10,8,28,3,12}\@{13,8,25,3,12}\@{16,6,24,3,12}\@{18,4,24,3,12}%
   \@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}%
   \@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{19,3,24,3,12}%
   \@{17,5,24,3,12}\@{14,7,25,3,12}\@{11,8,27,3,12}\@{8,9,29,3,12}%
   \@{5,9,32,3,12}\@{1,59,1}\@{1,59,1}\@{1,59,1}\@{5,9,32,3,12}%
   \@{8,9,29,3,12}\@{11,8,27,3,12}\@{14,7,25,3,12}\@{17,5,24,3,12}%
   \@{19,3,24,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}%
   \@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{18,4,24,3,12}%
   \@{16,6,24,3,12}\@{13,8,25,3,12}\@{10,8,28,3,12}\@{7,9,30,3,12}%
   \@{3,10,33,3,12}\@{1,48,12}\@{1,48,12}\@{1,47,13}\@{6,9,46}\@{9,8,44}%
   \@{12,8,41}\@{15,7,39}\@{17,5,39}\@{20,2,39}\@{61}}
\@namedef{@astrosym@209}{\@@{0}%
   \@{1,59,1}\@{1,59,1}\@{1,59,1}\@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}%
   \@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}%
   \@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}%
   \@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}%
   \@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}%
   \@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}%
   \@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}\@{1,3,32,3,18,3,1}%
   \@{1,3,32,3,18,3,1}\@{2,3,30,3,19,3,1}\@{2,3,30,3,19,3,1}\@{2,3,30,3,23}%
   \@{3,3,28,3,24}\@{3,3,28,3,24}\@{4,3,26,3,25}\@{4,4,24,4,25}%
   \@{5,4,22,4,26}\@{6,4,20,4,27}\@{7,5,16,5,28}\@{8,7,10,7,29}%
   \@{10,20,31}\@{12,16,33}\@{15,10,36}\@{61}}
\@namedef{@astrosym@210}{\@@{0}%
   \@{21,9,19}\@{18,16,15}\@{15,21,13}\@{13,8,9,8,11}\@{11,6,17,6,9}%
   \@{10,5,21,5,8}\@{9,4,25,4,7}\@{8,4,27,4,6}\@{7,4,29,4,5}\@{6,4,31,4,4}%
   \@{6,3,33,3,4}\@{5,3,35,3,3}\@{5,3,35,3,3}\@{4,3,37,3,2}\@{4,3,37,3,2}%
   \@{3,3,16,7,16,3,1}\@{3,3,13,13,13,3,1}\@{3,3,11,17,11,3,1}%
   \@{3,3,9,7,7,7,9,3,1}\@{2,3,9,5,13,5,9,3}\@{2,3,8,4,17,4,8,3}%
   \@{2,3,7,4,19,4,7,3}\@{2,3,6,4,21,4,6,3}\@{2,3,6,3,23,3,6,3}%
   \@{2,3,5,3,25,3,5,3}\@{2,3,5,3,25,3,5,3}\@{2,3,4,3,27,3,4,3}%
   \@{2,3,4,3,27,3,4,3}\@{2,3,3,3,29,3,3,3}\@{3,3,2,3,29,3,2,3,1}%
   \@{3,3,2,3,29,3,2,3,1}\@{3,3,2,3,29,3,2,3,1}\@{4,3,1,3,29,3,1,3,2}%
   \@{4,3,1,3,29,3,1,3,2}\@{5,6,29,6,3}\@{5,6,29,6,3}\@{6,6,27,6,4}%
   \@{6,6,27,6,4}\@{7,5,27,5,5}\@{8,5,25,5,6}\@{9,5,23,5,7}\@{10,4,23,4,8}%
   \@{12,2,23,2,10}\@{49}}
\@namedef{@astrosym@211}{\@@{0}%
   \@{55}\@{6,3,46}\@{5,4,46}\@{4,4,47}\@{3,4,48}\@{3,3,49}\@{2,3,50}%
   \@{2,3,50}\@{2,3,50}\@{2,3,50}\@{2,3,50}\@{3,3,49}\@{3,3,49}\@{3,4,48}%
   \@{4,4,5,3,39}\@{5,16,34}\@{6,20,29}\@{8,5,3,15,24}\@{21,15,19}%
   \@{26,15,14}\@{31,15,9}\@{36,15,4}\@{41,14}\@{46,9}\@{41,14}\@{36,15,4}%
   \@{31,15,9}\@{26,15,14}\@{21,15,19}\@{8,5,3,15,24}\@{6,20,29}\@{5,16,34}%
   \@{4,4,5,3,39}\@{3,4,48}\@{3,3,49}\@{3,3,49}\@{2,3,50}\@{2,3,50}%
   \@{2,3,50}\@{2,3,50}\@{2,3,50}\@{3,3,49}\@{3,4,48}\@{4,4,47}\@{5,4,46}%
   \@{6,3,46}\@{55}\@{55}}
\@namedef{@astrosym@212}{\@@{4}%
   \@{12,6,43}\@{9,11,41}\@{7,15,39}\@{6,6,6,5,38}\@{5,4,11,4,37}%
   \@{3,5,13,3,17,7,13}\@{2,5,15,3,13,12,11}\@{2,3,17,3,12,15,9}%
   \@{23,3,9,6,7,6,7}\@{23,3,8,5,11,5,6}\@{24,3,6,4,15,4,5}%
   \@{24,3,5,4,17,4,4}\@{24,3,4,4,19,3,4}\@{25,3,3,3,21,3,3}%
   \@{25,3,2,3,22,4,2}\@{25,3,2,3,23,3,2}\@{25,3,1,3,25,3,1}%
   \@{26,6,25,3,1}\@{26,5,26,3,1}\@{26,5,27,3}\@{26,5,27,3}\@{26,4,28,3}%
   \@{27,3,28,3}\@{27,3,28,3}\@{27,3,28,3}\@{26,4,28,3}\@{26,5,27,3}%
   \@{26,5,27,3}\@{26,5,26,3,1}\@{26,6,25,3,1}\@{25,3,1,3,25,3,1}%
   \@{25,3,2,3,23,3,2}\@{25,3,2,3,22,4,2}\@{25,3,3,3,21,3,3}%
   \@{24,3,4,4,19,3,4}\@{24,3,5,4,17,4,4}\@{24,3,6,4,15,4,5}%
   \@{23,3,8,5,11,5,6}\@{23,3,9,6,7,6,7}\@{2,3,17,3,12,15,9}%
   \@{2,4,16,3,13,12,11}\@{3,4,14,3,17,7,13}\@{4,4,12,4,37}%
   \@{5,6,7,5,38}\@{6,16,39}\@{8,12,41}\@{11,7,43}\@{61}}
\@namedef{@astrosym@213}{\@@{4}%
   \@{2,3,54,2}\@{2,3,53,3}\@{3,3,51,3,1}\@{3,4,49,4,1}\@{4,4,47,4,2}%
   \@{5,4,45,4,3}\@{6,3,45,3,4}\@{7,3,43,3,5}\@{7,3,43,3,5}\@{8,3,41,3,6}%
   \@{8,3,41,3,6}\@{8,47,6}\@{9,45,7}\@{9,45,7}\@{9,3,39,3,7}\@{10,3,37,3,8}%
   \@{10,3,37,3,8}\@{10,3,37,3,8}\@{10,3,37,3,8}\@{10,3,37,3,8}%
   \@{10,3,37,3,8}\@{10,3,37,3,8}\@{10,3,37,3,8}\@{10,3,37,3,8}%
   \@{10,3,37,3,8}\@{10,3,37,3,8}\@{9,3,39,3,7}\@{9,45,7}\@{9,45,7}%
   \@{8,47,6}\@{8,3,41,3,6}\@{8,3,41,3,6}\@{7,3,43,3,5}\@{7,3,43,3,5}%
   \@{6,3,45,3,4}\@{5,4,45,4,3}\@{4,4,47,4,2}\@{3,4,49,4,1}\@{3,3,51,3,1}%
   \@{2,3,53,3}\@{2,3,53,3}\@{61}}
\@namedef{@astrosym@214}{\@@{0}%
   \@{22,8,22}\@{19,14,19}\@{17,17,7,2,9}\@{15,9,6,5,5,4,8}%
   \@{13,9,10,3,6,3,8}\@{12,5,1,3,12,3,6,3,7}\@{11,4,3,3,12,3,6,3,7}%
   \@{10,4,3,3,14,3,6,3,6}\@{9,4,4,3,14,3,6,3,6}\@{8,4,5,3,14,3,7,3,5}%
   \@{8,3,6,3,14,3,7,3,5}\@{7,3,7,3,14,3,8,3,4}\@{7,3,7,3,14,3,8,3,4}%
   \@{6,3,9,3,12,3,10,3,3}\@{6,3,9,3,12,3,10,3,3}\@{5,3,11,3,10,3,11,3,3}%
   \@{5,3,11,5,6,5,12,3,2}\@{4,3,13,14,13,3,2}\@{4,3,14,12,14,3,2}%
   \@{4,3,17,6,17,3,2}\@{3,3,42,3,1}\@{3,3,42,3,1}\@{3,3,42,3,1}%
   \@{3,3,42,3,1}\@{2,3,43,3,1}\@{2,3,44,3}\@{2,3,44,3}\@{2,3,44,3}%
   \@{2,3,44,3}\@{2,3,44,3}\@{2,3,44,3}\@{2,3,44,3}\@{2,3,44,3}\@{2,3,44,3}%
   \@{2,3,44,3}\@{2,3,44,3}\@{2,3,44,3}\@{3,3,43,3}\@{3,3,42,3,1}%
   \@{3,3,42,3,1}\@{3,3,42,3,1}\@{3,3,42,3,1}\@{4,3,17,6,17,3,2}%
   \@{4,3,14,12,14,3,2}\@{4,3,13,14,13,3,2}\@{4,3,12,5,6,5,11,3,3}%
   \@{5,3,11,3,10,3,11,3,3}\@{5,3,10,3,12,3,9,3,4}\@{5,3,10,3,12,3,9,3,4}%
   \@{6,3,8,3,14,3,7,3,5}\@{6,3,8,3,14,3,7,3,5}\@{7,3,7,3,14,3,6,3,6}%
   \@{7,3,7,3,14,3,5,4,6}\@{8,3,6,3,14,3,4,4,7}\@{8,3,6,3,14,3,3,4,8}%
   \@{9,3,6,3,12,3,3,4,9}\@{9,3,6,3,12,3,1,5,10}\@{10,3,6,3,10,9,11}%
   \@{10,4,5,5,6,9,13}\@{11,2,7,17,15}\@{21,14,17}\@{24,8,20}\@{52}}
\@namedef{@astrosym@215}{\@@{5}%
   \@{47,7,14}\@{45,11,12}\@{44,13,11}\@{43,4,7,4,10}\@{42,4,9,4,9}%
   \@{42,3,11,3,9}\@{42,3,11,3,9}\@{41,3,13,3,8}\@{13,9,19,3,13,3,8}%
   \@{10,16,15,3,13,3,8}\@{8,21,12,3,13,3,8}\@{7,6,9,10,9,3,13,3,8}%
   \@{6,4,16,9,7,3,11,3,9}\@{5,4,20,9,4,3,11,3,9}\@{4,4,24,9,1,4,9,4,9}%
   \@{4,3,28,13,6,4,10}\@{3,3,32,19,11}\@{3,3,35,15,12}\@{2,3,40,9,14}%
   \@{2,3,63}\@{2,3,63}\@{1,3,64}\@{1,3,64}\@{1,3,64}\@{1,3,64}\@{1,3,64}%
   \@{1,3,64}\@{1,3,64}\@{1,3,64}\@{1,3,64}\@{2,3,63}\@{2,3,63}\@{2,3,63}%
   \@{3,3,46,10,6}\@{3,3,40,18,4}\@{4,3,35,23,3}\@{4,4,30,14,10,4,2}%
   \@{5,4,24,13,17,3,2}\@{6,4,19,13,22,3,1}\@{7,6,10,15,26,3,1}%
   \@{8,25,31,3,1}\@{10,18,36,3,1}\@{13,10,41,3,1}\@{64,3,1}\@{64,3,1}%
   \@{63,3,2}\@{62,4,2}\@{58,7,3}\@{57,7,4}\@{58,4,6}\@{68}}
\@namedef{@astrosym@216}{\@@{5}%
   \@{2,50,7}\@{2,50,7}\@{2,50,7}\@{12,3,44}\@{11,4,44}\@{11,3,45}%
   \@{10,3,46}\@{9,4,46}\@{9,3,47}\@{8,3,48}\@{8,3,48}\@{7,3,49}\@{7,3,49}%
   \@{7,3,49}\@{6,3,50}\@{6,3,50}\@{6,3,50}\@{5,3,51}\@{5,3,51}\@{5,3,51}%
   \@{5,3,51}\@{5,3,51}\@{5,3,51}\@{5,4,50}\@{6,46,7}\@{7,45,7}\@{9,43,7}%
   \@{12,3,44}\@{11,3,45}\@{10,4,45}\@{10,3,46}\@{9,3,47}\@{9,3,47}\@{8,3,48}%
   \@{8,3,48}\@{7,3,49}\@{7,3,42,3,4}\@{6,3,42,4,4}\@{6,3,42,3,5}%
   \@{6,3,41,3,6}\@{5,3,42,3,6}\@{5,3,41,3,7}\@{5,3,41,3,7}\@{5,3,41,3,7}%
   \@{5,3,40,3,8}\@{5,3,40,3,8}\@{5,4,39,3,8}\@{6,53}\@{7,52}\@{9,50}%
   \@{12,4,32,3,8}\@{11,4,33,3,8}\@{10,4,34,3,8}\@{9,4,35,3,8}%
   \@{8,4,36,3,8}\@{8,3,37,3,8}\@{7,3,38,3,8}\@{6,4,38,3,8}\@{6,3,39,3,8}%
   \@{5,3,40,3,8}\@{4,4,40,3,8}\@{4,3,41,3,8}\@{3,3,42,3,8}\@{3,3,42,3,8}%
   \@{3,3,43,3,7}\@{2,3,43,3,8}\@{2,3,43,3,8}\@{2,3,42,3,9}\@{2,3,41,4,9}%
   \@{2,3,39,5,10}\@{3,3,36,6,11}\@{3,43,13}\@{4,40,15}\@{6,36,17}}
\@namedef{@astrosym@217}{\@@{0}%
   \@{18,5,11,3,6}\@{18,6,10,3,6}\@{18,6,10,3,6}\@{21,3,10,3,6}%
   \@{21,3,10,3,6}\@{21,3,10,3,6}\@{21,3,10,3,6}\@{21,3,10,3,6}%
   \@{21,3,10,3,6}\@{21,3,10,3,6}\@{21,3,10,3,6}\@{11,7,3,3,10,3,6}%
   \@{9,11,1,3,10,3,6}\@{7,17,10,3,6}\@{6,5,7,6,10,3,6}\@{5,4,11,4,10,3,6}%
   \@{4,4,26,3,6}\@{4,3,27,3,6}\@{3,3,28,3,6}\@{3,3,28,3,6}\@{2,3,29,3,6}%
   \@{2,3,29,3,6}\@{2,3,29,3,6}\@{2,3,29,3,6}\@{2,3,29,3,6}\@{2,3,29,3,6}%
   \@{2,3,29,3,6}\@{3,3,28,3,6}\@{3,3,28,3,6}\@{4,3,27,3,6}\@{4,4,26,3,6}%
   \@{5,4,11,3,11,3,6}\@{6,5,7,6,10,3,6}\@{7,17,10,3,6}\@{9,11,1,3,10,3,6}%
   \@{11,7,3,3,10,3,6}\@{21,3,10,3,6}\@{21,3,10,3,6}\@{21,3,10,3,6}%
   \@{21,3,10,3,6}\@{21,3,10,3,6}\@{21,3,10,3,6}\@{21,3,10,3,6}%
   \@{21,3,10,3,6}\@{18,6,10,3,6}\@{18,6,10,3,6}\@{18,6,10,3,6}\@{43}}
\@namedef{@astrosym@218}{\@@{5}%
   \@{2,50,7}\@{2,50,7}\@{2,50,7}\@{12,3,44}\@{11,4,44}\@{10,4,45}%
   \@{10,3,46}\@{9,3,47}\@{9,3,47}\@{8,3,48}\@{8,3,48}\@{7,3,49}%
   \@{7,3,49}\@{6,3,50}\@{6,3,50}\@{6,3,50}\@{5,3,51}\@{5,3,51}\@{5,3,51}%
   \@{5,3,51}\@{5,3,51}\@{5,3,51}\@{6,3,50}\@{6,5,48}\@{7,45,7}\@{9,43,7}%
   \@{11,41,7}\@{12,3,44}\@{11,3,45}\@{10,4,45}\@{9,4,46}\@{9,3,47}%
   \@{8,3,48}\@{8,3,48}\@{7,3,49}\@{7,3,49}\@{7,2,50}\@{6,3,50}\@{6,3,50}%
   \@{6,3,50}\@{5,3,51}\@{5,3,51}\@{5,3,51}\@{5,3,51}\@{5,3,51}\@{6,3,50}%
   \@{6,5,48}\@{7,48,4}\@{9,48,2}\@{11,47,1}\@{55,3,1}\@{56,3}\@{56,3}%
   \@{56,3}\@{49,1,6,3}\@{48,3,4,3,1}\@{47,3,4,4,1}\@{47,3,3,4,2}%
   \@{47,3,2,4,3}\@{46,3,1,5,4}\@{46,8,5}\@{45,7,7}\@{44,7,3,2,3}%
   \@{44,13,2}\@{43,14,2}\@{42,12,5}\@{42,8,9}\@{41,6,12}\@{42,2,15}\@{59}}
\@namedef{@astrosym@219}{\@@{4}%
   \@{63,3,1}\@{48,1,13,4,1}\@{47,3,10,5,2}\@{47,3,9,5,3}\@{48,3,6,5,5}%
   \@{48,4,3,6,6}\@{49,3,2,5,8}\@{50,7,10}\@{50,6,11}\@{49,5,13}\@{47,8,12}%
   \@{46,5,1,3,12}\@{44,5,4,3,11}\@{42,6,5,3,11}\@{41,5,8,3,10}%
   \@{39,5,10,3,10}\@{37,6,12,1,11}\@{36,5,26}\@{34,5,28}\@{32,6,29}%
   \@{31,5,31}\@{29,5,33}\@{28,5,34}\@{14,2,10,5,36}\@{14,3,7,6,37}%
   \@{13,3,7,5,39}\@{12,4,5,5,41}\@{11,4,4,6,42}\@{11,3,4,5,44}%
   \@{10,3,3,5,46}\@{9,4,2,5,47}\@{8,4,1,5,49}\@{7,10,50}\@{6,9,6,1,45}%
   \@{5,8,3,7,44}\@{5,18,44}\@{4,17,46}\@{3,13,51}\@{2,9,56}\@{1,6,60}%
   \@{1,3,63}\@{67}}
\@namedef{@astrosym@220}{\@@{0}%
   \@{27,2,20}\@{26,3,20}\@{25,4,20}\@{24,4,21}\@{24,3,22}\@{23,3,23}%
   \@{23,3,23}\@{22,3,24}\@{22,3,24}\@{3,1,17,3,25}\@{2,3,16,3,25}%
   \@{2,3,15,3,26}\@{2,3,15,3,26}\@{2,3,14,3,6,9,12}\@{2,3,14,3,3,15,9}%
   \@{2,3,14,3,1,19,7}\@{2,3,13,3,1,6,9,7,5}\@{2,3,13,7,15,5,4}%
   \@{2,3,13,6,18,4,3}\@{2,3,13,4,21,4,2}\@{2,3,12,4,23,3,2}%
   \@{2,3,11,4,25,3,1}\@{2,3,10,5,25,3,1}\@{2,3,9,6,26,3}\@{2,3,9,6,26,3}%
   \@{2,3,8,3,1,3,26,3}\@{2,3,7,4,1,3,26,3}\@{2,3,6,4,2,3,26,3}%
   \@{2,3,6,3,3,3,26,3}\@{2,3,5,3,4,3,26,3}\@{2,3,4,4,5,3,25,3}%
   \@{2,3,3,4,6,3,24,3,1}\@{2,3,3,3,7,3,24,3,1}\@{2,3,2,3,9,3,22,3,2}%
   \@{2,3,1,4,9,4,20,4,2}\@{2,7,11,4,18,4,3}\@{2,6,13,5,14,5,4}%
   \@{2,5,15,7,8,7,5}\@{2,4,18,18,7}\@{2,3,21,14,9}\@{2,3,24,8,12}\@{49}}
\@namedef{@astrosym@221}{\@@{0}%
   \@{10,2,17,2,14}\@{8,4,15,4,14}\@{6,6,13,6,14}\@{4,6,13,6,16}%
   \@{2,6,13,6,18}\@{1,5,14,5,20}\@{1,5,14,5,20}\@{3,5,14,5,18}%
   \@{4,6,13,6,16}\@{6,6,13,6,14}\@{8,6,13,6,12}\@{10,6,13,6,10}%
   \@{12,6,13,6,8}\@{14,6,13,6,6}\@{16,4,15,4,6}\@{15,5,14,5,6}%
   \@{13,6,13,6,7}\@{11,6,13,6,9}\@{9,6,13,6,11}\@{7,6,13,6,13}%
   \@{5,6,13,6,15}\@{3,6,13,6,17}\@{2,5,14,5,19}\@{1,4,15,4,21}%
   \@{1,6,13,6,19}\@{3,6,13,6,17}\@{5,6,13,6,15}\@{7,6,13,6,13}%
   \@{9,6,13,6,11}\@{11,5,14,5,10}\@{13,5,14,5,8}\@{14,6,13,6,6}%
   \@{16,4,15,4,6}\@{14,6,13,6,6}\@{12,6,13,6,8}\@{10,6,13,6,10}%
   \@{9,5,14,5,12}\@{7,5,14,5,14}\@{5,6,13,6,15}\@{3,6,13,6,17}%
   \@{1,6,13,6,19}\@{1,5,14,5,20}\@{2,6,13,6,18}\@{4,6,13,6,16}%
   \@{6,5,14,5,15}\@{8,5,14,5,13}\@{9,6,13,6,11}\@{11,6,13,6,9}%
   \@{13,6,13,6,7}\@{15,5,14,5,6}\@{15,5,14,5,6}\@{14,5,14,5,7}%
   \@{12,5,14,5,9}\@{10,6,13,6,10}\@{9,5,14,5,12}\@{10,2,17,2,14}\@{45}}
\@namedef{@astrosym@222}{\@@{4}%
   \@{2,3,53,3}\@{2,4,51,4}\@{3,5,47,5,1}\@{4,6,43,6,2}\@{6,7,37,7,4}%
   \@{8,7,33,7,6}\@{10,9,25,9,8}\@{13,11,15,11,11}\@{15,33,13}\@{19,25,17}%
   \@{24,15,22}\@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}%
   \@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}%
   \@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}\@{30,3,28}%
   \@{30,3,28}\@{30,3,28}\@{24,15,22}\@{19,25,17}\@{15,33,13}%
   \@{13,11,15,11,11}\@{10,9,25,9,8}\@{8,7,33,7,6}\@{6,7,37,7,4}%
   \@{4,6,43,6,2}\@{3,5,47,5,1}\@{2,4,51,4}\@{2,3,53,3}\@{61}}
\@namedef{@astrosym@223}{\@@{6}%
   \@{10,3,51}\@{10,3,51}\@{10,3,51}\@{10,3,51}\@{10,3,51}\@{10,3,51}%
   \@{10,3,45,5,1}\@{10,3,43,8}\@{10,3,41,10}\@{10,3,40,5,6}\@{10,3,39,4,8}%
   \@{10,3,38,4,9}\@{10,3,37,4,10}\@{2,19,29,3,11}\@{2,19,28,3,12}%
   \@{2,19,27,4,12}\@{10,3,5,3,26,4,13}\@{10,3,5,3,25,4,14}%
   \@{10,3,5,3,25,3,15}\@{10,3,5,3,24,3,16}\@{10,3,6,3,22,4,16}%
   \@{10,3,6,3,21,4,17}\@{10,3,6,3,20,4,18}\@{10,3,6,3,19,4,19}%
   \@{10,3,7,3,17,4,20}\@{10,3,7,3,16,4,21}\@{10,3,8,3,13,5,22}%
   \@{10,3,8,4,10,6,23}\@{11,1,10,4,7,6,25}\@{23,14,27}\@{24,11,29}%
   \@{26,7,31}\@{64}}
\@namedef{@astrosym@224}{\@@{0}%
   \@{20,2,39}\@{17,5,39}\@{15,7,39}\@{12,8,41}\@{9,8,44}\@{6,9,46}%
   \@{1,23,37}\@{1,26,34}\@{1,29,31}\@{3,10,11,8,29}\@{7,9,11,6,28}%
   \@{10,8,11,6,26}\@{13,8,10,5,25}\@{16,6,11,4,24}\@{18,4,12,4,23}%
   \@{35,4,22}\@{36,3,22}\@{37,3,21}\@{37,3,21}\@{38,3,20}\@{38,3,20}%
   \@{39,3,19}\@{39,3,19}\@{40,3,18}\@{40,3,18}\@{19,3,18,3,9,3,6}%
   \@{17,5,18,3,9,3,6}\@{14,7,20,3,8,3,6}\@{11,8,22,3,8,3,6}%
   \@{8,9,24,3,8,3,6}\@{5,9,27,3,8,3,6}\@{1,59,1}\@{1,59,1}\@{1,59,1}%
   \@{5,9,27,3,8,3,6}\@{8,9,24,3,8,3,6}\@{11,8,22,3,8,3,6}%
   \@{14,7,20,3,8,3,6}\@{17,5,18,3,9,3,6}\@{19,3,18,3,9,3,6}\@{40,3,18}%
   \@{40,3,18}\@{39,3,19}\@{39,3,19}\@{38,3,20}\@{38,3,20}\@{37,3,21}%
   \@{37,3,21}\@{36,3,22}\@{35,4,22}\@{18,4,12,4,23}\@{16,6,11,4,24}%
   \@{13,8,10,5,25}\@{10,8,11,6,26}\@{7,9,11,6,28}\@{3,10,11,8,29}%
   \@{1,29,31}\@{1,26,34}\@{1,23,37}\@{6,9,46}\@{9,8,44}\@{12,8,41}%
   \@{15,7,39}\@{17,5,39}\@{20,2,39}\@{61}}
\@namedef{@astrosym@225}{\@@{0}%
   \@{20,2,39}\@{17,5,39}\@{14,8,39}\@{11,9,41}\@{7,10,44}\@{3,11,47}%
   \@{1,48,12}\@{1,48,12}\@{1,48,12}\@{7,10,29,3,12}\@{11,9,26,3,12}%
   \@{14,8,24,3,12}\@{17,5,24,3,12}\@{20,2,24,3,12}\@{46,3,12}\@{46,3,12}%
   \@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}%
   \@{46,3,12}\@{46,3,12}\@{46,14,1}\@{46,14,1}\@{46,14,1}\@{46,3,12}%
   \@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}\@{46,3,12}%
   \@{46,3,12}\@{46,3,12}\@{20,2,24,3,12}\@{17,5,24,3,12}\@{14,8,24,3,12}%
   \@{11,9,26,3,12}\@{7,10,29,3,12}\@{1,48,12}\@{1,48,12}\@{1,48,12}%
   \@{3,11,47}\@{7,10,44}\@{11,9,41}\@{14,8,39}\@{17,5,39}\@{20,2,39}\@{61}}
\@namedef{@astrosym@226}{\@@{0}%
   \@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}%
   \@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}%
   \@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}%
   \@{20,3,8,3,15}\@{10,5,5,3,8,3,15}\@{8,9,3,3,8,3,15}\@{6,13,1,3,8,3,15}%
   \@{5,5,5,8,8,3,15}\@{4,4,9,6,8,3,15}\@{4,3,11,5,8,3,15}\@{3,3,13,4,8,3,15}%
   \@{3,3,13,4,8,3,15}\@{2,3,15,3,8,3,15}\@{2,3,15,3,8,3,15}%
   \@{2,3,15,3,8,3,15}\@{2,3,15,3,8,3,15}\@{2,3,15,3,8,3,15}%
   \@{3,3,13,4,8,3,15}\@{3,3,13,4,8,3,15}\@{4,3,11,5,8,3,15}%
   \@{4,4,9,6,8,3,15}\@{5,5,5,8,8,3,15}\@{6,13,1,3,8,3,15}\@{8,9,3,3,8,3,15}%
   \@{10,5,5,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}%
   \@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}%
   \@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}\@{20,3,8,3,15}%
   \@{20,3,8,3,15}\@{20,3,8,3,15}\@{49}}
\@namedef{@astrosym@227}{\@@{0}%
   \@{9,2,8,2,18}\@{7,5,5,5,17}\@{6,5,5,5,18}\@{5,4,6,4,20}\@{4,4,6,4,21}%
   \@{4,3,7,3,22}\@{3,3,7,3,23}\@{3,3,7,3,23}\@{2,3,7,3,24}\@{2,3,7,3,24}%
   \@{2,3,7,3,24}\@{1,3,7,3,25}\@{1,3,7,3,25}\@{1,3,7,3,25}\@{1,3,7,3,25}%
   \@{1,3,7,3,25}\@{1,3,7,3,25}\@{1,3,7,3,25}\@{2,3,7,3,24}\@{2,3,7,3,24}%
   \@{3,3,7,3,23}\@{3,3,7,3,23}\@{4,3,7,3,22}\@{4,4,6,4,21}\@{5,4,6,4,20}%
   \@{6,3,7,3,20}\@{7,3,7,3,19}\@{7,3,7,3,19}\@{8,3,7,3,18}\@{8,3,7,3,18}%
   \@{9,3,7,3,17}\@{9,3,7,3,17}\@{9,3,7,3,17}\@{9,3,7,3,17}\@{9,3,7,3,17}%
   \@{9,3,7,3,17}\@{8,3,7,3,18}\@{7,4,6,4,18}\@{7,3,7,3,19}\@{6,3,7,3,20}%
   \@{5,4,6,4,20}\@{4,4,6,4,21}\@{3,4,6,4,22}\@{3,3,7,3,23}\@{2,3,7,3,24}%
   \@{1,5,5,5,23}\@{1,7,3,7,21}\@{4,5,5,5,20}\@{6,4,6,4,19}\@{7,3,7,3,19}%
   \@{8,3,7,3,18}\@{8,3,7,3,18}\@{9,3,7,3,17}\@{9,3,7,3,17}\@{9,3,7,3,17}%
   \@{9,3,7,3,17}\@{39}}
\@namedef{@astrosym@228}{\@@{0}%
   \@{8,3,14,3,15}\@{6,6,11,6,14}\@{5,7,10,7,14}\@{4,4,13,4,18}%
   \@{4,3,14,3,19}\@{3,3,14,3,20}\@{3,3,14,3,20}\@{3,3,14,3,20}%
   \@{3,3,14,3,20}\@{4,3,14,3,19}\@{4,4,13,4,18}\@{5,8,9,8,13}\@{6,9,8,9,11}%
   \@{8,8,9,8,10}\@{13,4,13,4,9}\@{14,3,14,3,9}\@{15,3,14,3,8}\@{15,3,14,3,8}%
   \@{15,3,14,3,8}\@{15,3,14,3,8}\@{14,3,14,3,9}\@{13,4,13,4,9}\@{8,8,9,8,10}%
   \@{6,9,8,9,11}\@{5,8,9,8,13}\@{4,4,13,4,18}\@{4,3,14,3,19}\@{3,3,14,3,20}%
   \@{3,3,14,3,20}\@{3,3,14,3,20}\@{3,3,14,3,20}\@{4,3,14,3,19}%
   \@{4,4,13,4,18}\@{5,8,9,8,13}\@{6,9,8,9,11}\@{8,8,9,8,10}\@{13,4,13,4,9}%
   \@{14,3,14,3,9}\@{15,3,14,3,8}\@{15,3,14,3,8}\@{15,3,14,3,8}%
   \@{15,3,14,3,8}\@{14,3,14,3,9}\@{13,4,13,4,9}\@{8,8,9,8,10}\@{6,9,8,9,11}%
   \@{5,8,9,8,13}\@{4,4,13,4,18}\@{4,3,14,3,19}\@{3,3,14,3,20}\@{3,3,14,3,20}%
   \@{3,3,14,3,20}\@{3,3,14,3,20}\@{4,3,14,3,19}\@{4,4,13,4,18}%
   \@{5,6,11,6,15}\@{6,6,11,6,14}\@{8,4,13,4,14}}
%%% end of font data
%
%%% miscellaneous symbols
\let\solar\Sol
\DeclareRobustCommand*\MO{%%% solar mass
   \relax\ifmmode\@math@sub@solar{M}\else\@text@sub@solar{M}\fi}
\let\Mo\MO
\DeclareRobustCommand*\LO{%%% solar luminosity
   \relax\ifmmode\@math@sub@solar{L}\else\@text@sub@solar{L}\fi}
\DeclareRobustCommand*\RO{%%% solar radius
   \relax\ifmmode\@math@sub@solar{R}\else\@text@sub@solar{R}\fi}
\def\@math@sub@solar#1{{{#1}_{\solar}}}
\def\@text@sub@solar#1{%
   \ifvmode\leavevmode\fi
   \hbox{$\m@th{#1}_{\solar}$}}
\if@useamsfonts
   \RequirePackage{amssymb}
\else
   \def\lesssim{\mathcomposite[4]\mathrel<\sim}
   \def\gtrsim{\mathcomposite[4]\mathrel>\sim}
   \def\leqq{\mathcomposite[3]\mathrel<=}
   \def\geqq{\mathcomposite[3]\mathrel>=}
   \def\lessgtr{\mathcomposite[-2]\mathrel<>}
   \def\gtrless{\mathcomposite[-2]\mathrel><}
   \def\lessapprox{\mathcomposite[2]\mathrel<\approx}
   \def\gtrapprox{\mathcomposite[2]\mathrel>\approx}
   \def\leftrightarrows{\mathcomposite\mathrel\gets\to}
   \def\square{\Box}
   \def\varnothing{\mathcomposite*\mathord\bigcirc{\big/}}
\fi
\def\D{\mathrm{d}}
\def\intkern@{\mkern-6mu\mathchoice{\mkern-3mu}{}{}{}}
\def\intdots@{%
   \mathchoice
      {{\cdotp\cdotp\cdotp}}%
      {{\cdotp}\mkern1.5mu{\cdotp}\mkern1.5mu{\cdotp}}%
      {{\cdotp}\mkern1mu{\cdotp}\mkern1mu{\cdotp}}%
      {{\cdotp}\mkern1mu{\cdotp}\mkern1mu{\cdotp}}}
\def\iint{\intop\intkern@\intop\nolimits}
\def\iiint{\intop\intkern@\intop\intkern@\intop\nolimits}
\def\iiiint{\intop\intkern@\intop\intkern@\intop\intkern@\intop\nolimits}
\def\idotsint{\intop\intdots@\intop\nolimits}
\def\hateqq{\mathrel{\widehat=}}
\def\simless{\mathcomposite[-2]\mathrel\sim<}
\def\simgtr{\mathcomposite[-2]\mathrel\sim>}
\def\lesssimeq{\mathcomposite\mathrel<{\mathcomposite[-6]\mathrel\sim-}}
\def\gtrsimeq{\mathcomposite\mathrel>{\mathcomposite[-6]\mathrel\sim-}}
\let\ltsim\lesssim
\let\gtsim\gtrsim
\let\getsto\leftrightarrows
\def\diameter{\ensuremath{\varnothing}}
\def\earth{\ensuremath{\oplus}}
\def\singlebond{\@makechembond\@ne}
\def\doublebond{\@makechembond\tw@}
\def\triplebond{\@makechembond\thr@@}
\let\sbond\singlebond
\let\dbond\doublebond
\let\tbond\triplebond
\def\@makechembond{\relax
   \ifmmode \expandafter\@math@makechembond
   \else    \expandafter\@text@makechembond \fi}
\def\@math@makechembond#1{%
   \mathchoice
      {\@makechembond@{#1}\@ne}%
      {\@makechembond@{#1}\@ne}%
      {\@makechembond@{#1}\defaultscriptratio}%
      {\@makechembond@{#1}\defaultscriptscriptratio}}
\def\@text@makechembond#1{\@makechembond@{#1}\@ne}
\def\@makechembond@#1#2{%
   \hbox{%
      \count@#1\relax
      \@tempdima .16667ex \@tempdima#2\@tempdima
      \@tempdimb .1em     \@tempdimb#2\@tempdimb
      \kern\@tempdimb
      \dimen@ -\@tempdima \multiply\dimen@\count@
      \advance\dimen@ 5.7\@tempdima %%% .95ex x ((scaling factor))
      \raise\dimen@\vbox{%
         \hrule\@height\@tempdima \@width 8\@tempdimb
         \loop \ifnum\count@ > \@ne
            \kern\@tempdima
            \hrule\@height\@tempdima \@width 8\@tempdimb
            \advance\count@\m@ne
         \repeat}%
      \kern\@tempdimb}}
\def\mathcomposite{%
   \@ifstar
      {\def\@mathcomposite@option{%
          \baselineskip\z@skip\lineskiplimit-\maxdimen}%
       \@mathcomposite}%
      {\let\@mathcomposite@option\offinterlineskip\@mathcomposite}}
\def\@mathcomposite{%
   \@ifnextchar[\@@mathcomposite{\@@mathcomposite[0]}}
\def\@@mathcomposite[#1]#2#3#4{%
   #2{\mathchoice
      {\@mathcomposite@{#1}{#3}{#4}\displaystyle{1}}%
      {\@mathcomposite@{#1}{#3}{#4}\textstyle{1}}%
      {\@mathcomposite@{#1}{#3}{#4}\scriptstyle\defaultscriptratio}%
      {\@mathcomposite@{#1}{#3}{#4}%
       \scriptscriptstyle\defaultscriptscriptratio}}}
\def\@mathcomposite@#1#2#3#4#5{%
   \vcenter{\m@th\@mathcomposite@option
      \dimen@\f@size\p@\dimen@#1\dimen@\dimen@#5\dimen@
      \divide\dimen@ 18 %%% \dimen@ is about #1 x #5 mu
      \edef\@mathcomposite@skipamount{\the\dimen@}%
      \ialign{\hfil$#4##$\hfil\cr
         #2\crcr\noalign{\vskip\@mathcomposite@skipamount}%
         #3\crcr}}}
\DeclareRobustCommand*\boldsymbol[1]{%
   \begingroup
   \mathchoice
      {\hbox{\mathversion{bold}$\m@th\displaystyle#1$}}%
      {\hbox{\mathversion{bold}$\m@th\textstyle#1$}}%
      {\hbox{\mathversion{bold}$\m@th\scriptstyle#1$}}%
      {\hbox{\mathversion{bold}$\m@th\scriptscriptstyle#1$}}%
   \endgroup}
\DeclareRobustCommand*\textbackslash{%
   \@nomath\textbackslash
   \ifmmode
      \backslash
   \else
      \edef\@tempa{\ttdefault}%
      \ifx\@tempa\f@family
         \begingroup\fontencoding{OT1}\selectfont\char'134\endgroup
      \else
         \begingroup\fontencoding{OMS}\selectfont\char'156\endgroup
      \fi
   \fi}
\DeclareRobustCommand*\atom{%
   \ifmmode \expandafter\@math@atom
   \else    \expandafter\@text@atom \fi}
\def\@text@atom#1#2#3{\ensuremath{\@atom\scriptstyle{#1}{#2}{#3}}}
\def\@math@atom#1#2#3{%
   \mathchoice
      {\@atom\scriptstyle{#1}{#2}{#3}}%
      {\@atom\scriptstyle{#1}{#2}{#3}}%
      {\@atom\scriptscriptstyle{#1}{#2}{#3}}%
      {\@atom\scriptscriptstyle{#1}{#2}{#3}}}
\def\@atom#1#2#3#4{%
   \begingroup
   \setbox\z@\hbox{$\m@th#1#3$}%
   \setbox\tw@\hbox{$\m@th#1#4$}%
   \ifdim\wd\z@<\wd\tw@ \dimen@\wd\tw@
   \else                \dimen@\wd\z@  \fi
   {\vphantom{#2}}_{\hbox to\dimen@{\hss\unhbox\z@}}%
                  ^{\hbox to\dimen@{\hss\unhbox\tw@}}%
   \nobreak
   \mathrm{#2}%
   \endgroup}
\DeclareRobustCommand*\emissiontype{%
   \relax
   \ifmmode \expandafter\@math@emissiontype
   \else    \expandafter\@text@emissiontype
   \fi}
\def\@text@emissiontype#1{%
   \ifvmode \leavevmode \fi
   \unskip\nobreak\,\nobreak
   \@@emissiontype\f@size{#1}}
\def\@math@emissiontype#1{%
   \nobreak\,\nobreak
   \mathchoice
      {\@@emissiontype\tf@size{#1}}%
      {\@@emissiontype\tf@size{#1}}%
      {\@@emissiontype\sf@size{#1}}%
      {\@@emissiontype\ssf@size{#1}}}
\def\@@emissiontype#1#2{%
   \hbox{\dimen@#1\p@ \dimen@.8\dimen@
      \ifdim\dimen@<4\p@ \dimen@4\p@ \fi
      \fontsize\dimen@\f@baselineskip\selectfont
      #2}}
\newcount\leftroot@
\newcount\uproot@
\def\leftroot{\@latexerr{Invalid \string\leftroot}\@eha}
\def\uproot{\@latexerr{Invalid \string\uproot}\@eha}
\DeclareRobustCommand*\sqrt{%
   \bgroup
   \leftroot@\z@ \uproot@\z@
   \@ifnextchar[\@osqrt\@nsqrt}
\DeclareRobustCommand*\safesqrt{%
   \bgroup
   \let\@makesqrt\@noadjust@makesqrt
   \leftroot@\z@ \uproot@\z@
   \@ifnextchar[\@osqrt\@nsqrt}
\def\@nsqrt#1{\mathpalette\@makesqrt{#1}\egroup}
\def\@osqrt[#1]#2{\root #1\of{#2}\egroup}
\def\root#1\of{%
   \@get@root@shift#1\@nnil
   \setbox\rootbox\hbox{$\m@th\scriptscriptstyle{\@tempa}$}%
   \mathpalette\r@@t}
\def\@get@root@shift{\futurelet\let@token\@get@root@shift@}
\def\@get@root@shift@{%
   \def\next@{\@collect@root}%
   \ifx     \let@token\uproot   \def\next@{\@get@uproot}%
   \else\ifx\let@token\leftroot \def\next@{\@get@leftroot}%
   \else\ifx\let@token\@sptoken \def\next@{\@get@space@in@root}%
   \fi\fi\fi
   \next@}
\def\@get@uproot#1\uproot#2{%
   \advance\uproot@#2\relax
   \@get@root@shift}
\def\@get@leftroot#1\leftroot#2{%
   \advance\leftroot@#2\relax
   \@get@root@shift}
\begingroup
\def\:{\def\@get@space@in@root}
\expandafter\endgroup\: {\@get@root@shift}
\def\@collect@root#1\@nnil{\def\@tempa{#1}}
\def\r@@t#1#2{%
   \setbox\z@\hbox{$\m@th\@makesqrt{#1}{#2}$}%
   \dimen@\ht\z@ \advance\dimen@-\dp\z@
   \setbox\tw@\hbox{$\m@th#1\mskip\uproot@ mu$}%
   \advance\dimen@ by1.667\wd\tw@
   \mkern-\leftroot@ mu\mkern5mu
   \raise.6\dimen@\copy\rootbox
   \mkern-10mu\mkern\leftroot@ mu
   \box\z@}
\def\@@makesqrt#1#2{%
   \setbox\z@\hbox{$\m@th#1#2$}%
   \setbox\tw@\hbox{$\m@th#1\mkern50mu$}%
   \dimen@\wd\tw@ \@tempdima\dimen@
   \advance\dimen@-\ht\z@ \advance\dimen@-\dp\z@
   \ifdim\dimen@<\z@
      \setbox\tw@\hbox{$\m@th#1\fixedsqrtsign$}%
      \dimen@\f@size\p@
      \ifx#1\scriptscriptstyle \dimen@\defaultscriptscriptratio\dimen@ \fi
      \ifx#1\scriptstyle       \dimen@\defaultscriptratio\dimen@       \fi
      \dimen@.125\dimen@
      \advance\dimen@\ht\z@ \advance\dimen@\dp\z@
      \advance\dimen@-\dp\tw@ \divide\dimen@ 5\relax
      \ifdim\dimen@>\z@
         \@tempdima\dimen@ \ifdim\@tempdima<\tw@\p@ \@tempdima\tw@\p@ \fi
         \advance\dimen@.1\p@
         \advance\dimen@-\@tempdima \@tempdimb5\dimen@
         \edef\@tempa{%
            \kern\the\dimen@
            \raise\the\@tempdimb
            \hbox{\noexpand\line(1,5){\strip@pt\@tempdima}}}%
      \else
         \let\@tempa\@empty
      \fi
      \@tempdima\dp\tw@ \advance\@tempdima-\dp\z@
      \advance\@tempdima-\ht\tw@
      \setbox\tw@\hbox{%
         \unitlength\p@
         \box\tw@
         \@tempa}%
      \raise\@tempdima\box\tw@\nobreak\overline{\box\z@}%
   \else
      {#1\sqrtsign{#2}}%
   \fi}
\def\@noadjust@makesqrt#1#2{{#1\sqrtsign{#2}}}
\let\@makesqrt\@@makesqrt
\DeclareMathSymbol\fixedsqrtsign\mathord{largesymbols}{'163}
%
%%% some abbreviations
\def\LETTERLABEL{{\LARGE  Letter} \\ [8pt] }
\def\REVIEWLABEL{{\LARGE  Review} \\ [8pt]}
\def\arcdeg{\ensuremath{{}^{\circ}}}
\let\degree\arcdeg
\def\arcmin{\ensuremath{{}^{\prime}}}
\def\arcsec{\ensuremath{{}^{\prime\prime}}}
\def\farcm@mss{\ensuremath{.\mkern-4mu{}^{\prime}}}%
\let\farcm\farcm@mss
\def\farcs@mss{\ensuremath{.\!\!{}^{\prime\prime}}}%
\let\farcs\farcs@mss
\def\fp{\ensuremath{.\!\!^{\scriptscriptstyle\mathrm{p}}}%
   \ambiguouswarn{fp}{timeform}}
\def\fd{\ensuremath{.\!\!^{\mathrm{d}}}\ambiguouswarn{fd}{timeform}}
\def\fh{\ensuremath{.\!\!^{\mathrm{h}}}\ambiguouswarn{fh}{timeform}}
\def\fm{\ensuremath{.\!\!^{\mathrm{m}}}\ambiguouswarn{fs}{timeform}}
\def\fs{\ensuremath{.\!\!^{\mathrm{s}}}\ambiguouswarn{fm}{timeform}}
\def\fdg{\ensuremath{.\!\!^{\circ}}\ambiguouswarn{fdg}{timeform}}
\def\ubvr{\mbox{$U\!BV\!R$}\ambiguouswarn{ubvr}{ensuremath{UBVR}}}
\def\ub{\mbox{$U\!-\!B$}\ambiguouswarn{ub}{ensuremath{U-B}}}
\def\bv{\mbox{$B\!-\!V$}\ambiguouswarn{bv}{ensuremath{B-V}}}
\def\vr{\mbox{$V\!-\!R$}\ambiguouswarn{vr}{ensuremath{V-R}}}
\def\ur{\mbox{$U\!-\!R$}\ambiguouswarn{ur}{ensuremath{U-R}}}
\def\onehalf{\ensuremath{\frac{1}{2}}}
\def\onethird{\ensuremath{\frac{1}{3}}}
\def\twothirds{\ensuremath{\frac{2}{3}}}
\def\onequarter{\ensuremath{\frac{1}{4}}}
\def\threequarters{\ensuremath{\frac{3}{4}}}
\def\micron{\ensuremath{\mu\mathrm{m}}}
\DeclareRobustCommand\ambiguouswarn[2]{%
   \typeout{\@@lineno Warning [pasj]: ^^J\@spaces
The use of ambiguous command `\@backslashchar#1' is not recommended.^^J%
\@spaces Use `\@backslashchar#2' in place of `\@backslashchar#1'.}}
%
%%% timeform
\DeclareRobustCommand\timeform[1]{\@timeform\timeform{#1}}
\DeclareRobustCommand\TF[1]{\@timeform\TF{#1}}
\def\@timeform#1#2{{%
   \def\@timeform@csname{#1}%
   \begingroup
   \def\circ{D}\def\deg{D}\def\prime{'}%
   \let\rm\@empty \let\mathrm\@empty
   \let~\@empty
   \def\pm{\@other@tilde P}%
   \def\mp{\@other@tilde M}%
   \let\protect\noexpand
   \edef\@tempa{\def\noexpand\@tempb{#2}}%
   \expandafter\endgroup\@tempa
   \@onelevel@sanitize\@tempb
   \let\@tempa\@empty
   \expandafter\@timeform@preprocess\@tempb\@nil
   \let\@timeform@body\@empty
   \let\@timeform@prevdigits\@empty
   \let\@timeform@lastdigits\@empty
   \let\@timeform@lastunit\@empty
   \@chclass\m@ne
   \@lastchclass\m@ne
   \let\@templist\@empty
   \let\protect\@unexpandable@protect
   \expandafter\@timeform@loop@\@tempa\@nil
   \ifx\@timeform@lastunit\@empty \def\@timeform@lastunit{\ }\fi
   \let\protect\relax
   \@timeform@body}}
\def\@timeform@preprocess#1{%
   \def\@tempb{#1}%
   \ifx\@tempb\@nnil\else
      \if \@charlb#1\relax \let\@tempb\@empty \fi
      \if \@charrb#1\relax \let\@tempb\@empty \fi
      \if ^#1\relax        \let\@tempb\@empty \fi
      \edef\@tempa{\@tempa\@tempb}%
      \expandafter\@timeform@preprocess
   \fi}
\begingroup
\catcode`\~=12
\def\x{\def\@other@tilde{~}}
\expandafter\endgroup\x
\def\@timeform@loop@#1{%
   \ifnum\@chclass=\z@ \ifx\@currchar\@empty\else
      \typeout{%
         \@@lineno Warning [pasj]: Invalid character `\@currchar' in
         \expandafter\string\@timeform@csname.}%
   \fi\fi
   \def\@currchar{#1}%
   \@timeform@check@char
   \@timeform@loop}
\def\@timeform@loop{%
   \ifnum\@chclass<\z@
      \ifx\@timeform@prevdigits\@empty
         \let\@tempa\@timeform@lastdigits
      \else
         \toks@\expandafter{\@timeform@lastunit}%
         \edef\@tempa{%
            \@timeform@prevdigits
            \noexpand\@timeform@unit{\the\toks@}%
            \@timeform@lastdigits}%
      \fi
      \@csc@t\@timeform@body\@timeform@body\@tempa
   \else
      \expandafter\expandafter
      \csname @timeform@loop@\romannumeral\@chclass\endcsname
   \fi}
\def\@timeform@check@char{%
   \ifx\@currchar\@nnil
      \@chclass\m@ne
   \else
      \expandafter\count@\expandafter=\expandafter`\@currchar\relax
      \@chclass\z@
      \ifnum`0>\count@\else \ifnum`9<\count@\else
         \@chclass\@ne
      \fi\fi
      \if +\@currchar\relax
         \@chclass\@ne
         \def\@currchar{\protect\ensuremath{+}}%
      \fi
      \if -\@currchar\relax
         \@chclass\@ne
         \def\@currchar{\protect\ensuremath{-}}%
      \fi
      \if D\@currchar\relax \@chclass\tw@ \def\@currchar{\circ}\fi
      \if d\@currchar\relax \@chclass\tw@ \fi
      \if h\@currchar\relax \@chclass\tw@ \fi
      \if m\@currchar\relax \@chclass\tw@ \fi
      \if p\@currchar\relax
         \@chclass\tw@
         \def\@currchar{\scriptscriptstyle p}%
      \fi
      \if s\@currchar\relax \@chclass\tw@ \fi
      \if '\@currchar\relax \@chclass\thr@@ \fi
      \if "\@currchar\relax \@chclass\thr@@ \fi
      \if .\@currchar\relax \@chclass4\relax \fi
      \if \@other@tilde\@currchar\relax \@chclass5\relax \fi
   \fi}
\def\@timeform@loop@i#1{%
   \edef\@templist{\@templist\@currchar}%
   \def\@currchar{#1}%
   \@timeform@check@char
   \ifnum\@chclass<\z@
      \ifx\@timeform@lastdigits\@empty
         \let\@tempa\@templist
      \else
         \toks@\expandafter{\@timeform@lastunit}%
         \edef\@tempa{%
            \@timeform@lastdigits
            \noexpand\@timeform@unit{\the\toks@}%
            \@templist}%
      \fi
      \@csc@t\@timeform@body\@timeform@body\@tempa
      \let\@timeform@next\relax
   \else
      \ifnum\@chclass=\@ne
         \def\@timeform@next{\@timeform@loop@i}%
      \else
         \@lastchclass\@ne
         \ifnum 5=\@chclass\else
            \let\@timeform@prevdigits\@timeform@lastdigits
            \let\@timeform@lastdigits\@templist
            \let\@templist\@empty
         \fi
         \def\@timeform@next{\@timeform@loop}%
      \fi
   \fi
   \@timeform@next}
\def\@timeform@loop@ii#1{%
   \ifx\@timeform@lastunit\@empty\else
      \ifnum\@lastchclass=\tw@
         \toks@\expandafter{\@timeform@lastunit}%
         \edef\@tempa{%
            \@timeform@lastdigits
            \noexpand\@timeform@unit{\the\toks@}}%
         \let\@timeform@lastdigits\@empty
      \else
         \toks@\expandafter{\@timeform@lastunit}%
         \edef\@tempa{%
            \@timeform@prevdigits
            \noexpand\@timeform@unit{\the\toks@}}%
         \let\@timeform@prevdigits\@empty
      \fi
      \@csc@t\@timeform@body\@timeform@body\@tempa
   \fi
   \let\@timeform@lastunit\@currchar
   \def\@currchar{#1}%
   \@timeform@check@char
   \ifnum\@chclass<\z@
      \edef\@tempa{%
         \@timeform@lastdigits
         \noexpand\@timeform@unit{\noexpand\@timeform@lastunit}}%
      \@csc@t\@timeform@body\@timeform@body\@tempa
   \else
      \@lastchclass\tw@
      \expandafter\@timeform@loop
   \fi}
\def\@timeform@loop@iii#1{%
   \ifnum\@lastchclass=\thr@@
      \if\@currchar'\relax \def\@tempa{\prime}%
      \else                \def\@tempa{\prime\prime}%
      \fi
      \@csc@t\@templist\@templist\@tempa
   \else
      \ifnum\@lastchclass=\tw@
         \toks@\expandafter{\@timeform@lastunit}%
         \edef\@tempa{%
            \@timeform@lastdigits
            \noexpand\@timeform@unit{\the\toks@}}%
         \let\@timeform@lastdigits\@empty
         \let\@timeform@lastunit\@empty
         \@csc@t\@timeform@body\@timeform@body\@tempa
      \fi
      \if\@currchar'\relax
         \def\@templist{\prime}%
      \else
         \def\@templist{\prime\prime}%
      \fi
   \fi
   \def\@currchar{#1}%
   \@timeform@check@char
   \@lastchclass=\thr@@
   \ifnum\@chclass=\thr@@
      \def\@timeform@next{\@timeform@loop@iii}%
   \else
      \let\@currchar\@templist
      \let\@templist\@empty
      \def\@timeform@next{\@timeform@loop@ii#1}%
   \fi
   \@timeform@next}
\def\@timeform@loop@iv#1{%
   \ifx\@timeform@prevdigits\@empty
      \edef\@tempa{%
         \@timeform@lastdigits
         \noexpand\@timeform@dot}%
   \else
      \toks@\expandafter{\@timeform@lastunit}%
      \edef\@tempa{%
         \@timeform@prevdigits
         \noexpand\@timeform@unit{\the\toks@}%
         \@timeform@lastdigits
         \noexpand\@timeform@dot}%
      \let\@timeform@lastunit\@empty
   \fi
   \@csc@t\@timeform@body\@timeform@body\@tempa
   \let\@timeform@prevdigits\@empty
   \let\@timeform@lastdigits\@empty
   \def\@currchar{#1}%
   \@timeform@check@char
   \ifnum\@chclass<\z@\else
      \@lastchclass4\relax
      \expandafter\@timeform@loop
   \fi}
\def\@timeform@loop@v#1{%
   \def\@currchar{#1}%
   \ifx\@currchar\@nnil
      \ifx\@timeform@lastdigits\@empty
         \let\@tempa\@templist
      \else
         \toks@\expandafter{\@timeform@lastunit}%
         \edef\@tempa{%
            \@timeform@lastdigits
            \noexpand\@timeform@unit{\the\toks@}%
            \@templist}%
      \fi
      \@csc@t\@timeform@body\@timeform@body\@tempa
      \let\@timeform@next\relax
   \else
      \expandafter\ifx\csname @timeform@cmdlist@\@currchar\endcsname\relax
         \let\@currchar\@empty
      \else
         \edef\@currchar{%
            \noexpand\protect\expandafter\noexpand
            \csname @timeform@cmdlist@\@currchar\endcsname}%
      \fi
      \def\@timeform@next{\@timeform@loop}%
      \@lastchclass\@ne
      \@chclass\@ne
   \fi
   \@timeform@next}
\def\@timeform@cmdlist@P{\ensuremath{\pm}}
\def\@timeform@cmdlist@M{\ensuremath{\mp}}
\def\@timeform@unit#1{%
   \ensuremath{%
      \mathchoice
         {\@timeform@unit@\scriptstyle{#1}}%
         {\@timeform@unit@\scriptstyle{#1}}%
         {\@timeform@unit@\scriptscriptstyle{#1}}%
         {\@timeform@unit@\scriptscriptstyle{#1}}}}
\def\@timeform@unit@#1#2{%
   \setbox\z@\hbox{$\m@th#1\mathrm{#2}$}%
   \setbox\tw@\hbox{$\m@th#1\mathrm{m}$}%
   \dimen@\ht\tw@ \advance\dimen@-\ht\z@
   \ifdim\dimen@<\z@ \dimen@\z@ \fi
   {}^{\raise\dimen@\box\z@}}
\def\@timeform@dot{%
   \ensuremath{%
      \mathchoice
         {\@timeform@dot@\displaystyle\scriptstyle}%
         {\@timeform@dot@\textstyle\scriptstyle}%
         {\@timeform@dot@\scriptstyle\scriptscriptstyle}%
         {\@timeform@dot@\scriptscriptstyle\scriptscriptstyle}}%
   \def\@timeform@lastunit{}}
\def\@timeform@dot@#1#2{%
   \rlap{$\m@th#1.$}%
   \mkern1mu\@timeform@unit@#2{\@timeform@lastunit}}
\def\contentsname{Contents}
\def\papersname{Papers}
\def\lettersname{Letters}
\def\errataname{Errata}
\def\listfigurename{List of Figures}
\def\listtablename{List of Tables}
\def\bibname{References}
\def\indexname{Index}
\def\figurename{Fig.}
\def\tablename{Table}
\def\partname{Part}
\def\chaptername{Chapter}
\def\appendixname{Appendix}
\def\abstractname{Abstract}
\def\today{%
   \number\year~%
   \ifcase\month\or
      January\or February\or March\or     April\or   May\or      June\or
      July\or    August\or   September\or October\or November\or December\fi
   ~\number\day}
\def\re{%
   \par
   \hangindent=5mm
   \hangafter=1
   \noindent}
%
%%% fleqn
\def\[{\relax
   \ifmmode\@badmath\else
   \begin{trivlist}%
   \@beginparpenalty\predisplaypenalty
   \@endparpenalty\postdisplaypenalty
   \item[]\leavevmode
      \hbox to\linewidth\bgroup $\m@th\displaystyle %$
         \hskip\mathindent\bgroup
   \fi}
\def\]{\relax
   \ifmmode
      \egroup $\hfil% $
      \egroup
      \end{trivlist}%
   \else
      \@badmath
   \fi}
\def\equation{%
   \@beginparpenalty\predisplaypenalty
   \@endparpenalty\postdisplaypenalty
   \refstepcounter{equation}%
   \trivlist \item[]\leavevmode
   \hbox to\linewidth\bgroup $\m@th% $
      \displaystyle
      \hskip\mathindent}%
\def\endequation{$\hfil % $
      \displaywidth\linewidth\hbox{\@eqnnum}%
   \egroup
   \endtrivlist}
\def\eqnarray{%
   \stepcounter{equation}%
   \def\@currentlabel{\p@equation\theequation}%
   \global\@eqnswtrue\m@th
   \global\@eqcnt\z@
   \tabskip\mathindent
   \let\\=\@eqncr
   \setlength\abovedisplayskip{\topsep}%
   \ifvmode
      \addtolength\abovedisplayskip{\partopsep}%
   \fi
   \addtolength\abovedisplayskip{\parskip}%
   \setlength\belowdisplayskip{\abovedisplayskip}%
   \setlength\belowdisplayshortskip{\abovedisplayskip}%
   \setlength\abovedisplayshortskip{\abovedisplayskip}%
   $$\everycr{}\halign to\linewidth% $$
   \bgroup
      \hskip\@centering
      $\displaystyle\tabskip\z@skip{##}$\@eqnsel&%
      \global\@eqcnt\@ne
      \hfil$\displaystyle{{}##{}}$\hfil&%
      \global\@eqcnt\tw@
      $\displaystyle{##}$\hfil \tabskip\@centering&%
      \global\@eqcnt\thr@@
      \hbox to\z@\bgroup\hss##\egroup\tabskip\z@skip\cr}%
\def\endeqnarray{%
      \@@eqncr
   \egroup
   \global\advance\c@equation\m@ne$$% $$
   \@ignoretrue}
\def\DeclareAbbreviation#1#2{%
   \DeclareRobustCommand*#1{\@journalname{#2}}}
\def\@journalname#1{{\normalfont#1}}
\DeclareAbbreviation\aj{AJ}
\DeclareAbbreviation\araa{ARA\&A}
\DeclareAbbreviation\apj{ApJ}
\DeclareAbbreviation\apjl{ApJL}
\DeclareAbbreviation\apjs{ApJS}
\DeclareAbbreviation\ao{Appl.\ Opt.}
\DeclareAbbreviation\apss{Ap\&SS}
\DeclareAbbreviation\aap{A\&A}
\DeclareAbbreviation\aapr{A\&AR}
\DeclareAbbreviation\aaps{A\&AS}
\DeclareAbbreviation\azh{AZh}
\DeclareAbbreviation\baas{BAAS}
\DeclareAbbreviation\jrasc{JRASC}
\DeclareAbbreviation\memras{MmRAS}
\DeclareAbbreviation\mnras{MNRAS}
\DeclareAbbreviation\pra{Phys.\ Rev.\ A}
\DeclareAbbreviation\prb{Phys.\ Rev.\ B}
\DeclareAbbreviation\prc{Phys.\ Rev.\ C}
\DeclareAbbreviation\prd{Phys.\ Rev.\ D}
\DeclareAbbreviation\pre{Phys.\ Rev.\ E}
\DeclareAbbreviation\prl{Phys.\ Rev.\ Lett.}
\DeclareAbbreviation\pasp{PASP}
\DeclareAbbreviation\pasj{PASJ}
\DeclareAbbreviation\qjras{QJRAS}
\DeclareAbbreviation\raa{Res.\ Astron.\ Astronphys.}
\DeclareAbbreviation\skytel{S\&T}
\DeclareAbbreviation\solphys{Sol.\ Phys.}
\DeclareAbbreviation\sovast{Soviet\ Ast.}
\DeclareAbbreviation\ssr{Space\ Sci.\ Rev.}
\DeclareAbbreviation\zap{ZAp}
\DeclareAbbreviation\nat{Nature}
\DeclareAbbreviation\iaucirc{IAU\ Circ.}
\DeclareAbbreviation\aplett{Astrophys.\ Lett.}
\DeclareAbbreviation\apspr{Astrophys.\ Space\ Phys.\ Res.}
\DeclareAbbreviation\bain{Bull.\ Astron.\ Inst.\ Netherlands}
\DeclareAbbreviation\fcp{Fund.\ Cosmic\ Phys.}
\DeclareAbbreviation\gca{Geochim.\ Cosmochim.\ Acta}
\DeclareAbbreviation\grl{Geophys.\ Res.\ Lett.}
\DeclareAbbreviation\jcp{J.\ Chem.\ Phys.}
\DeclareAbbreviation\jgr{J.\ Geophys.\ Res.}
\DeclareAbbreviation\jqsrt{J.\ Quant.\ Spectrosc.\ Radiat.\ Transfer}
\DeclareAbbreviation\memsai{Mem.\ Soc.\ Astron.\ Italiana}
\DeclareAbbreviation\nphysa{Nucl.\ Phys.\ A}
\DeclareAbbreviation\physrep{Phys.\ Rep.}
\DeclareAbbreviation\physscr{Phys.\ Scr.}
\DeclareAbbreviation\planss{Planet.\ Space\ Sci.}
\DeclareAbbreviation\procspie{Proc.\ SPIE}
\DeclareAbbreviation\aip{AIP Conf.\ Proc.}
\DeclareAbbreviation\asp{ASP Conf.\ Ser.}
\let\astap=\aap
\let\apjlett=\apjl
\let\apjsupp=\apjs
\let\applopt=\ao
%
%%% about graphics
\def\RelativeFigurePath#1{%
   \def\@figurepath{#1}%
   \ifx\@figurepath\@empty \def\@figurepath{.}\fi}
\RelativeFigurePath{}
\def\FigureFile{\@ifstar\@FigureFile\@FigureFile}
\def\@FigureFile(#1,#2)#3{%
   \def\@figfilename{#3}%
   \@onelevel@sanitize\@figfilename
   \begingroup
   \if@pasj@usefigure
      \edef\@@figfilename{\@figurepath/\@figfilename}%
      \openin\@inputcheck \@@figfilename\relax
      \ifeof\@inputcheck
         \typeout{No file `\@@figfilename'.}%
         \let\@@figfilename\@empty
      \fi
      \closein\@inputcheck
   \else
      \let\@@figfilename\@empty
   \fi
   \ifx\@@figfilename\@empty
      \@defaultunits\@tempdima#1mm\relax\@nnil
      \@defaultunits\@tempdimb#2mm\relax\@nnil
      \edef\@tempa{(\strip@pt\@tempdima,\strip@pt\@tempdimb)}%
      \edef\@tempa{%
         \begingroup
         \unitlength\p@
         \noexpand\begin{picture}\@tempa
           \noexpand\put(0,0){\noexpand\@framepicbox\@tempa[c]{%
              \noexpand\footnotesize
              \noexpand\texttt{\@figfilename}}}%
         \noexpand\end{picture}%
         \endgroup}%
   \else
      \@defaultunits\@tempdima#1mm\relax\@nnil
      \@tempdima.35146\@tempdima %%% 1pt = .35146mm
      \edef\@tempa{%
         \noexpand\@saved@includegraphics
            [width=\strip@pt\@tempdima mm,keepaspectratio]%
            {\@@figfilename}}%
   \fi
   \noindent
   \vtop{\kern.5\baselineskip\hbox{\@tempa}}%
   \endgroup}
\if@pasj@usefigure
\RequirePackage[]{graphicx,color}
\let\@saved@includegraphics\includegraphics
%\def\includegraphics{%
%   \typeout{Do not use \string\includegraphics\space directly.
%            Use \string\FigureFile\space for graphics.}%
%   \@saved@includegraphics}
\else
\let\@saved@includegraphics\relax
\fi
\predisplaypenalty\z@
\postdisplaypenalty\z@
\uchyph = 0
\interdisplaylinepenalty\z@
\RequirePackage{latexsym}
\thinmuskip  = 2mu plus 1mu minus 1mu
\medmuskip   = 3mu plus 1mu minus 2mu
\thickmuskip = 4mu plus 2mu minus 2mu
\clubpenalty\@lowpenalty
\widowpenalty\@lowpenalty
\pagestyle{headings}
\pagenumbering{arabic}
\if@twocolumn \twocolumn \else \onecolumn \fi
\AtBeginDocument{\sloppy}
\if@proofread \draft \fi
%%%%%
\def\rhfont{\fontfamily{\sfdefault}\fontsize{8}{12}\selectfont\raggedleft}
\def\titlefont{\fontfamily{\sfdefault}\fontsize{18}{23}\selectfont\bfseries\rightskip6pc plus1fill}
\def\authorfont{\fontfamily{\sfdefault}\fontsize{12}{15}\selectfont\bfseries\rightskip6pc plus1fill}%
\def\affilfont{\reset@font\fontfamily{\sfdefault}\fontsize{10}{13}\selectfont\rightskip6pc plus1fill}%
\def\corfont{\reset@font\fontfamily{\sfdefault}\fontsize{8.5}{12}\selectfont\rightskip6pc plus1fill}%
\def\historyfont{\reset@font\fontfamily{\sfdefault}\fontsize{7}{10}\selectfont\rightskip6pc plus1fill}%
\def\abstractfont{\fontfamily{\sfdefault}\fontsize{10}{13.25}\selectfont\rightskip6pc}
\def\keywordfont{\fontfamily{\sfdefault}\fontsize{9}{12}\selectfont\rightskip6pc}
\def\abstractheadfont{\fontfamily{\sfdefault}\fontsize{11.5}{13}\selectfont\bfseries}
\def\keywordheadfont{\fontfamily{\sfdefault}\fontsize{9}{12}\selectfont\bfseries}
\def\rffont{\fontfamily{\sfdefault}\fontsize{7}{10}\selectfont}
%%
\def\sectionfont{\fontfamily{\sfdefault}\fontsize{11}{13}\selectfont\bfseries\rightskip0pt plus1fill}
\def\subsectionfont{\fontfamily{\sfdefault}\fontsize{10}{13}\selectfont\rightskip0pt plus1fill}
\def\subsubsectionfont{\fontsize{9.25}{13}\selectfont\bfseries}
\def\paragraphfont{\fontsize{9.25}{13}\selectfont\itshape}%
\def\subparagraphfont{\fontfamily{\sfdefault}\fontsize{9.25}{13}\selectfont}%
\def\extractfont{\reset@font\fontfamily{\rmdefault}\fontsize{8.75}{12.5}\selectfont\leftskip12pt\rightskip12pt}
\def\figcaptionfont{\fontfamily{\sfdefault}\fontsize{7}{10.25}\selectfont}
\def\figcaptionnumfont{\fontfamily{\sfdefault}\fontsize{7}{10.25}\selectfont\bfseries}
\def\bibliofont{\fontfamily{\rmdefault}\if@proofread\fontsize{11}{13}\else\fontsize{8}{11.5}\fi\selectfont}
%%
\newskip\tableleftskip
\newskip\tablerightskip
\newskip\tablenoteleftskip
\newskip\tablenoterightskip
%%
\def\tablefont{\fontsize{8}{11.5}\selectfont}%
\def\tablecaptionfont{\fontfamily{\sfdefault}\fontsize{8.2}{13}\selectfont\leftskip\tableleftskip\rightskip\tablerightskip}% 
\def\tablecaptionnumfont{\fontfamily{\sfdefault}\fontsize{8.2}{13}\selectfont\bfseries}% 
\def\TCHfont{\fontsize{8}{10}\selectfont}%
\def\TSCHfont{}%
\def\tabnotefont{\fontsize{7}{10}\selectfont\hangindent.1pt\leftskip\tableleftskip\rightskip\tablerightskip}% use plus 1fill if needed
\def\rhhfont{\fontfamily{\sfdefault}\fontsize{8}{12}\selectfont\raggedleft}
\def\foliofont{\fontfamily{\sfdefault}\fontsize{8}{10}\selectfont\bfseries}
%%
\newbox\tempbox
\newdimen\tabledim%
\def\tbl#1#2{%
\setbox\tempbox\hbox{\tablefont#2}%
 \tabledim\hsize
  \advance\tabledim-\wd\tempbox
  \ifdim\tabledim>0pt
     \divide\tabledim2
  \else
     \global\tabledim0pt
  \fi
   \global\tableleftskip\tabledim%%Call Id:390490
   \global\tablerightskip\tabledim plus1fill%%Call Id:390490
  \caption{#1}%
  {\centerline{\box\tempbox}}}%
%%
\renewenvironment{quotation}{\par\addvspace{3.4pt plus2pt}%
      \extractfont\ignorespaces% 
}{%
      \par\addvspace{3.1pt plus2pt}}
%%
\newenvironment{tabnote}{\par\vskip3pt\tabnotefont}{\par}
%%%
\def\jyear#1{\gdef\@jyear{#1}}\jyear{2018}
\def\endpage#1{\gdef\@endpage{#1}}\endpage{0}
\def\doi#1{\gdef\@doi{doi:\ 10.1093/pasj/#1}}\doi{xxx000}
\def\volume#1{\gdef\@jvol{#1}}\volume{00}
\def\Issue#1{\gdef\@Issue{#1}}\Issue{0}
\AtEndDocument{\immediate\write\@mainaux{\string\endpage{\thepage}}}%
\setlength\footskip{20pt}%{24pt}
\setlength{\skip\footins}{12\p@ \@plus 6\p@ \@minus 6\p@}% change + based on FN font height
\newenvironment{ack}{\section*{Acknowledgments}\fontsize{8}{11}\selectfont}{\par}
%%% typeset with Computer Modern for estimating page in length.
\renewcommand{\sfdefault}{phv}%{cmss} %
\renewcommand{\rmdefault}{cmr} %{ptm}
%%\usepackage{txfonts}
\renewcommand{\ttdefault}{cmtt}

%%\raggedbottom
%% ===========================
\AtBeginDocument{\@ifpackageloaded{natbib}{%
\def\bibfont{\bibliofont}\renewcommand\bibsection{\section{\refname}}%
\def\NAT@parse@date#1#2#3#4#5#6@@{%
  \ifnum\the\catcode`#1=11\def\NAT@year{}\def\NAT@exlab{#1}\else
  \ifnum\the\catcode`#2=11\def\NAT@year{#1}\def\NAT@exlab{#2}\else
  \ifnum\the\catcode`#3=11\def\NAT@year{#1#2}\def\NAT@exlab{#3}\else
  \ifnum\the\catcode`#4=11\def\NAT@year{#1#2#3}\def\NAT@exlab{#4}\else
  \def\NAT@year{#1#2#3#4}\def\NAT@exlab{{#1#2#3#4#5}}\fi\fi\fi\fi}
  \renewcommand\NAT@yrsep{,\space}
  \renewcommand\NAT@aysep{}
}{}}
%%
\typeout{ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! }
\typeout{  For LETTER article, be sure to compile with  "Computer Modern (defalt font)".  }
\typeout{  fonts to estimate page numbers. Do NOT use "Times" font. }
\typeout{  (defalt font setting in pasj01.cls: Computer Modern)  } 
\typeout{ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! } 
%%
\endinput
%%
%% End of file `pasj01.cls'.
