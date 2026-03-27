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
        except:
            pass
    return {"total_count": 0, "patterns": [], "raw_examples": []}

def save_db(data):
    try:
        with open(LEARNING_DB, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_all_ascii=False, indent=4)
    except Exception as e:
        st.error(f"저장 중 오류: {e}")

# --- 2. 텍스트 처리 로직 ---
def decode_text(raw_data, encoding_method):
    if encoding_method == "자동 감지":
        detected = chardet.detect(raw_data)
        enc = detected['encoding'] if detected['confidence'] > 0.6 else 'utf-8'
    else:
        enc = encoding_method
    
    try:
        return raw_data.decode(enc), enc
    except:
        # 실패 시 가장 흔한 cp949로 마지막 시도
        try: return raw_data.decode('cp949'), 'cp949'
        except: return raw_data.decode('utf-8', errors='ignore'), 'utf-8(ignore)'

# --- 3. UI 레이아웃 ---
st.set_page_config(page_title="TOC Master", layout="wide")
st.title("🧠 목차 패턴 학습기 (인코딩 수동 선택 추가)")

# 사이드바 설정
st.sidebar.title("🛠️ 설정")
api_key = st.sidebar.text_input("Gemini API Key", type="password")
encoding_mode = st.sidebar.selectbox(
    "인코딩 선택 (글자가 깨지면 변경하세요)",
    ["자동 감지", "utf-8", "cp949", "euc-kr", "utf-16"]
)

if 'db' not in st.session_state:
    st.session_state.db = load_db()

tab1, tab2 = st.tabs(["📊 패턴 추출", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("소설 파일을 올려주세요", type=['txt'])
    if uploaded_file:
        raw_data = uploaded_file.read()
        content, used_enc = decode_text(raw_data, encoding_mode)
        
        st.info(f"💡 현재 **[{used_enc}]** 방식으로 읽었습니다. 글자가 깨진다면 사이드바에서 인코딩을 바꿔보세요.")
        
        lines = content.splitlines()
        candidates = []
        for i, line in enumerate(lines):
            clean = line.strip()
            if not clean or len(clean) > 40: continue
            if re.match(r'^["\'「『].*', clean): continue 
            
            if re.search(r'제\s?\d+|^\d+[\.\s]|Part|Chapter|외전|후기|[\(\[\<〈].+?[\)\]\>〉]', clean):
                candidates.append({"line": i, "text": clean})

        if candidates:
            with st.form("learning_form"):
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    # 파일명+인코딩을 키에 포함해 상태 초기화 방지
                    k = f"c_{uploaded_file.name}_{used_enc}_{idx}"
                    if cols[idx % 2].checkbox(f"L{cand['line']}: {cand['text']}", key=k):
                        selected_items.append(cand['text'])
                
                if st.form_submit_button("📌 선택 패턴 저장"):
                    if selected_items:
                        for item in selected_items:
                            # 숫자 치환 로직
                            rule = re.escape(item)
                            rule = re.sub(r'\d+', '[NUM]', rule)
                            
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
    st.subheader("⚙️ 학습된 데이터 리스트")
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
