import os
import io
import json
import logging
import pandas as pd
import matplotlib.pyplot as plt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

MATCHES = []

PROMPT_OCR = """
Analisis gambar hasil pertandingan Domino/Koa ini.
Sebutkan nama pemenang (2 orang), nama yang kalah (2 orang), dan Skor (misal "2-0" atau "2-1").
Keluaran HARUS berupa JSON murni tanpa teks/markdown ekstra:
{"win": ["NamaPemain1", "NamaPemain2"], "loss": ["NamaPemain3", "NamaPemain4"], "score": "2-0", "day": "Sn"}
"""

def generate_klasemen_image():
    players = {}
    for m in MATCHES:
        w_pts = 3 if m["score"] == "2-0" else 2
        l_pts = 0 if m["score"] == "2-0" else 1
        day_code = m.get("day", "Sn")
        
        for p in m["win"]:
            if p not in players:
                players[p] = {'Sn': 0, 'Sl': 0, 'Rb': 0, 'Km': 0, 'Jm': 0, 'Sb': 0, 'Mg': 0, 'M': 0, 'W': 0, 'L': 0, 'Pts': 0, 'today': 0}
            stats = players[p]
            stats['M'] += 1
            stats[day_code] += 1
            stats['today'] += 1
            if stats['today'] <= 3:
                stats['W'] += 1
                stats['Pts'] += w_pts
                
        for p in m["loss"]:
            if p not in players:
                players[p] = {'Sn': 0, 'Sl': 0, 'Rb': 0, 'Km': 0, 'Jm': 0, 'Sb': 0, 'Mg': 0, 'M': 0, 'W': 0, 'L': 0, 'Pts': 0, 'today': 0}
            stats = players[p]
            stats['M'] += 1
            stats[day_code] += 1
            stats['today'] += 1
            if stats['today'] <= 3:
                stats['L'] += 1
                stats['Pts'] += l_pts

    df = pd.DataFrame.from_dict(players, orient='index')
    if df.empty:
        return None
        
    df.reset_index(inplace=True)
    df.rename(columns={'index': 'Nama Pemain'}, inplace=True)
    df.sort_values(by=['Pts', 'W', 'M'], ascending=[False, False, True], inplace=True)
    df['Rank'] = df['Pts'].rank(method='min', ascending=False).astype(int)
    df.insert(0, 'No', range(1, len(df) + 1))

    day_cols = ['Sn', 'Sl', 'Rb', 'Km', 'Jm', 'Sb', 'Mg']
    for col in day_cols:
        df[col] = df[col].apply(lambda x: str(x) if x > 0 else '')

    df = df[['No', 'Rank', 'Nama Pemain', 'Sn', 'Sl', 'Rb', 'Km', 'Jm', 'Sb', 'Mg', 'M', 'W', 'L', 'Pts']]

    fig, ax = plt.subplots(figsize=(4.5, max(4, len(df)*0.22)), dpi=150)
    ax.axis('tight')
    ax.axis('off')

    table_data = df.values.tolist()
    columns = ["No", "Rank", "Nama Pemain", "Sn", "Sl", "Rb", "Km", "Jm", "Sb", "Mg", "M", "W", "L", "Pts"]

    table = ax.table(cellText=table_data, colLabels=columns, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(6.5)

    for key, cell in table.get_celld().items():
        cell.set_height(0.022)
        if key[0] == 0:
            cell.set_facecolor('#d9ea80')
            cell.set_text_props(weight='bold')
        else:
            if key[1] == 2:
                cell.set_text_props(ha='left')
            if key[1] == 3 and cell.get_text().get_text() != '':
                val = int(cell.get_text().get_text())
                if val > 3:
                    cell.set_facecolor('#cc0000')
                    cell.get_text().set_color('#ffff00')
                    cell.get_text().set_weight('bold')

    col_widths = [0.06, 0.08, 0.28, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.07, 0.07, 0.07, 0.09]
    for i, width in enumerate(col_widths):
        for j in range(len(table_data) + 1):
            table[j, i].set_width(width)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.02)
    buf.seek(0)
    plt.close(fig)
    return buf

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content([PROMPT_OCR, {"mime_type": "image/jpeg", "data": bytes(image_bytes)}])
    
    try:
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match_data = json.loads(clean_text)
        MATCHES.append(match_data)
        
        await update.message.reply_text(f"✅ Screenshot diproses:\n🏆 Menang: {', '.join(match_data['win'])}\n❌ Kalah: {', '.join(match_data['loss'])}\n📊 Skor: {match_data['score']}")
        
        img_buf = generate_klasemen_image()
        if img_buf:
            await update.message.reply_photo(photo=img_buf, caption="🏆 **BINTANG LIGA PKPM PREMIUM EDISI 4**")
    except Exception as e:
        await update.message.reply_text("⚠️ Gagal membaca screenshot. Pastikan gambar jelas.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo! Kirimkan screenshot pertandingan untuk memperbarui klasemen otomatis.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
