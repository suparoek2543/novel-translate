from google import genai
from google.genai import types
import cloudscraper
import requests
from bs4 import BeautifulSoup
import time
import os
import re
import random

# ==========================================
# ⚙️ ส่วนตั้งค่า (รายชื่อนิยาย)
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 

# 🟢 เพิ่มนิยายของคุณตรงนี้ (ก๊อปปี้ปีกกา {...} เพิ่มต่อท้ายได้เลย)
NOVEL_LIST = [
    {
        "name": "พื่อนสมัยเด็กสาวสวยอันดับหนึ่งของโรงเรียน", 
        "url": "https://kakuyomu.jp/works/822139839754922306",
        # ใส่ Webhook URL ของเรื่องนี้ (แนะนำให้ดึงจาก Secret หรือใส่ตรงนี้ถ้า Repo เป็น Private)
        "webhook_url": os.getenv("WEBHOOK_NOVEL_1"), 
        "db_file": "last_ep_novel_1.txt" # ไฟล์จำตอนล่าสุด (ห้ามซ้ำกับเรื่องอื่น)
    },
    {
        "name": "เรื่องที่ผมไปช่วยพี่น้องสาวสวย",
        "url": "https://kakuyomu.jp/works/16816700429097793676",
        "webhook_url": os.getenv("WEBHOOK_NOVEL_2"), 
        "db_file": "last_ep_novel_2.txt"
    },
]

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
# 🛠️ ฟังก์ชันทำงาน
# ==========================================

class Episode:
    def __init__(self, title, link, ep_id):
        self.title = title
        self.link = link
        self.ep_id = int(ep_id)

def get_latest_episode_from_web(novel_url):
    print(f"📖 เช็คสารบัญ: {novel_url}")
    try:
        response = scraper.get(novel_url)
        if response.status_code != 200:
            print(f"❌ เข้าเว็บไม่ได้ Status: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        target_pattern = re.compile(r'/works/\d+/episodes/(\d+)')
        episode_links = soup.find_all('a', href=target_pattern)
        
        if episode_links:
            # ดึงตัวสุดท้าย (ตอนล่าสุด)
            last_ep = episode_links[-1]
            match = target_pattern.search(last_ep['href'])
            ep_id = match.group(1) if match else 0
            
            title = last_ep.text.strip()
            if not title:
                span = last_ep.find('span')
                title = span.text.strip() if span else f"Episode {ep_id}"
            
            href = last_ep['href']
            link = "https://kakuyomu.jp" + href if href.startswith('/') else href
            
            return Episode(title, link, ep_id)
        
        return None

    except Exception as e:
        print(f"❌ Error checking page: {e}")
        return None

def get_content_with_retry(url, main_url, max_retries=3):
    headers = {'Referer': main_url, 'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'}
    
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(2, 5))
            response = scraper.get(url, headers=headers, timeout=20)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                body = soup.select_one('.widget-episodeBody')
                
                if not body:
                    main_content = soup.select_one('#contentMain-inner')
                    if main_content:
                        for invalid in main_content.select('button, .widget-episode-navigation'):
                            invalid.decompose()
                        body = main_content

                if body:
                    return body.get_text(separator="\n", strip=True)
            
            print(f"   ⚠️ ครั้งที่ {attempt+1} ไม่สำเร็จ (Status: {response.status_code})")
        except Exception as e:
            print(f"   ⚠️ Error: {e}")
            
    return None

def translate(text):
    if not text or not client: return None
    
    # Prompt แบบ Soften (แปลได้ทุกแนว)
    prompt = f"""
    คุณคือนักแปลนิยายมืออาชีพ แปลนิยายญี่ปุ่นเรื่องนี้เป็นภาษาไทย
    กติกา:
    1. สำนวนวัยรุ่น อ่านสนุก เป็นธรรมชาติ
    2. หากพบเนื้อหาล่อแหลม/รุนแรง ให้ "ปรับสำนวนให้ซอฟต์ลง" (ใช้คำเลี่ยง/คำเปรียบเปรย) 
    3. ห้ามหยุดแปล ให้แปลจนจบตอน
    
    เนื้อหา:
    {text}
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')
                ]
            )
        )
        return response.text
    except Exception as e:
        print(f"   ❌ Gemini Error: {e}")
        return None

def send_discord(webhook_url, title, link, content):
    if not webhook_url: 
        print("⚠️ ไม่มี Webhook URL")
        return

    requests.post(webhook_url, json={
        "content": f"🚨 **ตอนใหม่มาแล้ว!**\n📖 **{title}**\n🔗 [อ่านต้นฉบับ]({link})\n🤖 กำลังแปล..."
    })
    
    chunk_size = 1900
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        msg = f"**[Part {i+1}/{len(chunks)}]**\n{chunk}" if len(chunks) > 1 else chunk
        requests.post(webhook_url, json={"content": msg})
        time.sleep(1)

    requests.post(webhook_url, json={"content": "✅ **แปลจบตอนครับ**"})

# ==========================================
# 🚀 Main Loop (วนทำทีละเรื่อง)
# ==========================================

def process_novel(novel):
    """ฟังก์ชันจัดการนิยาย 1 เรื่อง"""
    print(f"\n--- 🔄 เริ่มตรวจสอบ: {novel['name']} ---")
    
    webhook = novel.get('webhook_url')
    if not webhook:
        print("❌ ข้าม: ไม่ได้ตั้งค่า Webhook URL")
        return

    db_file = novel['db_file']
    
    # สร้างไฟล์ DB ถ้าไม่มี
    if not os.path.exists(db_file):
        with open(db_file, "w") as f: f.write("")

    with open(db_file, "r") as f:
        last_link = f.read().strip()

    # เช็คตอนล่าสุด
    latest = get_latest_episode_from_web(novel['url'])
    
    if latest:
        print(f"🔍 ล่าสุดบนเว็บ: {latest.title}")
        
        if latest.link != last_link:
            print(f"✨ พบตอนใหม่! ({latest.title})")
            
            content = get_content_with_retry(latest.link, novel['url'])
            if content:
                print("⏳ กำลังแปล...")
                translated = translate(content)
                if translated:
                    print("🚀 ส่งเข้า Discord...")
                    send_discord(webhook, latest.title, latest.link, translated)
                    
                    # อัปเดตล่าสุด
                    with open(db_file, "w") as f:
                        f.write(latest.link)
                    print("💾 บันทึกสถานะแล้ว")
                else:
                    print("❌ แปลไม่สำเร็จ")
            else:
                print("❌ ดึงเนื้อหาไม่สำเร็จ")
        else:
            print("😴 ยังไม่มีตอนใหม่")
    else:
        print("❌ หาตอนล่าสุดไม่เจอ")

def main():
    print("🤖 บอทเริ่มทำงาน (รองรับหลายเรื่อง)...")
    
    for novel in NOVEL_LIST:
        process_novel(novel)
        print("-" * 30)

if __name__ == "__main__":
    main()
