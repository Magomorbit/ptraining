import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 관리 로직 (더욱 방어적인 설계) ---
LEARNING_DB = "gemini_instruction_data.json"

def load_db():
    default_structure = {"total_count": 0, "patterns": [], "raw_examples": []}
    if os.path.exists(LEARNING_DB):
        try:
            with open(LEARNING_DB, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # 필수 키가 있는지 확인
                    for key in default_structure.keys():
                        if key not in data:
                            data[key] = default_structure[key]
                    return data
        except:
            return default_structure
    return default_structure

def save_db(data):
    """
    JSON 저장 시 발생할 수 있는 TypeError를 원천 차단하기 위해
    모든 데이터를 원시 타입(str, int)으로 완전히 새로 재구성합니다.
    """
    try:
        new_patterns = []
        for p in data.get("patterns", []):
            new_patterns.append({
                "rule": str(p.get("rule", "")),
                "example": str(p.get("example", "")),
                "weight": int(p.get("weight", 1))
            })
            
        clean_data = {
            "total_count": int(len(data.get("raw_examples", []))),
            "patterns": new_patterns,
            "raw_examples": [str(x) for x in data.get("raw_examples", [])]
        }
        
        with open(LEARNING_DB, "w", encoding="utf-8") as f:
            json.dump(clean_data, f, ensure_all_ascii=False, indent=4)
    except Exception as e:
        st.error(f"데이터 저장 중 치명적 오류 발생: {e}")

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
    # 정규식 특수문자 보호 및 숫자 치환
    pattern = re.escape(str(text))
    pattern = re.sub(r'\d+', '[NUM]', pattern)
    return str(pattern)

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
            # 폼을 사용하여 버튼 클릭 시에만 데이터가 처리되도록 격리
            with st.form("learning_form"):
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    # 파일명과 인덱스를 조합해 고유 키 생성
                    if cols[idx % 2].checkbox(f"L{cand['line']}: {cand['text']}", key=f"c_{uploaded_file.name}_{idx}"):
                        selected_items.append(str(cand['text']))
                
                submit = st.form_submit_button("📌 선택한 패턴 저장")
                
                if submit:
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
                        
                        save_db(db)
                        st.success("데이터가 성공적으로 저장되었습니다.")
                        st.rerun()
                    else:
                        st.warning("선택된 항목이 없습니다.")

with tab2:
    st.subheader("🗑️ 학습된 데이터 관리")
    db = load_db()
    if db['patterns']:
        sorted_p = sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)
        for i, p in enumerate(sorted_p):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.code(str(p['rule']).replace("\\", ""))
            c2.write(f"빈도: {p['weight']}")
            if c3.button("삭제", key=f"del_{i}"):
                db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
                save_db(db)
                st.rerun()
        
        st.divider()
        if st.button("⚠️ 초기화"):
            save_db({"total_count": 0, "patterns": [], "raw_examples": []})
            st.rerun()

# --- 4. 제미나이 생성 로직 ---
if api_key:
    genai.configure(api_key=api_key)
    if st.sidebar.button("✨ 최적 정규식 생성"):
        db = load_db()
        if db['patterns']:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                p_info = "\n".join([f"- {p['rule']} (빈도:{p['weight']})" for p in db['patterns']])
                resp = model.generate_content(f"다음은 소설의 목차 패턴들이야. 이들을 모두 매칭하는 Python 정규식 하나만 문자열로 출력해:\n{p_info}")
                st.session_state['res_regex'] = resp.text.strip()
            except Exception as e:
                st.sidebar.error(f"API 오류: {e}")

if 'res_regex' in st.session_state:
    st.sidebar.success("생성된 정규표현식:")
    st.sidebar.code(st.session_state['res_regex'])
