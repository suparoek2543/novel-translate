import os, sys, time, json, re
import cloudscraper
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from urllib.parse import urljoin

# ==========================================
# ⚙️ ส่วนตั้งค่า
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JSON_DB_FILE = "novels.json"
HISTORY_FILE = "history_all.txt"
LIST_FILE = "novel_list.txt"  # ไฟล์เก็บรายชื่อนิยายที่ต้องเช็คทุกวัน

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})

# --- ฟังก์ชันแปลและบันทึก (คงเดิมจากที่รวมไว้ก่อนหน้า) ---
def translate_text(text, is_chapter=False):
    if not client or not text: return text
    try:
        res = client.models.generate_content(model='gemini-2.5-pro', contents=f"Translate to Thai: {text}")
        return res.text.strip().replace('"', '')
    except: return text

def translate_smart_content(text):
    if not client: return "Error", True
    try:
        res = client.models.generate_content(
            model='gemini-2.5-pro', 
            contents=f"แปลนิยายญี่ปุ่นนี้เป็นไทย:\n{text[:15000]}",
            config=types.GenerateContentConfig(safety_settings=[
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
            ])
        )
        return res.text, False
    except: return "⚠️ ติดนโยบายความปลอดภัย", True

def save_to_json(novel_url, novel_title, ep_data):
    data = {}
    if os.path.exists(JSON_DB_FILE):
        with open(JSON_DB_FILE, "r", encoding="utf-8") as f:
            try: data = json.load(f)
            except: data = {}
    if novel_url not in data: data[novel_url] = {"title": novel_title, "chapters": []}
    if not any(c['link'] == ep_data['link'] for c in data[novel_url]["chapters"]):
        data[novel_url]["chapters"].append(ep_data)
        data[novel_url]["chapters"].sort(key=lambda x: int(x['ep_id']))
        with open(JSON_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    return False

# ==========================================
# 🚀 Logic การจัดการรายการ (List Management)
# ==========================================

def get_novel_list():
    if not os.path.exists(LIST_FILE): return []
    with open(LIST_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def add_to_novel_list(url):
    current_list = get_novel_list()
    if url not in current_list:
        with open(LIST_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")
        print(f"➕ เพิ่มนิยายใหม่ลงในรายการติดตาม: {url}")

def process_novel(main_url):
    print(f"--- 🔄 ตรวจสอบ: {main_url} ---")
    try:
        r = scraper.get(main_url)
        soup = BeautifulSoup(r.text, 'html.parser')
        raw_title = soup.select_one('#workTitle').text.strip()
        thai_novel_title = translate_text(raw_title)

        first_ep_node = soup.select_one('a#readFromFirstEpisode')
        if not first_ep_node: return
        current_url = urljoin(main_url, first_ep_node['href'])

        while current_url:
            history = ""
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f: history = f.read()
            
            if current_url in history:
                res = scraper.get(current_url); s = BeautifulSoup(res.text, 'html.parser')
                next_a = s.select_one('a.widget-episode-navigation-next')
                current_url = urljoin(current_url, next_a['href']) if next_a else None
                continue

            res = scraper.get(current_url); s = BeautifulSoup(res.text, 'html.parser')
            title = s.select_one('.widget-episodeTitle').text.strip()
            body = s.select_one('.widget-episodeBody').get_text(separator="\n")
            ep_id = re.search(r'episodes/(\d+)', current_url).group(1)

            thai_content, is_error = translate_smart_content(body)
            thai_ep_title = translate_text(title, is_chapter=True)
            ep_data = {"ep_id": ep_id, "title": thai_ep_title, "content": thai_content, "link": current_url}
            
            if save_to_json(main_url, thai_novel_title, ep_data):
                with open(HISTORY_FILE, "a") as f: f.write(current_url + "\n")
                print(f"✅ บันทึกสำเร็จ: {thai_ep_title}")

            next_a = s.select_one('a.widget-episode-navigation-next')
            current_url = urljoin(current_url, next_a['href']) if next_a else None
            time.sleep(2)
    except Exception as e: print(f"❌ Error: {e}")

if __name__ == "__main__":
    target_url = os.getenv("TARGET_URL")
    
    if target_url and "kakuyomu.jp" in target_url:
        # 1. ถ้ามีลิงก์ใหม่จากหน้าเว็บ -> เพิ่มเข้าลิสต์ และเริ่มแปลทันที
        add_to_novel_list(target_url.strip())
        process_novel(target_url.strip())
    else:
        # 2. ถ้าไม่มีลิงก์ใหม่ (รันรายวัน) -> อ่านจากไฟล์แล้วตรวจสอบทุกเรื่อง
        novels = get_novel_list()
        for url in novels:
            process_novel(url)