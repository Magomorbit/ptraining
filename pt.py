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
                data = json.load(f)
                # 데이터 구조가 깨져있을 경우를 대비한 보정
                if not isinstance(data, dict):
                    return {"total_count": 0, "patterns": [], "raw_examples": []}
                return data
        except:
            pass
    return {"total_count": 0, "patterns": [], "raw_examples": []}

def save_db(data):
    # 중요: 저장 전 모든 데이터를 문자열화하여 TypeError 방지
    clean_data = {
        "total_count": int(data.get("total_count", 0)),
        "patterns": [],
        "raw_examples": [str(x) for x in data.get("raw_examples", [])]
    }
    for p in data.get("patterns", []):
        clean_data["patterns"].append({
            "rule": str(p["rule"]),
            "example": str(p["example"]),
            "weight": int(p["weight"])
        })
    
    with open(LEARNING_DB, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, ensure_all_ascii=False, indent=4)

# --- 2. 언어 및 인코딩 처리 로직 ---
def smart_decode(raw_data):
    detected = chardet.detect(raw_data)
    encoding = detected['encoding']
    confidence = detected['confidence']
    if not encoding or confidence < 0.6:
        encoding = 'utf-8'
    try:
        return raw_data.decode(encoding), encoding
    except:
        try:
            return raw_data.decode('cp949'), 'cp949'
        except:
            return raw_data.decode('utf-8', errors='ignore'), 'utf-8 (fallback)'

def analyze_pattern(text):
    pattern = re.escape(str(text))
    pattern = re.sub(r'\d+', '[NUM]', pattern)
    return pattern

# --- 3. UI 레이아웃 ---
st.set_page_config(page_title="TOC Pattern Master", layout="wide")
st.title("🧠 목차 패턴 학습 및 제미나이 정규식 생성기")

api_key = st.sidebar.text_input("Gemini API Key", type="password")

tab1, tab2 = st.tabs(["📊 패턴 추출 및 학습", "⚙️ 데이터 관리 및 삭제"])

with tab1:
    uploaded_file = st.file_uploader("소설 TXT 파일을 업로드하세요", type=['txt'])
    if uploaded_file:
        raw_data = uploaded_file.read()
        content, used_enc = smart_decode(raw_data)
        st.caption(f"ℹ️ 인코딩: {used_enc}")
        
        lines = content.splitlines()
        candidates = []
        for i, line in enumerate(lines):
            clean = line.strip()
            if not clean or len(clean) > 50: continue
            if re.search(r'제\s?\d+|^\d+[\.\s]|^[\[\<〈\(].+?[\]\>〉\)]|Part|Chapter|외전|후기', clean):
                candidates.append({"line": i, "text": clean})

        if candidates:
            st.subheader("✅ 실제 목차 선택")
            selected_items = []
            # 파일명을 기반으로 고유 세션 생성
            for idx, cand in enumerate(candidates):
                if st.checkbox(f"L{cand['line']}: {cand['text']}", key=f"chk_{uploaded_file.name}_{idx}"):
                    selected_items.append(str(cand['text']))

            if st.button("📌 선택한 패턴 저장"):
                if selected_items:
                    db = load_db()
                    for item in selected_items:
                        abstract = analyze_pattern(item)
                        found = False
                        for p in db['patterns']:
                            if p['rule'] == abstract:
                                p['weight'] += 1
                                found = True
                                break
                        if not found:
                            db['patterns'].append({"rule": abstract, "example": item, "weight": 1})
                        if item not in db['raw_examples']:
                            db['raw_examples'].append(item)
                    
                    db['total_count'] = len(db['raw_examples'])
                    save_db(db) # 여기서 정제된 데이터가 저장됨
                    st.success("데이터가 안전하게 저장되었습니다!")
                    st.rerun()

with tab2:
    st.subheader("🗑️ 학습된 데이터 관리")
    db = load_db()
    if db['patterns']:
        sorted_p = sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)
        for i, p in enumerate(sorted_p):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"빈도: {p['weight']}")
            if c3.button("삭제", key=f"del_{i}"):
                db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
                save_db(db)
                st.rerun()
        if st.button("⚠️ 초기화"):
            save_db({"total_count": 0, "patterns": [], "raw_examples": []})
            st.rerun()

# --- 4. 제미나이 생성 로직 ---
if api_key and st.sidebar.button("✨ 최적 정규식 생성"):
    db = load_db()
    if db['patterns']:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            p_info = "\n".join([f"- {p['rule']} (빈도:{p['weight']})" for p in db['patterns']])
            resp = model.generate_content(f"다음 패턴을 모두 잡는 Python 정규식 하나만 출력해:\n{p_info}")
            st.session_state['res'] = resp.text.strip()
        except Exception as e:
            st.sidebar.error(f"오류: {e}")

if 'res' in st.session_state:
    st.sidebar.code(st.session_state['res'])
