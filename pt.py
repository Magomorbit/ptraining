import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 관리 로직 (백업 제외) ---
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
    with open(LEARNING_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_all_ascii=False, indent=4)

# --- 2. 언어 및 인코딩 처리 로직 ---
def smart_decode(raw_data):
    """글자 깨짐 방지를 위한 다중 디코딩 전략"""
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
    """숫자 등을 [NUM]으로 치환하여 추상적 규칙 생성"""
    pattern = re.escape(text)
    pattern = re.sub(r'\d+', '[NUM]', pattern)
    return pattern

# --- 3. UI 레이아웃 및 메인 로직 ---
st.set_page_config(page_title="TOC Pattern Master", layout="wide")
st.title("🧠 목차 패턴 학습 및 제미나이 정규식 생성기")

# 사이드바: API 설정
st.sidebar.title("🚀 AI 설정")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Google AI Studio에서 발급받은 키를 입력하세요.")

tab1, tab2 = st.tabs(["📊 패턴 추출 및 학습", "⚙️ 데이터 관리 및 삭제"])

# --- TAB 1: 패턴 학습 ---
with tab1:
    uploaded_file = st.file_uploader("소설 TXT 파일을 업로드하세요", type=['txt'])
    
    if uploaded_file:
        raw_data = uploaded_file.read()
        content, used_enc = smart_decode(raw_data)
        st.caption(f"ℹ️ 적용된 인코딩: {used_enc} (파일: {uploaded_file.name})")
        
        lines = content.splitlines()
        candidates = []
        
        # 한국어 소설의 주요 목차 키워드 탐색
        for i, line in enumerate(lines):
            clean = line.strip()
            if not clean or len(clean) > 50: continue
            if re.search(r'제\s?\d+|^\d+[\.\s]|^[\[\<〈\(].+?[\]\>〉\)]|Part|Chapter|Chapter\s?\d+|[Pp]rologue|[Ee]pilogue|외전|후기', clean):
                candidates.append({"line": i, "text": clean})

        if not candidates:
            st.warning("인식된 목차 후보가 없습니다.")
        else:
            st.subheader("✅ 실제 목차 선택")
            selected_items = []
            file_id = uploaded_file.name
            
            cols = st.columns(2)
            for idx, cand in enumerate(candidates):
                target_col = cols[idx % 2]
                if target_col.checkbox(f"L{cand['line']}: {cand['text']}", key=f"{file_id}_{idx}"):
                    selected_items.append(cand['text'])

            if st.button("📌 선택한 패턴 저장"):
                if not selected_items:
                    st.error("체크된 항목이 없습니다.")
                else:
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
                    save_db(db)
                    st.success(f"총 {len(selected_items)}개의 데이터를 학습 DB에 추가했습니다!")
                    st.balloons()

# --- TAB 2: 데이터 관리 및 삭제 ---
with tab2:
    st.subheader("🗑️ 학습된 데이터 관리")
    db = load_db()
    
    if not db['patterns']:
        st.info("저장된 데이터가 없습니다.")
    else:
        st.write(f"현재 누적된 고유 패턴 수: **{len(db['patterns'])}개**")
        sorted_p = sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)
        
        for i, p in enumerate(sorted_p):
            with st.container():
                c1, c2, c3 = st.columns([3, 2, 1])
                display_rule = p['rule'].replace("\\", "")
                c1.code(display_rule)
                c2.write(f"예시: {p['example']} (빈도: {p['weight']})")
                if c3.button("삭제", key=f"del_{i}"):
                    db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
                    save_db(db)
                    st.rerun()

        st.divider()
        if st.button("⚠️ 전체 데이터 초기화"):
            save_db({"total_count": 0, "patterns": [], "raw_examples": []})
            st.rerun()

# --- 4. 제미나이 정규식 생성 기능 ---
if api_key:
    genai.configure(api_key=api_key)
    
    if st.sidebar.button("✨ 최적 정규식 생성 (Gemini)"):
        db = load_db()
        if not db['patterns']:
            st.sidebar.error("학습 데이터가 부족합니다.")
        else:
            with st.spinner("AI 분석 중..."):
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    pattern_info = "\n".join([f"- 패턴: {p['rule']}, 예시: {p['example']}, 가중치: {p['weight']}" for p in db['patterns']])
                    
                    prompt = f"""
                    한국어 장르 소설 텍스트 분석 전문가로서, 아래 목차 패턴들을 모두 포함하는 단 하나의 최적화된 Python 정규표현식을 작성해줘.
                    설명 없이 정규표현식 문자열만 출력해.

                    [데이터]
                    {pattern_info}
                    """
                    response = model.generate_content(prompt)
                    st.session_state['final_regex'] = response.text.strip()
                except Exception as e:
                    st.sidebar.error(f"API 오류: {e}")

if 'final_regex' in st.session_state:
    st.sidebar.success("생성된 최적 정규표현식:")
    st.sidebar.code(st.session_state['final_regex'], language='python')
