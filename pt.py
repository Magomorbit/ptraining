import streamlit as st
import re
import json
import os
import chardet
from datetime import datetime

# --- 설정 및 데이터 관리 ---
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

def backup_db(reason="auto"):
    """백업 기능 (비밀 유지)"""
    if os.path.exists(LEARNING_DB):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"backup_{reason}_{timestamp}.json", "w", encoding="utf-8") as b:
            json.dump(load_db(), b, ensure_all_ascii=False)

def analyze_pattern(text):
    """목차의 추상적 규칙 생성"""
    pattern = re.sub(r'\d+', '[NUM]', text)
    return pattern

# --- UI 레이아웃 ---
st.set_page_config(page_title="TOC Pattern Manager", layout="wide")
st.title("🧠 제미나이 전용: 목차 패턴 학습 및 관리")

tab1, tab2 = st.tabs(["📊 패턴 학습 (파일 업로드)", "⚙️ 데이터 관리 및 삭제"])

# --- TAB 1: 패턴 학습 ---
with tab1:
    uploaded_file = st.file_uploader("패턴을 추출할 소설 TXT 업로드", type=['txt'])
    if uploaded_file:
        raw = uploaded_file.read()
        enc = chardet.detect(raw)['encoding'] or 'utf-8'
        content = raw.decode(enc)
        lines = content.splitlines()

        candidates = []
        for i, line in enumerate(lines):
            clean = line.strip()
            if not clean or len(clean) > 30: continue
            if re.search(r'제\s?\d+|^\d+[\.\s]|^[\[\<].+?[\]\>]|Part|Chapter', clean):
                candidates.append({"line": i, "text": clean})

        st.subheader("✅ 실제 목차 선택")
        selected_items = []
        cols = st.columns(2)
        for idx, cand in enumerate(candidates):
            target_col = cols[idx % 2]
            if target_col.checkbox(f"[{cand['line']}] {cand['text']}", key=f"c_{idx}"):
                selected_items.append(cand['text'])

        if st.button("📌 선택한 패턴 학습 저장"):
            if not selected_items:
                st.warning("선택된 항목이 없습니다.")
            else:
                db = load_db()
                for item in selected_items:
                    abstract = analyze_pattern(item)
                    # 패턴 업데이트
                    pattern_exists = False
                    for p in db['patterns']:
                        if p['rule'] == abstract:
                            p['weight'] += 1
                            pattern_exists = True
                            break
                    if not pattern_exists:
                        db['patterns'].append({"rule": abstract, "example": item, "weight": 1})
                    
                    if item not in db['raw_examples']:
                        db['raw_examples'].append(item)
                
                db['total_count'] = len(db['raw_examples'])
                save_db(db)
                st.success(f"학습 완료! 현재 총 {db['total_count']}개의 데이터가 축적되었습니다.")

# --- TAB 2: 데이터 관리 및 삭제 ---
with tab2:
    st.subheader("🗑️ 저장된 패턴 관리")
    db = load_db()
    
    if not db['patterns']:
        st.info("아직 저장된 패턴이 없습니다.")
    else:
        # 가중치 높은 순으로 정렬
        sorted_patterns = sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)
        
        for i, p in enumerate(sorted_patterns):
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.write(f"**패턴:** `{p['rule']}`")
            col2.write(f"**예시:** {p['example']} (빈도: {p['weight']})")
            if col3.button("삭제", key=f"del_{i}"):
                # 삭제 전 백업
                backup_db(reason="before_delete")
                # 해당 패턴 삭제
                db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
                # 관련 raw_examples도 일부 정리 (패턴에 맞는 것들)
                # (주의: raw_examples는 참고용이므로 유지하거나 필요시 전체 초기화 지원)
                save_db(db)
                st.rerun()

        st.divider()
        if st.button("⚠️ 모든 학습 데이터 초기화", type="secondary"):
            backup_db(reason="reset")
            save_db({"total_count": 0, "patterns": [], "raw_examples": []})
            st.success("데이터가 초기화되었습니다. (백업 파일 생성됨)")

# --- 제미나이 전달용 텍스트 ---
st.sidebar.title("🚀 AI 전달용 데이터")
db_final = load_db()
if db_final['patterns']:
    instruction = "### [목차 인식 패턴 가이드]\n"
    for p in sorted(db_final['patterns'], key=lambda x: x['weight'], reverse=True):
        instruction += f"- {p['rule']} (중요도: {p['weight']})\n"
    
    st.sidebar.text_area("복사하여 제미나이에게 전달:", value=instruction, height=300)
else:
    st.sidebar.write("학습 데이터 없음")

# 비밀 동기화/백업 버튼
if st.sidebar.button("Internal Sync", help="비밀 백업 및 동기화"):
    backup_db(reason="manual")
    st.sidebar.write("✅ 시스템 백업 완료")

import google.generativeai as genai

# --- 제미나이 API 설정 ---
st.sidebar.divider()
st.sidebar.subheader("🤖 제미나이 AI 연동")
api_key = st.sidebar.text_input("Gemini API Key를 입력하세요", type="password")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

def generate_regex_with_gemini(db_data):
    """학습 데이터를 기반으로 제미나이에게 정규식 생성을 요청"""
    # 학습 데이터 요약
    patterns_str = ""
    for p in sorted(db_data['patterns'], key=lambda x: x['weight'], reverse=True):
        patterns_str += f"- 패턴 규칙: {p['rule']} (실제 예시: {p['example']}, 빈도: {p['weight']})\n"
    
    prompt = f"""
    너는 정규표현식 전문가야. 아래는 소설 파일에서 추출한 '실제 목차' 패턴들이야.
    이 패턴들을 모두 포괄하면서, 일반적인 본문 문장과 겹치지 않는 최적의 Python 정규표현식(Regex)을 하나만 만들어줘.
    
    [학습된 패턴 데이터]
    {patterns_str}
    
    [요구사항]
    1. `re.search()` 또는 `re.match()`에서 사용할 수 있는 형태여야 함.
    2. 가중치(빈도)가 높은 패턴을 최우선으로 고려할 것.
    3. 결과물은 코드 블럭 없이 정규식 문자열만 출력해줘. (예: ^제\s?\d+\s?[화장])
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"오류 발생: {str(e)}"

# --- UI 반영 (데이터 관리 탭 하단 혹은 사이드바) ---
if st.sidebar.button("✨ 최적의 정규식 생성하기"):
    if not api_key:
        st.sidebar.error("API Key가 필요합니다.")
    else:
        db = load_db()
        if not db['patterns']:
            st.sidebar.warning("학습된 데이터가 없습니다.")
        else:
            with st.spinner("제미나이가 패턴을 분석 중..."):
                final_regex = generate_regex_with_gemini(db)
                st.session_state['generated_regex'] = final_regex

if 'generated_regex' in st.session_state:
    st.info("### 🎯 제미나이가 생성한 최적의 정규식")
    st.code(st.session_state['generated_regex'], language='python')
    st.success("이 정규표현식을 변환기 앱의 목차 인식 로직에 그대로 사용하세요.")
