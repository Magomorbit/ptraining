import streamlit as st
import re
import json
import os
import chardet

# --- 1. 데이터 레이어 (물리 파일 및 세션 동기화) ---
DB_FILE = "toc_database.json"

def load_persistent_db():
    """파일에서 데이터를 로드하고 구조를 보장함"""
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
    """TypeError 방지를 위한 데이터 정제 및 ensure_ascii=False 적용"""
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
            json.dump(clean_data, f, ensure_ascii=False, indent=4)
        
        # 세션 상태 즉시 갱신
        st.session_state.db = clean_data
        return True
    except Exception as e:
        st.error(f"❌ 파일 저장 에러: {e}")
        return False

def merge_db(uploaded_json):
    """외부 JSON 파일을 현재 DB와 안전하게 병합"""
    try:
        new_data = json.load(uploaded_json)
        current_db = load_persistent_db()
        for new_p in new_data.get("patterns", []):
            found = False
            for old_p in current_db["patterns"]:
                if old_p["rule"] == new_p["rule"]:
                    old_p["weight"] += new_p.get("weight", 1)
                    found = True
                    break
            if not found:
                current_db["patterns"].append(new_p)
        return save_persistent_db(current_db)
    except Exception as e:
        st.error(f"❌ JSON 병합 에러: {e}")
        return False

# --- 2. 텍스트 엔진 (인코딩 및 추출) ---
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
        
    detected = chardet.detect(raw_data)
    d_enc = detected.get('encoding')
    if d_enc:
        try: return raw_data.decode(d_enc), f"{d_enc}(추측)"
        except: pass
    return raw_data.decode('utf-8', errors='ignore'), 'utf-8(fallback)'

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

# --- 3. UI 메인 레이아웃 ---
st.set_page_config(page_title="TOC Master (Perfect)", layout="wide")
st.title("🧠 목차 패턴 학습기")

if 'db' not in st.session_state:
    st.session_state.db = load_persistent_db()

# 사이드바 관리 영역
st.sidebar.title("🛠️ 시스템 관리")
st.sidebar.caption(f"ID: goepark | 패턴: {len(st.session_state.db['patterns'])}개")

# [기능] JSON 불러오기
uploaded_db_file = st.sidebar.file_uploader("📥 기존 데이터 병합", type=['json'], key="side_uploader")
if uploaded_db_file and st.sidebar.button("병합 실행", type="secondary"):
    if merge_db(uploaded_db_file):
        st.sidebar.success("성공적으로 병합되었습니다!")
        st.rerun()

st.sidebar.divider()
manual_enc = st.sidebar.selectbox("인코딩 강제 설정", ["자동 감지", "utf-8", "cp949", "euc-kr"])

# [기능] 현재 DB 다운로드
try:
    final_db_str = json.dumps(st.session_state.db, ensure_ascii=False, indent=4)
except:
    final_db_str = "{}"
st.sidebar.download_button("💾 현재 DB 다운로드", final_db_str, "toc_database.json", mime="application/json")

tab1, tab2 = st.tabs(["📊 패턴 학습", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("텍스트 파일 업로드", type=['txt'])
    
    if uploaded_file:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        content, used_enc = smart_decode(uploaded_file.getvalue(), manual_enc)
        st.info(f"📍 인식된 인코딩: **{used_enc}**")
        
        candidates = get_logical_candidates(content.splitlines())
        if not candidates:
            st.warning("후보를 찾지 못했습니다.")
        else:
            st.subheader(f"✅ 후보군 ({len(candidates)}개)")
            
            # [기능] 저장 버튼 상단 배치
            if st.button("📌 선택 패턴 누적 저장", type="primary", use_container_width=True):
                selected = [c['text'] for idx, c in enumerate(candidates) if st.session_state.get(f"chk_{file_id}_{idx}")]
                if selected:
                    db = load_persistent_db()
                    for item in selected:
                        rule = re.sub(r'\d+', '[NUM]', re.escape(str(item)))
                        found = False
                        for p in db['patterns']:
                            if p['rule'] == rule:
                                p['weight'] += 1
                                found = True
                                break
                        if not found:
                            db['patterns'].append({"rule": rule, "example": str(item), "weight": 1})
                    
                    if save_persistent_db(db):
                        st.success("저장 완료!")
                        st.rerun()
                else:
                    st.warning("선택된 패턴이 없습니다.")
            
            st.divider()
            
            # [기능] 체크박스 리스트 (file_id를 활용한 리프레시 보장)
            cols = st.columns(2)
            for idx, cand in enumerate(candidates):
                cols[idx % 2].checkbox(f"L{cand['idx']+1}: {cand['text']}", key=f"chk_{file_id}_{idx}")

with tab2:
    db = load_persistent_db()
    st.subheader(f"⚙️ 누적 패턴 리스트 (총 {len(db['patterns'])}개)")
    
    if not db['patterns']:
        st.info("저장된 패턴이 없습니다.")
    else:
        # 가중치 순 정렬 출력
        sorted_patterns = sorted(db['patterns'], key=lambda x: x['weight'], reverse=True)
        for i, p in enumerate(sorted_patterns):
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.code(p['rule'].replace("\\", ""))
            c2.write(f"W: {p['weight']}")
            if c3.button("삭제", key=f"del_{i}"):
                db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
                save_persistent_db(db)
                st.rerun()
