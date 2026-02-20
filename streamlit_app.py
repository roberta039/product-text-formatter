import streamlit as st
import unicodedata
import re

from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator

st.set_page_config(page_title="Product Text Formatter", layout="centered")

# ----------------- text helpers -----------------
def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    replacements = {
        "ș": "s", "Ş": "S", "ț": "t", "Ţ": "T",
        "ă": "a", "Ă": "A", "â": "a", "Â": "A",
        "î": "i", "Î": "I",
    }
    for a, b in replacements.items():
        no_marks = no_marks.replace(a, b)
    no_marks = re.sub(r"[ \t]+\n", "\n", no_marks)
    no_marks = re.sub(r"\n{3,}", "\n\n", no_marks)
    return no_marks

def normalize(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")

def norm_key(k: str) -> str:
    k = remove_diacritics(k or "").lower().strip()
    k = re.sub(r"\s+", " ", k)
    return k

# ----------------- rules -----------------
# Always remove these fields from "Caracteristici"
BANNED_KEYS = {
    # RO
    "tara de origine",
    "cod unic de inregistrare",
    "cod unic de înregistrare",
    "cod",
    "cod articol",
    "model",
    "marca",
    "marcă",
    "numarul paginii din catalog",
    "cod de bare",
    "nume in catalog",
    "pachet",
    # EN
    "country of origin",
    "catalogue (title / chapter / page)",
    "catalog (title / chapter / page)",
    "catalogue",
    "catalog",
    "code",
    "article code",
    "brand",
    "catalogue page number",
    "catalog page number",
    "bar code",
    "barcode",
    "package",
}

def is_banned_key(key: str) -> bool:
    k = norm_key(key)
    banned_norm = {norm_key(x) for x in BANNED_KEYS}
    if k in banned_norm:
        return True
    banned_sub = [
        "tara de origine", "country of origin",
        "catalogue", "catalog",
        "cod unic",
        "numarul paginii din catalog", "catalog page number", "catalogue page number",
        "cod de bare", "bar code", "barcode",
        "cod articol", "article code",
    ]
    return any(s in k for s in banned_sub) or k in {
        norm_key("cod"), norm_key("code"), norm_key("model"), norm_key("marca"), norm_key("brand"),
        norm_key("package"), norm_key("pachet"), norm_key("cod articol"), norm_key("article code")
    }

# Map common keys to Romanian (for nicer output)
KEY_MAP = {
    "color": "Culoare",
    "culori": "Culoare",
    "culoare/culori": "Culoare",
    "net weight": "Greutate neta",
    "gross weight": "Greutate bruta",
    "weight": "Greutate",
    "material": "Material",
    "materials": "Material",
    "material(e)": "Material",
    "dimension": "Dimensiuni",
    "dimensions": "Dimensiuni",
    "dimenzija": "Dimensiuni",
    "size": "Dimensiuni",
    "capacity": "Capacitate",
    "volume": "Capacitate",
    "performance": "Performanta",
    "additional equipment": "Echipamente suplimentare",
    "product weight": "Greutatea produsului",
    "individual product weight": "Greutatea produsului individual",
}

def map_key_to_ro(key: str) -> str:
    k = norm_key(key)
    return KEY_MAP.get(k, key.strip())

# ----------------- language (better translation) -----------------
@st.cache_data(show_spinner=False)
def detect_lang_safe(text: str) -> str:
    try:
        sample = re.sub(r"\s+", " ", (text or "")).strip()
        if len(sample) < 35:
            return "unknown"
        return detect(sample)
    except LangDetectException:
        return "unknown"
    except Exception:
        return "unknown"

@st.cache_data(show_spinner=False)
def translate_to_ro(text: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="ro").translate(text)
    except Exception:
        return text

EN_HINT_WORDS = {
    "pocket", "zip", "zippers", "connector", "lock", "waterproof", "nylon", "gift", "packaging",
    "front", "hidden", "back", "laptop", "tablet", "business", "executive", "anti-theft", "type-c", "usb",
    "black", "grey", "blue", "red", "green"
}

def looks_english_or_foreign_short(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = remove_diacritics(t).lower()
    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in EN_HINT_WORDS):
        return True
    if re.fullmatch(r"[A-Za-z0-9 \-–—,:;\"'()\[\]/\.]+", t) and not re.search(r"\b(si|sau|pentru|cu|din|este)\b", low):
        return True
    return False

def maybe_translate_to_ro(text: str) -> tuple[str, str]:
    t = text or ""
    lang = detect_lang_safe(t)
    if lang not in ("ro", "unknown"):
        return translate_to_ro(t), lang
    if lang == "unknown" and looks_english_or_foreign_short(t):
        return translate_to_ro(t), "auto"
    return t, lang

def polish_ro_phrasing(text: str) -> str:
    t = text or ""
    t = t.replace("”", '"').replace("“", '"').replace("„", '"')
    t = re.sub(r"\brucsac de afaceri\b", "rucsac business", t, flags=re.IGNORECASE)
    t = re.sub(r"\bport de tip c\b", "port Type-C", t, flags=re.IGNORECASE)
    t = re.sub(r"\bport type-c\b", "port Type-C", t, flags=re.IGNORECASE)
    t = re.sub(r"\banti[- ]theft\b", "antifurt", t, flags=re.IGNORECASE)
    return t

# ----------------- parsing -----------------
def header_match(line: str, header: str) -> bool:
    a = line.strip().lower().rstrip(":").strip()
    b = header.strip().lower().rstrip(":").strip()
    return a == b

def extract_section(text: str, headers: list[str]) -> str:
    t = normalize(text)
    lines = t.split("\n")

    idx = None
    for i, ln in enumerate(lines):
        if any(header_match(ln, h) for h in headers):
            idx = i
            break
    if idx is None:
        return ""

    start = idx + 1
    known_headers = [
        "Informații de bază", "Informatii de baza", "Descriere", "Caracteristici cheie", "Caracteristici",
        "Basic Information", "Description", "Key features", "Key features:", "Product specific details",
    ]
    end = len(lines)
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if not s:
            continue
        if any(header_match(s, h) for h in known_headers):
            end = j
            break
        if (":" not in s) and ("\t" not in s) and (len(s) <= 40) and re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", s):
            end = j
            break

    return "\n".join(lines[start:end]).strip()

def parse_key_values_colon(block: str):
    out = []
    for ln in normalize(block).split("\n"):
        ln = ln.strip()
        if not ln or ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        k, v = k.strip(), v.strip()
        if k and v:
            out.append((k, v))
    return out

def parse_tab_kvs(text: str):
    out = []
    for ln in normalize(text).split("\n"):
        ln = ln.strip()
        if not ln:
            continue

        if any(header_match(ln, h) for h in [
            "Product specific details",
            "Informatii de baza", "Informații de bază",
            "Descriere", "Caracteristici cheie",
            "Basic Information", "Description", "Key features", "Key features:"
        ]):
            continue

        if "\t" in ln:
            parts = [p.strip() for p in ln.split("\t") if p.strip()]
        else:
            parts = [p.strip() for p in re.split(r"\s{2,}", ln) if p.strip()]

        if len(parts) >= 2:
            out.append((parts[0], " ".join(parts[1:]).strip()))
    return out

def parse_bullets(block: str):
    if not block:
        return []
    b = normalize(block).strip()
    b = re.sub(r"\n+", " ", b)
    if "•" in b:
        parts = [p.strip(" \t-•") for p in b.split("•")]
        return [p for p in parts if p]
    return [b] if b else []

def build_formatted(title: str, description: str, characteristics_lines: list[str]) -> str:
    parts = []
    title = (title or "").strip()
    description = (description or "").strip()

    if title:
        parts += [title, ""]
    if description:
        parts += [description, ""]
    if characteristics_lines:
        parts.append("Caracteristici:")
        for ln in characteristics_lines:
            ln = (ln or "").strip()
            if not ln:
                continue
            if not ln.endswith(";"):
                ln += ";"
            parts.append(ln)
    return ("\n".join(parts).strip() + "\n") if parts else ""

def translate_characteristics_lines(lines: list[str]) -> tuple[list[str], str]:
    detected_any = "unknown"
    out = []
    for line in lines:
        if ":" in line:
            k, v = line.split(":", 1)
            k_ro = map_key_to_ro(k)
            v2, lang2 = maybe_translate_to_ro(v.strip())
            if detected_any == "unknown":
                detected_any = lang2
            out.append(f"{k_ro}: {polish_ro_phrasing(v2)}")
        else:
            l2, lang2 = maybe_translate_to_ro(line)
            if detected_any == "unknown":
                detected_any = lang2
            out.append(polish_ro_phrasing(l2))
    return out, detected_any

def process_input(raw_text: str) -> tuple[str, str]:
    raw = normalize(raw_text).strip()
    if not raw:
        return "", "unknown"

    tab_lines = sum(1 for ln in raw.split("\n") if "\t" in ln)
    is_tabular = tab_lines >= 2

    title = ""
    description = ""
    characteristics = []
    detected_lang_any = "unknown"

    if is_tabular:
        kvs = [(k, v) for (k, v) in parse_tab_kvs(raw) if not is_banned_key(k)]
        data = {norm_key(k): v for k, v in kvs}

        title = data.get(norm_key("Nume produs"), "") or data.get(norm_key("Product name"), "")
        description = data.get(norm_key("Descriere"), "") or data.get(norm_key("Description"), "")

        skip = {norm_key("Nume produs"), norm_key("Product name"), norm_key("Descriere"), norm_key("Description")}
        for k, v in kvs:
            if norm_key(k) in skip:
                continue
            characteristics.append(f"{k}: {v}")

        description, detected_lang_any = maybe_translate_to_ro(description)
        description = polish_ro_phrasing(description)

        characteristics, detected2 = translate_characteristics_lines(characteristics)
        if detected_lang_any == "unknown":
            detected_lang_any = detected2

    else:
        basic = extract_section(raw, ["Informații de bază", "Informatii de baza", "Basic Information"])
        description = extract_section(raw, ["Descriere", "Description"])
        keyf = extract_section(raw, ["Caracteristici cheie", "Key features", "Key features:"])

        kvs_basic = [(k, v) for (k, v) in parse_key_values_colon(basic) if not is_banned_key(k)]
        for k, v in kvs_basic:
            characteristics.append(f"{k}: {v}")

        characteristics.extend(parse_bullets(keyf))

        description, detected_lang_any = maybe_translate_to_ro(description)
        description = polish_ro_phrasing(description)

        characteristics, detected2 = translate_characteristics_lines(characteristics)
        if detected_lang_any == "unknown":
            detected_lang_any = detected2

    formatted = build_formatted(title, description, characteristics)
    formatted = remove_diacritics(formatted)  # final output without diacritics
    return formatted, detected_lang_any

# ----------------- UI -----------------
st.title("Formatare text produs (input brut / tabel -> output formatat, fara diacritice)")
st.caption("Lipeste textul, apoi apasa **Aranjeaza textul**. Foloseste **Reset** pentru alt produs.")

# Reset-safe strategy: use a changing widget key (no direct assignment to widget's session key)
if "reset_counter" not in st.session_state:
    st.session_state["reset_counter"] = 0
if "formatted" not in st.session_state:
    st.session_state["formatted"] = ""
if "detected_lang" not in st.session_state:
    st.session_state["detected_lang"] = "unknown"

widget_key = f"raw_text_{st.session_state['reset_counter']}"

with st.form("formatter_form"):
    st.text_area(
        "Text brut (accepta: sectiuni sau tabel cu TAB-uri)",
        height=320,
        key=widget_key,
        placeholder="Lipeste aici textul brut…",
    )
    c1, c2 = st.columns(2)
    with c1:
        submitted = st.form_submit_button("Aranjeaza textul", use_container_width=True)
    with c2:
        reset = st.form_submit_button("Reset (text nou)", use_container_width=True)

if reset:
    # increment counter -> creates a new text_area key, empty by default
    st.session_state["reset_counter"] += 1
    st.session_state["formatted"] = ""
    st.session_state["detected_lang"] = "unknown"
    st.rerun()

if submitted:
    raw_input = st.session_state.get(widget_key, "")
    formatted, lang = process_input(raw_input)
    st.session_state["formatted"] = formatted
    st.session_state["detected_lang"] = lang

if st.session_state["formatted"]:
    st.subheader("Rezultat")
    if st.session_state["detected_lang"] not in ("unknown", "ro"):
        st.caption(f"Detectat: {st.session_state['detected_lang']} → tradus in romana, apoi eliminare diacritice")
    st.code(st.session_state["formatted"], language="text")

    st.components.v1.html(
        f"""
        <div style="display:flex; gap:10px; align-items:center; margin-top:6px;">
          <button id="copyBtn" style="
            padding:8px 12px; border-radius:8px; border:1px solid #ccc; cursor:pointer;
            background:#fff;">
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

    st.download_button(
        "Descarca rezultat .txt",
        data=st.session_state["formatted"].encode("utf-8"),
        file_name="text_produs_formatat.txt",
        mime="text/plain",
        use_container_width=True,
    )
