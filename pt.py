import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 관리 로직 ---
LEARNING_DB = "gemini_instruction_data.json"

def load_db():
    if os.path.exists(LEARNING_DB):
        try:
            with open(LEARNING_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"total_count": 0, "patterns": [], "raw_examples": []}

def save_db(data):
    with open(LEARNING_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_all_ascii=False, indent=4)

# --- 2. 텍스트 처리 로직 (개선) ---
def decode_text(raw_data, enc_method):
    if enc_method == "자동 감지":
        detected = chardet.detect(raw_data)
        enc = detected['encoding'] if detected['confidence'] > 0.6 else 'utf-8'
    else:
        enc = enc_method
    
    try:
        return raw_data.decode(enc), enc
    except:
        try: return raw_data.decode('cp949'), 'cp949'
        except: return raw_data.decode('utf-8', errors='ignore'), 'utf-8(ignore)'

# --- 3. UI 레이아웃 ---
st.set_page_config(page_title="TOC Master", layout="wide")
st.title("🧠 목차 패턴 학습기 (실시간 반영)")

# 사이드바 설정
st.sidebar.title("🛠️ 설정")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

# 인코딩 변경 시 즉시 리런되도록 처리
encoding_mode = st.sidebar.selectbox(
    "인코딩 선택 (글자가 깨지면 변경하세요)",
    ["자동 감지", "utf-8", "cp949", "euc-kr", "utf-16"],
    key="encoding_selector"
)

if 'db' not in st.session_state:
    st.session_state.db = load_db()

tab1, tab2 = st.tabs(["📊 패턴 추출", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("소설 파일을 올려주세요", type=['txt'])
    
    # 파일이 업로드되면 세션에 바이너리 데이터 저장
    if uploaded_file:
        raw_bytes = uploaded_file.read()
        # [핵심] 선택된 인코딩으로 즉시 디코딩 시도
        content, used_enc = decode_text(raw_bytes, encoding_mode)
        
        st.info(f"💡 현재 **[{used_enc}]** 인코딩 적용 중")
        
        # 글자가 여전히 깨졌는지 확인하기 위한 미리보기 (상단 5줄)
        with st.expander("📄 파일 미리보기 (글자가 깨지는지 확인하세요)"):
            st.text("\n".join(content.splitlines()[:5]))

        lines = content.splitlines()
        candidates = []
        for i, line in enumerate(lines):
            clean = line.strip()
            if not clean or len(clean) > 40 or re.match(r'^["\'「『]', clean): continue 
            if re.search(r'제\s?\d+|^\d+[\.\s]|Part|Chapter|외전|후기|[\(\[\<〈].+?[\)\]\>〉]', clean):
                candidates.append({"line": i, "text": clean})

        if candidates:
            with st.form("learning_form"):
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    # 키값에 인코딩 정보를 넣어 상태 변화 감지
                    if cols[idx % 2].checkbox(f"L{cand['line']}: {cand['text']}", key=f"c_{used_enc}_{idx}"):
                        selected_items.append(cand['text'])
                
                if st.form_submit_button("📌 선택 패턴 저장"):
                    if selected_items:
                        for item in selected_items:
                            rule = re.sub(r'\d+', '[NUM]', re.escape(item))
                            found = False
                            for p in st.session_state.db['patterns']:
                                if p['rule'] == rule:
                                    p['weight'] += 1
                                    found = True
                                    break
                            if not found:
                                st.session_state.db['patterns'].append({"rule": rule, "example": item, "weight": 1})
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
