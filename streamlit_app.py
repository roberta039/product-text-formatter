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
    "model",
    "marca",
    "marcă",
    "numarul paginii din catalog",
    "numarul paginii din catalog:",
    "cod de bare",
    "nume in catalog",
    "catalogue", "catalog",
    # EN
    "country of origin",
    "catalogue (title / chapter / page)",
    "catalog (title / chapter / page)",
    "code",
    "brand",
    "catalogue page number",
    "catalog page number",
    "bar code",
    "barcode",
    "package",
    "pachet",
}

def is_banned_key(key: str) -> bool:
    k = norm_key(key)
    banned_norm = {norm_key(x) for x in BANNED_KEYS}
    if k in banned_norm:
        return True
    # catch variants
    banned_sub = [
        "tara de origine", "country of origin",
        "catalogue", "catalog",
        "cod unic",
        "numarul paginii din catalog", "catalog page number", "catalogue page number",
        "cod de bare", "bar code", "barcode",
    ]
    return any(s in k for s in banned_sub) or k in {
        norm_key("cod"), norm_key("code"), norm_key("model"), norm_key("marca"), norm_key("brand")
    }

# ----------------- language -----------------
@st.cache_data(show_spinner=False)
def detect_lang_safe(text: str) -> str:
    try:
        sample = re.sub(r"\s+", " ", (text or "")).strip()
        if len(sample) < 20:
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

def maybe_translate_to_ro(text: str) -> tuple[str, str]:
    lang = detect_lang_safe(text)
    if lang not in ("ro", "unknown"):
        return translate_to_ro(text), lang
    return text, lang

# ----------------- parsing -----------------
def header_match(line: str, header: str) -> bool:
    # compare ignoring trailing ":" and spaces
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
        # RO
        "Informații de bază", "Informatii de baza",
        "Descriere",
        "Caracteristici cheie", "Caracteristici",
        # EN
        "Basic Information",
        "Description",
        "Key features", "Key features:",
        "Product specific details",
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

        # ignore headings
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

        translated = []
        for line in characteristics:
            if ":" in line:
                k, v = line.split(":", 1)
                v2, lang2 = maybe_translate_to_ro(v.strip())
                if detected_lang_any == "unknown":
                    detected_lang_any = lang2
                translated.append(f"{k.strip()}: {v2}")
            else:
                l2, lang2 = maybe_translate_to_ro(line)
                if detected_lang_any == "unknown":
                    detected_lang_any = lang2
                translated.append(l2)
        characteristics = translated

    else:
        basic = extract_section(raw, ["Informații de bază", "Informatii de baza", "Basic Information"])
        description = extract_section(raw, ["Descriere", "Description"])
        keyf = extract_section(raw, ["Caracteristici cheie", "Key features", "Key features:"])

        kvs_basic = [(k, v) for (k, v) in parse_key_values_colon(basic) if not is_banned_key(k)]

        # title: try to find an explicit name line if present (optional)
        m = re.search(r"(?im)^(nume produs|product name)\s*:\s*(.+)$", raw)
        if m:
            title = m.group(2).strip()

        for k, v in kvs_basic:
            characteristics.append(f"{k}: {v}")

        for it in parse_bullets(keyf):
            it2, lang2 = maybe_translate_to_ro(it)
            if detected_lang_any == "unknown":
                detected_lang_any = lang2
            characteristics.append(it2)

        description, detected_lang_any = maybe_translate_to_ro(description)

    formatted = build_formatted(title, description, characteristics)

    # final output: always no diacritics
    formatted = remove_diacritics(formatted)
    return formatted, detected_lang_any

# ----------------- UI -----------------
st.title("Formatare text produs (input brut / tabel -> output formatat, fara diacritice)")
st.caption("Lipeste textul, apoi apasa **Aranjeaza textul**. Foloseste **Reset** pentru alt produs.")

if "raw_text" not in st.session_state:
    st.session_state["raw_text"] = ""
if "formatted" not in st.session_state:
    st.session_state["formatted"] = ""
if "detected_lang" not in st.session_state:
    st.session_state["detected_lang"] = "unknown"

def do_reset():
    st.session_state["raw_text"] = ""
    st.session_state["formatted"] = ""
    st.session_state["detected_lang"] = "unknown"

with st.form("formatter_form"):
    raw = st.text_area(
        "Text brut (accepta: sectiuni sau tabel cu TAB-uri)",
        height=320,
        key="raw_text",
        placeholder="Lipeste aici textul brut…",
    )
    c1, c2 = st.columns(2)
    with c1:
        submitted = st.form_submit_button("Aranjeaza textul", use_container_width=True)
    with c2:
        reset = st.form_submit_button("Reset (text nou)", use_container_width=True)

if reset:
    do_reset()
    st.rerun()

if submitted:
    formatted, lang = process_input(st.session_state.get("raw_text", ""))
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
