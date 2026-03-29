import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 관리 레이어 (안정성 강화) ---
DB_FILE = "toc_database.json"

def load_persistent_db():
    """파일이 없거나 깨졌을 때를 대비한 안전한 로드"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "patterns" in data:
                    return data
        except Exception:
            pass
    return {"patterns": [], "total_learned": 0}

def save_persistent_db(data):
    """TypeError 방지를 위해 데이터를 정제한 후 물리적 저장"""
    try:
        # 직렬화 가능한 형태로 데이터 정제
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
            json.dump(clean_data, f, ensure_all_ascii=False, indent=4)
        return True
    except Exception as e:
        st.error(f"❌ 파일 물리 저장 실패: {e}")
        return False

# --- 2. 인코딩 엔진 ---
def smart_decode(raw_data, manual_enc=None):
    if manual_enc and manual_enc != "자동 감지":
        try: return raw_data.decode(manual_enc), manual_enc
        except: pass
    
    # 한국어 우선순위 강제 적용 (cp1006 오판 방지)
    enc_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'utf-16']
    for enc in enc_list:
        try:
            text = raw_data.decode(enc)
            if re.search(r'[가-힣]{2,}', text): return text, enc
        except: continue
    
    detected = chardet.detect(raw_data)
    d_enc = detected.get('encoding')
    if d_enc:
        try: return raw_data.decode(d_enc), f"{d_enc}(추측)"
        except: pass
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

# --- 3. 목차 후보 추출 ---
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
st.title("🧠 목차 패턴 학습기 (데이터 유실 방지 버전)")

if 'db' not in st.session_state:
    st.session_state.db = load_persistent_db()

# 사이드바
st.sidebar.title("🛠️ 시스템 관리")
st.sidebar.caption(f"ID: goepark | 패턴 수: {len(st.session_state.db['patterns'])}")

# 수동 DB 병합
uploaded_db = st.sidebar.file_uploader("기존 JSON 병합", type=['json'])
if uploaded_db and st.sidebar.button("병합 실행"):
    try:
        new_data = json.load(uploaded_db)
        for new_p in new_data.get("patterns", []):
            found = False
            for old_p in st.session_state.db["patterns"]:
                if old_p["rule"] == new_p["rule"]:
                    old_p["weight"] += new_p.get("weight", 1)
                    found = True
                    break
            if not found:
                st.session_state.db["patterns"].append(new_p)
        save_persistent_db(st.session_state.db)
        st.sidebar.success("병합 성공!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"병합 실패: {e}")

# 실시간 다운로드 버튼 (안전한 직렬화 보장)
try:
    final_db_str = json.dumps(st.session_state.db, ensure_all_ascii=False, indent=4)
except:
    final_db_str = "{}"
st.sidebar.download_button("💾 현재 DB 다운로드", final_db_str, "toc_database.json", mime="application/json")

tab1, tab2 = st.tabs(["📊 패턴 학습", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("텍스트 파일 업로드", type=['txt'])
    if uploaded_file:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        content, used_enc = smart_decode(uploaded_file.getvalue())
        st.info(f"📍 인코딩: {used_enc}")
        
        candidates = get_logical_candidates(content.splitlines())
        if candidates:
            st.subheader(f"✅ 후보군 ({len(candidates)}개)")
            save_trigger = st.button("📌 선택 패턴 누적 저장", type="primary", use_container_width=True)
            
            selected_items = []
            cols = st.columns(2)
            for idx, cand in enumerate(candidates):
                if cols[idx % 2].checkbox(f"L{cand['idx']+1}: {cand['text']}", key=f"chk_{file_id}_{idx}"):
                    selected_items.append(cand['text'])
            
            if save_trigger:
                if selected_items:
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
                    
                    if save_persistent_db(st.session_state.db):
                        st.success("데이터가 물리 파일에 기록되었습니다!")
                        st.rerun()
