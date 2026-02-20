import streamlit as st
import unicodedata
import re

from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator

st.set_page_config(page_title="Product Text Formatter", layout="centered")

# ----------------- utils -----------------
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
    # lowercase + remove diacritics + collapse spaces
    k = remove_diacritics((k or "")).lower().strip()
    k = re.sub(r"\s+", " ", k)
    return k

BANNED_KEYS = {
    "tara de origine",
    "country of origin",
    "catalogue",
    "catalog",
    "catalogue (title / chapter / page)",
    "nume in catalog",
    "catalog (title / chapter / page)",
    "cod unic de inregistrare",
    "cod unic de inregistrare ",
    "cod",  # product code
    "model",
    "marca",
    "marcă",
    "numarul paginii din catalog",
    "numarul paginii din catalog ",
    "numarul paginii",
    "cod de bare",
    "barcode",
}

def is_banned_key(key: str) -> bool:
    k = norm_key(key)
    if k in BANNED_KEYS:
        return True
    # substring checks to catch variants
    banned_sub = [
        "tara de origine",
        "country of origin",
        "catalogue",
        "catalog",
        "cod unic",
        "numarul paginii din catalog",
        "cod de bare",
        "barcode",
    ]
    return any(s in k for s in banned_sub) or k in {"cod", "model", "marca"}

@st.cache_data(show_spinner=False)
def detect_lang_safe(text: str) -> str:
    try:
        # langdetect needs some length; keep it safe
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
    # GoogleTranslator may fail if rate limited; keep fallback to original
    try:
        return GoogleTranslator(source="auto", target="ro").translate(text)
    except Exception:
        return text

def maybe_translate_block_to_ro(text: str, auto_translate: bool) -> tuple[str, str]:
    """
    Returns (translated_text, detected_lang)
    """
    t = text or ""
    lang = detect_lang_safe(t)
    if auto_translate and lang not in ("ro", "unknown"):
        return translate_to_ro(t), lang
    return t, lang

def extract_section(text: str, header: str):
    t = normalize(text)
    lines = t.split("\n")

    idx = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == header.strip().lower():
            idx = i
            break
    if idx is None:
        return None

    start = idx + 1

    known = {
        "informatii de baza", "informații de bază",
        "descriere",
        "caracteristici cheie",
        "caracteristici", "specificatii",
        "product specific details"
    }
    end = len(lines)
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if not s:
            continue
        low = s.lower()
        if low in known:
            end = j
            break
        if (":" not in s) and ("\t" not in s) and (len(s) <= 40) and re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", s):
            end = j
            break

    section = "\n".join(lines[start:end]).strip()
    return section if section else ""

def parse_key_values(block: str):
    if not block:
        return []
    out = []
    for ln in normalize(block).split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if ":" in ln:
            k, v = ln.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                out.append((k, v))
    return out

def parse_bullets_or_list(block: str):
    if not block:
        return []
    b = normalize(block).strip()
    b = re.sub(r"\n+", " ", b)

    if "•" in b:
        parts = [p.strip(" \t-•") for p in b.split("•")]
        return [p for p in parts if p]

    if "," in b:
        parts = [p.strip() for p in b.split(",")]
        return [p for p in parts if p]

    return [b] if b else []

def parse_tab_kvs(text: str):
    if not text:
        return []
    out = []
    for ln in normalize(text).split("\n"):
        ln = ln.strip()
        if not ln:
            continue

        # section headers
        if ln.lower() in {"product specific details", "informatii de baza", "informații de bază", "descriere", "caracteristici cheie"}:
            continue

        if "\t" in ln:
            parts = [p.strip() for p in ln.split("\t") if p.strip()]
        else:
            parts = [p.strip() for p in re.split(r"\s{2,}", ln) if p.strip()]

        if len(parts) >= 2:
            key = parts[0]
            value = " ".join(parts[1:]).strip()
            if key and value:
                out.append((key, value))
    return out

def guess_title(kvs):
    model = None
    marca = None
    for k, v in kvs:
        if norm_key(k) == "model":
            model = v
        if norm_key(k) in ("marca", "marca"):
            marca = v
    if model and marca:
        return f"Rucsac antifurt {model} ({marca})"
    if model:
        return f"Rucsac {model}"
    return ""

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

# ----------------- UI -----------------
st.title("Formatare text produs (input brut / tabel -> output formatat, fara diacritice)")

if "raw_text" not in st.session_state:
    st.session_state.raw_text = ""

with st.form("main_form", clear_on_submit=False):
    raw = st.text_area(
        "Lipeste aici textul brut (accepta: sectiuni sau tabel cu TAB-uri). Apasa Enter/Submit.",
        height=320,
        key="raw_text",
    )

    colA, colB, colC = st.columns(3)
    with colA:
        auto_translate = st.checkbox("Tradu automat in romana (daca e alta limba)", value=True)
    with colB:
        remove = st.checkbox("Elimina diacritice", value=True)
    with colC:
        hide_banned = st.checkbox("Elimina campuri nedorite (Cod/Model/Marca/etc.)", value=True)

    include_basic_info = st.checkbox("Include 'Informatii de baza' in Caracteristici (format pe sectiuni)", value=True)
    include_key_features = st.checkbox("Include 'Caracteristici cheie' in Caracteristici (format pe sectiuni)", value=True)

    title_override = st.text_input("Titlu (optional, daca vrei sa il fortezi)", placeholder="(lasa gol pentru auto)")

    submitted = st.form_submit_button("Aranjeaza textul")

# Reset button (outside the form so it works anytime)
if st.button("Reset (text nou)"):
    st.session_state.raw_text = ""
    st.rerun()

raw_norm = normalize(raw)

# Detecteaza daca e input "tabular" (are multe linii cu TAB)
tab_lines = sum(1 for ln in raw_norm.split("\n") if "\t" in ln)
is_tabular = tab_lines >= 2

title_final = ""
desc_text = ""
characteristics = []

detected_lang = "unknown"

if submitted and raw_norm.strip():
    if is_tabular:
        kvs_tab = parse_tab_kvs(raw_norm)
        # optionally remove banned keys
        if hide_banned:
            kvs_tab = [(k, v) for (k, v) in kvs_tab if not is_banned_key(k)]

        # build dict for title/description (even if user chose to hide banned keys)
        data = {norm_key(k): v for k, v in kvs_tab}

        title_final = title_override.strip() if title_override.strip() else data.get(norm_key("Nume produs"), "").strip()
        desc_text = data.get(norm_key("Descriere"), "").strip()

        # characteristics = rest (exclude title/desc)
        skip_keys = {norm_key("Nume produs"), norm_key("Descriere")}
        for k, v in kvs_tab:
            if norm_key(k) in skip_keys:
                continue
            characteristics.append(f"{k}: {v}")

        # Translate description + characteristics values (not keys)
        desc_text, detected_lang = maybe_translate_block_to_ro(desc_text, auto_translate)

        if auto_translate:
            translated = []
            for line in characteristics:
                # split "Key: Value" to keep key, translate value
                if ":" in line:
                    k, v = line.split(":", 1)
                    v2, _ = maybe_translate_block_to_ro(v.strip(), auto_translate)
                    translated.append(f"{k.strip()}: {v2}")
                else:
                    l2, _ = maybe_translate_block_to_ro(line, auto_translate)
                    translated.append(l2)
            characteristics = translated

    else:
        basic = extract_section(raw_norm, "Informații de bază") or extract_section(raw_norm, "Informatii de baza") or ""
        desc_text = extract_section(raw_norm, "Descriere") or ""
        keyf = extract_section(raw_norm, "Caracteristici cheie") or ""

        kvs = parse_key_values(basic)
        if hide_banned:
            kvs = [(k, v) for (k, v) in kvs if not is_banned_key(k)]

        title_auto = guess_title(parse_key_values(basic))  # title can use original full kvs
        title_final = title_override.strip() if title_override.strip() else title_auto

        if include_basic_info:
            for k, v in kvs:
                characteristics.append(f"{k}: {v}")

        if include_key_features:
            items = parse_bullets_or_list(keyf)
            if auto_translate:
                items_tr = []
                for it in items:
                    it2, detected_lang = maybe_translate_block_to_ro(it, auto_translate)
                    items_tr.append(it2)
                items = items_tr
            for it in items:
                characteristics.append(it)

        desc_text, detected_lang = maybe_translate_block_to_ro(desc_text, auto_translate)

    formatted = build_formatted(title_final, desc_text, characteristics)

    if remove:
        formatted = remove_diacritics(formatted)

    st.subheader("Rezultat")
    if auto_translate and detected_lang not in ("unknown", "ro"):
        st.caption(f"Detectat: {detected_lang} → tradus in romana")
    st.code(formatted, language="text")

    # Copy button
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
        <textarea id="txt" style="position:absolute; left:-9999px; top:-9999px;">{formatted.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</textarea>
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
        data=formatted.encode("utf-8"),
        file_name="text_produs_formatat.txt",
        mime="text/plain",
    )
elif submitted and not raw_norm.strip():
    st.info("Lipeste textul in caseta, apoi apasa 'Aranjeaza textul'.")
else:
    st.caption("Lipeste textul si apasa 'Aranjeaza textul'. Foloseste 'Reset' cand vrei alt produs.")
