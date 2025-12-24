from google import genai
import requests
from bs4 import BeautifulSoup
import time
import os

# ==========================================
# ⚙️ ส่วนตั้งค่า
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# ❌ ไม่ใช้ RSS แล้ว แต่ใช้หน้าสารบัญหลักแทน
NOVEL_MAIN_URL = "https://kakuyomu.jp/works/822139839754922306"
DB_FILE = "last_episode_discord.txt"

# ตั้งค่า Client
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("❌ ไม่พบ GEMINI_API_KEY")
    exit(1)

# ==========================================
# 🛠️ ฟังก์ชันทำงาน
# ==========================================

class Episode:
    """สร้างคลาสจำลองเพื่อให้เหมือน structure เดิม"""
    def __init__(self, title, link):
        self.title = title
        self.link = link

def get_latest_episode_from_web():
    """แกะหน้าเว็บสารบัญเพื่อหาตอนล่าสุด (ล่างสุด)"""
    print(f"กำลังเช็คหน้านิยายหลัก: {NOVEL_MAIN_URL}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(NOVEL_MAIN_URL, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ เข้าเว็บไม่ได้ Status Code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ค้นหาลิงก์ตอนทั้งหมดในสารบัญ (Class: widget-toc-episode)
        # Kakuyomu เรียงจากบนลงล่าง ตอนใหม่สุดจะอยู่ล่างสุด
        episode_links = soup.select('.widget-toc-episode a')
        
        if episode_links:
            last_ep = episode_links[-1] # เอาตัวสุดท้าย
            
            # ดึงชื่อตอน
            title_span = last_ep.select_one('.widget-toc-episode-titleLabel')
            title = title_span.text.strip() if title_span else "No Title"
            
            # ดึงลิงก์ (ลิงก์จะเป็นแบบ relative เช่น /works/xxx/episodes/yyy ต้องเอามาต่อ domain)
            link = "https://kakuyomu.jp" + last_ep['href']
            
            return Episode(title, link)
            
        return None

    except Exception as e:
        print(f"❌ Error checking main page: {e}")
        return None

def get_novel_content(url):
    print(f"กำลังดึงเนื้อหาจาก: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        body_elem = soup.select_one('.widget-episodeBody')
        if body_elem:
            return body_elem.get_text(separator="\n", strip=True)
        return ""
    except Exception as e:
        print(f"❌ Error fetching content: {e}")
        return None

def translate_with_gemini(text):
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
            model='gemini-1.5-flash', 
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ Translation Error: {e}")
        return None

def send_to_discord(title, link, content):
    if not DISCORD_WEBHOOK_URL:
        return

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

    # เปลี่ยนฟังก์ชันตรงนี้ เป็นการเช็คจากหน้าเว็บโดยตรง
    latest = get_latest_episode_from_web()
    
    if latest:
        print(f"🔍 ล่าสุดบนเว็บคือตอน: {latest.title}")
        print(f"🔗 Link: {latest.link}")
        
        # เปรียบเทียบลิงก์ (ต้องระวังเรื่อง string ตรงกันเป๊ะๆ)
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
            print("😴 ยังไม่มีตอนใหม่ (ลิงก์ตรงกับบันทึกเดิม)")
    else:
        print("❌ หาข้อมูลตอนล่าสุดไม่เจอ")

if __name__ == "__main__":
    main()
