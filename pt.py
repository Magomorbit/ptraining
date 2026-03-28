import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 누적 레이어 (Visible Database) ---
DB_FILE = "toc_database.json"

def load_persistent_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 데이터 구조 강제 교정
                if not isinstance(data, dict): data = {}
                if "patterns" not in data: data["patterns"] = []
                return data
        except Exception:
            pass
    return {"patterns": [], "total_learned": 0}

def save_persistent_db(data):
    # JSON 직렬화 에러 방지: 모든 키와 값을 안전하게 변환
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_all_ascii=False, indent=4)
    except Exception as e:
        st.error(f"데이터 저장 중 오류 발생: {e}")

# --- 2. [강화] 인코딩 엔진 (한국어 우선 순위) ---
def smart_decode(raw_data, manual_enc=None):
    if manual_enc and manual_enc != "자동 감지":
        try: return raw_data.decode(manual_enc), manual_enc
        except: pass
        
    # 한국어 텍스트에서 가장 흔한 순서대로 강제 시도
    # chardet은 이 뒤에 보조용으로만 사용 (cp1006 같은 오판 방지)
    enc_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'utf-16']
    
    for enc in enc_list:
        try:
            text = raw_data.decode(enc)
            # 실제 한글 문자가 포함되어 있는지 엄격하게 검증
            if re.search(r'[가-힣]{2,}', text): 
                return text, enc
        except: continue
        
    # 위 방식이 실패했을 때만 chardet 사용
    detected = chardet.detect(raw_data)
    d_enc = detected['encoding']
    if d_enc:
        try:
            return raw_data.decode(d_enc), f"{d_enc} (추측)"
        except: pass
        
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

# --- 3. 목차 추출 로직 (연속성 강화) ---
def get_logical_candidates(lines):
    raw_list = []
    for i, line in enumerate(lines):
        clean = line.strip()
        if not clean or len(clean) > 50 or re.match(r'^[{"\'「『〈\(]', clean): continue
        
        nums = re.findall(r'\d+', clean)
        if nums:
            raw_list.append({
                "idx": i, "text": str(clean), "num": int(nums[-1]), 
                "struct": re.sub(r'\d+', '[NUM]', clean), "valid": False
            })
        elif re.search(r'^[Ee]pilogue|^[Pp]rologue|외전|후기|完|공지', clean):
            raw_list.append({"idx": i, "text": str(clean), "num": None, "struct": "SPECIAL", "valid": True})

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

# --- 4. 메인 UI ---
st.set_page_config(page_title="TOC Master (Fix)", layout="wide")
st.title("🧠 목차 패턴 학습기 (오류 수정 버전)")

if 'db' not in st.session_state:
    st.session_state.db = load_persistent_db()

st.sidebar.title("🛠️ 설정")
api_key = st.sidebar.text_input("Gemini API Key", type="password")
manual_enc = st.sidebar.selectbox("인코딩 강제 지정", ["자동 감지", "utf-8", "cp949", "euc-kr"])

# JSON 에러 방지용 안전한 다운로드 준비
try:
    db_json = json.dumps(st.session_state.db, indent=4, ensure_all_ascii=False)
except:
    db_json = "{}"

st.sidebar.download_button("💾 누적 데이터 다운로드", db_json, "toc_database.json")

tab1, tab2 = st.tabs(["📊 패턴 학습", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("파일 업로드", type=['txt'])
    if uploaded_file:
        raw_bytes = uploaded_file.getvalue()
        content, used_enc = smart_decode(raw_bytes, manual_enc)
        
        # cp1006 같은 황당한 결과가 나왔을 때를 위한 경고
        if 'cp1006' in used_enc.lower():
            st.warning("⚠️ 인코딩이 잘못 인식된 것 같습니다. 사이드바에서 'cp949' 또는 'utf-8'로 강제 지정해 보세요.")
        
        st.success(f"📍 사용된 인코딩: **{used_enc}**")
        
        with st.expander("📄 미리보기"):
            st.text("\n".join(content.splitlines()[:10]))

        candidates = get_logical_candidates(content.splitlines())

        if not candidates:
            st.warning("패턴을 찾지 못했습니다.")
        else:
            with st.form("learning_form"):
                selected_items = []
                cols = st.columns(2)
                for idx, cand in enumerate(candidates):
                    if cols[idx % 2].checkbox(f"L{cand['idx']+1}: {cand['text']}", key=f"c_{idx}"):
                        selected_items.append(cand['text'])
                
                if st.form_submit_button("📌 패턴 누적 저장"):
                    for item in selected_items:
                        rule = re.sub(r'\d+', '[NUM]', re.escape(str(item)))
                        found = False
                        for p in st.session_state.db['patterns']:
                            if p['rule'] == rule:
                                p['weight'] += 1
                                found = True
                                break
                        if not found:
                            st.session_state.db['patterns'].append({"rule": rule, "example": str(item), "weight": 1})
                    
                    save_persistent_db(st.session_state.db)
                    st.success("데이터가 누적되었습니다.")
                    st.rerun()

with tab2:
    st.subheader("⚙️ 누적된 패턴 리스트")
    db = st.session_state.db
    for i, p in enumerate(sorted(db.get('patterns', []), key=lambda x: x['weight'], reverse=True)):
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.code(p['rule'].replace("\\", ""))
        c2.write(f"W: {p['weight']}")
        if c3.button("삭제", key=f"del_{i}"):
            st.session_state.db['patterns'].pop(i)
            save_persistent_db(st.session_state.db)
            st.rerun()
