import streamlit as st
import unicodedata
import re

st.set_page_config(page_title="Product Text Formatter", layout="centered")

def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))

    # Extra safety for common RO diacritics
    replacements = {
        "ș": "s", "Ş": "S", "ț": "t", "Ţ": "T",
        "ă": "a", "Ă": "A", "â": "a", "Â": "A",
        "î": "i", "Î": "I",
    }
    for a, b in replacements.items():
        no_marks = no_marks.replace(a, b)

    # Clean spacing a bit
    no_marks = re.sub(r"[ \t]+\n", "\n", no_marks)
    no_marks = re.sub(r"\n{3,}", "\n\n", no_marks)
    return no_marks

def build_formatted(title: str, description: str, characteristics: str) -> str:
    title = (title or "").strip()
    description = (description or "").strip()
    characteristics = (characteristics or "").strip()

    parts = []
    if title:
        parts.append(title)
        parts.append("")  # blank line after title

    if description:
        parts.append(description)
        parts.append("")

    if characteristics:
        parts.append("Caracteristici:")
        lines = [ln.strip() for ln in characteristics.splitlines() if ln.strip()]
        for ln in lines:
            if not ln.endswith(";"):
                ln += ";"
            parts.append(ln)

    return ("\n".join(parts).strip() + "\n") if parts else ""

st.title("Formatter text produs (fara diacritice)")
st.write("Introdu titlul, descrierea si caracteristicile. Vei obtine textul formatat + buton Copy.")

title = st.text_input("Titlu produs", placeholder="Rucsac antifurt Norden")

description = st.text_area(
    "Descriere (paragrafele se pastreaza)",
    height=180,
    placeholder=(
        "Rucsacul antifurt RPET 300 D este o optiune sigura si durabila...\n"
        "Acest rucsac are doua compartimente principale captusite...\n"
        "Rucsacul include si o curea pentru carucior..."
    ),
)

characteristics = st.text_area(
    "Caracteristici (cate o linie pe rand)",
    height=160,
    placeholder=(
        "Dimensiuni: 32 x 42 x 12 cm\n"
        "Culori disponibile: Negru, gri, albastru denim\n"
        "Material: RPET 300 D\n"
        "Diagonala laptop: 15 inch"
    ),
)

remove = st.checkbox("Elimina diacritice", value=True)

formatted = build_formatted(title, description, characteristics)
if remove:
    formatted = remove_diacritics(formatted)

st.subheader("Rezultat (copiere rapida)")
st.code(formatted, language="text")

# Copy button (works in modern browsers)
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
          status.textContent = "Nu pot copia automat. Selecteaza manual din caseta de mai sus.";
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
