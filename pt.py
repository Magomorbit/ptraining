import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 누적 레이어 (Visible Database) ---
DB_FILE = "toc_database.json"

def load_persistent_db():
    """파일에서 기존 학습 데이터를 불러오거나 새로 생성"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "patterns" not in data: data["patterns"] = []
                return data
        except: pass
    return {"patterns": [], "total_learned": 0}

def save_persistent_db(data):
    """데이터를 파일에 물리적으로 저장하여 누적 보장"""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_all_ascii=False, indent=4)

# --- 2. 범용 인코딩 엔진 (EUC-KR 포함) ---
def smart_decode(raw_data, manual_enc=None):
    if manual_enc and manual_enc != "자동 감지":
        try: return raw_data.decode(manual_enc), manual_enc
        except: pass
        
    enc_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'utf-16']
    detected = chardet.detect(raw_data)
    if detected['encoding'] and detected['encoding'].lower() not in enc_list:
        enc_list.insert(0, detected['encoding'])

    for enc in enc_list:
        try:
            text = raw_data.decode(enc)
            if re.search(r'[가-힣]{2,}', text): return text, enc
        except: continue
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

# --- 3. 논리적 연속성 기반 추출기 ---
def get_logical_candidates(lines):
    raw_list = []
    for i, line in enumerate(lines):
        clean = line.strip()
        # 필터: 빈 줄, 대사, 너무 긴 줄 제외
        if not clean or len(clean) > 45 or re.match(r'^[{"\'「『〈\(]', clean): continue
        
        nums = re.findall(r'\d+', clean)
        if nums:
            raw_list.append({
                "idx": i, "text": clean, "num": int(nums[-1]), 
                "struct": re.sub(r'\d+', '[NUM]', clean), "valid": False
            })
        elif re.search(r'^[Ee]pilogue|^[Pp]rologue|외전|후기|完|공지', clean):
            raw_list.append({"idx": i, "text": clean, "num": None, "struct": "SPECIAL", "valid": True})

    # 연속성 검사 (숫자 증감 또는 구조 동일성)
    for i in range(len(raw_list)):
        curr = raw_list[i]
        if curr['num'] is None: continue
        for offset in [-1, 1, -2, 2]:
            t_idx = i + offset
            if 0 <= t_idx < len(raw_list):
                target = raw_list[t_idx]
                if target['num'] is not None:
                    if abs(curr['num'] - target['num']) <= 2 or curr['struct'] == target['struct']:
                        curr['valid'] = True
                        break
    return [c for c in raw_list if c['valid']]

# --- 4. 메인 UI 및 학습 로직 ---
st.set_page_config(page_title="TOC Master (Persistent)", layout="wide")
st.title("🧠 목차 패턴 학습기 (데이터 누적 모드)")

# DB 초기화 (세션이 아닌 파일 시스템 기준)
if 'db' not in st.session_state:
    st.session_state.db = load_persistent_db()

# 사이드바
st.sidebar.title("🛠️ 설정 및 상태")
st.sidebar.caption(f"ID: goepark | 누적 패턴 수: {len(st.session_state.db['patterns'])}개")
api_key = st.sidebar.text_input("Gemini API Key", type="password")
manual_enc = st.sidebar.selectbox("인코딩", ["자동 감지", "utf-8", "cp949", "euc-kr", "utf-16"])

# 수동 내보내기
db_json = json.dumps(st.session_state.db, indent=4, ensure_all_ascii=False)
st.sidebar.download_button("💾 누적 DB 다운로드", db_json, "toc_database.json")

tab1, tab2 = st.tabs(["📊 패턴 추출 및 학습", "⚙️ 누적 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("소설 파일을 올려주세요", type=['txt'])
    if uploaded_file:
        content, used_enc = smart_decode(uploaded_file.getvalue(), manual_enc)
        st.success(f"📍 인식 인코딩: **{used_enc}**")
        
        with st.expander("📄 본문 미리보기"):
            st.text("\n".join(content.splitlines()[:10]))

        candidates = get_logical_candidates(content.splitlines())

        if not candidates:
            st.warning("연속성 있는 패턴이 없습니다.")
        else:
            with st.form("learning_form"):
                st.subheader(f"✅ 발견된 후보: {len(candidates)}개")
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    if cols[idx % 2].checkbox(f"L{cand['idx']+1}: {cand['text']}", key=f"c_{idx}"):
                        selected_items.append(cand['text'])
                
                if st.form_submit_button("📌 선택 패턴 누적 저장"):
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
                        
                        save_persistent_db(st.session_state.db) # 파일로 물리 저장
                        st.success("데이터가 파일에 누적되었습니다!")
                        st.rerun()

with tab2:
    st.subheader("⚙️ 누적된 학습 데이터 리스트")
    db = st.session_state.db
    if not db['patterns']:
        st.info("누적된 데이터가 없습니다.")
    else:
        for i, p in enumerate(sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)):
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"가중치: {p['weight']}")
            if c3.button("삭제", key=f"del_{i}"):
                st.session_state.db['patterns'].pop(i)
                save_persistent_db(st.session_state.db)
                st.rerun()
        
        st.divider()
        if st.button("⚠️ 데이터베이스 초기화"):
            st.session_state.db = {"patterns": [], "total_learned": 0}
            save_persistent_db(st.session_state.db)
            st.rerun()

# --- 5. 제미나이 정규식 생성 ---
if api_key and st.sidebar.button("✨ 최적 정규식 생성"):
    if st.session_state.db['patterns']:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            p_list = "\n".join([f"- {p['rule']}" for p in st.session_state.db['patterns']])
            resp = model.generate_content(f"다음 목차 패턴들을 매칭하는 Python 정규식을 한 줄로 짜줘. 대사는 제외해:\n{p_list}")
            st.sidebar.code(resp.text.strip())
        except Exception as e: st.sidebar.error(f"오류: {e}")
