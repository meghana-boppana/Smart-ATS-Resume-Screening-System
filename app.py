import streamlit as st
import pandas as pd
import re
import io
import fitz # PyMuPDF
import docx
import sqlite3
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from PIL import Image
import pytesseract
import textract
import os

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Smart Resume Screener", layout="wide", page_icon="🎯")

# ---------------- LOGIN SYSTEM ----------------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 Smart Resume Screener - Admin Login")
    st.markdown("---")
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.subheader("Login to Continue")
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        if st.button("🔓 Login", use_container_width=True, type="primary"):
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("❌ Invalid username or password")
    st.stop()

# ---------------- SIDEBAR ----------------
st.sidebar.success(f"👋 Welcome, {ADMIN_USERNAME}")
st.sidebar.button("🚪 Logout", on_click=lambda: st.session_state.update(logged_in=False), use_container_width=True)
st.sidebar.markdown("---")

DB_FILE = 'resumes.db'
UPLOAD_DIR = 'uploads'
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            mobile TEXT,
            experience REAL,
            ats_score INTEGER,
            file_path TEXT,
            upload_time TIMESTAMP,
            candidate_type TEXT,
            education TEXT,
            certifications TEXT,
            skills TEXT,
            projects TEXT,
            jd_skills_matched TEXT,
            missing_skills TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- UTILS ----------------
def extract_text_from_pdf(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def extract_text_from_docx(file_bytes):
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join([para.text for para in doc.paragraphs])

def extract_text_from_txt(file_bytes):
    return file_bytes.decode('utf-8', errors='ignore')

def extract_text_from_doc(file_bytes):
    try:
        temp_file = f"temp_{datetime.now().timestamp()}.doc"
        with open(temp_file, "wb") as f:
            f.write(file_bytes)
        text = textract.process(temp_file).decode('utf-8', errors='ignore')
        os.remove(temp_file)
        return text
    except:
        return ""

def extract_text_from_image(file_bytes):
    try:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
        return text
    except:
        return ""

def extract_email(text):
    match = re.search(r'[\w\.-]+@[\w\.-]+', text)
    return match.group(0) if match else "Not Found"

def extract_mobile(text):
    match = re.search(r'(\+?\d{1,3}[-.\s]?)?(\d{10})', text)
    return match.group(0) if match else "Not Found"

def extract_experience(text):
    matches = re.findall(r'(\d+(\.\d+)?)\s*(?:\+?\s*)?(years|yrs|year)', text.lower())
    if matches:
        return max([float(m[0]) for m in matches])
    return 0.0

def extract_name(text, filename):
    lines = text.strip().split('\n')
    for line in lines[:5]:
        line = line.strip()
        if len(line.split()) >= 2 and len(line) < 50 and not any(char.isdigit() for char in line):
            if '@' not in line and 'resume' not in line.lower():
                return line.title()
    name_from_file = re.sub(r'\.(pdf|docx|doc|txt|jpg|jpeg|png)$', '', filename, flags=re.I)
    name_from_file = re.sub(r'[_-]', ' ', name_from_file)
    return name_from_file.title()

def extract_education(text):
    keywords = ['b.tech', 'btech', 'b.e', 'bachelor', 'm.tech', 'mtech', 'master', 'mba', 'b.sc', 'm.sc', 'phd', 'iit', 'nit']
    lines = text.lower().split('\n')
    edu_lines = []
    for line in lines:
        if any(kw in line for kw in keywords):
            edu_lines.append(line.strip())
    return "; ".join(edu_lines[:2]) if edu_lines else "Not Found"

def extract_certifications(text):
    keywords = ['certified', 'certification', 'certificate', 'aws', 'azure', 'gcp', 'oracle', 'cisco', 'pmp']
    lines = text.split('\n')
    cert_lines = []
    for line in lines:
        if any(kw in line.lower() for kw in keywords):
            cert_lines.append(line.strip())
    return "; ".join(cert_lines[:3]) if cert_lines else "Not Found"

def extract_projects(text):
    text_lower = text.lower()

    start_match = re.search(
        r'\n\s*(?:projects?|personal projects?|academic projects?|key projects?|major projects?)\s*[:\n]',
        text_lower
    )
    if not start_match:
        return "Not Found"

    start_pos = start_match.end()

    end_keywords = ['experience', 'work experience', 'employment', 'education', 'skills',
                    'technical skills', 'internship', 'training', 'summary', 'objective',
                    'certifications', 'certification', 'achievements', 'awards', 'courses',
                    'honors', 'publications', 'languages', 'hobbies']
    end_pos = len(text)

    for keyword in end_keywords:
        match = re.search(r'\n\s*' + keyword + r'\s*[:\n]', text_lower[start_pos:])
        if match:
            end_pos = start_pos + match.start()
            break

    project_text = text[start_pos:end_pos].strip()

    if not project_text or len(project_text) < 5:
        return "Not Found"

    projects = []
    lines = project_text.split('\n')

    blacklist = [
        'certificate', 'certificates', 'certification', 'certified',
        'achievement', 'achievements', 'award', 'awards', 'honor', 'honors',
        'course', 'courses', 'license', 'licenses', 'training',
        'won', 'secured', 'issued by', 'completed', 'received', 'rank', 'place',
        'nptel', 'excelr', 'foundation', 'employability', 'software testing'
    ]

    for line in lines:
        line = line.strip()

        if not line or len(line) < 4:
            continue

        if any(word in line.lower() for word in blacklist):
            continue

        if line[0].islower():
            continue

        line = re.sub(r'^[\-\*•\d\.\)\s]+', '', line)
        line = line.strip()

        if not line or len(line) < 4:
            continue

        project_name = re.split(r'\s*[:\-]\s*(?:Developed|Built|Created|Designed|Implemented|Used|Using|with|by|for|in)', line, flags=re.I)[0]
        project_name = re.split(r'\s+(?:Developed|Built|Created|Designed|Implemented|Used|Using|with|by|for|in)\s+', project_name, flags=re.I)[0]
        project_name = project_name.strip().rstrip('.,:-')

        if 4 < len(project_name) < 80 and project_name[0].isupper():
            projects.append(project_name)

    clean_projects = []
    seen = set()
    for p in projects:
        p = re.sub(r'\s+', ' ', p).strip()
        if p and p.lower() not in seen:
            clean_projects.append(p)
            seen.add(p.lower())

    return "; ".join(clean_projects) if clean_projects else "Not Found"

def extract_skills_from_text(text):
    skill_keywords = [
        'python', 'java', 'javascript', 'c++', 'c#', 'sql', 'html', 'css', 'react',
        'angular', 'vue', 'node', 'django', 'flask', 'spring', 'aws', 'azure', 'gcp',
        'docker', 'kubernetes', 'git', 'linux', 'machine learning', 'data science',
        'tensorflow', 'pytorch', 'pandas', 'numpy', 'scikit-learn', 'tableau', 'power bi',
        'excel', 'mongodb', 'mysql', 'postgresql', 'api', 'rest', 'microservices'
    ]
    text_lower = text.lower()
    found = []
    for skill in skill_keywords:
        if skill in text_lower:
            found.append(skill.title())
    return ", ".join(list(set(found))) if found else "Not Found"

def extract_exp_from_jd(jd_text):
    matches = re.findall(r'(\d+)\s*-\s*(\d+)\s*(?:years|yrs|year)', jd_text.lower())
    if matches:
        return int(matches[0][0]), int(matches[0][1])
    single = re.findall(r'(\d+)\s*\+?\s*(?:years|yrs|year)', jd_text.lower())
    if single:
        exp = int(single[0])
        return exp, exp + 5
    return 0, 10

def extract_skills_from_jd(jd_text):
    skill_keywords = [
        'python', 'java', 'javascript', 'c++', 'c#', 'sql', 'html', 'css', 'react',
        'angular', 'vue', 'node', 'django', 'flask', 'spring', 'aws', 'azure', 'gcp',
        'docker', 'kubernetes', 'git', 'linux', 'machine learning', 'data science',
        'tensorflow', 'pytorch', 'pandas', 'numpy', 'scikit-learn', 'tableau', 'power bi',
        'excel', 'mongodb', 'mysql', 'postgresql', 'api', 'rest', 'microservices'
    ]
    jd_lower = jd_text.lower()
    found_skills = []
    for skill in skill_keywords:
        if skill in jd_lower:
            found_skills.append(skill.title())
    return list(set(found_skills))

def calculate_jd_based_ats(resume_text, jd_skills, min_exp, max_exp, candidate_exp):
    resume_lower = resume_text.lower()
    matched = [skill for skill in jd_skills if skill.lower() in resume_lower]
    missing = [skill for skill in jd_skills if skill.lower() not in resume_lower]

    skill_match = len(matched)
    skill_score = (skill_match / len(jd_skills)) * 50 if jd_skills else 0
    exp_score = 25 if min_exp <= candidate_exp <= max_exp else 0
    quality_score = 25 if len(resume_text) > 500 else 10

    ats_score = int(skill_score + exp_score + quality_score)

    return {
        'ats_score': min(ats_score, 100),
        'matched_skills': ", ".join(matched) if matched else "None",
        'missing_skills': ", ".join(missing) if missing else "None",
        'match_count': f"{skill_match}/{len(jd_skills)}"
    }

def generate_report_pdf(df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=8, leftMargin=8, topMargin=15, bottomMargin=15)
    styles = getSampleStyleSheet()
    elements = []

    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=10, leading=12, wordWrap='CJK')
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold', alignment=1)

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, spaceAfter=10, alignment=1)
    elements.append(Paragraph("ATS Resume Screening Report", title_style))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                              ParagraphStyle('Date', parent=styles['Normal'], fontSize=10, alignment=1)))
    elements.append(Spacer(1, 15))

    headers = [
        Paragraph('<b>Rank</b>', header_style),
        Paragraph('<b>Name</b>', header_style),
        Paragraph('<b>Email</b>', header_style),
        Paragraph('<b>Mobile</b>', header_style),
        Paragraph('<b>JD Skills Matched</b>', header_style),
        Paragraph('<b>Missing Skills</b>', header_style),
        Paragraph('<b>Projects</b>', header_style),
        Paragraph('<b>Exp</b>', header_style),
        Paragraph('<b>ATS Score</b>', header_style)
    ]

    table_data = [headers]
    for idx, row in df.iterrows():
        table_data.append([
            Paragraph(f"{idx + 1}", cell_style),
            Paragraph(str(row['Name']), cell_style),
            Paragraph(str(row['Email']), cell_style),
            Paragraph(str(row['Mobile']), cell_style),
            Paragraph(str(row['JD Skills Matched']), cell_style),
            Paragraph(str(row['Missing Skills']), cell_style),
            Paragraph(str(row['Projects']), cell_style),
            Paragraph(f"{row['Experience']:.1f} yrs", cell_style),
            Paragraph(f"{row['ATS Score']}", cell_style)
        ])

    col_widths = [40, 100, 130, 90, 120, 120, 130, 50, 60]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (7, 1), (8, -1), 'CENTER'),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ---------------- UI ----------------
st.title("🎯 Smart Resume Screener - Simple Mode")
st.caption(f"👤 Logged in as: **{ADMIN_USERNAME}** | 💾 Local Storage")

st.sidebar.header("📋 Job Description")
jd_text = st.sidebar.text_area("Paste JD Here", height=200,
                               value="Looking for Python Developer with 2-5 years experience. Skills: Python, Pandas, Numpy, Data Science, SQL, Machine Learning")

min_exp_input, max_exp_input = extract_exp_from_jd(jd_text)

if jd_text:
    auto_skills = extract_skills_from_jd(jd_text)
    default_skills = ", ".join(auto_skills) if auto_skills else "Python, Machine Learning, SQL"
    jd_skills_input = st.sidebar.text_input("Required Skills (comma-separated)", default_skills)
    if auto_skills:
        st.sidebar.success(f"✅ Auto-detected {len(auto_skills)} skills from JD")
else:
    jd_skills_input = st.sidebar.text_input("Required Skills (comma-separated)", "Python, Machine Learning, SQL")

jd_skills = [s.strip() for s in jd_skills_input.split(',') if s.strip()]

col1, col2 = st.sidebar.columns(2)
min_exp = col1.number_input("Min Exp", value=min_exp_input, step=1)
max_exp = col2.number_input("Max Exp", value=max_exp_input, step=1)

if min_exp <= 1 and max_exp <= 1:
    st.sidebar.info("🎓 Detected: Fresher Job (0-1 years)")
elif min_exp <= 2:
    st.sidebar.info(f"💼 Detected: {min_exp}-{max_exp} years")
else:
    st.sidebar.info(f"💼 Detected: {min_exp}-{max_exp} years")

st.sidebar.markdown("---")
st.sidebar.markdown("**Supported Files:** PDF, DOCX, DOC, TXT, JPG, PNG ✅")
st.sidebar.caption("ATS = 50% JD Skills + 25% JD Exp + 25% Quality")

st.header("📤 Upload Resumes")
uploaded_files = st.file_uploader(
    "Choose files",
    type=['pdf', 'docx', 'doc', 'txt', 'jpg', 'jpeg', 'png'],
    accept_multiple_files=True
)

if st.button("🚀 Process Resumes", type="primary", use_container_width=True) and uploaded_files:
    if not jd_skills:
        st.warning("⚠️ Enter JD skills first")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing {idx+1}/{len(uploaded_files)}: {uploaded_file.name}")
            file_bytes = uploaded_file.read()
            filename = uploaded_file.name.lower()

            if filename.endswith('.pdf'):
                text = extract_text_from_pdf(file_bytes)
            elif filename.endswith('.docx'):
                text = extract_text_from_docx(file_bytes)
            elif filename.endswith('.doc'):
                text = extract_text_from_doc(file_bytes)
            elif filename.endswith('.txt'):
                text = extract_text_from_txt(file_bytes)
            elif filename.endswith(('.jpg', '.jpeg', '.png')):
                text = extract_text_from_image(file_bytes)
            else:
                st.warning(f"⚠️ Unsupported file: {uploaded_file.name}")
                continue

            if not text or len(text) < 50:
                st.warning(f"⚠️ Could not extract text from {uploaded_file.name}")
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r'[^a-zA-Z0-9]', '_', uploaded_file.name)
            file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_name}")
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            name = extract_name(text, uploaded_file.name)
            email = extract_email(text)
            mobile = extract_mobile(text)
            exp = extract_experience(text)
            education = extract_education(text)
            certifications = extract_certifications(text)
            all_skills = extract_skills_from_text(text)
            projects = extract_projects(text)
            candidate_type = "Fresher" if exp <= 1 else "Experienced"

            result_data = calculate_jd_based_ats(text, jd_skills, min_exp, max_exp, exp)
            ats_score = result_data['ats_score']
            matched_skills = result_data['matched_skills']
            missing_skills = result_data['missing_skills']
            match_count = result_data['match_count']

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO resumes (name, email, mobile, experience, ats_score, file_path, upload_time, candidate_type, education, certifications, skills, projects, jd_skills_matched, missing_skills)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (name, email, mobile, exp, ats_score, file_path, datetime.now(), candidate_type, education, certifications, all_skills, projects, matched_skills, missing_skills))
                conn.commit()
            except sqlite3.IntegrityError:
                st.warning(f"⚠️ {email} already exists - Skipped")
            finally:
                conn.close()

            results.append({
                'Name': name, 'Email': email, 'Mobile': mobile,
                'JD Skills Matched': matched_skills, 'Missing Skills': missing_skills,
                'Projects': projects, 'Experience': exp, 'ATS Score': ats_score,
                'Skill Match': match_count, 'All Skills': all_skills, 'Candidate Type': candidate_type
            })

            progress_bar.progress((idx + 1) / len(uploaded_files))

        status_text.empty()
        progress_bar.empty()
        st.success(f"✅ Processed {len(results)} resumes successfully!")
        st.balloons()

        if results:
            df = pd.DataFrame(results).sort_values('ATS Score', ascending=False).reset_index(drop=True)
            df.insert(0, 'Rank', range(1, len(df) + 1))

            display_cols = ['Rank', 'Name', 'Email', 'Mobile', 'JD Skills Matched', 'Missing Skills',
                            'Projects', 'Experience', 'ATS Score']

            st.dataframe(
                df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Rank": st.column_config.NumberColumn("Rank", help="Ranking based on ATS Score", width="small"),
                    "ATS Score": st.column_config.ProgressColumn("ATS Score", help="JD Based ATS Score",
                                                                 min_value=0, max_value=100, format="%d"),
                    "Experience": st.column_config.NumberColumn("Exp (yrs)", format="%.1f")
                }
            )

            pdf_buffer = generate_report_pdf(df)
            st.download_button("📥 Download ATS Report (PDF)", pdf_buffer,
                               "ats_report.pdf", "application/pdf", use_container_width=True)

# ---------------- SIDEBAR STATS ----------------
st.sidebar.markdown("---")
st.sidebar.header("📊 Stats")

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*), AVG(ats_score) FROM resumes")
total, avg_ats = cursor.fetchone()
conn.close()

st.sidebar.metric("Total Candidates", total or 0)
st.sidebar.metric("Avg ATS Score", f"{avg_ats:.1f}%" if avg_ats else "0%")

st.sidebar.markdown("---")
st.sidebar.header("ℹ️ Info")
st.sidebar.write(f"**Storage:** `Local /uploads`")
st.sidebar.write(f"**Projects:** ONLY project names")

st.markdown("---")
st.header("📊 View All Stored Resumes")
if st.button("🔄 Refresh Database"):
    conn = sqlite3.connect(DB_FILE)
    all_df = pd.read_sql_query("SELECT * FROM resumes ORDER BY ats_score DESC", conn)
    conn.close()
    all_df.insert(0, 'Rank', range(1, len(all_df) + 1))
    st.dataframe(all_df, use_container_width=True, hide_index=True)