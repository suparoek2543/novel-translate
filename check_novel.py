from google import genai
import cloudscraper
import requests  # <--- เติมตัวนี้กลับเข้ามาครับ
from bs4 import BeautifulSoup
import time
import os
import re

# ==========================================
# ⚙️ ส่วนตั้งค่า
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# ลิงก์หน้าสารบัญหลัก
NOVEL_MAIN_URL = "https://kakuyomu.jp/works/822139839754922306"
DB_FILE = "last_episode_discord.txt"

# ตั้งค่า Client
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"❌ Error initializing Gemini: {e}")
        client = None
else:
    print("⚠️ ไม่พบ GEMINI_API_KEY")
    client = None

# สร้างตัวยิงเว็บ (Cloudscraper)
scraper = cloudscraper.create_scraper()

# ==========================================
# 🛠️ ฟังก์ชันทำงาน
# ==========================================

class Episode:
    def __init__(self, title, link):
        self.title = title
        self.link = link

def get_latest_episode_from_web():
    """แกะหน้าเว็บสารบัญเพื่อหาตอนล่าสุด (ใช้วิธีหา Pattern Link)"""
    print(f"กำลังเช็คหน้านิยายหลัก: {NOVEL_MAIN_URL}")
    try:
        response = scraper.get(NOVEL_MAIN_URL)
        
        if response.status_code != 200:
            print(f"❌ เข้าเว็บไม่ได้ Status Code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        page_title = soup.title.text.strip() if soup.title else "No Title"
        print(f"✅ เข้าถึงหน้าเว็บ: {page_title[:30]}...") 

        # Pattern คือ /works/เลขไอดี/episodes/เลขไอดี
        target_pattern = re.compile(r'/works/\d+/episodes/\d+')
        
        episode_links = soup.find_all('a', href=target_pattern)
        
        if episode_links:
            # ดึงตัวสุดท้ายของลิสต์
            last_ep = episode_links[-1]
            
            # ดึงชื่อตอน
            title = last_ep.text.strip()
            if not title:
                span = last_ep.find('span')
                if span: title = span.text.strip()
                else: title = "ตอนล่าสุด (ไม่ทราบชื่อ)"
            
            # ดึงลิงก์
            href = last_ep['href']
            if href.startswith('/'):
                link = "https://kakuyomu.jp" + href
            else:
                link = href
            
            return Episode(title, link)
        else:
            print("❌ ไม่พบลิงก์ตอนนิยายเลย")
            return None

    except Exception as e:
        print(f"❌ Error checking main page: {e}")
        return None

def get_novel_content(url):
    print(f"กำลังดึงเนื้อหาจาก: {url}")
    try:
        # ใช้ scraper ดึงเนื้อหา
        response = scraper.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        body_elem = soup.select_one('.widget-episodeBody')
        if body_elem:
            return body_elem.get_text(separator="\n", strip=True)
        
        print("❌ ไม่พบเนื้อหา (Element .widget-episodeBody หายไป)")
        return ""
    except Exception as e:
        print(f"❌ Error fetching content: {e}")
        return None

def translate_with_gemini(text):
    if not text or not client: return None
    
    print("⏳ กำลังส่งให้ Gemini แปล...")
    prompt = f"""
    คุณคือนักแปลนิยายไลท์โนเวลมืออาชีพ แปลเนื้อหาต่อไปนี้จากภาษาญี่ปุ่นเป็นภาษาไทย
    - ขอสำนวนวัยรุ่น อ่านง่าย สนุก เป็นธรรมชาติ
    - ไม่ต้องแปลคำทับศัพท์ที่เกมเมอร์เข้าใจ
    - จัดย่อหน้าให้อ่านง่าย
    
    เนื้อหาต้นฉบับ:
    {text}
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-pro', 
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ Translation Error: {e}")
        return None

def send_to_discord(title, link, content):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ ไม่มี Webhook URL (แสดงผลหน้าจอแทน)")
        return

    print("🚀 กำลังส่งเข้า Discord...")
    header = {
        "content": f"🚨 **ตอนใหม่มาแล้ว!** 🚨\n\n📖 **{title}**\n🔗 [อ่านต้นฉบับ]({link})\n\n🤖 กำลังแปล... รอสักครู่ครับ",
        "username": "น้องบอทนักแปล"
    }
    requests.post(DISCORD_WEBHOOK_URL, json=header)
    
    chunk_size = 1900
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        msg = chunk
        if len(chunks) > 1:
            msg = f"**[Part {i+1}/{len(chunks)}]**\n{chunk}"
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg, "username": "น้องบอทนักแปล"})
        time.sleep(1)

    requests.post(DISCORD_WEBHOOK_URL, json={"content": "✅ **แปลจบตอนครับ!**", "username": "น้องบอทนักแปล"})

# ==========================================
# 🚀 Main Loop
# ==========================================

def main():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: f.write("")

    with open(DB_FILE, "r") as f:
        last_link = f.read().strip()

    latest = get_latest_episode_from_web()
    
    if latest:
        print(f"🔍 ล่าสุดบนเว็บ: {latest.title}")
        print(f"🔗 Link: {latest.link}")
        
        if latest.link != last_link:
            print("✨ พบตอนใหม่! เริ่มดำเนินการ...")
            raw_content = get_novel_content(latest.link)
            
            if raw_content:
                translated_text = translate_with_gemini(raw_content)
                if translated_text:
                    send_to_discord(latest.title, latest.link, translated_text)
                    
                    with open(DB_FILE, "w") as f:
                        f.write(latest.link)
                    print("💾 บันทึกสถานะเรียบร้อย")
        else:
            print("😴 ยังไม่มีตอนใหม่")
    else:
        print("❌ ไม่สามารถดึงข้อมูลตอนล่าสุดได้")

if __name__ == "__main__":
    main()
