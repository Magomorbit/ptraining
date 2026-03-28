import streamlit as st
import re
import json
import os
import chardet
import google.generativeai as genai

# --- 1. 데이터 관리 레이어 ---
DB_FILE = "toc_database.json"

def load_persistent_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "patterns" not in data: data["patterns"] = []
                return data
        except: pass
    return {"patterns": [], "total_learned": 0}

def save_persistent_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_all_ascii=False, indent=4)
    except Exception as e:
        st.error(f"데이터 저장 실패: {e}")

def merge_db(uploaded_json):
    try:
        new_data = json.load(uploaded_json)
        current_db = st.session_state.db
        for new_p in new_data.get("patterns", []):
            found = False
            for old_p in current_db["patterns"]:
                if old_p["rule"] == new_p["rule"]:
                    old_p["weight"] += new_p.get("weight", 1)
                    found = True
                    break
            if not found:
                current_db["patterns"].append(new_p)
        save_persistent_db(current_db)
        return True
    except Exception as e:
        st.error(f"JSON 병합 중 오류: {e}")
        return False

# --- 2. 인코딩 및 추출 로직 ---
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
    d_enc = detected['encoding']
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

# --- 3. 메인 UI ---
st.set_page_config(page_title="TOC Master (UI Opt)", layout="wide")
st.title("🧠 목차 패턴 학습기")

if 'db' not in st.session_state:
    st.session_state.db = load_persistent_db()

# 사이드바 관리
st.sidebar.title("🛠️ 시스템 관리")
st.sidebar.caption(f"ID: goepark | 누적 패턴: {len(st.session_state.db['patterns'])}개")

uploaded_db = st.sidebar.file_uploader("JSON DB 파일 병합", type=['json'], key="db_uploader")
if uploaded_db and st.sidebar.button("데이터 병합 실행"):
    if merge_db(uploaded_db):
        st.sidebar.success("병합 완료!")
        st.rerun()

st.sidebar.divider()
api_key = st.sidebar.text_input("Gemini API Key", type="password")
manual_enc = st.sidebar.selectbox("인코딩", ["자동 감지", "utf-8", "cp949", "euc-kr"])

try:
    db_json = json.dumps(st.session_state.db, indent=4, ensure_all_ascii=False)
except:
    db_json = "{}"
st.sidebar.download_button("💾 현재 DB 다운로드", db_json, "toc_database.json")

tab1, tab2 = st.tabs(["📊 패턴 학습", "⚙️ 데이터 관리"])

with tab1:
    uploaded_file = st.file_uploader("텍스트 파일 업로드", type=['txt'])
    
    if uploaded_file:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        content, used_enc = smart_decode(uploaded_file.getvalue(), manual_enc)
        st.info(f"📍 인코딩: **{used_enc}**")
        
        candidates = get_logical_candidates(content.splitlines())

        if not candidates:
            st.warning("후보를 찾지 못했습니다.")
        else:
            # [수정] 폼 대신 일반 컨테이너를 사용하고 버튼을 상단에 배치
            st.subheader(f"✅ 후보군 ({len(candidates)}개)")
            
            # 저장 버튼을 상단에 고정
            save_trigger = st.button("📌 선택한 패턴들 누적 저장", type="primary", use_container_width=True)
            
            st.divider()
            
            selected_items = []
            cols = st.columns(2)
            for idx, cand in enumerate(candidates):
                # 파일 변경 시 초기화를 위해 file_id 포함된 키 사용
                if cols[idx % 2].checkbox(f"L{cand['idx']+1}: {cand['text']}", key=f"chk_{file_id}_{idx}"):
                    selected_items.append(cand['text'])
            
            # 버튼 클릭 시 로직 수행
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
                    
                    save_persistent_db(st.session_state.db)
                    st.success(f"{len(selected_items)}개 패턴 저장 완료!")
                    st.rerun()
                else:
                    st.warning("선택된 패턴이 없습니다.")

with tab2:
    st.subheader("⚙️ 누적 패턴 리스트")
    db = st.session_state.db
    patterns = sorted(db.get('patterns', []), key=lambda x: x['weight'], reverse=True)
    
    for i, p in enumerate(patterns):
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.code(p['rule'].replace("\\", ""))
        c2.write(f"W: {p['weight']}")
        if c3.button("삭제", key=f"del_{i}"):
            st.session_state.db['patterns'] = [item for item in db['patterns'] if item['rule'] != p['rule']]
            save_persistent_db(st.session_state.db)
            st.rerun()

if api_key and st.sidebar.button("✨ 최적 정규식 생성"):
    if st.session_state.db['patterns']:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            p_list = "\n".join([f"- {p['rule']}" for p in st.session_state.db['patterns']])
            resp = model.generate_content(f"다음 목차 패턴들을 매칭하는 Python 정규식을 한 줄로 짜줘. 대사는 제외해:\n{p_list}")
            st.sidebar.code(resp.text.strip())
        except Exception as e: st.sidebar.error(f"오류: {e}")
