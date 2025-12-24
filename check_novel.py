import google.generativeai as genai
import feedparser
import requests
from bs4 import BeautifulSoup
import time
import os

# --- ส่วนตั้งค่า (CONFIG) ---
GEMINI_API_KEY = "AIzaSyAI63JO6_TOJC5Hi0084q5JaWck362_wDc"  # <-- อย่าลืมใส่ Key
RSS_URL = "https://kakuyomu.jp/works/822139839754922306/rss"
DB_FILE = "last_seen_episode.txt"

# ตั้งค่า Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-pro') # ใช้ flash เพื่อความเร็วและประหยัด (หรือใช้ gemini-1.5-pro เพื่อภาษาที่สวยขึ้น)

# --- ฟังก์ชันใช้งาน ---

def get_latest_episode():
    """เช็ค RSS Feed หาตอนล่าสุด"""
    feed = feedparser.parse(RSS_URL)
    if feed.entries:
        return feed.entries[0]
    return None

def get_novel_content(url):
    """ดึงเนื้อหานิยายจากเว็บ Kakuyomu"""
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ดึงเนื้อหา (ปรับตามโครงสร้างเว็บ)
        body_elem = soup.select_one('.widget-episodeBody')
        if body_elem:
            return body_elem.get_text(separator="\n", strip=True)
        return ""
    except Exception as e:
        print(f"Error fetching content: {e}")
        return None

def translate_with_gemini(japanese_text):
    """ส่งให้ Gemini แปล"""
    
    # Prompt สั่งงาน: สำคัญมาก! คือการบอกบทบาทให้ AI
    prompt = f"""
    คุณคือนักแปลนิยายไลท์โนเวลมืออาชีพ
    หน้าที่ของคุณคือแปลเนื้อหานิยายภาษาญี่ปุ่นต่อไปนี้ให้เป็นภาษาไทย
    
    ข้อกำหนด:
    - ใช้สำนวนที่สละสลวย เป็นธรรมชาติ เหมือนนิยายวัยรุ่น
    - รักษาบริบทและอารมณ์ของตัวละคร
    - ไม่ต้องแปลคำทับศัพท์ที่คนไทยคุ้นเคย (เช่น อนิเมะ, สกิล) แต่ถ้าจำเป็นให้ทับศัพท์แล้ววงเล็บความหมาย
    - จัดย่อหน้าให้อ่านง่าย
    
    เนื้อหาต้นฉบับ:
    {japanese_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "เกิดข้อผิดพลาดในการแปล"

# --- Main Loop ---

def main():
    print("เริ่มระบบบอทนักแปล...")
    
    # 1. เช็คว่าเคยแปลตอนไหนไปล่าสุด
    last_link = ""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            last_link = f.read().strip()

    # 2. เช็คตอนล่าสุดจากเว็บ
    latest_entry = get_latest_episode()
    
    if latest_entry and latest_entry.link != last_link:
        print(f"✨ เจอตอนใหม่: {latest_entry.title}")
        print("กำลังดึงเนื้อหา...")
        
        raw_content = get_novel_content(latest_entry.link)
        
        if raw_content:
            print("กำลังขอให้ Gemini แปล (รอสักครู่)...")
            thai_translation = translate_with_gemini(raw_content)
            
            # --- ส่วนแสดงผล / บันทึกไฟล์ / แจ้งเตือน ---
            print("\n" + "="*20 + " ผลลัพธ์การแปล " + "="*20)
            print(f"ชื่อตอน: {latest_entry.title}")
            print(thai_translation[:500] + "...") # แสดงตัวอย่าง 500 ตัวอักษร
            print("="*50)
            
            # (Optional) บันทึกลงไฟล์
            filename = f"แปล_{latest_entry.title}.txt".replace("/", "_") # แก้ชื่อไฟล์ที่มี /
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Link: {latest_entry.link}\n\n{thai_translation}")
                
            print(f"บันทึกไฟล์ {filename} เรียบร้อย")
            
            # 3. อัปเดตสถานะว่าแปลแล้ว
            with open(DB_FILE, "w") as f:
                f.write(latest_entry.link)
                
        else:
            print("ไม่สามารถดึงเนื้อหาได้")
            
    else:
        print("ยังไม่มีตอนใหม่จ้า")

if __name__ == "__main__":
    main()
