import os
import traceback
import uuid
from pathlib import Path
import re

import google.generativeai as genai
import fitz  # PyMuPDF
from dotenv import load_dotenv
from flask import Flask, request, render_template, send_from_directory
from PIL import Image

# --- Konfigurasi Awal ---
load_dotenv()
app = Flask(__name__)

# Folder Upload
UPLOAD_FOLDER = '/tmp' if os.environ.get('VERCEL') else 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Konfigurasi Gemini ---
GEMINI_MODEL = None
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY tidak ditemukan di environment variable!")

    genai.configure(api_key=api_key)
    GEMINI_MODEL = genai.GenerativeModel("gemini-2.5-pro")
    print("✅ Gemini berhasil dikonfigurasi.")
except Exception as e:
    print(f"❌ Error Konfigurasi Gemini: {e}")

# --- Prompt Utama ---
CONVERSION_PROMPT = """Anda adalah asisten AI yang mengonversi dokumen atau gambar menjadi HTML semantik yang bersih dan terstruktur.
Gunakan elemen HTML5 seperti <section>, <article>, <header>, <footer>, <p>, <h1>–<h6>, <ul>, <ol>, <table> secara tepat.
Jangan sertakan tag <html>, <head>, atau <body> di hasil output.
"""

class ConversionAssistant:
    def _call_gemini_vision(self, image: Image.Image):
        if not GEMINI_MODEL:
            return "<strong>Error:</strong> Gemini belum dikonfigurasi dengan benar."

        try:
            response = GEMINI_MODEL.generate_content(
                contents=[CONVERSION_PROMPT, image],
                generation_config={
                    "temperature": 0.4,
                    "max_output_tokens": 4096,
                },
            )
            result_text = getattr(response, "text", None) or ""
            clean_html = re.sub(r'```html\n|```', '', result_text).strip()
            return clean_html or "<p><strong>Error:</strong> Tidak ada output dari Gemini.</p>"
        except Exception as e:
            print("❌ Error Gemini:", traceback.format_exc())
            return f"<p><strong>Error saat menghubungi Gemini API:</strong> {e}</p>"

    def to_pure_html(self, file_path_str: str):
        file_path = Path(file_path_str)
        suffix = file_path.suffix.lower()

        if suffix in ['.png', '.jpg', '.jpeg', '.bmp']:
            img = Image.open(file_path)
            return self._call_gemini_vision(img)

        elif suffix == '.pdf':
            doc = fitz.open(file_path)
            full_html = ""
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=120)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                html_snippet = self._call_gemini_vision(img)
                full_html += f"\n<!-- Halaman {i+1} -->\n{html_snippet}\n\n"
            doc.close()
            return full_html.strip()

        return "<p><strong>Error:</strong> Format file tidak didukung.</p>"

assistant = ConversionAssistant()

@app.route('/', methods=['GET', 'POST'])
def index():
    context = {}
    if request.method == 'POST':
        file = request.files.get('file_upload')
        if not file or file.filename == '':
            context['error'] = "Silakan pilih file terlebih dahulu."
            return render_template('index.html', **context)

        filename = f"{uuid.uuid4()}{Path(file.filename).suffix.lower()}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        html_snippet = assistant.to_pure_html(filepath)
        context['html_snippet'] = html_snippet
        if filename.endswith('.pdf'):
            context['pdf_filename'] = filename

    return render_template('index.html', **context)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True)