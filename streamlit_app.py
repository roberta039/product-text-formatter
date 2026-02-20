import streamlit as st
import unicodedata
import re
from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator

st.set_page_config(page_title="Product Text Formatter", layout="centered")

def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    replacements = {"ș":"s","Ş":"S","ț":"t","Ţ":"T","ă":"a","Ă":"A","â":"a","Â":"A","î":"i","Î":"I"}
    for a,b in replacements.items():
        no_marks = no_marks.replace(a,b)
    no_marks = re.sub(r"[ \t]+\n", "\n", no_marks)
    no_marks = re.sub(r"\n{3,}", "\n\n", no_marks)
    return no_marks

def normalize(text: str) -> str:
    return (text or "").replace("\r\n","\n").replace("\r","\n")

def norm_key(k: str) -> str:
    k = remove_diacritics(k or "").lower().strip()
    k = re.sub(r"\s+"," ",k)
    return k

BANNED_KEYS = {
    "tara de origine","country of origin",
    "cod unic de inregistrare","cod unic de înregistrare",
    "cod","code","cod articol","article code",
    "model","marca","marcă","brand",
    "numarul paginii din catalog","catalog page number","catalogue page number",
    "cod de bare","bar code","barcode",
    "nume in catalog",
    "catalogue","catalog","catalogue (title / chapter / page)","catalog (title / chapter / page)",
    "pachet","package","pack",
}

def is_banned_key(key: str) -> bool:
    k = norm_key(key)
    banned_norm = {norm_key(x) for x in BANNED_KEYS}
    if k in banned_norm:
        return True
    banned_sub = ["tara de origine","country of origin","catalogue","catalog","cod unic","numarul paginii din catalog","catalog page number",
                  "cod de bare","bar code","barcode","cod articol","article code"]
    return any(s in k for s in banned_sub) or k in {norm_key("cod"),norm_key("code"),norm_key("model"),norm_key("marca"),norm_key("brand"),
                                                   norm_key("package"),norm_key("pachet"),norm_key("pack")}

KEY_MAP = {
    "color":"Culoare","net weight":"Greutate neta","weight":"Greutate","material":"Material",
    "dimensions":"Dimensiuni","dimension":"Dimensiuni","size":"Dimensiuni","dimenzija":"Dimensiuni",
    "capacity":"Capacitate","performance":"Performanta","additional equipment":"Echipamente suplimentare",
    "measures":"Dimensiuni produs","ctn dimesions":"Dimensiuni carton","ctn dimensions":"Dimensiuni carton",
    "ctn weight":"Greutate carton","carton":"Bucati / carton"
}
def map_key_to_ro(key: str) -> str:
    return KEY_MAP.get(norm_key(key), key.strip())

@st.cache_data(show_spinner=False)
def translate_to_ro(text: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="ro").translate(text)
    except Exception:
        return text

EN_HINT_WORDS = {"pocket","zip","zippers","connector","lock","waterproof","nylon","gift","packaging",
                 "front","hidden","back","laptop","tablet","business","executive","anti-theft","type-c","usb",
                 "black","white","grey","gray","blue","red","green","leather","extendable","trolley","strap",
                 "technical","information","additional","material","made of","offers"}

def looks_english_or_foreign(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = remove_diacritics(t).lower()
    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in EN_HINT_WORDS):
        return True
    if re.fullmatch(r"[A-Za-z0-9 \-–—,:;\"'()\[\]/\.\n]+", t) and not re.search(r"\b(si|sau|pentru|cu|din|este|sunt)\b", low):
        return True
    return False

@st.cache_data(show_spinner=False)
def detect_lang_safe(text: str) -> str:
    try:
        sample = re.sub(r"\s+"," ", (text or "")).strip()
        if len(sample) < 50:
            return "en" if looks_english_or_foreign(sample) else "unknown"
        sample2 = re.sub(r"[\d\[\]\(\)/\"'.,:;-]+"," ",sample)
        sample2 = re.sub(r"\s+"," ",sample2).strip()
        if looks_english_or_foreign(sample2):
            return "en"
        return detect(sample2)
    except LangDetectException:
        return "unknown"
    except Exception:
        return "unknown"

def maybe_translate_to_ro(text: str):
    lang = detect_lang_safe(text)
    if lang not in ("ro","unknown"):
        return translate_to_ro(text), lang
    if lang=="unknown" and looks_english_or_foreign(text):
        return translate_to_ro(text), "auto"
    return text, lang

def polish_ro_phrasing(text: str) -> str:
    t = text or ""
    t = t.replace("”", '"').replace("“", '"').replace("„", '"')
    t = re.sub(r"\banti[- ]theft\b","antifurt",t,flags=re.IGNORECASE)
    t = re.sub(r"\bpu leather\b","piele PU",t,flags=re.IGNORECASE)
    t = re.sub(r"\btrolley strap\b","curea pentru troler",t,flags=re.IGNORECASE)
    return t

def header_match(line: str, header: str) -> bool:
    return line.strip().lower().rstrip(":").strip() == header.strip().lower().rstrip(":").strip()

def extract_section(text: str, headers: list[str]) -> str:
    t = normalize(text)
    lines = t.split("\n")
    idx=None
    for i,ln in enumerate(lines):
        if any(header_match(ln,h) for h in headers):
            idx=i; break
    if idx is None:
        return ""
    start=idx+1
    known=["Informații de bază","Informatii de baza","Descriere","Caracteristici cheie","Caracteristici",
           "Basic Information","Description","Key features","Key features:","Technical information","Additional info","Product specific details"]
    end=len(lines)
    for j in range(start,len(lines)):
        s=lines[j].strip()
        if not s: 
            continue
        if any(header_match(s,h) for h in known):
            end=j; break
    return "\n".join(lines[start:end]).strip()

def parse_key_values_colon(block: str):
    out=[]
    for ln in normalize(block).split("\n"):
        ln=ln.strip()
        if not ln or ":" not in ln: 
            continue
        k,v=ln.split(":",1)
        k,v=k.strip(),v.strip()
        if k and v: out.append((k,v))
    return out

def is_kv_tabular_style(raw: str) -> bool:
    lines=[ln for ln in normalize(raw).split("\n") if ln.strip()]
    tabbed=[ln for ln in lines if "\t" in ln]
    if len(tabbed)<3:
        return False
    cols=[len([p for p in ln.split("\t") if p.strip()]) for ln in tabbed]
    if any(c>=3 for c in cols):
        return False
    kv_like=sum(1 for c in cols if c==2)
    return kv_like/max(1,len(tabbed))>=0.7

def parse_tab_kvs(raw: str):
    out=[]
    for ln in normalize(raw).split("\n"):
        if "\t" not in ln: 
            continue
        parts=[p.strip() for p in ln.split("\t") if p.strip()]
        if len(parts)==2:
            out.append((parts[0],parts[1]))
    return out

def detect_color_line(lines):
    colors={"black","white","grey","gray","red","blue","green","yellow","orange","pink","purple","brown","beige","navy"}
    for ln in lines:
        s=ln.strip()
        if s and len(s)<=18 and re.fullmatch(r"[A-Za-z \-]+", s) and s.lower().strip() in colors:
            return s
    return ""

def parse_technical_table(block: str):
    lines=[ln.rstrip() for ln in normalize(block).split("\n") if ln.strip()]
    if len(lines)<2:
        return []
    header_line=lines[0].strip()
    data_line=None
    for ln in lines[1:]:
        if re.match(r"^\s*\d", ln):
            data_line=ln.strip(); break
    if not data_line:
        data_line=lines[1].strip()

    def split_cols(s: str):
        if "\t" in s:
            return [p.strip() for p in s.split("\t") if p.strip()]
        parts=[p.strip() for p in re.split(r"\s{2,}", s) if p.strip()]
        if len(parts)>=3:
            return parts
        return [p.strip() for p in re.split(r"\s+", s) if p.strip()]

    headers=split_cols(header_line)
    values=split_cols(data_line)

    joined=" ".join(headers).lower()
    if "ctn" in joined and ("dimesions" in joined or "dimensions" in joined):
        headers=["Pack","Carton","Measures","Ctn dimensions","Ctn weight"]

    out=[]
    for i,h in enumerate(headers):
        if i<len(values):
            out.append((h, values[i]))
    return out

def build_formatted(title, description, characteristics_lines):
    parts=[]
    if title: parts += [title.strip(), ""]
    if description: parts += [description.strip(), ""]
    if characteristics_lines:
        parts.append("Caracteristici:")
        for ln in characteristics_lines:
            ln=ln.strip()
            if not ln: 
                continue
            if not ln.endswith(";"): ln += ";"
            parts.append(ln)
    return ("\n".join(parts).strip()+"\n") if parts else ""

def translate_characteristics(lines):
    detected_any="unknown"
    out=[]
    for line in lines:
        if ":" in line:
            k,v=line.split(":",1)
            k_ro=map_key_to_ro(k)
            v2,lang2=maybe_translate_to_ro(v.strip())
            if detected_any=="unknown": detected_any=lang2
            out.append(f"{k_ro}: {polish_ro_phrasing(v2)}")
        else:
            l2,lang2=maybe_translate_to_ro(line)
            if detected_any=="unknown": detected_any=lang2
            out.append(polish_ro_phrasing(l2))
    return out, detected_any

def process_input(raw_text: str):
    raw=normalize(raw_text).strip()
    if not raw:
        return "", "unknown"
    lines=raw.split("\n")
    title=""; description=""; characteristics=[]
    detected_lang_any="unknown"

    if is_kv_tabular_style(raw):
        kvs=[(k,v) for (k,v) in parse_tab_kvs(raw) if not is_banned_key(k)]
        data={norm_key(k):v for k,v in kvs}
        title=data.get(norm_key("Nume produs"),"") or data.get(norm_key("Product name"),"")
        description=data.get(norm_key("Descriere"),"") or data.get(norm_key("Description"),"")
        skip={norm_key("Nume produs"),norm_key("Product name"),norm_key("Descriere"),norm_key("Description")}
        for k,v in kvs:
            if norm_key(k) in skip: 
                continue
            characteristics.append(f"{k}: {v}")
    else:
        # freeform
        for ln in lines:
            if ln.strip(): title=ln.strip(); break
        stop_headers={"technical information","additional info","key features","key features:","basic information","informatii de baza","informații de bază"}
        desc_lines=[]; started=False
        for ln in lines:
            s=ln.strip()
            if not started:
                if s==title: started=True
                continue
            if s and s.lower().rstrip(":") in stop_headers:
                break
            desc_lines.append(ln)
        description="\n".join(desc_lines).strip()

        color=detect_color_line(lines)
        if color:
            characteristics.append(f"Color: {color}")

        tech=extract_section(raw, ["Technical information"])
        if tech:
            for k,v in parse_technical_table(tech):
                if is_banned_key(k): 
                    continue
                characteristics.append(f"{k}: {v}")

        add=extract_section(raw, ["Additional info"])
        if add:
            for k,v in parse_key_values_colon(add):
                if is_banned_key(k): 
                    continue
                characteristics.append(f"{k}: {v}")

    description, detected_lang_any = maybe_translate_to_ro(description)
    description = polish_ro_phrasing(description)

    characteristics, detected2 = translate_characteristics(characteristics)
    if detected_lang_any=="unknown": detected_lang_any=detected2

    # final cleanup: remove pack/pachet lines if any
    cleaned=[]
    for ln in characteristics:
        key=ln.split(":",1)[0] if ":" in ln else ln
        if norm_key(key) in {norm_key("pack"),norm_key("package"),norm_key("pachet")}:
            continue
        cleaned.append(ln)

    formatted=build_formatted(title, description, cleaned)
    formatted=remove_diacritics(formatted)
    return formatted, detected_lang_any

st.title("Formatare text produs (input brut / tabel -> output formatat, fara diacritice)")
st.caption("Lipeste textul, apoi apasa **Aranjeaza textul**. Foloseste **Reset** pentru alt produs.")

if "reset_counter" not in st.session_state:
    st.session_state["reset_counter"]=0
if "formatted" not in st.session_state:
    st.session_state["formatted"]=""
if "detected_lang" not in st.session_state:
    st.session_state["detected_lang"]="unknown"

widget_key=f"raw_text_{st.session_state['reset_counter']}"

with st.form("formatter_form"):
    st.text_area("Text brut", height=320, key=widget_key, placeholder="Lipeste aici textul brut…")
    c1,c2 = st.columns(2)
    with c1:
        submitted = st.form_submit_button("Aranjeaza textul", use_container_width=True)
    with c2:
        reset = st.form_submit_button("Reset (text nou)", use_container_width=True)

if reset:
    st.session_state["reset_counter"] += 1
    st.session_state["formatted"] = ""
    st.session_state["detected_lang"] = "unknown"
    st.rerun()

if submitted:
    formatted, lang = process_input(st.session_state.get(widget_key,""))
    st.session_state["formatted"]=formatted
    st.session_state["detected_lang"]=lang

if st.session_state["formatted"]:
    st.subheader("Rezultat")
    if st.session_state["detected_lang"] not in ("unknown","ro"):
        st.caption(f"Detectat: {st.session_state['detected_lang']} → tradus in romana, apoi eliminare diacritice")
    st.code(st.session_state["formatted"], language="text")

    st.components.v1.html(
        f"""
        <div style="display:flex; gap:10px; align-items:center; margin-top:6px;">
          <button id="copyBtn" style="padding:8px 12px; border-radius:8px; border:1px solid #ccc; cursor:pointer; background:#fff;">
            Copy
          </button>
          <span id="copyStatus" style="font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; font-size: 14px;"></span>
        </div>
        <textarea id="txt" style="position:absolute; left:-9999px; top:-9999px;">{st.session_state["formatted"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</textarea>
        <script>
          const btn = document.getElementById("copyBtn");
          const status = document.getElementById("copyStatus");
          btn.addEventListener("click", async () => {{
            try {{
              const text = document.getElementById("txt").value;
              await navigator.clipboard.writeText(text);
              status.textContent = "Copiat!";
              setTimeout(() => status.textContent = "", 1500);
            }} catch (e) {{
              status.textContent = "Nu pot copia automat. Copiaza manual din caseta de mai sus.";
            }}
          }});
        </script>
        """,
        height=60,
    )

    st.download_button("Descarca rezultat .txt",
        data=st.session_state["formatted"].encode("utf-8"),
        file_name="text_produs_formatat.txt",
        mime="text/plain",
        use_container_width=True)
