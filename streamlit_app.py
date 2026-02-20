import streamlit as st
import unicodedata
import re
from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator

st.set_page_config(page_title="Product Text Formatter", layout="centered")

# ----------------- helpers -----------------
def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    repl = {"ș":"s","Ş":"S","ț":"t","Ţ":"T","ă":"a","Ă":"A","â":"a","Â":"A","î":"i","Î":"I"}
    for a,b in repl.items():
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

# ----------------- filters -----------------
BANNED_KEYS = {
    "tara de origine","country of origin",
    "cod unic de inregistrare","cod unic de înregistrare",
    "cod","code","cod articol","article code",
    "model",
    "marca","marcă","brand",
    "numarul paginii din catalog","catalog page number","catalogue page number",
    "cod de bare","bar code","barcode",
    "nume in catalog",
    "catalogue","catalog","catalogue (title / chapter / page)","catalog (title / chapter / page)",
    "pachet","package","pack",
    "engraving color","culoare de gravare",
}
def is_banned_key(key: str) -> bool:
    k = norm_key(key)
    banned_norm = {norm_key(x) for x in BANNED_KEYS}
    if k in banned_norm:
        return True
    banned_sub = [
        "tara de origine","country of origin",
        "catalogue","catalog",
        "cod unic","numarul paginii din catalog",
        "cod de bare","bar code","barcode",
        "cod articol","article code",
        "engraving","gravare",
    ]
    return any(s in k for s in banned_sub)

KEY_MAP = {
    "color":"Culoare","colour":"Culoare",
    "net weight":"Greutate neta","weight":"Greutate",
    "material":"Material",
    "length":"Lungimea","width":"Latimea","height":"Inaltime",
}
def map_key_to_ro(key: str) -> str:
    return KEY_MAP.get(norm_key(key), key.strip())

# ----------------- translation -----------------
@st.cache_data(show_spinner=False)
def translate_to_ro(text: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="ro").translate(text)
    except Exception:
        return text

EN_HINT = {"pocket","zip","zippers","lock","water-repellent","waterproof","recycled","certified","anti-theft",
           "black","grey","gray","leather","strap","laptop","tablet","airport","work","class","lining","volume","litres","liters"}

def looks_english(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = remove_diacritics(t).lower()
    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in EN_HINT):
        return True
    return re.fullmatch(r"[A-Za-z0-9 \-–—,:;\"'()\[\]/\.\n]+", t) is not None

@st.cache_data(show_spinner=False)
def detect_lang_safe(text: str) -> str:
    try:
        sample = re.sub(r"\s+"," ", (text or "")).strip()
        if len(sample) < 50:
            return "en" if looks_english(sample) else "unknown"
        sample2 = re.sub(r"[\d\[\]\(\)/\"'.,:;-]+"," ",sample)
        sample2 = re.sub(r"\s+"," ",sample2).strip()
        if looks_english(sample2):
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
    if lang=="unknown" and looks_english(text):
        return translate_to_ro(text), "auto"
    return text, lang

def polish_ro(text: str) -> str:
    t = (text or "")
    t = t.replace("”", '"').replace("“", '"').replace("„", '"')
    t = re.sub(r"\banti[- ]theft\b","antifurt",t,flags=re.IGNORECASE)
    t = re.sub(r"\brpet\b","RPET",t,flags=re.IGNORECASE)
    t = re.sub(r"\bgrs\b","GRS",t,flags=re.IGNORECASE)
    t = re.sub(r"^\s*Descriere\s*\n+", "", t, flags=re.IGNORECASE)
    return t

def drop_hallucinated_title(desc: str) -> str:
    d = (desc or "").strip()
    if "\n" not in d:
        return d
    first, rest = d.split("\n", 1)
    first = first.strip()
    rest2 = rest.strip()
    if 0 < len(first) <= 90 and not first.endswith((".", "!", "?")):
        if re.match(r"^(Fabricat|Realizat|Conceput|Rucsacul|Acest|Aceasta|Cu)\b", rest2, flags=re.IGNORECASE):
            return rest2
    return d

# ----------------- parsing -----------------
KNOWN_KEYS = {
    "brand","material","colour","color","length","width","height","weight","country of origin","engraving color",
    "marca","material","culoare","lungime","latime","inaltime","greutate","tara de origine","culoare de gravare"
}
KNOWN_KEYS_NORM = {norm_key(x) for x in KNOWN_KEYS}

def parse_vertical_kvs(lines: list[str]):
    out=[]
    i=0
    while i < len(lines)-1:
        k=lines[i].strip()
        v=lines[i+1].strip()
        if k and v and len(k)<=35 and re.fullmatch(r"[A-Za-zĂÂÎȘȚăâîșț \-/]+", k) and ":" not in k and "\t" not in k:
            out.append((k,v))
            i += 2
        else:
            i += 1
    dedup={}
    for k,v in out:
        dedup[norm_key(k)] = (k,v)
    return list(dedup.values())

def split_description_then_kvs(lines: list[str]) -> tuple[str, list[str]]:
    """
    Works for:
    - starts with 'Description' header
    - OR starts directly with a long paragraph, then vertical keys.
    Returns (description, tail_lines_from_first_key)
    """
    clean = [ln.strip() for ln in lines if ln.strip()]
    if not clean:
        return "", []
    # Case A: explicit header
    if norm_key(clean[0]) in {norm_key("description"), norm_key("descriere")}:
        i = 1
        desc_lines=[]
        while i < len(clean) and norm_key(clean[i]) not in KNOWN_KEYS_NORM:
            desc_lines.append(clean[i])
            i += 1
        return "\n".join(desc_lines).strip(), clean[i:]
    # Case B: no header; find first known key line that has a value after it
    i = 0
    first_key_idx = None
    while i < len(clean)-1:
        if norm_key(clean[i]) in KNOWN_KEYS_NORM:
            first_key_idx = i
            break
        i += 1
    if first_key_idx is not None:
        desc = "\n".join(clean[:first_key_idx]).strip()
        tail = clean[first_key_idx:]
        return desc, tail
    # fallback: everything is description
    return "\n".join(clean).strip(), []

def build_output(description: str, kv_lines: list[str]) -> str:
    parts=[]
    if description:
        parts.append("Descriere:")
        parts.append(description.strip())
        parts.append("")
    parts.extend([ln.strip() for ln in kv_lines if ln.strip()])
    return ("\n".join(parts).strip()+"\n") if parts else ""

def process_input(raw_text: str):
    raw = normalize(raw_text).strip()
    if not raw:
        return "", "unknown"

    raw_lines = raw.split("\n")
    description, tail = split_description_then_kvs(raw_lines)

    kv_pairs=[]
    if tail:
        for k,v in parse_vertical_kvs(tail):
            k_ro = map_key_to_ro(k)
            if is_banned_key(k) or is_banned_key(k_ro):
                continue
            kv_pairs.append((k_ro, v))

    detected="unknown"
    if description:
        description, detected = maybe_translate_to_ro(description)
        description = polish_ro(description)
        description = drop_hallucinated_title(description)

    kv_lines=[]
    detected2="unknown"
    for k_ro, v in kv_pairs:
        if is_banned_key(k_ro):
            continue
        v2, lang2 = maybe_translate_to_ro(v)
        if detected2=="unknown":
            detected2=lang2
        kv_lines.append(f"{k_ro}: {polish_ro(v2)}")

    if detected=="unknown":
        detected=detected2

    out = build_output(description, kv_lines)
    out = remove_diacritics(out)
    return out, detected

# ----------------- UI -----------------
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
