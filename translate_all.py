from google import genai
from google.genai import types
import cloudscraper
import requests
from bs4 import BeautifulSoup
import time
import os
import re
import random
from urllib.parse import urljoin

# ==========================================
# ⚙️ ส่วนตั้งค่า
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = os.getenv("WEBHOOK_NOVEL_2")
NOVEL_MAIN_URL = "https://kakuyomu.jp/works/16816700429097793676"
DB_FILE = "last_ep_novel_2.txt" 

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

# Scraper
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

# ==========================================
# 🛠️ ฟังก์ชันทำงาน
# ==========================================

def get_first_episode_url():
    """หาลิงก์ตอนที่ 1"""
    print(f"📖 กำลังหาตอนแรกจาก: {NOVEL_MAIN_URL}")
    try:
        response = scraper.get(NOVEL_MAIN_URL)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        first_ep_link = soup.select_one('a#readFromFirstEpisode')
        
        if first_ep_link:
            full_link = urljoin(NOVEL_MAIN_URL, first_ep_link['href'])
            print(f"✅ เจอตอนแรก: {full_link}")
            return full_link
        else:
            target_pattern = re.compile(r'/works/\d+/episodes/\d+')
            links = soup.find_all('a', href=target_pattern)
            if links:
                sorted_links = sorted(links, key=lambda x: int(re.search(r'episodes/(\d+)', x['href']).group(1)))
                full_link = urljoin(NOVEL_MAIN_URL, sorted_links[0]['href'])
                print(f"⚠️ เจอลิงก์ในสารบัญ: {full_link}")
                return full_link
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def find_next_link(soup, current_url):
    """หาปุ่ม Next"""
    next_link = None
    next_btn = soup.select_one('a.widget-episode-navigation-next')
    if not next_btn: next_btn = soup.select_one('a#contentMain-readNextEpisode')
    if not next_btn: next_btn = soup.find('a', string=re.compile('次のエピソード'))
        
    if next_btn:
        return urljoin(current_url, next_btn['href'])
    return None

def get_content_and_next_link(url, max_retries=3):
    headers = {'Referer': NOVEL_MAIN_URL}
    
    for attempt in range(max_retries):
        try:
            # ⚡ ลดเวลาหน่วงสุ่มเหลือแค่ 1-2 วินาที (จากเดิม 2-4)
            time.sleep(random.uniform(1, 2)) 
            
            response = scraper.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                title = soup.select_one('.widget-episodeTitle').text.strip()
                body = soup.select_one('.widget-episodeBody').get_text(separator="\n", strip=True)
                next_link = find_next_link(soup, url)
                
                return {"title": title, "content": body, "next_link": next_link}
            
            print(f"   ⚠️ ครั้งที่ {attempt+1} ไม่สำเร็จ (Status: {response.status_code})")
            time.sleep(2) # พักแป๊บเดียวพอ
            
        except Exception as e:
            print(f"   ⚠️ Error: {e}")
            
    return None

def translate(text):
    if not text or not client: return None
    
    prompt = f"""
    แปลนิยายญี่ปุ่นนี้เป็นไทย สำนวนวัยรุ่น อ่านสนุก:
    - เจอฉากวูบวาบให้ปรับสำนวนให้ซอฟต์ลง
    - ห้ามหยุดแปล ให้แปลจนจบ
    
    เนื้อหา:
    {text[:15000]} 
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

def send_discord(ep_num, title, link, content):
    if not DISCORD_WEBHOOK_URL: return
    
    # รวมหัวข้อกับเนื้อหาส่วนแรกเลย เพื่อลดจำนวน Request
    requests.post(DISCORD_WEBHOOK_URL, json={
        "content": f"📚 **[ตอนที่ {ep_num}] {title}**\n🔗 {link}\n*(กำลังแปล...)*"
    })
    
    chunk_size = 1900
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    for chunk in chunks:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk})
        time.sleep(0.5) # ⚡ ลดเวลาส่ง Discord ให้รัวขึ้น
    
    requests.post(DISCORD_WEBHOOK_URL, json={"content": f"✅ **จบตอนที่ {ep_num}**"})

def send_discord_error(ep_num, url, msg):
    if not DISCORD_WEBHOOK_URL: return
    requests.post(DISCORD_WEBHOOK_URL, json={
        "content": f"⚠️ **[ข้ามตอนที่ {ep_num}]** {msg}\n🔗 {url}"
    })

# ==========================================
# 🚀 Main Loop
# ==========================================

def main():
    print("🚀 เริ่มระบบแปลแบบลูกโซ่ (V.6 - Turbo Speed ⚡)...")
    
    current_url = get_first_episode_url()
    if not current_url: return

    ep_count = 1
    
    while current_url:
        print(f"\n[{ep_count}] กำลังทำ: {current_url}")
        
        data = get_content_and_next_link(current_url)
        
        if not data:
            print("   ❌ ดึงข้อมูลไม่ได้ -> จบ")
            send_discord_error(ep_count, current_url, "ดึงเนื้อหาไม่ได้")
            break

        title = data['title']
        translated = translate(data['content'])
        
        if translated:
            print("   🚀 ส่ง Discord...")
            send_discord(ep_count, title, current_url, translated)
            with open(DB_FILE, "w") as f:
                f.write(current_url)
        else:
            print("   ❌ แปลไม่ผ่าน")
            send_discord_error(ep_count, current_url, "แปลไม่ผ่าน")

        if data['next_link']:
            print(f"   ➡️ ไปตอนถัดไป (พัก 5 วิ)")
            current_url = data['next_link']
            ep_count += 1
            # ⚡ แก้ตรงนี้: ลดเวลาพักเหลือ 5 วินาที
            time.sleep(5) 
        else:
            print("\n🏁 จบเรื่องแล้ว")
            current_url = None

    print("\n🎉 เสร็จสิ้น!")

if __name__ == "__main__":
    main()
