import streamlit as st
import unicodedata
import re

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

def extract_section(text: str, header: str):
    """
    Returns section text that starts after a header line equal to `header`,
    until the next 'likely header' line or end.
    """
    t = normalize(text)
    lines = t.split("\n")
    # find header line index (case-insensitive)
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == header.strip().lower():
            idx = i
            break
    if idx is None:
        return None

    # section starts after header line
    start = idx + 1

    # heuristic: next header is a line that has no ":" and length <= 40 and has letters,
    # OR is exactly one of known headers
    known = {"informatii de baza", "descriere", "caracteristici cheie", "caracteristici", "specificatii"}
    end = len(lines)
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if not s:
            continue
        low = s.lower()
        if low in known:
            end = j
            break
        if (":" not in s) and (len(s) <= 40) and re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", s):
            # looks like a heading
            end = j
            break

    section = "\n".join(lines[start:end]).strip()
    return section if section else ""

def parse_key_values(block: str):
    """
    Parse lines like 'Cod: 34.711.10' into list of (key, value)
    """
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
    """
    Parse '• item • item' OR lines containing bullets into list of items.
    """
    if not block:
        return []
    b = normalize(block).strip()

    # turn newlines into spaces to catch "•" inline lists
    b = re.sub(r"\n+", " ", b)

    if "•" in b:
        parts = [p.strip(" \t-•") for p in b.split("•")]
        return [p for p in parts if p]

    # fallback: split by " , " or ";" if looks like a list
    if "," in b:
        parts = [p.strip() for p in b.split(",")]
        return [p for p in parts if p]

    # last fallback: one item
    return [b] if b else []

def guess_title(kvs):
    """
    Prefer: 'Rucsac' + Model if exists, else Model, else first strong identifier.
    """
    model = None
    marca = None
    for k, v in kvs:
        if k.lower() == "model":
            model = v
        if k.lower() in ("marca", "marcă"):
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
        parts += [description.strip(), ""]
    if characteristics_lines:
        parts.append("Caracteristici:")
        for ln in characteristics_lines:
            ln = ln.strip()
            if not ln:
                continue
            if not ln.endswith(";"):
                ln += ";"
            parts.append(ln)

    return ("\n".join(parts).strip() + "\n") if parts else ""

# ----------------- UI -----------------
st.title("Formatare text produs (input brut -> output ca in catalog, fara diacritice)")

raw = st.text_area(
    "Lipeste aici textul brut (ex: Informatii de baza / Descriere / Caracteristici cheie)",
    height=320,
)

remove = st.checkbox("Elimina diacritice", value=True)
include_basic_info = st.checkbox("Include 'Informatii de baza' in Caracteristici", value=True)
include_key_features = st.checkbox("Include 'Caracteristici cheie' in Caracteristici", value=True)

title_override = st.text_input("Titlu (optional, daca vrei sa il fortezi)", placeholder="(lasa gol pentru auto)")

# ----------------- Parse & build -----------------
basic = extract_section(raw, "Informații de bază") or extract_section(raw, "Informatii de baza") or ""
desc = extract_section(raw, "Descriere") or ""
keyf = extract_section(raw, "Caracteristici cheie") or ""

kvs = parse_key_values(basic)
title_auto = guess_title(kvs)

characteristics = []

if include_basic_info:
    # Keep same order as in input
    for k, v in kvs:
        characteristics.append(f"{k}: {v}")

if include_key_features:
    items = parse_bullets_or_list(keyf)
    # show each feature as a separate line
    for it in items:
        characteristics.append(it)

title_final = title_override.strip() if title_override.strip() else title_auto

formatted = build_formatted(title_final, desc, characteristics)
if remove:
    formatted = remove_diacritics(formatted)

st.subheader("Rezultat")
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
