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
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except:
            return default_structure
    return default_structure

def save_db(data):
    try:
        # 모든 데이터를 안전한 형태로 재구성
        clean_data = {
            "total_count": int(len(data.get("raw_examples", []))),
            "patterns": data.get("patterns", []),
            "raw_examples": data.get("raw_examples", [])
        }
        with open(LEARNING_DB, "w", encoding="utf-8") as f:
            json.dump(clean_data, f, ensure_all_ascii=False, indent=4)
    except Exception as e:
        st.error(f"저장 오류: {e}")

# --- 2. 텍스트 처리 로직 ---
def smart_decode(raw_data):
    detected = chardet.detect(raw_data)
    enc = detected['encoding'] if detected['confidence'] > 0.6 else 'utf-8'
    try:
        return raw_data.decode(enc), enc
    except:
        try:
            return raw_data.decode('cp949'), 'cp949'
        except:
            return raw_data.decode('utf-8', errors='ignore'), 'utf-8(ignore)'

def analyze_pattern(text):
    # 숫자를 [NUM]으로 치환하고 특수문자 보호
    pattern = re.escape(str(text))
    pattern = re.sub(r'\d+', '[NUM]', pattern)
    return str(pattern)

# --- 3. UI 레이아웃 ---
st.set_page_config(page_title="TOC Master", layout="wide")
st.title("🧠 목차 패턴 학습기 (개선 버전)")

api_key = st.sidebar.text_input("Gemini API Key", type="password")

tab1, tab2 = st.tabs(["📊 패턴 추출", "⚙️ 데이터 관리"])

# 데이터 불러오기
if 'db' not in st.session_state:
    st.session_state.db = load_db()

with tab1:
    uploaded_file = st.file_uploader("소설 파일을 올려주세요", type=['txt'])
    if uploaded_file:
        raw_data = uploaded_file.read()
        content, used_enc = smart_decode(raw_data)
        lines = content.splitlines()
        
        candidates = []
        for i, line in enumerate(lines):
            clean = line.strip()
            # [수정] 대사(따옴표 시작)는 제외하고, 목차 키워드가 있는 짧은 줄만 추출
            if not clean or len(clean) > 40: continue
            if re.search(r'^["\'「『].*', clean): continue # 따옴표로 시작하면 무조건 패스
            
            # 목차 후보군 키워드 탐색
            if re.search(r'제\s?\d+|^\d+[\.\s]|Part|Chapter|외전|후기|[\(\[\<].+?[\)\]\>]', clean):
                candidates.append({"line": i, "text": clean})

        if candidates:
            st.subheader(f"✅ 후보군 ({len(candidates)}개)")
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
                            # 중복 체크 및 업데이트
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
                        st.success("학습 데이터가 저장되었습니다!")
                        st.rerun()

with tab2:
    st.subheader("🗑️ 학습된 데이터 리스트")
    db = st.session_state.db
    if not db['patterns']:
        st.info("데이터가 없습니다.")
    else:
        for i, p in enumerate(sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"빈도: {p['weight']} (예: {p['example']})")
            if c3.button("삭제", key=f"del_{i}"):
                st.session_state.db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
                save_db(st.session_state.db)
                st.rerun()
        
        if st.button("⚠️ 전체 초기화"):
            st.session_state.db = {"total_count": 0, "patterns": [], "raw_examples": []}
            save_db(st.session_state.db)
            st.rerun()

# --- 4. 제미나이 생성 ---
if api_key and st.sidebar.button("✨ 최적 정규식 생성"):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        p_list = [f"- {p['rule']} (빈도:{p['weight']})" for p in st.session_state.db['patterns']]
        prompt = f"다음 패턴들을 목차로 인식하는 Python 정규식을 딱 하나만 출력해. 따옴표로 시작하는 문장은 제외되도록 짜줘:\n" + "\n".join(p_list)
        resp = model.generate_content(prompt)
        st.sidebar.code(resp.text.strip())
    except Exception as e:
        st.sidebar.error(f"오류: {e}")
