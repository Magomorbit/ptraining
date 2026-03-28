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

# --- 2. 지능형 디코딩 ---
def smart_decode(raw_data):
    for enc in ['utf-8-sig', 'cp949', 'utf-8', 'euc-kr']:
        try:
            text = raw_data.decode(enc)
            if re.search(r'[가-힣]', text): return text, enc
        except: continue
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

# --- 3. [핵심] 연속성 기반 목차 추출기 ---
def get_refined_candidates(lines):
    raw_candidates = []
    
    # 1단계: 기본적인 형태를 갖춘 후보군 1차 수집
    for i, line in enumerate(lines):
        clean = line.strip()
        if not clean or len(clean) > 40 or re.match(r'^[{"\'「『〈]', clean): continue
        
        # 숫자 추출 시도
        nums = re.findall(r'\d+', clean)
        if nums:
            raw_candidates.append({
                "line_idx": i,
                "text": clean,
                "num": int(nums[0]), # 첫 번째 발견된 숫자를 기준점으로 삼음
                "valid": False
            })
        elif re.search(r'^[Ee]pilogue|^[Pp]rologue|외전|후기', clean):
            raw_candidates.append({"line_idx": i, "text": clean, "num": None, "valid": True})

    # 2단계: 연속성(Continuity) 검증
    # 앞뒤 후보와 숫자가 1씩 증가하거나, 줄 간격이 일정한지 체크
    for i in range(len(raw_candidates)):
        curr = raw_candidates[i]
        if curr['num'] is None: continue # 특수 목차는 패스
        
        # 앞뒤 2개씩 뒤져서 연속성 확인
        for offset in [-1, 1]:
            target_idx = i + offset
            if 0 <= target_idx < len(raw_candidates):
                target = raw_candidates[target_idx]
                if target['num'] is not None:
                    # 숫자가 1 차이나면 '연속된 목차'로 강력하게 의심
                    if abs(curr['num'] - target['num']) == 1:
                        curr['valid'] = True
                        break
    
    # 연속성이 증명된 것 + 특수 목차만 반환
    return [c for c in raw_candidates if c['valid']]

# --- 4. UI 구성 ---
st.set_page_config(page_title="TOC Continuity Master", layout="wide")
st.title("🧠 목차 패턴 학습기 (연속성 인식 버전)")

if 'db' not in st.session_state:
    st.session_state.db = load_db()

api_key = st.sidebar.text_input("Gemini API Key", type="password")

tab1, tab2 = st.tabs(["📊 지능형 추출", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("소설 TXT 파일을 업로드하세요", type=['txt'])
    if uploaded_file:
        content, used_enc = smart_decode(uploaded_file.getvalue())
        st.caption(f"ℹ️ 인코딩: {used_enc}")
        
        lines = content.splitlines()
        candidates = get_refined_candidates(lines)

        if not candidates:
            st.warning("연속적인 목차 패턴을 찾지 못했습니다. 수동으로 데이터를 쌓아주세요.")
        else:
            with st.form("learning_form"):
                st.subheader(f"✅ 연속성이 확인된 후보군: {len(candidates)}개")
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    # 줄 번호와 함께 표시하여 신뢰도 상승
                    if cols[idx % 2].checkbox(f"L{cand['line_idx']+1}: {cand['text']}", key=f"k_{idx}"):
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
                        st.success("연속성 기반 데이터가 저장되었습니다!")
                        st.rerun()

with tab2:
    db = st.session_state.db
    if db['patterns']:
        for i, p in enumerate(sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)):
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"가중치: {p['weight']}")
            if c3.button("삭제", key=f"del_{i}"):
                st.session_state.db['patterns'].pop(i)
                save_db(st.session_state.db)
                st.rerun()
