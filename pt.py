import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 관리 로직 ---
LEARNING_DB = "gemini_instruction_data.json"

def load_db():
    default_structure = {"total_count": 0, "patterns": [], "raw_examples": []}
    if os.path.exists(LEARNING_DB):
        try:
            with open(LEARNING_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default_structure
    return default_structure

def save_db(data):
    try:
        clean_data = {
            "total_count": int(len(data.get("raw_examples", []))),
            "patterns": data.get("patterns", []),
            "raw_examples": data.get("raw_examples", [])
        }
        with open(LEARNING_DB, "w", encoding="utf-8") as f:
            json.dump(clean_data, f, ensure_all_ascii=False, indent=4)
    except Exception as e:
        st.error(f"저장 오류: {e}")

# --- 2. [핵심 수정] 인코딩 강제 순회 로직 ---
def smart_decode(raw_data):
    """한국어 파일 인코딩 문제를 해결하기 위한 강제 순회 디코딩"""
    # 시도해볼 인코딩 목록 (우선순위 순)
    encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'latin1']
    
    # 1. chardet으로 먼저 시도
    detected = chardet.detect(raw_data)
    if detected['encoding']:
        encodings.insert(0, detected['encoding'])

    for enc in encodings:
        try:
            return raw_data.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
            
    # 모두 실패할 경우 에러 무시하고 utf-8로 강제 로드
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

def analyze_pattern(text):
    pattern = re.escape(str(text))
    pattern = re.sub(r'\d+', '[NUM]', pattern)
    return str(pattern)

# --- 3. UI 레이아웃 ---
st.set_page_config(page_title="TOC Master", layout="wide")
st.title("🧠 목차 패턴 학습기 (인코딩 강화 버전)")

api_key = st.sidebar.text_input("Gemini API Key", type="password")

if 'db' not in st.session_state:
    st.session_state.db = load_db()

tab1, tab2 = st.tabs(["📊 패턴 추출", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("소설 파일을 올려주세요", type=['txt'])
    if uploaded_file:
        raw_data = uploaded_file.read()
        content, used_enc = smart_decode(raw_data)
        
        # 인코딩 확인용 메시지
        st.info(f"💡 '{used_enc}' 인코딩으로 파일을 읽었습니다. 글자가 잘 보이나요?")
        
        lines = content.splitlines()
        candidates = []
        for i, line in enumerate(lines):
            clean = line.strip()
            # 필터: 빈 줄, 너무 긴 줄, 대사(따옴표) 시작 제외
            if not clean or len(clean) > 45: continue
            if re.match(r'^["\'「『].*', clean): continue 
            
            # 목차 후보 키워드
            if re.search(r'제\s?\d+|^\d+[\.\s]|Part|Chapter|외전|후기|[\(\[\<〈].+?[\)\]\>〉]', clean):
                candidates.append({"line": i, "text": clean})

        if candidates:
            with st.form("learning_form"):
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    if cols[idx % 2].checkbox(f"L{cand['line']}: {cand['text']}", key=f"c_{idx}"):
                        selected_items.append(cand['text'])
                
                if st.form_submit_button("📌 선택 패턴 저장"):
                    if selected_items:
                        for item in selected_items:
                            rule = analyze_pattern(item)
                            found = False
                            for p in st.session_state.db['patterns']:
                                if p['rule'] == rule:
                                    p['weight'] += 1
                                    found = True
                                    break
                            if not found:
                                st.session_state.db['patterns'].append({"rule": rule, "example": item, "weight": 1})
                            if item not in st.session_state.db['raw_examples']:
                                st.session_state.db['raw_examples'].append(item)
                        save_db(st.session_state.db)
                        st.success("데이터가 저장되었습니다!")
                        st.rerun()

with tab2:
    st.subheader("⚙️ 학습된 데이터")
    db = st.session_state.db
    if db['patterns']:
        for i, p in enumerate(sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"빈도: {p['weight']} (예: {p['example']})")
            if c3.button("삭제", key=f"del_{i}"):
                st.session_state.db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
                save_db(st.session_state.db)
                st.rerun()
