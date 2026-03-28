import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 관리 로직 (축적 및 다운로드 유지) ---
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

# --- 2. [개선] 다중 레이어 인코딩 인식 시스템 ---
def smart_decode(raw_data):
    """우선순위 편향 없이 데이터 무결성을 검증하며 디코딩"""
    test_encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'utf-16']
    
    # chardet 결과 참고 (우선순위 큐에 삽입)
    detected = chardet.detect(raw_data)
    if detected['encoding'] and detected['encoding'].lower() not in test_encodings:
        test_encodings.insert(0, detected['encoding'])

    for enc in test_encodings:
        try:
            decoded_text = raw_data.decode(enc)
            # 한글 깨짐 현상을 방지하기 위한 최소한의 검증 (가-힣 포함 여부)
            if re.search(r'[가-힣]', decoded_text):
                return decoded_text, enc
        except: continue
    
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

# --- 3. [개선] 목차 추출 정교화 로직 ---
def is_likely_toc(text):
    """대사 및 일반 문장을 걸러내고 목차일 확률이 높은 것만 반환"""
    clean = text.strip()
    if not clean or len(clean) > 50: return False
    
    # 1. 대사 기호로 시작하면 즉시 제외
    if re.match(r'^[{"\'「『〈\-\s\.]', clean): return False
    
    # 2. 목차 핵심 패턴 (숫자, 제X화, Chapter 등)
    toc_patterns = [
        r'^제\s?\d+.*',        # 제 1화, 제1장
        r'^\d+[\.\s].*',       # 1. 목차, 01 목차
        r'^[Pp]art\s?\d+.*',   # Part 1
        r'^[Cc]hapter\s?\d+.*',# Chapter 5
        r'^[\[\<].+?[\]\>]',   # [1화], <공지>
        r'.*?[\(\[\<]\d+[\)\]\>]', # 제목 (1)
        r'^[Ee]pilogue|^[Pp]rologue|외전|후기'
    ]
    
    return any(re.search(p, clean) for p in toc_patterns)

# --- 4. UI 레이아웃 ---
st.set_page_config(page_title="TOC Master Pro", layout="wide")
st.title("🧠 목차 패턴 학습기 (인식률 최적화 버전)")

if 'db' not in st.session_state:
    st.session_state.db = load_db()

# 사이드바 설정
st.sidebar.title("🛠️ 데이터 컨트롤")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

# 다운로드 버튼
db_json = json.dumps(st.session_state.db, indent=4, ensure_all_ascii=False)
st.sidebar.download_button("💾 데이터(JSON) 다운로드", db_json, "patterns.json", "application/json")

tab1, tab2 = st.tabs(["📊 지능형 패턴 추출", "⚙️ 학습 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("소설 파일을 업로드하세요", type=['txt'])
    if uploaded_file:
        raw_bytes = uploaded_file.getvalue()
        content, used_enc = smart_decode(raw_bytes)
        
        st.success(f"✅ 인식된 인코딩: **{used_enc}**")
        
        with st.expander("📄 데이터 무결성 확인 (상단 10줄)"):
            st.text("\n".join(content.splitlines()[:10]))

        lines = content.splitlines()
        candidates = []
        for i, line in enumerate(lines):
            if is_likely_toc(line):
                candidates.append({"line": i + 1, "text": line.strip()})

        if not candidates:
            st.warning("분석 결과, 목차로 추정되는 라인이 없습니다. 필터를 조정해 보세요.")
        else:
            with st.form("learning_form"):
                st.subheader(f"✅ 발견된 후보군: {len(candidates)}개")
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    if cols[idx % 2].checkbox(f"L{cand['line']}: {cand['text']}", key=f"chk_{idx}"):
                        selected_items.append(cand['text'])
                
                if st.form_submit_button("📌 선택 패턴 축적"):
                    if selected_items:
                        for item in selected_items:
                            # 패턴 일반화: 숫자 -> [NUM], 따옴표 제거 등
                            p_rule = re.escape(item)
                            p_rule = re.sub(r'\d+', '[NUM]', p_rule)
                            
                            found = False
                            for p in st.session_state.db['patterns']:
                                if p['rule'] == p_rule:
                                    p['weight'] += 1
                                    found = True
                                    break
                            if not found:
                                st.session_state.db['patterns'].append({"rule": p_rule, "example": item, "weight": 1})
                        
                        save_db(st.session_state.db)
                        st.success(f"{len(selected_items)}개의 패턴이 성공적으로 학습되었습니다!")
                        st.rerun()

with tab2:
    st.subheader("⚙️ 축적된 패턴 데이터베이스")
    db = st.session_state.db
    if not db['patterns']:
        st.info("현재 저장된 패턴이 없습니다.")
    else:
        for i, p in enumerate(sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)):
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"가중치: {p['weight']}")
            if c3.button("삭제", key=f"del_{i}"):
                st.session_state.db['patterns'].pop(i)
                save_db(st.session_state.db)
                st.rerun()

# --- 5. 제미나이 정규식 생성 (인식률 향상 프롬프트) ---
if api_key and st.sidebar.button("✨ 최적 정규식 생성"):
    if not st.session_state.db['patterns']:
        st.sidebar.error("학습된 데이터가 없습니다.")
    else:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            p_info = "\n".join([f"패턴: {p['rule']}, 예시: {p['example']}" for p in st.session_state.db['patterns']])
            
            prompt = f"""
            너는 정규표현식 전문가야. 아래의 소설 목차 패턴들을 분석해서, 
            모든 패턴을 정확히 잡아내면서도 일반 대사(특히 따옴표로 시작하는 문장)는 
            절대 포함하지 않는 '가장 우아한' 단 하나의 Python 정규식을 만들어줘.
            
            [학습 데이터]
            {p_info}
            
            결과물은 설명 없이 raw string 형태의 정규식만 출력해.
            """
            resp = model.generate_content(prompt)
            st.sidebar.success("추천 정규식:")
            st.sidebar.code(resp.text.strip())
        except Exception as e:
            st.sidebar.error(f"오류 발생: {e}")
