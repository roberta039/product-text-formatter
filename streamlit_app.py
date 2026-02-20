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

# ----------------- translation -----------------
@st.cache_data(show_spinner=False)
def translate_to_ro(text: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="ro").translate(text)
    except Exception:
        return text

EN_HINT = {"pocket","zip","zippers","lock","water-repellent","waterproof","recycled","certified","anti-theft",
           "black","grey","gray","leather","strap","laptop","tablet","airport","work","class","lining","volume","litres","liters",
           "specifications","primary","secondary","material","colour","length","width","height","weight"}

def looks_english(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = remove_diacritics(t).lower()
    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in EN_HINT):
        return True
    return re.fullmatch(r"[A-Za-z0-9 \-–—,:;\"'()\[\]/\.\n®™]+", t) is not None

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
    t = t.replace("AWARE™", "AWARETM").replace("AWARE™", "AWARETM")
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

# ----------------- key mapping / filtering -----------------
KEY_MAP = {
    "colour":"Culoare","color":"Culoare",
    "volume":"Volum",
    "fits laptop size":"Se potriveste cu laptop de",
    "material":"Material",
    "secondary material":"Material secundar",
    "secondary colour":"Culoare secundara",
    "product width":"Latimea produsului",
    "length product":"Lungime produs",
    "height product":"Inaltime produs",
    "net weight product":"Greutate neta produs",
    "gross weight product":"Greutate bruta produs",
    "pms colour":"Culoare PMS",
}

def map_key_to_ro(key: str) -> str:
    return KEY_MAP.get(norm_key(key), key.strip())

# remove fields user doesn't want (and similar)
BANNED_KEY_SUBSTR = [
    "co2", "emissions benchmark", "co2 emissions",
    "brand", "product category", "subcategory",
    "width product box", "height product box", "lenght product box", "length product box",
    "carton ", "packaging", "intrastat", "quantity per carton", "ean",
    "per polybag", "inner carton", "country of origin", "tara de origine",
    "pms secondary colour", "pms secondary color",
]
def is_banned_key(key: str) -> bool:
    k = norm_key(key)
    return any(s in k for s in [norm_key(x) for x in BANNED_KEY_SUBSTR])

# ----------------- parsing -----------------
def parse_pairs_from_tab_line(line: str) -> list[tuple[str,str]]:
    parts = [p.strip() for p in line.split("\t") if p.strip()]
    out=[]
    # pairs (0,1), (2,3) ...
    for i in range(0, len(parts)-1, 2):
        k, v = parts[i], parts[i+1]
        if k and v:
            out.append((k, v))
    return out

def find_first_nonempty(lines: list[str]) -> str:
    for ln in lines:
        if ln.strip():
            return ln.strip()
    return ""

def process_input(raw_text: str):
    raw = normalize(raw_text).strip()
    if not raw:
        return "", "unknown"

    lines = raw.split("\n")
    detected="unknown"

    # Title = first non-empty line if it does NOT look like a section header
    title = find_first_nonempty(lines)
    if norm_key(title) in {norm_key("description"), norm_key("primary specifications"), norm_key("secondary specifications")}:
        title = ""

    # Description from "Description<TAB>...." or "Description" section
    desc = ""
    for ln in lines:
        if "\t" in ln:
            pairs = parse_pairs_from_tab_line(ln)
            for k,v in pairs:
                if norm_key(k) in {norm_key("description"), norm_key("descriere")}:
                    desc = v
                    break
        if desc:
            break

    # specs: parse under Primary/Secondary specifications blocks
    specs=[]
    in_specs=False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if norm_key(s) in {norm_key("primary specifications"), norm_key("secondary specifications")}:
            in_specs=True
            continue
        if in_specs and "\t" in ln:
            for k,v in parse_pairs_from_tab_line(ln):
                k_ro = map_key_to_ro(k)
                if is_banned_key(k) or is_banned_key(k_ro):
                    continue
                specs.append((k_ro, v))

    # translate title + desc + specs values
    if title:
        title_ro, lang_t = maybe_translate_to_ro(title)
        detected = lang_t if detected=="unknown" else detected
        title_ro = polish_ro(title_ro)
    else:
        title_ro = ""

    if desc:
        desc_ro, lang_d = maybe_translate_to_ro(desc)
        detected = lang_d if detected=="unknown" else detected
        desc_ro = drop_hallucinated_title(polish_ro(desc_ro))
    else:
        # fallback: if no desc field, take everything except specs tables
        desc_ro, lang_d = maybe_translate_to_ro(raw)
        detected = lang_d if detected=="unknown" else detected
        desc_ro = drop_hallucinated_title(polish_ro(desc_ro))

    spec_lines=[]
    for k_ro, v in specs:
        v2, lang_v = maybe_translate_to_ro(v)
        if detected=="unknown":
            detected = lang_v
        # light normalizations for units
        vv = polish_ro(v2)
        vv = vv.replace(' "', '"').replace("16 ”", '16"')
        spec_lines.append(f"{k_ro}: {vv}")

    # build output
    out=[]
    out.append("Descriere:")
    if title_ro:
        out.append(title_ro.strip())
    out.append(desc_ro.strip())
    out.append("")
    if spec_lines:
        out.append("Specificatii:")
        out.extend(spec_lines)

    formatted = "\n".join(out).strip() + "\n"
    formatted = remove_diacritics(formatted)
    return formatted, detected

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
