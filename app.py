import os
import traceback
import uuid
from pathlib import Path
import re

from google import genai
import fitz  # PyMuPDF
from dotenv import load_dotenv
from flask import Flask, request, render_template, send_from_directory
from PIL import Image

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Explain how AI works in a few words",
)

print(response.text)

# --- Konfigurasi Awal ---
load_dotenv()
app = Flask(__name__)

# Konfigurasi Folder
UPLOAD_FOLDER = '/tmp' if os.environ.get('VERCEL') else 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Konfigurasi API Gemini
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash-latest')
except Exception as e:
    print(f"Error Konfigurasi Gemini: {e}")
    GEMINI_MODEL = None

# --- Prompt Paten untuk Asisten AI ---
CONVERSION_PROMPT = """Anda adalah asisten AI untuk web content administrator yang bertugas mengonversi file .pdf atau gambar menjadi *pure HTML snippet* (tanpa DOCTYPE, <html>, <head>, atau <body>). Output hanya boleh berisi struktur HTML inti seperti <h1>, <h2>, <p>, <ul>, <ol>, <li>, <table>, dan <a>. Jangan sertakan teks tambahan, penjelasan, atau pembuka seperti 'Berikut hasil konversi'. Hanya berikan konten HTML murni.

Instruksi konversi:
1. Gunakan <h1> untuk judul utama, <h2> untuk subjudul, <h3> untuk sub-subjudul.
2. Gunakan <table> standar dengan border="1" tanpa CSS.
3. Gunakan <p> untuk paragraf, <strong> untuk bold.
4. Untuk list, gunakan <ul><li> atau <ol><li> sesuai konteks.
5. Jangan tulis <html> atau <body>, cukup isi konten HTML-nya saja.

Instruksi konversi khusus untuk SOP:
1. Judul SOP menggunakan <h2>.
2. Subjudul seperti 'Standard Operating Procedure' menggunakan <h3>.
3. Jika terdapat tabel, gunakan <table> dengan border="1", tanpa style CSS. Isi tabel jika kosong dengan strip (-).
4. List yang ditemukan dalam tabel harus menggunakan <ol> untuk urutan numerik dan <ul> untuk bullet list, walaupun hanya memiliki satu item.
5. Untuk FAQ, setiap pertanyaan setelah <h2> harus diikuti <br> (bukan <p>). Berikan penegasan seperti "Berikut ini adalah (copy judulnya)" setelah setiap pertanyaan.
6. Setiap kali ada teks tebal, gunakan <strong></strong>, namun jika terdapat teks italic, jangan menggunakan tag apapun.
7. Ketika terdapat aritmatika (misalnya 10+5/2), tulis dalam format teks (misalnya sepuluh ditambah lima dibagi dua).
8. Jangan mengubah urutan elemen atau isi teks dari dokumen asli kecuali untuk memperbaiki kesalahan penulisan."""

class ConversionAssistant:
    def _call_gemini_vision(self, image: Image.Image):
        """Fungsi inti untuk memanggil API Gemini menggunakan pola GenerativeModel."""
        if not GEMINI_MODEL:
            return "<strong>Error:</strong> API Key Gemini tidak terkonfigurasi."
        
        try:
            # --- PERUBAHAN UTAMA: Kembali ke pola GenerativeModel yang benar ---
            response = GEMINI_MODEL.generate_content([CONVERSION_PROMPT, image])
            # ------------------------------------------------------------------
            
            clean_response = re.sub(r'```html\n|```', '', response.text)
            return clean_response
        except Exception as e:
            return f"<strong>Error saat menghubungi Gemini API:</strong> {e}"

    def to_pure_html(self, file_path_str: str):
        file_path = Path(file_path_str)
        
        if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp']:
            img = Image.open(file_path)
            return self._call_gemini_vision(img)

        elif file_path.suffix.lower() == '.pdf':
            doc = fitz.open(file_path)
            full_html = ""
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=96)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                html_snippet = self._call_gemini_vision(img)
                full_html += f"\n{html_snippet}\n\n"
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

        filename = str(uuid.uuid4()) + Path(file.filename).suffix.lower()
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