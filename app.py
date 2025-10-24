import os
import re
import uuid
import traceback
from collections import Counter

import pdfplumber
from flask import Flask, request, render_template, send_from_directory
from PIL import Image

try:
    import pytesseract
    # Jika menggunakan Windows, Anda mungkin perlu menambahkan baris ini:
    # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except ImportError:
    pytesseract = None

app = Flask(__name__)

# --- Konfigurasi Folder untuk Vercel ---
# Semua file sementara HARUS disimpan di direktori /tmp
UPLOAD_FOLDER = '/tmp'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Asisten AI untuk konversi (logika inti tidak berubah)
class ConversionAssistant:
    def to_pure_html(self, file_path):
        if file_path.lower().endswith('.pdf'):
            return self._convert_pdf(file_path)
        elif file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            return self._convert_image(file_path)
        return "<p><strong>Error:</strong> Format file tidak didukung.</p>"

    def _convert_image(self, file_path):
        if not pytesseract:
            return "<p><strong>Error:</strong> Pytesseract tidak terinstal.</p>"
        try:
            text = pytesseract.image_to_string(Image.open(file_path), lang='ind')
            return self._structure_text_to_html(text)
        except Exception as e:
            return f"<p><strong>Error OCR:</strong> {e}</p>"

    def _structure_text_to_html(self, text):
        html_output = ""
        lines = text.split('\n')
        is_in_list = None
        is_faq = False
        faq_title = ""

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            
            if is_in_list and not re.match(r'^((\d+\.)|([a-z]\))|[-•*])\s', stripped_line):
                html_output += f"</{is_in_list}>\n"
                is_in_list = None
            
            if stripped_line.isupper() and len(stripped_line.split()) < 6:
                html_output += f"<h1>{stripped_line}</h1>\n"
                if "FAQ" in stripped_line.upper():
                    is_faq, faq_title = True, stripped_line
            elif stripped_line.istitle() and len(stripped_line.split()) < 8:
                html_output += f"<h2>{stripped_line}</h2>\n"
                if "Standard Operating Procedure" in stripped_line:
                    html_output += f"<h3>{stripped_line}</h3>\n"
            elif re.match(r'^\d+\.\s', stripped_line):
                if is_in_list != 'ol':
                    if is_in_list: html_output += f"</{is_in_list}>\n"
                    html_output += "<ol>\n"
                    is_in_list = 'ol'
                html_output += f"  <li>{re.sub(r'^\d+\.\s', '', stripped_line)}</li>\n"
            elif re.match(r'^([a-z]\))|[-•*]\s', stripped_line):
                if is_in_list != 'ul':
                    if is_in_list: html_output += f"</{is_in_list}>\n"
                    html_output += "<ul>\n"
                    is_in_list = 'ul'
                html_output += f"  <li>{re.sub(r'^([a-z]\))|[-•*]\s', '', stripped_line)}</li>\n"
            elif is_faq and stripped_line.endswith('?'):
                 html_output += f"{stripped_line}<br>\n<strong>Berikut ini adalah {faq_title}</strong>\n"
            else:
                html_output += f"<p>{stripped_line}</p>\n"
        
        if is_in_list:
            html_output += f"</{is_in_list}>\n"
            
        return html_output

    def _convert_pdf(self, file_path):
        html_output = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    full_text += page.extract_text(layout=True) or ""
                html_output = self._structure_text_to_html(full_text)
        except Exception as e:
            return f"<p><strong>Error PDF:</strong> {e}</p>"
        
        return html_output.strip()

assistant = ConversionAssistant()

@app.route('/', methods=['GET', 'POST'])
def index():
    context = {}
    if request.method == 'POST':
        file = request.files.get('file_upload')
        if not file or file.filename == '':
            context['error'] = "Silakan pilih file terlebih dahulu."
            return render_template('index.html', **context)

        # Simpan file dengan nama unik agar tidak tertimpa
        filename = str(uuid.uuid4()) + os.path.splitext(file.filename)[1].lower()
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Lakukan konversi
        html_snippet = assistant.to_pure_html(filepath)
        
        # Kirim nama file dan hasil snippet ke template
        context['html_snippet'] = html_snippet
        # Hanya kirim nama file jika itu adalah PDF
        if filename.endswith('.pdf'):
            context['pdf_filename'] = filename

    return render_template('index.html', **context)

# Route baru untuk menyajikan file yang diunggah
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == '__main__':
    app.run(debug=True)