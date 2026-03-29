import streamlit as st
import re
import json
import os
import chardet

# --- 1. 데이터 관리 레이어 ---
DB_FILE = "toc_database.json"

def load_persistent_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "patterns" in data:
                    return data
        except:
            pass
    return {"patterns": [], "total_learned": 0}

def save_persistent_db(data):
    """ensure_ascii=False 로 수정하여 한글 저장 보장"""
    try:
        clean_data = {
            "patterns": [
                {
                    "rule": str(p["rule"]),
                    "example": str(p["example"]),
                    "weight": int(p["weight"])
                } for p in data.get("patterns", [])
            ],
            "total_learned": int(data.get("total_learned", 0))
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            # [수정 완료] ensure_all_ascii -> ensure_ascii
            json.dump(clean_data, f, ensure_ascii=False, indent=4)
        
        st.session_state.db = clean_data
        return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False

# --- 2. 인코딩 엔진 ---
def smart_decode(raw_data, manual_enc=None):
    if manual_enc and manual_enc != "자동 감지":
        try: return raw_data.decode(manual_enc), manual_enc
        except: pass
    enc_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'utf-16']
    for enc in enc_list:
        try:
            text = raw_data.decode(enc)
            if re.search(r'[가-힣]{2,}', text): return text, enc
        except: continue
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

# --- 3. 목차 후보 추출 ---
def get_logical_candidates(lines):
    raw_list = []
    for i, line in enumerate(lines):
        clean = line.strip()
        if not clean or len(clean) > 50 or re.match(r'^[{"\'「『〈\(]', clean): continue
        nums = re.findall(r'\d+', clean)
        if nums:
            raw_list.append({"idx": i, "text": str(clean), "num": int(nums[-1]), "struct": re.sub(r'\d+', '[NUM]', clean), "valid": False})
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
st.set_page_config(page_title="TOC Master (Final Fix)", layout="wide")
st.title("🧠 목차 패턴 학습기")

if 'db' not in st.session_state:
    st.session_state.db = load_persistent_db()

# 사이드바
st.sidebar.title("🛠️ 시스템 관리")
st.sidebar.caption(f"ID: goepark | 패턴 수: {len(st.session_state.db['patterns'])}")

# 다운로드 버튼 (수정 완료)
try:
    final_db_str = json.dumps(st.session_state.db, ensure_ascii=False, indent=4)
except:
    final_db_str = "{}"
st.sidebar.download_button("💾 현재 DB 다운로드", final_db_str, "toc_database.json")

tab1, tab2 = st.tabs(["📊 패턴 학습", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("텍스트 파일 업로드", type=['txt'])
    if uploaded_file:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        content, used_enc = smart_decode(uploaded_file.getvalue())
        
        candidates = get_logical_candidates(content.splitlines())
        if candidates:
            st.subheader(f"✅ 후보군 ({len(candidates)}개)")
            
            # 저장 버튼을 상단에 배치
            if st.button("📌 선택 패턴 누적 저장", type="primary", use_container_width=True):
                selected_items = [c['text'] for idx, c in enumerate(candidates) if st.session_state.get(f"chk_{file_id}_{idx}")]
                
                if selected_items:
                    current_db = load_persistent_db()
                    for item in selected_items:
                        rule = re.sub(r'\d+', '[NUM]', re.escape(str(item)))
                        found = False
                        for p in current_db['patterns']:
                            if p['rule'] == rule:
                                p['weight'] += 1
                                found = True
                                break
                        if not found:
                            current_db['patterns'].append({"rule": rule, "example": str(item), "weight": 1})
                    
                    if save_persistent_db(current_db):
                        st.success("저장 완료!")
                        st.rerun()
                else:
                    st.warning("선택된 패턴이 없습니다.")
            
            st.divider()
            cols = st.columns(2)
            for idx, cand in enumerate(candidates):
                cols[idx % 2].checkbox(f"L{cand['idx']+1}: {cand['text']}", key=f"chk_{file_id}_{idx}")

with tab2:
    # 데이터 관리 탭에 진입할 때마다 최신 파일을 읽어옴
    current_db = load_persistent_db()
    st.subheader(f"⚙️ 누적 패턴 리스트 (총 {len(current_db['patterns'])}개)")
    
    if not current_db['patterns']:
        st.info("학습된 데이터가 없습니다.")
    else:
        patterns = sorted(current_db['patterns'], key=lambda x: x['weight'], reverse=True)
        for i, p in enumerate(patterns):
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"W: {p['weight']}")
            if c3.button("삭제", key=f"del_{i}"):
                current_db['patterns'] = [item for item in current_db['patterns'] if item['rule'] != p['rule']]
                save_persistent_db(current_db)
                st.rerun()
