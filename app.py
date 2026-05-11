import streamlit as st
import anthropic
import os
import base64
import io
from dotenv import load_dotenv
from PIL import Image
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

load_dotenv()
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── System Prompts ───────────────────────────────────────────────

INTERVIEW_SYSTEM_PROMPT = """你是一位資深軟體專案需求分析師，正在協助 PM 進行即時需求訪談。
PM 會描述客戶剛說的需求，可能很簡短或不完整。
請快速分析，輸出以下三個部分，每個部分用指定標記包起來，不要加其他說明：

[AMBIGUOUS_START]
・（第一個模糊點）
・（第二個模糊點）
（共 2~4 條，每條一行，簡短）
[AMBIGUOUS_END]

[ISSUES_START]
・（第一個潛在問題）
・（第二個潛在問題）
（共 2~4 條，每條一行，簡短）
[ISSUES_END]

[QUESTIONS_START]
・（第一個追問問題，用問句）
・（第二個追問問題，用問句）
（共 3~5 條，每條一行，可直接開口問）
[QUESTIONS_END]

規則：每條都要簡短（一行以內）、具體、可直接在訪談中使用。用繁體中文。"""

SRS_SYSTEM_PROMPT = """你是一位資深的軟體專案需求分析師。使用者會提供需求訪談的筆記或逐字稿，內容可能雜亂、口語化或不完整。
請從中整理出結構化的需求文件，輸出以下六個部分，用指定標記包起來，不要加其他說明：

[FUNC_DESC_START]
（2~4 句話說明功能目的與範圍，語氣正式）
[FUNC_DESC_END]

[USER_STORY_START]
（「身為＿＿，我希望能夠＿＿，以便＿＿」格式，一段完整句子）
[USER_STORY_END]

[AC_START]
條件之間空一行，必須含 1~2 條異常或邊界情境：

條件 1
前提：xxx
操作：xxx
預期結果：xxx

（共 3~6 條）
[AC_END]

[NFR_START]
每條一行，以「・」開頭，只列訪談中有明確提到的面向（效能、權限、安全性、相容性等）。若無，輸出「・無明確提及」：
[NFR_END]

[PENDING_START]
每條一行，以「・」開頭，列出訪談中未明確定義、需向業主或使用者追問的問題：
[PENDING_END]

[RISK_START]
每條一行，以「・」開頭，格式：風險描述（嚴重程度：高／中／低）：
[RISK_END]

規則：
- 只從訪談筆記中提取，不自行添加沒有提到的需求
- 資訊不足的部分標注「資訊不足，待補充」
- 用繁體中文，語氣正式"""

# ── Image Loading ────────────────────────────────────────────────

def _load_img(filename):
    path = os.path.join(os.path.dirname(__file__), filename)
    with open(path, "rb") as f:
        return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"

PARROT_SRC  = _load_img("parrot1.png")
PARROT_SRC2 = _load_img("parrot2.png")
PARROT_SRC3 = _load_img("parrot3.png")

_parrot_icon = Image.open(os.path.join(os.path.dirname(__file__), "parrot1.png"))
st.set_page_config(page_title="需求分析工具", page_icon=_parrot_icon, layout="centered", initial_sidebar_state="collapsed")

# ── CSS ──────────────────────────────────────────────────────────

st.markdown("""<style>
:root {
    --blue:#007AFF;--blue-hover:#0071E3;--blue-pressed:#0062CC;
    --blue-tint:rgba(0,122,255,0.10);--green:#34C759;--red:#FF3B30;--orange:#FF9500;
    --bg:#F2F2F7;--card:#FFFFFF;--label:#1C1C1E;--label-2:#6E6E73;--label-3:#AEAEB2;--sep:#E5E5EA;
    --r-md:12px;--r-lg:16px;
    --shadow:0 2px 8px rgba(0,0,0,0.07),0 0 1px rgba(0,0,0,0.05);
    --font:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Helvetica Neue",Arial,sans-serif;
}
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"],.stApp{background-color:var(--bg)!important;font-family:var(--font)!important;color:var(--label)!important;-webkit-font-smoothing:antialiased;}
[data-testid="stHeader"]{background-color:var(--bg)!important;border-bottom:1px solid var(--sep)!important;}
[data-testid="stMain"]{background-color:var(--bg)!important;}
[data-testid="stMainBlockContainer"],.block-container{padding-top:3.5rem!important;padding-bottom:4rem!important;max-width:700px!important;}
label,[data-testid="stWidgetLabel"] p{font-family:var(--font)!important;font-size:16px!important;font-weight:600!important;color:var(--label-2)!important;letter-spacing:0.03em!important;text-transform:uppercase!important;margin-bottom:6px!important;}
[data-testid="stTextArea"] textarea{font-family:var(--font)!important;font-size:18px!important;line-height:1.65!important;color:var(--label)!important;background-color:var(--card)!important;border:1.5px solid var(--sep)!important;border-radius:var(--r-md)!important;padding:14px 16px!important;box-shadow:none!important;transition:border-color 200ms ease,box-shadow 200ms ease!important;}
[data-testid="stTextArea"] textarea::placeholder{color:var(--label-3)!important;}
[data-testid="stTextArea"] textarea:focus,[data-testid="stTextArea"] div:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="base-input"]:focus-within{border-color:var(--blue)!important;box-shadow:0 0 0 3px var(--blue-tint)!important;outline:none!important;}
*:focus-visible{outline:2px solid var(--blue)!important;outline-offset:2px!important;}
[data-testid="stButton"]>button{font-family:var(--font)!important;font-size:18px!important;font-weight:800!important;color:#FFFFFF!important;background-color:var(--blue)!important;border:none!important;border-radius:980px!important;padding:13px 24px!important;letter-spacing:0.01em!important;box-shadow:0 1px 4px rgba(0,122,255,0.28)!important;transition:background-color 150ms ease,transform 100ms ease,box-shadow 150ms ease!important;}
[data-testid="stButton"]>button:hover{background-color:var(--blue-hover)!important;box-shadow:0 3px 12px rgba(0,122,255,0.32)!important;}
[data-testid="stButton"]>button:active{background-color:var(--blue-pressed)!important;transform:scale(0.975)!important;}
[data-testid="stAlert"]{border-radius:var(--r-md)!important;font-family:var(--font)!important;font-size:17px!important;}
[data-testid="stSuccess"]{background-color:rgba(52,199,89,0.10)!important;border-left:4px solid var(--green)!important;color:#1a5c2e!important;}
[data-testid="stWarning"]{background-color:rgba(255,149,0,0.10)!important;border-left:4px solid var(--orange)!important;color:#7a4800!important;}
[data-testid="stError"]{background-color:rgba(255,59,48,0.08)!important;border-left:4px solid var(--red)!important;color:#8b1a15!important;}
[data-testid="stSpinner"] p{color:var(--label-2)!important;font-family:var(--font)!important;font-size:17px!important;}
hr{border:none!important;border-top:1px solid var(--sep)!important;margin:1rem 0!important;}
.hero{display:flex;align-items:center;gap:20px;padding:0.5rem 0 0.6rem;}
.hero-parrot{height:120px;width:auto;object-fit:contain;flex-shrink:0;filter:drop-shadow(0 4px 12px rgba(0,0,0,0.15));}
.hero-text{flex:1;}
.hero-text h1{font-size:41px;font-weight:700;color:var(--label);margin:0 0 4px 0;letter-spacing:-0.03em;line-height:1.15;}
.hero-text p{font-size:20px;color:var(--label-2);margin:0;line-height:1.45;}
.section-label{display:flex;align-items:center;gap:8px;margin-bottom:10px;}
.step-dot{width:22px;height:22px;border-radius:50%;background:var(--blue);color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.section-label-text{font-size:16px;font-weight:600;color:var(--label);}
.output-preview{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0 20px;}
.preview-hint{font-size:14px;color:var(--label-3);font-weight:500;}
.preview-chip{display:inline-flex;align-items:center;gap:4px;font-size:14px;font-weight:600;padding:4px 10px;border-radius:980px;}
.chip-blue{background:#EBF3FF;color:#0055CC;}.chip-green{background:#E8F8ED;color:#1a6632;}.chip-orange{background:#FFF4E6;color:#7a4800;}.chip-purple{background:#F2F0FF;color:#4B35A1;}.chip-gray{background:#F2F2F7;color:#6E6E73;}
@keyframes fadeSlideUp{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:translateY(0);}}
.output-card{background:var(--card);border-radius:var(--r-lg);box-shadow:var(--shadow);padding:22px 26px;margin-bottom:16px;border:1px solid rgba(0,0,0,0.04);animation:fadeSlideUp 0.35s ease both;}
.output-card-header{margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--sep);}
.card-badge{display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:700;padding:5px 12px;border-radius:980px;letter-spacing:0.02em;}
.badge-blue{background:#EBF3FF;color:#0055CC;}.badge-green{background:#E8F8ED;color:#1a6632;}.badge-orange{background:#FFF4E6;color:#7a4800;}.badge-purple{background:#F2F0FF;color:#4B35A1;}.badge-gray{background:#F2F2F7;color:#6E6E73;}
.output-card-body{font-family:var(--font);font-size:18px;color:var(--label);line-height:1.78;}
.output-card-body p{margin:0 0 10px 0;}
.output-card-body p:last-child{margin-bottom:0;}
.output-card-body strong,.output-card-body b{font-weight:600;color:var(--label);}
.section-divider{display:flex;align-items:center;gap:12px;margin:24px 0 20px;}
.section-divider-label{font-size:13px;font-weight:700;color:var(--label-3);letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;}
.section-divider-line{flex:1;height:1px;background:var(--sep);}
.loading-overlay{position:fixed;inset:0;background:rgba(242,242,247,0.36);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);z-index:9999;display:flex;align-items:center;justify-content:center;}
.parrot-loading-wrap{background:linear-gradient(white,white) padding-box,linear-gradient(135deg,rgba(0,122,255,0.35),rgba(52,199,89,0.35)) border-box;border:2px solid transparent;border-radius:24px;box-shadow:0 12px 40px rgba(0,0,0,0.14),0 0 1px rgba(0,0,0,0.06),0 0 28px rgba(0,122,255,0.07);padding:2.64rem 3.6rem 2.16rem;text-align:center;display:flex;flex-direction:column;align-items:center;}
.parrot-loading{display:flex;justify-content:center;align-items:flex-end;gap:28px;margin-bottom:1.2rem;}
.loading-parrot{height:96px;width:auto;opacity:0;filter:saturate(1.3) brightness(1.05) drop-shadow(0 2px 6px rgba(0,0,0,0.10));}
.p1{animation:seq1 2.76s steps(1,end) infinite;}
.p2{animation:seq2 2.76s steps(1,end) infinite;}
.p3{animation:seq3 2.76s steps(1,end) infinite;}
@keyframes seq1{0%{opacity:1;}74.9%{opacity:1;}75%{opacity:0;}100%{opacity:0;}}
@keyframes seq2{0%{opacity:0;}24.9%{opacity:0;}25%{opacity:1;}74.9%{opacity:1;}75%{opacity:0;}100%{opacity:0;}}
@keyframes seq3{0%{opacity:0;}49.9%{opacity:0;}50%{opacity:1;}74.9%{opacity:1;}75%{opacity:0;}100%{opacity:0;}}
.loading-text{font-size:17px;color:var(--label-2);font-weight:500;letter-spacing:0.02em;}
.ac-item{display:flex;gap:14px;padding:14px 0;border-bottom:1px solid var(--sep);}
.ac-item:first-child{padding-top:0;}.ac-item:last-child{border-bottom:none;padding-bottom:0;}
.ac-num{font-size:20px;font-weight:700;color:var(--blue);min-width:22px;flex-shrink:0;line-height:1.5;}
.ac-body{flex:1;}
.ac-row{display:flex;align-items:baseline;gap:8px;margin-bottom:5px;}
.ac-row:last-child{margin-bottom:0;}
.ac-label{font-size:13px;font-weight:700;padding:2px 8px;border-radius:980px;letter-spacing:0.04em;flex-shrink:0;text-align:center;line-height:1.7;}
.label-premise{background:#F2F2F7;color:#6E6E73;}.label-action{background:#EBF3FF;color:#0055CC;}.label-result{background:#E8F8ED;color:#1a6632;}
.ac-text{font-size:17px;color:var(--label);line-height:1.65;}
.page-footer{text-align:center;font-size:14px;color:var(--label-3);line-height:1.7;padding:0.5rem 0;}
@media(max-width:640px){.hero h1{font-size:31px!important;}.output-card{padding:18px 20px!important;}[data-testid="stMainBlockContainer"],.block-container{padding-left:1rem!important;padding-right:1rem!important;}}
section[data-testid="stSidebar"]>div:first-child{padding-top:0.8rem!important;}
[data-testid="stSidebar"] [data-testid="stButton"]>button[kind="secondary"]{background:transparent!important;border:none!important;color:var(--label)!important;text-align:left!important;box-shadow:none!important;font-size:13px!important;font-weight:500!important;padding:3px 6px!important;border-radius:4px!important;}
[data-testid="stSidebar"] [data-testid="stButton"]>button[kind="secondary"]:hover{background:rgba(0,0,0,0.05)!important;color:var(--label)!important;box-shadow:none!important;}
[data-testid="stSidebar"] [data-testid="stButton"]>button[kind="primary"]{font-size:13px!important;font-weight:700!important;padding:5px 12px!important;border-radius:980px!important;}
[data-testid="stSidebar"] [data-baseweb="checkbox"] input:checked+div,[data-testid="stSidebar"] [role="checkbox"][aria-checked="true"]{background-color:var(--blue)!important;border-color:var(--blue)!important;}
button[data-baseweb="tab"]{font-weight:600!important;font-size:15px!important;}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--blue)!important;}
button[data-baseweb="tab"][aria-selected="false"]{color:var(--label-2)!important;}
[data-baseweb="tab-highlight"]{background-color:var(--blue)!important;}
[data-baseweb="tab-border"]{background-color:var(--sep)!important;}
[data-testid="stStatusWidget"]{display:none!important;}
</style>""", unsafe_allow_html=True)

# ── Auth ─────────────────────────────────────────────────────────

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("""<style>
    [data-testid="stForm"]{background:#FFFFFF;border-radius:20px;box-shadow:0 2px 8px rgba(0,0,0,0.07),0 0 1px rgba(0,0,0,0.05);border:none!important;padding:3rem 3.5rem 2.8rem;}
    [data-testid="InputInstructions"]{display:none!important;}
    [data-testid="stForm"] [data-baseweb="input"]{border:1.5px solid #BDD7FF!important;border-radius:10px!important;background:#FFFFFF!important;}
    [data-testid="stForm"] [data-baseweb="input"]:focus-within{border-color:var(--blue)!important;box-shadow:0 0 0 3px var(--blue-tint)!important;}
    [data-testid="stForm"] [data-baseweb="input"] input{border:none!important;border-right:none!important;outline:none!important;box-shadow:none!important;}
    [data-testid="stForm"] [data-baseweb="input"]>div{border:none!important;border-left:none!important;background:transparent!important;}
    [data-testid="stForm"] [data-baseweb="input"] button{border:none!important;border-right:none!important;background:transparent!important;box-shadow:none!important;outline:none!important;}
    [data-testid="stForm"] [data-baseweb="input"] *{border-color:transparent!important;}
    [data-testid="stForm"] [data-testid="stFormSubmitButton"]>button{font-family:var(--font)!important;font-size:17px!important;font-weight:600!important;color:#FFFFFF!important;background-color:var(--blue)!important;border:none!important;border-radius:980px!important;padding:11px 24px!important;box-shadow:0 1px 4px rgba(0,122,255,0.28)!important;}
    </style>""", unsafe_allow_html=True)
    st.markdown("<div style='height:10vh'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 4, 1])
    with col:
        with st.form("login_form"):
            st.markdown(f"""
            <div style="text-align:center;padding:0.5rem 0 1.4rem;">
                <img src="{PARROT_SRC}" style="height:110px;width:auto;filter:drop-shadow(0 4px 12px rgba(0,0,0,0.15));margin-bottom:1.2rem;">
                <div style="font-size:23px;font-weight:700;color:#1C1C1E;margin-bottom:0.4rem;">需求分析工具</div>
                <div style="font-size:15px;color:#6E6E73;margin-bottom:0.4rem;">請輸入密碼以繼續</div>
            </div>""", unsafe_allow_html=True)
            pwd = st.text_input("", type="password", placeholder="密碼", label_visibility="collapsed")
            submitted = st.form_submit_button("進入", use_container_width=True)
        if submitted:
            if pwd == os.environ.get("APP_PASSWORD", ""):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("密碼錯誤")
    st.components.v1.html("""<script>
    setTimeout(function(){
        var inp=window.parent.document.querySelector('input[type="password"]');
        if(inp){inp.setAttribute('autocomplete','new-password');inp.focus();}
    },300);
    </script>""", height=0)
    st.stop()

# ── Session State ────────────────────────────────────────────────

if "interview_history" not in st.session_state:
    st.session_state.interview_history = []
if "interview_results" not in st.session_state:
    st.session_state.interview_results = None
if "interview_input_key" not in st.session_state:
    st.session_state.interview_input_key = 0
if "srs_history" not in st.session_state:
    st.session_state.srs_history = []
if "srs_results" not in st.session_state:
    st.session_state.srs_results = None
if "srs_input_key" not in st.session_state:
    st.session_state.srs_input_key = 0

# ── Word Helper Functions ────────────────────────────────────────

def _set_font(run, name="標楷體", size=12, bold=False):
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:eastAsia", "w:ascii", "w:hAnsi"):
        rFonts.set(qn(attr), name)

def _cell_text(cell, text, size=12, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    _set_font(p.add_run(text), size=size, bold=bold)

def _cell_bg(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)

def _center_cell(cell):
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

def _section_box(doc, label, lines, header_color="EBF3FF"):
    """框格區塊：標題列（底色）+ 內容列，每個 section 獨立一個框格。"""
    t = doc.add_table(rows=2, cols=1)
    t.style = "Table Grid"
    # 標題列
    h = t.rows[0].cells[0]
    _cell_text(h, label, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)
    _cell_bg(h, header_color)
    # 內容列
    c = t.rows[1].cells[0]
    c.text = ""
    for i, line in enumerate(lines):
        p = c.paragraphs[0] if i == 0 else c.add_paragraph()
        _set_font(p.add_run(line), size=11)
        p.paragraph_format.space_after = Pt(3)
    # 間距
    gap = doc.add_paragraph()
    gap.paragraph_format.space_after = Pt(6)

def _ac_section(doc, ac_text):
    """驗收條件：合併標題列 + 欄位標題列 + 資料列。"""
    items = [i.strip() for i in ac_text.split("\n\n") if i.strip()]
    if not items:
        return
    numbers = ["①", "②", "③", "④", "⑤", "⑥"]
    t = doc.add_table(rows=2 + len(items), cols=4)
    t.style = "Table Grid"
    t.columns[0].width = Cm(0.9)
    # 合併標題列
    t.rows[0].cells[0].merge(t.rows[0].cells[3])
    _cell_text(t.rows[0].cells[0], "驗收條件", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _cell_bg(t.rows[0].cells[0], "E8F8ED")
    _center_cell(t.rows[0].cells[0])
    # 欄位標題
    for cell, lbl in zip(t.rows[1].cells, ["#", "前提", "操作", "預期結果"]):
        _cell_text(cell, lbl, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_bg(cell, "F2F2F7")
        _center_cell(cell)
    # 資料列
    for i, item in enumerate(items):
        d = {"前提": "", "操作": "", "預期": ""}
        for line in [l.strip() for l in item.split("\n") if l.strip()]:
            for k in d:
                if line.startswith(k):
                    d[k] = line.split("：", 1)[-1].strip()
        r = t.rows[2 + i].cells
        _cell_text(r[0], numbers[i] if i < len(numbers) else f"{i+1}.", align=WD_ALIGN_PARAGRAPH.CENTER)
        _center_cell(r[0])
        _cell_text(r[1], d["前提"])
        _cell_text(r[2], d["操作"])
        _cell_text(r[3], d["預期"])
    gap = doc.add_paragraph()
    gap.paragraph_format.space_after = Pt(6)

def _set_margins(doc):
    for sec in doc.sections:
        sec.top_margin = Cm(2); sec.bottom_margin = Cm(2)
        sec.left_margin = Cm(2.5); sec.right_margin = Cm(2.5)

# ── Word Generation Functions ────────────────────────────────────

def generate_interview_word(entries):
    doc = Document()
    _set_margins(doc)
    for idx, entry in enumerate(entries):
        if idx > 0:
            doc.add_page_break()
        _section_box(doc, "需求描述", [entry["input"]], "F2F2F7")
        lines = [l.strip() for l in entry["ambiguous"].split("\n") if l.strip()]
        _section_box(doc, "模糊點", lines, "EBF3FF")
        lines = [l.strip() for l in entry["issues"].split("\n") if l.strip()]
        _section_box(doc, "潛在問題", lines, "FFF4E6")
        lines = [l.strip() for l in entry["questions"].split("\n") if l.strip()]
        _section_box(doc, "追問清單", lines, "E8F8ED")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    return buf.getvalue()

def generate_srs_engineer_word(entries):
    doc = Document()
    _set_margins(doc)
    for idx, entry in enumerate(entries):
        if idx > 0:
            doc.add_page_break()
        _section_box(doc, "功能說明", [entry["func_desc"]], "EBF3FF")
        _section_box(doc, "使用者故事", [entry["user_story"]], "F2F0FF")
        _ac_section(doc, entry["ac_block"])
        lines = [l.strip() for l in entry["nfr"].split("\n") if l.strip()]
        _section_box(doc, "非功能性需求", lines, "F2F2F7")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    return buf.getvalue()

def generate_srs_pm_word(entries):
    doc = Document()
    _set_margins(doc)
    for idx, entry in enumerate(entries):
        if idx > 0:
            doc.add_page_break()
        lines = [l.strip() for l in entry["pending"].split("\n") if l.strip()]
        _section_box(doc, "待確認事項", lines, "FFFAE6")
        lines = [l.strip() for l in entry["risk"].split("\n") if l.strip()]
        _section_box(doc, "風險與疑慮", lines, "FFF4E6")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    return buf.getvalue()

# ── UI Helpers ───────────────────────────────────────────────────

def extract_block(text, start_tag, end_tag):
    try:
        return text.split(start_tag)[1].split(end_tag)[0].strip()
    except IndexError:
        return ""

def bullet_to_html(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return "".join(f"<p>{line}</p>" for line in lines)

def to_html(text):
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in text.split("\n\n"))

def ac_to_html(text):
    items = [i.strip() for i in text.split("\n\n") if i.strip()]
    numbers = ["①", "②", "③", "④", "⑤", "⑥"]
    html_parts = []
    idx = 0
    for item in items:
        rows = []
        for line in [l.strip() for l in item.split("\n") if l.strip()]:
            if line.startswith("條件"):
                continue
            if line.startswith("前提"):
                rows.append(f'<div class="ac-row"><span class="ac-label label-premise">前提</span><span class="ac-text">{line.split("：",1)[-1].strip()}</span></div>')
            elif line.startswith("操作"):
                rows.append(f'<div class="ac-row"><span class="ac-label label-action">操作</span><span class="ac-text">{line.split("：",1)[-1].strip()}</span></div>')
            elif line.startswith("預期"):
                rows.append(f'<div class="ac-row"><span class="ac-label label-result">預期</span><span class="ac-text">{line.split("：",1)[-1].strip()}</span></div>')
            else:
                rows.append(f'<div class="ac-row"><span class="ac-text">{line}</span></div>')
        if rows:
            num = numbers[idx] if idx < len(numbers) else f"{idx+1}."
            html_parts.append(f'<div class="ac-item"><div class="ac-num">{num}</div><div class="ac-body">{"".join(rows)}</div></div>')
            idx += 1
    return "".join(html_parts)

def _loading_html():
    return f"""
    <div class="loading-overlay">
        <div class="parrot-loading-wrap">
            <div class="parrot-loading">
                <img src="{PARROT_SRC2}" class="loading-parrot p1" alt="">
                <img src="{PARROT_SRC2}" class="loading-parrot p2" alt="">
                <img src="{PARROT_SRC2}" class="loading-parrot p3" alt="">
            </div>
            <div class="loading-text">分析中...</div>
        </div>
    </div>"""

# ── Sidebar ──────────────────────────────────────────────────────

with st.sidebar:
    # 套用全選/清除的動作（必須在 checkbox 渲染前執行）
    int_hist = st.session_state.interview_history
    srs_hist = st.session_state.srs_history
    if st.session_state.get("_int_select_action") == "all":
        for i in range(len(int_hist)): st.session_state[f"int_hist_{i}"] = True
        del st.session_state["_int_select_action"]
    elif st.session_state.get("_int_select_action") == "clear":
        for i in range(len(int_hist)): st.session_state[f"int_hist_{i}"] = False
        del st.session_state["_int_select_action"]
    if st.session_state.get("_srs_select_action") == "all":
        for i in range(len(srs_hist)): st.session_state[f"srs_hist_{i}"] = True
        del st.session_state["_srs_select_action"]
    elif st.session_state.get("_srs_select_action") == "clear":
        for i in range(len(srs_hist)): st.session_state[f"srs_hist_{i}"] = False
        del st.session_state["_srs_select_action"]

    # 訪談輔助紀錄
    st.markdown('<div style="background:#EBF3FF;border-radius:10px;padding:0.45rem 0.9rem;margin-bottom:0.6rem;"><span style="font-size:15px;font-weight:800;color:#0055CC;">訪談輔助紀錄</span></div>', unsafe_allow_html=True)
    if not int_hist:
        st.caption("分析後將顯示於此")
    else:
        n = len(int_hist)
        int_selected = []
        for real_idx in range(n - 1, -1, -1):
            entry = int_hist[real_idx]
            preview = entry["input"][:30] + "…" if len(entry["input"]) > 30 else entry["input"]
            cb_col, txt_col = st.columns([1, 6])
            with cb_col:
                checked = st.checkbox("", key=f"int_hist_{real_idx}")
            with txt_col:
                if st.button(preview, key=f"int_view_{real_idx}", use_container_width=True):
                    st.session_state.interview_results = {
                        "input": entry["input"],
                        "ambiguous": entry["ambiguous"],
                        "issues": entry["issues"],
                        "questions": entry["questions"],
                    }
                    st.rerun()
            if checked:
                int_selected.append(real_idx)
        c1, c2 = st.columns(2)
        if c1.button("全選", key="int_sel_all", use_container_width=True, type="primary"):
            st.session_state["_int_select_action"] = "all"
            st.rerun()
        if c2.button("清除", key="int_sel_clear", use_container_width=True, type="primary"):
            st.session_state["_int_select_action"] = "clear"
            st.rerun()
        if int_selected:
            sel = [int_hist[i] for i in sorted(int_selected)]
            st.download_button(
                label=f"匯出 Word（{len(int_selected)} 筆）",
                data=generate_interview_word(sel),
                file_name=f"訪談分析_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="int_export",
            )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # SRS 紀錄
    st.markdown('<div style="background:#E8F8ED;border-radius:10px;padding:0.45rem 0.9rem;margin-bottom:0.6rem;"><span style="font-size:15px;font-weight:800;color:#1a6632;">SRS 紀錄</span></div>', unsafe_allow_html=True)
    if not srs_hist:
        st.caption("生成後將顯示於此")
    else:
        n2 = len(srs_hist)
        srs_selected = []
        for real_idx in range(n2 - 1, -1, -1):
            entry = srs_hist[real_idx]
            preview = entry["input"][:30] + "…" if len(entry["input"]) > 30 else entry["input"]
            cb_col, txt_col = st.columns([1, 6])
            with cb_col:
                checked = st.checkbox("", key=f"srs_hist_{real_idx}")
            with txt_col:
                if st.button(preview, key=f"srs_view_{real_idx}", use_container_width=True):
                    st.session_state.srs_results = {k: entry[k] for k in ("func_desc","user_story","ac_block","nfr","pending","risk")}
                    st.rerun()
            if checked:
                srs_selected.append(real_idx)
        c3, c4 = st.columns(2)
        if c3.button("全選", key="srs_sel_all", use_container_width=True, type="primary"):
            st.session_state["_srs_select_action"] = "all"
            st.rerun()
        if c4.button("清除", key="srs_sel_clear", use_container_width=True, type="primary"):
            st.session_state["_srs_select_action"] = "clear"
            st.rerun()
        if srs_selected:
            sel2 = [srs_hist[i] for i in sorted(srs_selected)]
            st.download_button(
                label=f"工程師版 Word（{len(srs_selected)} 筆）",
                data=generate_srs_engineer_word(sel2),
                file_name=f"SRS_工程師版_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="srs_eng_export",
            )
            st.download_button(
                label=f"PM 版 Word（{len(srs_selected)} 筆）",
                data=generate_srs_pm_word(sel2),
                file_name=f"SRS_PM版_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="srs_pm_export",
            )

# ── Hero ─────────────────────────────────────────────────────────

st.markdown(f"""
<div class="hero">
    <img src="{PARROT_SRC}" class="hero-parrot" alt="鸚鵡">
    <div class="hero-text">
        <h1>需求分析工具</h1>
        <p>訪談輔助 · SRS 文件生成</p>
    </div>
</div>""", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["訪談輔助", "SRS 生成"])

# ── Tab 1：訪談輔助 ──────────────────────────────────────────────

with tab1:
    st.markdown("""
    <div class="section-label">
        <div class="step-dot">1</div>
        <span class="section-label-text">輸入客戶剛說的需求（幾個字就夠）</span>
    </div>""", unsafe_allow_html=True)

    interview_input = st.text_area(
        label="訪談輸入",
        placeholder="例如：他們說要一個報表，讓主管可以看到所有案件的狀態",
        height=120,
        label_visibility="collapsed",
        key=f"interview_{st.session_state.interview_input_key}",
    )

    st.markdown("""
    <div class="output-preview">
        <span class="preview-hint">將產出：</span>
        <span class="preview-chip chip-blue">模糊點</span>
        <span class="preview-chip chip-orange">潛在問題</span>
        <span class="preview-chip chip-green">追問清單</span>
    </div>""", unsafe_allow_html=True)

    if st.button("分析這個需求", type="primary", use_container_width=True, key="interview_btn"):
        if not interview_input.strip():
            st.warning("請先輸入需求，再按分析")
        else:
            loading_ph = st.empty()
            loading_ph.markdown(_loading_html(), unsafe_allow_html=True)
            try:
                message = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=[{"type": "text", "text": INTERVIEW_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": f"需求描述：\n{interview_input}"}]
                )
                result    = message.content[0].text
                ambiguous = extract_block(result, "[AMBIGUOUS_START]", "[AMBIGUOUS_END]")
                issues    = extract_block(result, "[ISSUES_START]",    "[ISSUES_END]")
                questions = extract_block(result, "[QUESTIONS_START]", "[QUESTIONS_END]")
                loading_ph.empty()
                entry = {"time": datetime.now().strftime("%H:%M"), "input": interview_input,
                         "ambiguous": ambiguous, "issues": issues, "questions": questions}
                st.session_state.interview_history.append(entry)
                st.session_state.interview_results = entry
                st.session_state.interview_input_key += 1
                st.rerun()
            except anthropic.AuthenticationError:
                loading_ph.empty(); st.error("API 金鑰錯誤，請確認 .env 檔案中的 ANTHROPIC_API_KEY")
            except anthropic.RateLimitError:
                loading_ph.empty(); st.error("API 使用量已達上限，請稍後再試")
            except Exception as e:
                loading_ph.empty(); st.error(f"發生未預期的錯誤：{str(e)}")

    if st.session_state.interview_results:
        r = st.session_state.interview_results
        st.success("分析完成，以下是你可以追問的方向")
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0s"><div class="output-card-header"><span class="card-badge badge-blue">模糊點</span></div><div class="output-card-body">{bullet_to_html(r["ambiguous"])}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0.1s"><div class="output-card-header"><span class="card-badge badge-orange">潛在問題</span></div><div class="output-card-body">{bullet_to_html(r["issues"])}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0.2s"><div class="output-card-header"><span class="card-badge badge-green">追問清單</span></div><div class="output-card-body">{bullet_to_html(r["questions"])}</div></div>', unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("清除", use_container_width=True, key="interview_clear"):
            st.session_state.interview_results = None
            st.session_state.interview_input_key += 1
            st.rerun()

# ── Tab 2：SRS 生成 ──────────────────────────────────────────────

with tab2:
    st.markdown("""
    <div class="section-label">
        <div class="step-dot">1</div>
        <span class="section-label-text">貼入訪談筆記或逐字稿（任何格式皆可）</span>
    </div>""", unsafe_allow_html=True)

    srs_input = st.text_area(
        label="訪談筆記",
        placeholder="例如：主管要看所有案件狀態 / 阿輝說要能篩選日期 / 不確定要不要分權限 / 要能匯出 Excel / 下週要給我們",
        height=200,
        label_visibility="collapsed",
        key=f"srs_{st.session_state.srs_input_key}",
    )

    st.markdown("""
    <div class="output-preview">
        <span class="preview-hint">工程師版：</span>
        <span class="preview-chip chip-blue">功能說明</span>
        <span class="preview-chip chip-purple">使用者故事</span>
        <span class="preview-chip chip-green">驗收條件</span>
        <span class="preview-chip chip-gray">非功能需求</span>
        <span class="preview-hint" style="margin-left:8px;">PM 版：</span>
        <span class="preview-chip chip-orange">待確認事項</span>
        <span class="preview-chip chip-orange">風險</span>
    </div>""", unsafe_allow_html=True)

    if st.button("生成需求規格文件", type="primary", use_container_width=True, key="srs_btn"):
        if not srs_input.strip():
            st.warning("請先貼入訪談筆記，再按生成")
        else:
            loading_ph2 = st.empty()
            loading_ph2.markdown(_loading_html(), unsafe_allow_html=True)
            try:
                message = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=3000,
                    system=[{"type": "text", "text": SRS_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": f"訪談筆記：\n{srs_input}"}]
                )
                result    = message.content[0].text
                func_desc = extract_block(result, "[FUNC_DESC_START]",  "[FUNC_DESC_END]")
                user_story= extract_block(result, "[USER_STORY_START]", "[USER_STORY_END]")
                ac_block  = extract_block(result, "[AC_START]",         "[AC_END]")
                nfr       = extract_block(result, "[NFR_START]",        "[NFR_END]")
                pending   = extract_block(result, "[PENDING_START]",    "[PENDING_END]")
                risk      = extract_block(result, "[RISK_START]",       "[RISK_END]")
                loading_ph2.empty()
                entry = {
                    "time": datetime.now().strftime("%H:%M"), "input": srs_input,
                    "func_desc": func_desc, "user_story": user_story,
                    "ac_block": ac_block, "nfr": nfr, "pending": pending, "risk": risk,
                }
                st.session_state.srs_history.append(entry)
                st.session_state.srs_results = entry
                st.session_state.srs_input_key += 1
                st.rerun()
            except anthropic.AuthenticationError:
                loading_ph2.empty(); st.error("API 金鑰錯誤，請確認 .env 檔案中的 ANTHROPIC_API_KEY")
            except anthropic.RateLimitError:
                loading_ph2.empty(); st.error("API 使用量已達上限，請稍後再試")
            except Exception as e:
                loading_ph2.empty(); st.error(f"發生未預期的錯誤：{str(e)}")

    if st.session_state.srs_results:
        r = st.session_state.srs_results
        st.success("文件生成完成")
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        # 工程師版
        st.markdown('<div class="section-divider"><div class="section-divider-line"></div><span class="section-divider-label">工程師版</span><div class="section-divider-line"></div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0s"><div class="output-card-header"><span class="card-badge badge-blue">功能說明</span></div><div class="output-card-body">{to_html(r["func_desc"])}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0.05s"><div class="output-card-header"><span class="card-badge badge-purple">使用者故事</span></div><div class="output-card-body">{to_html(r["user_story"])}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0.1s"><div class="output-card-header"><span class="card-badge badge-green">驗收條件</span></div><div class="output-card-body">{ac_to_html(r["ac_block"])}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0.15s"><div class="output-card-header"><span class="card-badge badge-gray">非功能性需求</span></div><div class="output-card-body">{bullet_to_html(r["nfr"])}</div></div>', unsafe_allow_html=True)

        # PM 版
        st.markdown('<div class="section-divider"><div class="section-divider-line"></div><span class="section-divider-label">PM 版</span><div class="section-divider-line"></div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0.2s"><div class="output-card-header"><span class="card-badge badge-orange">待確認事項</span></div><div class="output-card-body">{bullet_to_html(r["pending"])}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-card" style="animation-delay:0.25s"><div class="output-card-header"><span class="card-badge badge-orange">風險與疑慮</span></div><div class="output-card-body">{bullet_to_html(r["risk"])}</div></div>', unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("清除", use_container_width=True, key="srs_clear"):
            st.session_state.srs_results = None
            st.session_state.srs_input_key += 1
            st.rerun()

# ── Footer ───────────────────────────────────────────────────────

st.markdown("<hr>", unsafe_allow_html=True)
st.markdown('<div class="page-footer">本工具在本機運行 · 輸入內容僅傳送至 Anthropic API 進行分析<br>不會儲存於任何第三方系統</div>', unsafe_allow_html=True)
