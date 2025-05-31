from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import csv
import threading
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import difflib

app = Flask(__name__)
CORS(app) # Enable Cross-Origin Resource Sharing for frontend communication

# Dictionary to hold active monitoring threads/jobs
running_monitors = {}

# Define the column headers for section data
# This list must match the order and number of columns in your CSV
SECTION_HEADERS = [
    "Course Title", "Subject", "Course Number", "Section", "Credits", "CRN",
    "Term", "Instructor", "Time", "Campus", "Status", "Category", "Link Info", "Extra"
]

# --- HARDCODED GMAIL APP PASSWORD ---
# IMPORTANT: This is for YOUR TEST DEVELOPER ACCOUNT ONLY.
# In a real-world application, this should NEVER be hardcoded.
# Use environment variables or a secrets management service.
HARDCODED_GMAIL_APP_PASSWORD = "fygu yhak yjvu vsoy"

# === Email Alert Function ===
def send_email_alert(personal_email, subject, body):
    sender_email = "mybanner.bot@gmail.com"
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = personal_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, HARDCODED_GMAIL_APP_PASSWORD) # Using hardcoded password
            server.sendmail(sender_email, personal_email, msg.as_string())
            print("📧 Alert email sent!")
    except Exception as e:
        print("❌ Failed to send email alert:", e)

def fetch_sections_and_monitor(user_inputs, job_id):
    qu_email = user_inputs['qu_email']
    password = user_inputs['password']
    personal_email = user_inputs['personal_email']
    # app_password is no longer needed from user_inputs, it's hardcoded
    subject_code = user_inputs['subject_code']
    course_number = user_inputs['course_number']
    gender_preference = user_inputs['gender_preference']
    interval = float(user_inputs['interval'])

    initial_run_done = False

    while running_monitors.get(job_id, {}).get('status') == 'running':
        print(f"\n⏳ Running at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} for {subject_code} {course_number}...")

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = None

        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

            driver.get("https://ssr.qu.edu.qa/StudentRegistrationSsb/ssb/classRegistration/classRegistration")
            time.sleep(3)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "userNameInput"))).send_keys(qu_email + Keys.RETURN)
            time.sleep(2)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "passwordInput"))).send_keys(password + Keys.RETURN)
            time.sleep(4)
            try:
                driver.find_element(By.ID, "idBtn_Back").click()
            except:
                pass

            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Register for"))).click()
            time.sleep(5)
            WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CLASS_NAME, "select2-container"))).click()
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Fall 2025')]"))).click()
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Continue')]"))).click()

            subject_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txt_subject")))
            driver.execute_script(f"""
                const input = arguments[0];
                input.value = '{subject_code}';
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            """, subject_input)

            try:
                course_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "txt_courseNumber")))
                course_input.clear()
                course_input.send_keys(course_number)
            except:
                pass

            try:
                search_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "search-go")))
                search_btn.click()
            except TimeoutException:
                print("❌ Could not find or click the 'Search' button.")
                if driver: driver.quit()
                time.sleep(interval * 60)
                continue

            page_num = 1
            all_sections = []

            while True:
                try:
                    scrollable = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "searchResults"))
                    )
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable)
                except:
                    pass

                time.sleep(2.5)
                rows = driver.find_elements(By.CSS_SELECTOR, "tr[data-id]")

                for row in rows:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        section_info = [cell.text.strip() for cell in cells]

                        if len(section_info) < 10:
                            continue

                        campus = section_info[9].strip().lower()
                        if "designated area" not in campus:
                            continue

                        if gender_preference == "male" and "female" not in campus:
                            all_sections.append(section_info)
                        elif gender_preference == "female" and "female" in campus:
                            all_sections.append(section_info)
                    except StaleElementReferenceException:
                        continue

                try:
                    next_button = driver.find_element(By.XPATH, '//button[@title="Next"]')
                    is_disabled = (
                        next_button.get_attribute("disabled") is not None
                        or "disabled" in next_button.get_attribute("class").lower()
                        or next_button.get_attribute("aria-disabled") == "true"
                    )
                    if is_disabled:
                        break
                    next_button.click()
                    page_num += 1
                    time.sleep(2.5)
                except:
                    break

            filename = f"filtered_sections_{subject_code}_{course_number}.csv"
            previous_data = []
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    try:
                        previous_data = list(reader)[1:]
                    except IndexError:
                        previous_data = []

            if previous_data != all_sections:
                with open(filename, mode='w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    writer.writerow(SECTION_HEADERS)
                    for row in all_sections:
                        writer.writerow(row)

                print(f"✅ Exported {len(all_sections)} filtered sections to {filename}\n")

                if initial_run_done:
                    diff = difflib.unified_diff(
                        ["|".join(row) for row in previous_data],
                        ["|".join(row) for row in all_sections],
                        fromfile='previous_sections',
                        tofile='current_sections',
                        lineterm=''
                    )
                    diff_lines = list(diff)

                    formatted_diff_parts = []
                    added_sections = []
                    removed_sections = []

                    for line in diff_lines:
                        if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
                            continue
                        elif line.startswith('-'):
                            data_str = line[1:].strip()
                            if data_str:
                                removed_sections.append(data_str.split('|'))
                        elif line.startswith('+'):
                            data_str = line[1:].strip()
                            if data_str:
                                added_sections.append(data_str.split('|'))

                    if removed_sections:
                        formatted_diff_parts.append("--- REMOVED SECTIONS ---")
                        for section_data in removed_sections:
                            formatted_diff_parts.append("-" * 30)
                            for i, header in enumerate(SECTION_HEADERS):
                                if i < len(section_data):
                                    formatted_diff_parts.append(f"{header}: {section_data[i]}")
                        formatted_diff_parts.append("------------------------")

                    if added_sections:
                        if formatted_diff_parts:
                            formatted_diff_parts.append("\n")
                        formatted_diff_parts.append("+++ ADDED SECTIONS +++")
                        for section_data in added_sections:
                            formatted_diff_parts.append("+" * 30)
                            for i, header in enumerate(SECTION_HEADERS):
                                if i < len(section_data):
                                    formatted_diff_parts.append(f"{header}: {section_data[i]}")
                        formatted_diff_parts.append("++++++++++++++++++++++++")

                    if not formatted_diff_parts:
                        diff_text = "No specific changes detected in section details (might be minor, non-content changes)."
                    else:
                        diff_text = "\n".join(formatted_diff_parts)

                    send_email_alert(
                        personal_email,
                        f"🚨 {subject_code} {course_number} Update!",
                        f"Sections for {subject_code} {course_number} changed:\n\n{diff_text}"
                    )
                else:
                    print("📁 First run: CSV created, no email sent.")
                    initial_run_done = True
            else:
                print("✅ No changes detected.")

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            send_email_alert(
                personal_email,
                f"⚠️ Error Monitoring {subject_code} {course_number}",
                f"An error occurred while monitoring {subject_code} {course_number}: {e}"
            )
        finally:
            if driver:
                driver.quit()

        if running_monitors.get(job_id, {}).get('status') == 'stopped':
            print(f"Monitoring for {subject_code} {course_number} stopped.")
            break
        time.sleep(interval * 60)

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    # Removed 'app_password' from required_fields
    required_fields = ["qu_email", "password", "personal_email",
                       "subject_code", "course_number", "gender_preference", "interval"]
    if not all(field in data for field in required_fields):
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    job_id = f"{data['subject_code']}-{data['course_number']}-{data['gender_preference']}"

    if job_id in running_monitors and running_monitors[job_id]['status'] == 'running':
        return jsonify({"status": "warning", "message": "Monitoring for this course is already active."})

    running_monitors[job_id] = {
        'status': 'running',
        'thread': None,
        'inputs': data
    }

    thread = threading.Thread(target=fetch_sections_and_monitor, args=(running_monitors[job_id]['inputs'], job_id,))
    thread.daemon = True
    thread.start()
    running_monitors[job_id]['thread'] = thread

    return jsonify({"status": "success", "message": f"Monitoring started for {data['subject_code']} {data['course_number']}."})

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    subject_code = data.get('subject_code')
    course_number = data.get('course_number')
    gender_preference = data.get('gender_preference')

    if not all([subject_code, course_number, gender_preference]):
        return jsonify({"status": "error", "message": "Missing subject_code, course_number, or gender_preference."}), 400

    job_id = f"{subject_code}-{course_number}-{gender_preference}"

    if job_id in running_monitors and running_monitors[job_id]['status'] == 'running':
        running_monitors[job_id]['status'] = 'stopped'
        return jsonify({"status": "success", "message": f"Monitoring for {subject_code} {course_number} requested to stop."})
    else:
        return jsonify({"status": "warning", "message": "No active monitoring found for this course."})

@app.route('/status', methods=['GET'])
def get_status():
    active_jobs = []
    for job_id, details in running_monitors.items():
        if details['status'] == 'running':
            active_jobs.append({
                'job_id': job_id,
                'subject_code': details['inputs']['subject_code'],
                'course_number': details['inputs']['course_number'],
                'gender_preference': details['inputs']['gender_preference'],
                'interval': details['inputs']['interval'],
                'status': details['status']
            })
    return jsonify({"active_monitors": active_jobs})

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)