from google import genai
from google.genai import types
import cloudscraper
import requests
from bs4 import BeautifulSoup
import time
import os
import re
import random
import json # <--- เพิ่มตัวนี้
from urllib.parse import urljoin

# ==========================================
# ⚙️ ส่วนตั้งค่า
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
NOVEL_MAIN_URL = "https://kakuyomu.jp/works/822139841708705081"

# ไฟล์ที่จะเก็บข้อมูลนิยาย (Database)
JSON_DB_FILE = "novels.json"
HISTORY_FILE = "history_novel_2.txt"

# ตั้งค่า Client
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"❌ Error initializing Client: {e}")
        client = None
else:
    print("⚠️ ไม่พบ GEMINI_API_KEY")
    client = None

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

# ==========================================
# 🛠️ ฟังก์ชันจัดการ JSON
# ==========================================

def save_to_json(ep_data):
    """บันทึกตอนนิยายลงไฟล์ JSON"""
    data = []
    
    # 1. โหลดของเก่าถ้ามี
    if os.path.exists(JSON_DB_FILE):
        with open(JSON_DB_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except:
                data = [] # ถ้าไฟล์พัง ให้เริ่มใหม่
    
    # 2. เช็คว่ามีตอนเดิมอยู่ไหม (Update หรือ Append)
    # ใช้ Link เป็นตัวเช็คว่าซ้ำไหม
    existing_idx = next((index for (index, d) in enumerate(data) if d["link"] == ep_data["link"]), None)
    
    if existing_idx is not None:
        data[existing_idx] = ep_data # อัปเดตของเดิม
    else:
        data.append(ep_data) # เพิ่มตอนใหม่
        
    # 3. บันทึกกลับลงไฟล์
    with open(JSON_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"💾 บันทึกลง {JSON_DB_FILE} เรียบร้อย")

# ==========================================
# 🛠️ ฟังก์ชันเดิม (ปรับปรุงเล็กน้อย)
# ==========================================

def load_history():
    if not os.path.exists(HISTORY_FILE): return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_to_history(url):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def get_first_episode_url():
    print(f"📖 หาตอนแรกจาก: {NOVEL_MAIN_URL}")
    try:
        response = scraper.get(NOVEL_MAIN_URL)
        soup = BeautifulSoup(response.text, 'html.parser')
        first_ep_link = soup.select_one('a#readFromFirstEpisode')
        if first_ep_link: return urljoin(NOVEL_MAIN_URL, first_ep_link['href'])
        else:
            target_pattern = re.compile(r'/works/\d+/episodes/\d+')
            links = soup.find_all('a', href=target_pattern)
            if links:
                sorted_links = sorted(links, key=lambda x: int(re.search(r'episodes/(\d+)', x['href']).group(1)))
                return urljoin(NOVEL_MAIN_URL, sorted_links[0]['href'])
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def find_next_link(soup, current_url):
    next_btn = soup.select_one('a.widget-episode-navigation-next') or \
               soup.select_one('a#contentMain-readNextEpisode') or \
               soup.find('a', string=re.compile('次のエピソード'))
    if next_btn: return urljoin(current_url, next_btn['href'])
    return None

def get_content_and_next_link(url, max_retries=3):
    headers = {'Referer': NOVEL_MAIN_URL}
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(1, 1.5)) 
            response = scraper.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                title = soup.select_one('.widget-episodeTitle').text.strip()
                body = soup.select_one('.widget-episodeBody').get_text(separator="\n", strip=True)
                next_link = find_next_link(soup, url)
                
                # ดึง ID ตอนจาก URL เพื่อใช้เรียงลำดับ
                ep_id_match = re.search(r'episodes/(\d+)', url)
                ep_id = ep_id_match.group(1) if ep_id_match else "0"

                return {"title": title, "content": body, "next_link": next_link, "ep_id": ep_id}
            time.sleep(2)
        except Exception as e:
            print(f"   ⚠️ Error: {e}")
    return None

def translate_smart(text, retry_count=0):
    if not client: return None, "No Client"
    if not text: return None, "No Content"
    
    if retry_count == 0:
        prompt = f"แปลนิยายญี่ปุ่นนี้เป็นไทย สำนวนวัยรุ่น อ่านสนุก:\n- เจอคำล่อแหลมให้เลี่ยงคำ\nเนื้อหา:\n{text[:15000]}"
    elif retry_count == 1:
        prompt = f"**แปลโดยหลีกเลี่ยงเนื้อหาทางเพศ/รุนแรง**\n- สรุปฉากวาบหวิวแทน\nเนื้อหา:\n{text[:15000]}"
    else:
        prompt = f"สรุปเนื้อเรื่องตอนนี้เป็นภาษาไทย:\nเนื้อหา:\n{text[:15000]}"

    try:
        response = client.models.generate_content(
            model='gemini-2.5-pro', contents=prompt,
            config=types.GenerateContentConfig(safety_settings=[
                types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')
            ])
        )
        if not response.text or not response.text.strip(): raise ValueError("Empty response")
        return response.text, None 
    except Exception as e:
        error_msg = str(e)
        if ("429" in error_msg or "503" in error_msg):
            time.sleep((retry_count + 1) * 10)
            return translate_smart(text, retry_count) 
        elif retry_count < 2:
            time.sleep(2)
            return translate_smart(text, retry_count + 1)
        else:
            return None, f"ยอมแพ้ ({error_msg})"

# ==========================================
# 🚀 Main Loop
# ==========================================

def main():
    print("🚀 เริ่มระบบ Web Novel Generator...")
    completed_urls = load_history()
    current_url = get_first_episode_url()
    if not current_url: return

    ep_count = 1
    
    while current_url:
        print(f"\n[{ep_count}] ตรวจสอบ: {current_url}")
        
        if current_url in completed_urls:
            print("   ⏩ มีในฐานข้อมูลแล้ว -> ข้าม")
            data = get_content_and_next_link(current_url)
            if data and data['next_link']:
                current_url = data['next_link']
                ep_count += 1
                continue
            else:
                print("   🏁 จบเรื่อง (ในหน้าที่ข้าม)")
                break

        data = get_content_and_next_link(current_url)
        if not data:
            print("   ❌ ดึงข้อมูลไม่ได้ -> จบ")
            break

        title = data['title']
        translated, error_msg = translate_smart(data['content'])
        
        if translated:
            print("   ✅ แปลสำเร็จ -> บันทึกลง JSON")
            
            # เตรียมข้อมูลบันทึก
            episode_data = {
                "ep_id": data['ep_id'],
                "title": title,
                "content": translated,
                "link": current_url
            }
            
            # 💾 บันทึก
            save_to_json(episode_data)
            save_to_history(current_url)
            completed_urls.add(current_url)
        else:
            print(f"   ❌ ไม่ผ่าน: {error_msg}")

        if data['next_link']:
            print(f"   ➡️ ไปตอนถัดไป (พัก 5 วิ)")
            current_url = data['next_link']
            ep_count += 1
            time.sleep(5) 
        else:
            print("\n🏁 จบเรื่องแล้ว")
            current_url = None

    print("\n🎉 เสร็จสิ้น!")

if __name__ == "__main__":
    main()
