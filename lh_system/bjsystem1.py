import sys
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from datetime import datetime, date, timedelta
import re
import io
import hashlib
import warnings
from typing import Optional, Dict, Any, List, Tuple
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import pickle
from sklearn.linear_model import LinearRegression
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QStackedWidget, QListWidget, QListWidgetItem,
    QMessageBox, QDialog, QFormLayout, QTextEdit, QComboBox,
    QDateEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog,
    QHeaderView, QGroupBox, QGridLayout, QSplitter, QFrame,
    QScrollArea, QToolBar, QAction, QProgressBar, QCalendarWidget,
    QAbstractItemView, QMenuBar, QStatusBar, QButtonGroup, QRadioButton,
    QDialogButtonBox, QPlainTextEdit, QInputDialog, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QDate, QDateTime, QSize, pyqtSignal, QThread, QSettings
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QIntValidator

warnings.filterwarnings('ignore')

# ==================== 数据库配置与初始化 ====================
DB_PATH = "crm_ultimate.db"
PAGE_SIZE = 10

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def execute_sql(conn, sql, params=None, commit=True):
    c = conn.cursor()
    c.execute(sql, params or ())
    if commit:
        conn.commit()
    return c

def generate_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password_hash(hash_, password):
    return hash_ == hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # 原有表...
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    industry TEXT,
                    size TEXT,
                    stage TEXT,
                    estimated_revenue REAL DEFAULT 0,
                    owner TEXT,
                    created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    name TEXT,
                    title TEXT,
                    phone TEXT,
                    email TEXT,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    type TEXT,
                    content TEXT,
                    happened_at TEXT,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user TEXT,
                    action TEXT,
                    target TEXT,
                    details TEXT,
                    created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    priority TEXT,
                    assigned_to TEXT,
                    ticket_type TEXT,
                    parts_used TEXT,
                    cost REAL DEFAULT 0,
                    created_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_code TEXT UNIQUE NOT NULL,
                    project_name TEXT NOT NULL,
                    address TEXT,
                    tracker TEXT,
                    city TEXT,
                    usage_area TEXT,
                    progress TEXT,
                    last_followup TEXT,
                    products TEXT,
                    equipment_list TEXT,
                    construction_unit TEXT,
                    construction_dept TEXT,
                    construction_contact TEXT,
                    construction_phone TEXT,
                    design_unit TEXT,
                    design_dept TEXT,
                    design_contact TEXT,
                    design_phone TEXT,
                    general_unit TEXT,
                    general_dept TEXT,
                    general_contact TEXT,
                    general_phone TEXT,
                    estimated_amount REAL DEFAULT 0,
                    remarks TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS quotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quotation_no TEXT UNIQUE NOT NULL,
                    project_name TEXT,
                    customer_name TEXT,
                    contact_person TEXT,
                    contact_phone TEXT,
                    quotation_date TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS quotation_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quotation_id INTEGER,
                    seq INTEGER,
                    product_id INTEGER,
                    product_name TEXT,
                    specification TEXT,
                    unit TEXT,
                    quantity REAL DEFAULT 0,
                    discount REAL DEFAULT 0,
                    list_price REAL DEFAULT 0,
                    unit_price REAL DEFAULT 0,
                    amount REAL DEFAULT 0,
                    usage_area TEXT,
                    remarks TEXT,
                    FOREIGN KEY(quotation_id) REFERENCES quotations(id) ON DELETE CASCADE,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_code TEXT UNIQUE NOT NULL,
                    product_name TEXT NOT NULL,
                    specification TEXT,
                    unit TEXT,
                    list_price REAL DEFAULT 0,
                    category_major TEXT,
                    category_minor TEXT,
                    stock_quantity REAL DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )''')
    # 迭代新增表：标签、任务、邮件配置、库存流水等
    c.execute('''CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT DEFAULT '#2E86AB'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS customer_tags (
                    customer_id INTEGER,
                    tag_id INTEGER,
                    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                    PRIMARY KEY (customer_id, tag_id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    assigned_to TEXT,
                    created_by TEXT,
                    due_date TEXT,
                    status TEXT DEFAULT '待处理',
                    related_type TEXT,
                    related_id INTEGER,
                    created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER,
                    quantity REAL NOT NULL,
                    type TEXT, -- 'in' or 'out'
                    reason TEXT,
                    created_at TEXT,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    # 索引
    c.execute('CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_customers_stage ON customers(stage)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_projects_code ON projects(project_code)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_quotations_no ON quotations(quotation_no)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_products_code ON products(product_code)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date)')
    # 初始化默认数据
    admin_exists = c.execute("SELECT id FROM users WHERE username=?", ('admin',)).fetchone()
    if not admin_exists:
        password_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
                  ('admin', password_hash, 'admin', datetime.now().isoformat()))
    # 默认标签
    if not c.execute("SELECT id FROM tags LIMIT 1").fetchone():
        default_tags = ["重要客户", "长期合作", "潜在流失", "高价值"]
        for tag in default_tags:
            c.execute("INSERT INTO tags (name) VALUES (?)", (tag,))
    # 默认设置
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", ('company_name', '智云CRM'))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", ('smtp_server', ''))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", ('smtp_port', '25'))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", ('smtp_user', ''))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", ('smtp_password', ''))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", ('email_from', ''))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", ('theme', 'light'))
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=None):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    execute_sql(conn, "REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.close()

# ==================== 日志 ====================
def add_log(user, action, target, details=""):
    conn = get_db_connection()
    try:
        execute_sql(conn, "INSERT INTO logs (user, action, target, details, created_at) VALUES (?,?,?,?,?)",
                    (user, action, target, details, datetime.now().isoformat()))
    except Exception as e:
        print(f"日志记录失败: {e}")
    finally:
        conn.close()

# ==================== 用户认证 ====================
def authenticate_user(username, password):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id, username, password_hash, role FROM users WHERE username=?", (username,))
        row = c.fetchone()
        if row and check_password_hash(row[2], password):
            return row[0], row[1], row[3]
        return None
    finally:
        conn.close()

def register_user(username, password, role='user'):
    if check_username_exists(username):
        return False, "用户名已存在"
    conn = get_db_connection()
    try:
        password_hash = generate_password_hash(password)
        execute_sql(conn, "INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
                    (username, password_hash, role, datetime.now().isoformat()))
        return True, "注册成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def check_username_exists(username):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        return c.fetchone() is not None
    finally:
        conn.close()

def get_users():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, username, role, created_at FROM users", conn)
    conn.close()
    return df

def update_user_role(user_id, new_role):
    conn = get_db_connection()
    try:
        execute_sql(conn, "UPDATE users SET role=? WHERE id=?", (new_role, user_id))
        return True
    except Exception as e:
        print(f"更新角色失败: {e}")
        return False
    finally:
        conn.close()

# ==================== 客户相关 ====================
def get_customers(filters=None):
    conn = get_db_connection()
    query = "SELECT * FROM customers WHERE 1=1"
    params = []
    if filters:
        if filters.get('search_name'):
            query += " AND name LIKE ?"
            params.append(f"%{filters['search_name']}%")
        if filters.get('stage') and filters['stage'] != "全部":
            query += " AND stage = ?"
            params.append(filters['stage'])
        if filters.get('tag_ids'):
            # 通过子查询筛选包含任一标签的客户
            placeholders = ','.join(['?']*len(filters['tag_ids']))
            query += f" AND id IN (SELECT customer_id FROM customer_tags WHERE tag_id IN ({placeholders}))"
            params.extend(filters['tag_ids'])
    query += " ORDER BY created_at DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    df['estimated_revenue'] = pd.to_numeric(df['estimated_revenue'], errors='coerce').fillna(0)
    df['stage'] = df['stage'].fillna('潜在')
    return df

def get_customer_by_id(cid):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM customers WHERE id=?", conn, params=(cid,))
    conn.close()
    if not df.empty:
        row = df.iloc[0].to_dict()
        row['estimated_revenue'] = row.get('estimated_revenue') or 0.0
        if not row.get('stage'):
            row['stage'] = '潜在'
        return row
    return None

def add_customer(name, industry, size, stage, estimated_revenue=0, owner=""):
    if check_customer_exists(name):
        return False, "客户名称已存在"
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO customers
                     (name, industry, size, stage, estimated_revenue, owner, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, industry, size, stage, estimated_revenue, owner, datetime.now().isoformat()))
        add_log(st_session_state.username, "添加客户", name, f"行业:{industry}, 规模:{size}, 阶段:{stage}")
        return True, "添加成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_customer(cid, name, industry, size, stage, estimated_revenue, owner):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM customers WHERE name=? AND id!=?", (name, cid))
        if c.fetchone():
            return False, "客户名称已存在"
        execute_sql(conn, """UPDATE customers
                     SET name=?, industry=?, size=?, stage=?, estimated_revenue=?, owner=?
                     WHERE id=?""",
                    (name, industry, size, stage, estimated_revenue, owner, cid))
        add_log(st_session_state.username, "编辑客户", name, f"ID:{cid}")
        return True, "更新成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_customer(cid):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT name FROM customers WHERE id=?", (cid,))
        name = c.fetchone()[0]
        execute_sql(conn, "DELETE FROM customers WHERE id=?", (cid,), commit=False)
        execute_sql(conn, "DELETE FROM contacts WHERE customer_id=?", (cid,), commit=False)
        execute_sql(conn, "DELETE FROM interactions WHERE customer_id=?", (cid,), commit=False)
        execute_sql(conn, "DELETE FROM tickets WHERE customer_id=?", (cid,), commit=False)
        execute_sql(conn, "DELETE FROM customer_tags WHERE customer_id=?", (cid,), commit=False)
        conn.commit()
        add_log(st_session_state.username, "删除客户", name, f"ID:{cid}")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def check_customer_exists(name):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM customers WHERE name=?", (name,))
        return c.fetchone() is not None
    finally:
        conn.close()

# 标签管理
def get_all_tags():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM tags ORDER BY name", conn)
    conn.close()
    return df

def add_tag(name, color='#2E86AB'):
    conn = get_db_connection()
    try:
        execute_sql(conn, "INSERT INTO tags (name, color) VALUES (?,?)", (name, color))
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_tag(tag_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM tags WHERE id=?", (tag_id,))
    finally:
        conn.close()

def get_customer_tags(customer_id):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT tag_id FROM customer_tags WHERE customer_id=?", conn, params=(customer_id,))
    conn.close()
    return df['tag_id'].tolist()

def set_customer_tags(customer_id, tag_ids):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM customer_tags WHERE customer_id=?", (customer_id,), commit=False)
        for tid in tag_ids:
            execute_sql(conn, "INSERT INTO customer_tags (customer_id, tag_id) VALUES (?,?)", (customer_id, tid), commit=False)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# ==================== 联系人 ====================
def get_contacts(customer_id):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM contacts WHERE customer_id=?", conn, params=(customer_id,))
    conn.close()
    return df

def add_contact(customer_id, name, title, phone, email):
    if email and not validate_email(email):
        return False, "邮箱格式不正确"
    conn = get_db_connection()
    try:
        execute_sql(conn, "INSERT INTO contacts (customer_id, name, title, phone, email) VALUES (?,?,?,?,?)",
                    (customer_id, name, title, phone, email))
        add_log(st_session_state.username, "添加联系人", f"客户ID:{customer_id}", f"姓名:{name}, 邮箱:{email}")
        return True, "添加成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_contact(contact_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM contacts WHERE id=?", (contact_id,))
        add_log(st_session_state.username, "删除联系人", f"联系人ID:{contact_id}", "")
    except Exception as e:
        print(f"删除失败: {e}")
    finally:
        conn.close()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# ==================== 交互记录 ====================
def get_interactions(customer_id):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM interactions WHERE customer_id=? ORDER BY happened_at DESC",
                           conn, params=(customer_id,))
    conn.close()
    return df

def add_interaction(customer_id, type, content, happened_at):
    conn = get_db_connection()
    try:
        execute_sql(conn, "INSERT INTO interactions (customer_id, type, content, happened_at) VALUES (?,?,?,?)",
                    (customer_id, type, content, happened_at.isoformat()))
        add_log(st_session_state.username, "添加交互记录", f"客户ID:{customer_id}", f"类型:{type}, 内容:{content[:50]}")
    except Exception as e:
        print(f"添加失败: {e}")
    finally:
        conn.close()

# ==================== 工单 ====================
def get_tickets_by_customer(customer_id):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM tickets WHERE customer_id=? ORDER BY created_at DESC", conn,
                           params=(customer_id,))
    conn.close()
    return df

def get_all_tickets(status_filter=None):
    conn = get_db_connection()
    query = "SELECT t.*, c.name as customer_name FROM tickets t LEFT JOIN customers c ON t.customer_id = c.id"
    if status_filter and status_filter != "全部":
        query += " WHERE t.status = ?"
        df = pd.read_sql_query(query, conn, params=(status_filter,))
    else:
        df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_ticket(customer_id, title, description, priority, ticket_type, assigned_to):
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO tickets
                     (customer_id, title, description, status, priority, assigned_to, ticket_type, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (customer_id, title, description, "待分配", priority, assigned_to, ticket_type,
                     datetime.now().isoformat()))
        add_log(st_session_state.username, "创建工单", f"客户ID:{customer_id}", f"标题:{title}")
        # 发送邮件通知
        send_ticket_notification(customer_id, title, "created")
        return True
    except Exception as e:
        print(f"创建失败: {e}")
        return False
    finally:
        conn.close()

def update_ticket(ticket_id, title, description, status, priority, assigned_to, ticket_type):
    conn = get_db_connection()
    try:
        execute_sql(conn, """UPDATE tickets SET
                     title=?, description=?, status=?, priority=?, assigned_to=?, ticket_type=?
                     WHERE id=?""",
                    (title, description, status, priority, assigned_to, ticket_type, ticket_id))
        add_log(st_session_state.username, "编辑工单", f"工单ID:{ticket_id}", f"标题:{title}")
        # 如果状态变为已完成，发送完成通知
        if status == "已完成":
            send_ticket_notification_by_id(ticket_id, "completed")
        return True
    except Exception as e:
        print(f"更新失败: {e}")
        return False
    finally:
        conn.close()

def update_ticket_status(ticket_id, status, completed_at=None):
    conn = get_db_connection()
    try:
        execute_sql(conn, "UPDATE tickets SET status=?, completed_at=? WHERE id=?", (status, completed_at, ticket_id))
        if status == "已完成":
            send_ticket_notification_by_id(ticket_id, "completed")
    except Exception as e:
        print(f"更新失败: {e}")
    finally:
        conn.close()

def delete_ticket(ticket_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM tickets WHERE id=?", (ticket_id,))
        add_log(st_session_state.username, "删除工单", f"工单ID:{ticket_id}", "")
    except Exception as e:
        print(f"删除失败: {e}")
    finally:
        conn.close()

def send_ticket_notification(customer_id, title, event_type):
    # 获取客户邮箱
    conn = get_db_connection()
    contacts = pd.read_sql_query("SELECT email FROM contacts WHERE customer_id=? AND email IS NOT NULL AND email!='' LIMIT 1", conn, params=(customer_id,))
    conn.close()
    if contacts.empty:
        return
    email = contacts.iloc[0]['email']
    subject = f"工单通知：{title}"
    if event_type == "created":
        body = f"您好，您有一个新的工单“{title}”已创建，请关注。"
    else:
        body = f"您好，工单“{title}”已完成。"
    send_email(email, subject, body)

def send_ticket_notification_by_id(ticket_id, event_type):
    conn = get_db_connection()
    ticket = pd.read_sql_query("SELECT customer_id, title FROM tickets WHERE id=?", conn, params=(ticket_id,))
    conn.close()
    if not ticket.empty:
        customer_id = ticket.iloc[0]['customer_id']
        title = ticket.iloc[0]['title']
        send_ticket_notification(customer_id, title, event_type)

# ==================== 邮件发送 ====================
def send_email(to_email, subject, body, attachment_path=None):
    smtp_server = get_setting('smtp_server')
    smtp_port = int(get_setting('smtp_port') or 25)
    smtp_user = get_setting('smtp_user')
    smtp_password = get_setting('smtp_password')
    from_email = get_setting('email_from')
    if not smtp_server or not from_email:
        print("邮件服务器未配置")
        return False
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    if attachment_path:
        try:
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(attachment_path)}"')
                msg.attach(part)
        except Exception as e:
            print(f"添加附件失败: {e}")
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False

# ==================== 日志 ====================
def get_logs(limit=100):
    conn = get_db_connection()
    df = pd.read_sql_query(f"SELECT * FROM logs ORDER BY created_at DESC LIMIT {limit}", conn)
    conn.close()
    return df

# ==================== 客户价值评分 ====================
def calculate_customer_score(customer_id):
    conn = get_db_connection()
    interactions = pd.read_sql_query("SELECT COUNT(*) as cnt FROM interactions WHERE customer_id=?", conn,
                                     params=(customer_id,))
    int_cnt = interactions.iloc[0]['cnt']
    tickets = pd.read_sql_query(
        "SELECT COUNT(*) as total, SUM(CASE WHEN status='已完成' THEN 1 ELSE 0 END) as done FROM tickets WHERE customer_id=?",
        conn, params=(customer_id,))
    total_t = tickets.iloc[0]['total']
    done_t = tickets.iloc[0]['done']
    ticket_rate = done_t / total_t if total_t > 0 else 0.5
    stage_weights = {"潜在": 0.2, "意向": 0.4, "谈判": 0.7, "成交": 1.0, "流失": 0}
    stage = pd.read_sql_query("SELECT stage FROM customers WHERE id=?", conn, params=(customer_id,)).iloc[0]['stage']
    stage_weight = stage_weights.get(stage, 0.3)
    score = min(100, int(int_cnt * 5 + stage_weight * 50 + ticket_rate * 20))
    conn.close()
    return score

# ==================== 销售分析 ====================
def sales_funnel_analysis(df):
    if df.empty:
        return None
    stages_order = ["潜在", "意向", "谈判", "成交", "流失"]
    funnel_data = []
    for stage in stages_order:
        stage_df = df[df['stage'] == stage]
        funnel_data.append({
            "阶段": stage,
            "客户数": len(stage_df),
            "预计金额": stage_df['estimated_revenue'].sum()
        })
    fig, ax = plt.subplots(figsize=(8, 5))
    y_pos = list(range(len(funnel_data)))
    counts = [d['客户数'] for d in funnel_data]
    ax.barh(y_pos, counts, color=['#2E86AB','#4AA3C2','#6BB8D9','#A23B72','#F18F01'])
    ax.set_yticks(y_pos)
    ax.set_yticklabels([d['阶段'] for d in funnel_data])
    ax.set_xlabel('客户数')
    ax.set_title('销售漏斗分析')
    return fig

def monthly_trend(df):
    if df.empty:
        return None
    df['created_at'] = pd.to_datetime(df['created_at'])
    df['month'] = df['created_at'].dt.to_period('M').astype(str)
    monthly = df.groupby('month').size().reset_index(name='新增客户数')
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(monthly['month'], monthly['新增客户数'], marker='o', color='#2E86AB')
    ax.set_xlabel('月份')
    ax.set_ylabel('新增客户数')
    ax.set_title('月度新增客户趋势')
    ax.grid(True)
    return fig

def stage_distribution(df):
    if df.empty:
        return None
    counts = df['stage'].value_counts().reset_index()
    counts.columns = ['阶段', '数量']
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(counts['阶段'], counts['数量'], color='#4AA3C2')
    ax.set_xlabel('阶段')
    ax.set_ylabel('客户数')
    ax.set_title('客户阶段分布')
    return fig

# 销售预测
def sales_prediction():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT created_at, estimated_revenue FROM customers WHERE stage='成交'", conn)
    conn.close()
    if len(df) < 3:
        return None
    df['created_at'] = pd.to_datetime(df['created_at'])
    df['month'] = df['created_at'].dt.to_period('M').astype(str)
    monthly = df.groupby('month')['estimated_revenue'].sum().reset_index()
    monthly = monthly.sort_values('month')
    monthly['month_num'] = range(len(monthly))
    X = monthly['month_num'].values.reshape(-1,1)
    y = monthly['estimated_revenue'].values
    model = LinearRegression()
    model.fit(X, y)
    future_months = np.arange(len(monthly), len(monthly)+3).reshape(-1,1)
    pred = model.predict(future_months)
    # 绘图
    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot(monthly['month'], y, marker='o', label='历史')
    future_months_labels = [f"{datetime.now().replace(day=1) + timedelta(days=30*i)}" for i in range(1,4)]
    ax.plot(future_months_labels, pred, marker='x', linestyle='--', label='预测')
    ax.set_xlabel('月份')
    ax.set_ylabel('成交金额')
    ax.set_title('未来3个月成交金额预测')
    ax.legend()
    return fig

# ==================== 工程项目 ====================
def get_all_projects(filters=None):
    conn = get_db_connection()
    query = "SELECT * FROM projects WHERE 1=1"
    params = []
    if filters:
        if filters.get('search_code'):
            query += " AND project_code LIKE ?"
            params.append(f"%{filters['search_code']}%")
        if filters.get('search_name'):
            query += " AND project_name LIKE ?"
            params.append(f"%{filters['search_name']}%")
    query += " ORDER BY updated_at DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_project_by_id(pid):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM projects WHERE id=?", conn, params=(pid,))
    conn.close()
    return df.iloc[0] if not df.empty else None

def add_project(data):
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO projects (
            project_code, project_name, address, tracker, city, usage_area, progress,
            last_followup, products, equipment_list,
            construction_unit, construction_dept, construction_contact, construction_phone,
            design_unit, design_dept, design_contact, design_phone,
            general_unit, general_dept, general_contact, general_phone,
            estimated_amount, remarks, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (data['project_code'], data['project_name'], data['address'], data['tracker'],
                     data['city'], data['usage_area'], data['progress'], data['last_followup'],
                     data['products'], data['equipment_list'],
                     data['construction_unit'], data['construction_dept'], data['construction_contact'],
                     data['construction_phone'],
                     data['design_unit'], data['design_dept'], data['design_contact'], data['design_phone'],
                     data['general_unit'], data['general_dept'], data['general_contact'], data['general_phone'],
                     data['estimated_amount'], data['remarks'], datetime.now().isoformat(), datetime.now().isoformat()))
        add_log(st_session_state.username, "添加工程项目", data['project_name'], f"编号:{data['project_code']}")
        return True, "添加成功"
    except sqlite3.IntegrityError:
        return False, "项目编号已存在"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_project(pid, data):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM projects WHERE project_code=? AND id!=?", (data['project_code'], pid))
        if c.fetchone():
            return False, "项目编号已存在"
        execute_sql(conn, """UPDATE projects SET
            project_code=?, project_name=?, address=?, tracker=?, city=?, usage_area=?, progress=?,
            last_followup=?, products=?, equipment_list=?,
            construction_unit=?, construction_dept=?, construction_contact=?, construction_phone=?,
            design_unit=?, design_dept=?, design_contact=?, design_phone=?,
            general_unit=?, general_dept=?, general_contact=?, general_phone=?,
            estimated_amount=?, remarks=?, updated_at=?
            WHERE id=?""",
                    (data['project_code'], data['project_name'], data['address'], data['tracker'],
                     data['city'], data['usage_area'], data['progress'], data['last_followup'],
                     data['products'], data['equipment_list'],
                     data['construction_unit'], data['construction_dept'], data['construction_contact'],
                     data['construction_phone'],
                     data['design_unit'], data['design_dept'], data['design_contact'], data['design_phone'],
                     data['general_unit'], data['general_dept'], data['general_contact'], data['general_phone'],
                     data['estimated_amount'], data['remarks'], datetime.now().isoformat(), pid))
        add_log(st_session_state.username, "编辑工程项目", data['project_name'], f"ID:{pid}")
        return True, "更新成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_project(pid):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT project_name FROM projects WHERE id=?", (pid,))
        name = c.fetchone()[0]
        execute_sql(conn, "DELETE FROM projects WHERE id=?", (pid,))
        add_log(st_session_state.username, "删除工程项目", name, f"ID:{pid}")
    except Exception as e:
        print(f"删除失败: {e}")
    finally:
        conn.close()

# ==================== 产品 ====================
def get_all_products():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM products ORDER BY product_code", conn)
    conn.close()
    return df

def get_product_by_id(pid):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM products WHERE id=?", conn, params=(pid,))
    conn.close()
    return df.iloc[0] if not df.empty else None

def add_product(product_code, product_name, specification, unit, list_price, category_major, category_minor, stock_quantity=0):
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO products
                     (product_code, product_name, specification, unit, list_price, category_major, category_minor, stock_quantity, created_at, updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (product_code, product_name, specification, unit, list_price,
                     category_major, category_minor, stock_quantity,
                     datetime.now().isoformat(), datetime.now().isoformat()))
        add_log(st_session_state.username, "添加产品", product_name, f"编号:{product_code}")
        return True, "添加成功"
    except sqlite3.IntegrityError:
        return False, "产品编号已存在"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_product(pid, product_code, product_name, specification, unit, list_price, category_major, category_minor, stock_quantity):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM products WHERE product_code=? AND id!=?", (product_code, pid))
        if c.fetchone():
            return False, "产品编号已存在"
        execute_sql(conn, """UPDATE products SET
                     product_code=?, product_name=?, specification=?, unit=?, list_price=?,
                     category_major=?, category_minor=?, stock_quantity=?, updated_at=?
                     WHERE id=?""",
                    (product_code, product_name, specification, unit, list_price,
                     category_major, category_minor, stock_quantity,
                     datetime.now().isoformat(), pid))
        add_log(st_session_state.username, "编辑产品", product_name, f"ID:{pid}")
        return True, "更新成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_product(pid):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT product_name FROM products WHERE id=?", (pid,))
        name = c.fetchone()[0]
        execute_sql(conn, "DELETE FROM products WHERE id=?", (pid,))
        add_log(st_session_state.username, "删除产品", name, f"ID:{pid}")
    except Exception as e:
        print(f"删除失败: {e}")
    finally:
        conn.close()

def update_product_stock(product_id, quantity_change, reason, type):
    conn = get_db_connection()
    try:
        # 更新库存
        current = get_product_by_id(product_id)['stock_quantity']
        new_stock = current + quantity_change if type == 'in' else current - quantity_change
        if new_stock < 0:
            return False, "库存不足"
        execute_sql(conn, "UPDATE products SET stock_quantity=? WHERE id=?", (new_stock, product_id))
        # 记录流水
        execute_sql(conn, "INSERT INTO inventory_transactions (product_id, quantity, type, reason, created_at) VALUES (?,?,?,?,?)",
                    (product_id, quantity_change, type, reason, datetime.now().isoformat()))
        return True, "库存更新成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

# ==================== 报价 ====================
def get_all_quotations(filters=None):
    conn = get_db_connection()
    query = "SELECT * FROM quotations WHERE 1=1"
    params = []
    if filters:
        if filters.get('search_no'):
            query += " AND quotation_no LIKE ?"
            params.append(f"%{filters['search_no']}%")
        if filters.get('project_name'):
            query += " AND project_name LIKE ?"
            params.append(f"%{filters['project_name']}%")
    query += " ORDER BY quotation_date DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_quotation_by_id(qid):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM quotations WHERE id=?", conn, params=(qid,))
    conn.close()
    return df.iloc[0] if not df.empty else None

def get_quotation_items(qid):
    conn = get_db_connection()
    query = """
        SELECT qi.*, p.category_major, p.category_minor, p.stock_quantity
        FROM quotation_items qi
        LEFT JOIN products p ON qi.product_id = p.id
        WHERE qi.quotation_id = ?
        ORDER BY qi.seq
    """
    df = pd.read_sql_query(query, conn, params=(qid,))
    conn.close()
    return df

def add_quotation(data):
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO quotations
                     (quotation_no, project_name, customer_name, contact_person, contact_phone,
                      quotation_date, created_at, updated_at)
                     VALUES (?,?,?,?,?,?,?,?)""",
                    (data['quotation_no'], data['project_name'], data['customer_name'],
                     data['contact_person'], data['contact_phone'],
                     data['quotation_date'], datetime.now().isoformat(), datetime.now().isoformat()))
        qid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        add_log(st_session_state.username, "创建报价单", data['quotation_no'], f"项目:{data['project_name']}")
        return True, qid
    except sqlite3.IntegrityError:
        return False, "报价单号已存在"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_quotation(qid, data):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM quotations WHERE quotation_no=? AND id!=?", (data['quotation_no'], qid))
        if c.fetchone():
            return False, "报价单号已存在"
        execute_sql(conn, """UPDATE quotations SET
            quotation_no=?, project_name=?, customer_name=?, contact_person=?, contact_phone=?,
            quotation_date=?, updated_at=?
            WHERE id=?""",
                    (data['quotation_no'], data['project_name'], data['customer_name'],
                     data['contact_person'], data['contact_phone'], data['quotation_date'],
                     datetime.now().isoformat(), qid))
        add_log(st_session_state.username, "编辑报价单", data['quotation_no'], f"ID:{qid}")
        return True, "更新成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_quotation(qid):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT quotation_no FROM quotations WHERE id=?", (qid,))
        no = c.fetchone()[0]
        execute_sql(conn, "DELETE FROM quotations WHERE id=?", (qid,))
        add_log(st_session_state.username, "删除报价单", no, f"ID:{qid}")
    except Exception as e:
        print(f"删除失败: {e}")
    finally:
        conn.close()

def add_quotation_item(qid, item):
    conn = get_db_connection()
    try:
        # 检查库存
        if item.get('product_id'):
            prod = get_product_by_id(item['product_id'])
            if prod and prod['stock_quantity'] < item['quantity']:
                return False, f"产品 {prod['product_name']} 库存不足，当前库存 {prod['stock_quantity']}"
        execute_sql(conn, """INSERT INTO quotation_items
                     (quotation_id, seq, product_id, product_name, specification, unit, quantity, discount,
                      list_price, unit_price, amount, usage_area, remarks)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (qid, item['seq'], item.get('product_id'), item['product_name'], item['specification'],
                     item['unit'], item['quantity'], item['discount'], item['list_price'],
                     item['unit_price'], item['amount'], item['usage_area'], item['remarks']))
        return True, "添加成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_quotation_item(item_id, item):
    conn = get_db_connection()
    try:
        execute_sql(conn, """UPDATE quotation_items SET
                     seq=?, product_id=?, product_name=?, specification=?, unit=?, quantity=?, discount=?,
                     list_price=?, unit_price=?, amount=?, usage_area=?, remarks=?
                     WHERE id=?""",
                    (item['seq'], item.get('product_id'), item['product_name'], item['specification'],
                     item['unit'], item['quantity'], item['discount'], item['list_price'],
                     item['unit_price'], item['amount'], item['usage_area'], item['remarks'], item_id))
    except Exception as e:
        print(f"更新明细失败: {e}")
    finally:
        conn.close()

def delete_quotation_item(item_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM quotation_items WHERE id=?", (item_id,))
    except Exception as e:
        print(f"删除明细失败: {e}")
    finally:
        conn.close()

# 导出报价单为PDF
def export_quotation_pdf(quotation_id, output_path):
    quote = get_quotation_by_id(quotation_id)
    if not quote:
        return False
    items = get_quotation_items(quotation_id)
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    # 公司信息
    company = get_setting('company_name', '智云CRM')
    story.append(Paragraph(f"<b>{company}</b>", styles['Title']))
    story.append(Paragraph(f"报价单号: {quote['quotation_no']}", styles['Normal']))
    story.append(Paragraph(f"项目名称: {quote['project_name']}", styles['Normal']))
    story.append(Paragraph(f"客户名称: {quote['customer_name']}", styles['Normal']))
    story.append(Paragraph(f"联系人: {quote['contact_person']}  电话: {quote['contact_phone']}", styles['Normal']))
    story.append(Paragraph(f"报价日期: {quote['quotation_date']}", styles['Normal']))
    # 明细表格
    data = [['序号', '产品名称', '规格', '单位', '数量', '下浮%', '面价', '单价', '金额']]
    for _, row in items.iterrows():
        data.append([
            str(row['seq']), row['product_name'], row['specification'] or '', row['unit'] or '',
            str(row['quantity']), str(row['discount']), f"¥{row['list_price']:.2f}",
            f"¥{row['unit_price']:.2f}", f"¥{row['amount']:.2f}"
        ])
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    story.append(table)
    # 总额
    total = items['amount'].sum()
    story.append(Paragraph(f"<b>报价总额: ¥{total:,.2f}</b>", styles['Normal']))
    doc.build(story)
    return True

# ==================== 导入导出 ====================
def export_table_to_csv(table_name):
    conn = get_db_connection()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()
    return df.to_csv(index=False, encoding='utf-8-sig')

def safe_import(table_name, csv_content):
    conn = get_db_connection()
    c = conn.cursor()
    errors = []
    success = 0
    try:
        df = pd.read_csv(io.StringIO(csv_content))
        c.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in c.fetchall() if col[1] != 'id']
        conn.execute(f"DELETE FROM {table_name}")
        for idx, row in df.iterrows():
            try:
                placeholders = ','.join(['?' for _ in columns])
                insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"
                values = [row[col] if pd.notna(row[col]) else None for col in columns]
                c.execute(insert_sql, values)
                success += 1
            except Exception as e:
                errors.append(f"第{idx+2}行: {e}")
        conn.commit()
        return success, errors
    except Exception as e:
        return 0, [str(e)]
    finally:
        conn.close()

def backup_database():
    import shutil
    backup_path = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy(DB_PATH, backup_path)
    return backup_path

def restore_database(file_path):
    import shutil
    shutil.copy(file_path, DB_PATH)
    return True

# ==================== 任务管理 ====================
def get_tasks(filters=None):
    conn = get_db_connection()
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []
    if filters:
        if filters.get('assigned_to'):
            query += " AND assigned_to=?"
            params.append(filters['assigned_to'])
        if filters.get('status'):
            query += " AND status=?"
            params.append(filters['status'])
    query += " ORDER BY due_date ASC, created_at DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_task(title, description, assigned_to, due_date, related_type=None, related_id=None):
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO tasks
                     (title, description, assigned_to, created_by, due_date, status, related_type, related_id, created_at)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                    (title, description, assigned_to, st_session_state.username,
                     due_date.isoformat() if due_date else None,
                     "待处理", related_type, related_id, datetime.now().isoformat()))
        add_log(st_session_state.username, "创建任务", title, f"指派给:{assigned_to}")
        return True
    except Exception as e:
        print(f"创建任务失败: {e}")
        return False
    finally:
        conn.close()

def update_task(task_id, title, description, assigned_to, due_date, status):
    conn = get_db_connection()
    try:
        execute_sql(conn, """UPDATE tasks SET
                     title=?, description=?, assigned_to=?, due_date=?, status=?
                     WHERE id=?""",
                    (title, description, assigned_to, due_date.isoformat() if due_date else None, status, task_id))
        add_log(st_session_state.username, "更新任务", title, f"ID:{task_id}")
        return True
    except Exception as e:
        print(f"更新任务失败: {e}")
        return False
    finally:
        conn.close()

def delete_task(task_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM tasks WHERE id=?", (task_id,))
    except Exception as e:
        print(f"删除任务失败: {e}")
    finally:
        conn.close()

# ==================== AI助手 ====================
def ai_email_assistant(email_content):
    return f"""**📝 邮件摘要**  
客户在邮件中提到了关键需求，建议优先处理。

**💡 回复建议**  
1. 感谢客户的耐心等待，确认收到邮件。  
2. 针对客户提出的问题，提供详细解答。  
3. 主动邀约下一步沟通时间。"""

# ==================== PyQt5 界面 ====================
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("智云CRM - 登录")
        self.setFixedSize(400, 300)
        layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        self.login_tab = QWidget()
        self.register_tab = QWidget()
        self.tab_widget.addTab(self.login_tab, "登录")
        self.tab_widget.addTab(self.register_tab, "注册")
        layout.addWidget(self.tab_widget)

        login_layout = QFormLayout(self.login_tab)
        self.login_username = QLineEdit()
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.Password)
        login_layout.addRow("用户名:", self.login_username)
        login_layout.addRow("密码:", self.login_password)
        self.login_btn = QPushButton("登录")
        self.login_btn.clicked.connect(self.handle_login)
        login_layout.addRow(self.login_btn)

        reg_layout = QFormLayout(self.register_tab)
        self.reg_username = QLineEdit()
        self.reg_password = QLineEdit()
        self.reg_password.setEchoMode(QLineEdit.Password)
        self.reg_confirm = QLineEdit()
        self.reg_confirm.setEchoMode(QLineEdit.Password)
        self.reg_role = QComboBox()
        self.reg_role.addItems(["user", "sales", "support", "manager"])
        reg_layout.addRow("用户名:", self.reg_username)
        reg_layout.addRow("密码:", self.reg_password)
        reg_layout.addRow("确认密码:", self.reg_confirm)
        reg_layout.addRow("角色:", self.reg_role)
        self.reg_btn = QPushButton("注册")
        self.reg_btn.clicked.connect(self.handle_register)
        reg_layout.addRow(self.reg_btn)

        self.user_info = None

    def handle_login(self):
        username = self.login_username.text().strip()
        password = self.login_password.text()
        if not username or not password:
            QMessageBox.warning(self, "错误", "用户名和密码不能为空")
            return
        user = authenticate_user(username, password)
        if user:
            self.user_info = user
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "用户名或密码错误")

    def handle_register(self):
        username = self.reg_username.text().strip()
        password = self.reg_password.text()
        confirm = self.reg_confirm.text()
        role = self.reg_role.currentText()
        if not username or not password:
            QMessageBox.warning(self, "错误", "用户名和密码不能为空")
            return
        if password != confirm:
            QMessageBox.warning(self, "错误", "两次输入的密码不一致")
            return
        ok, msg = register_user(username, password, role)
        if ok:
            QMessageBox.information(self, "成功", "注册成功，请登录")
            self.tab_widget.setCurrentIndex(0)
            self.login_username.setText(username)
        else:
            QMessageBox.critical(self, "错误", msg)


class MainWindow(QMainWindow):
    def __init__(self, user_info):
        super().__init__()
        self.user_id, self.username, self.role = user_info
        global st_session_state
        st_session_state.username = self.username
        self.setWindowTitle(f"智云CRM - 欢迎 {self.username} ({self.role})")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.menu_list = QListWidget()
        self.menu_list.setFixedWidth(200)
        self.menu_list.setStyleSheet("""
            QListWidget {
                background-color: #1A2C3E;
                color: #EFF3F8;
                border: none;
                font-size: 14px;
                padding: 10px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 5px;
            }
            QListWidget::item:selected {
                background-color: #2E86AB;
            }
            QListWidget::item:hover {
                background-color: #2C6E8F;
            }
        """)
        main_layout.addWidget(self.menu_list)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # 先创建状态栏，以便在setup_menu中的页面可以访问
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.pages = {}
        self.setup_menu()

        self.menu_list.setCurrentRow(0)
        self.stacked_widget.setCurrentWidget(self.pages["仪表盘"])

        # 应用主题
        self.apply_theme()

        # 更新任务计数
        self.update_task_count()

    def apply_theme(self):
        theme = get_setting('theme', 'light')
        if theme == 'dark':
            dark_palette = QPalette()
            dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.WindowText, Qt.white)
            dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
            dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
            dark_palette.setColor(QPalette.ToolTipText, Qt.white)
            dark_palette.setColor(QPalette.Text, Qt.white)
            dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ButtonText, Qt.white)
            dark_palette.setColor(QPalette.BrightText, Qt.red)
            dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.HighlightedText, Qt.black)
            QApplication.setPalette(dark_palette)
        else:
            QApplication.setPalette(self.style().standardPalette())

    def update_task_count(self):
        tasks = get_tasks({'assigned_to': self.username, 'status': '待处理'})
        self.status_bar.showMessage(f"待处理任务: {len(tasks)}")

    def setup_menu(self):
        # 菜单权限映射
        role_menus = {
            'admin': ["仪表盘", "客户管理", "工单管理", "销售分析", "客户旅程", "工程项目", "项目报价", "产品管理", "数据管理", "AI助手", "操作日志", "任务管理", "系统设置"],
            'manager': ["仪表盘", "客户管理", "工单管理", "销售分析", "客户旅程", "工程项目", "项目报价", "产品管理", "数据管理", "AI助手", "操作日志", "任务管理", "系统设置"],
            'sales': ["仪表盘", "客户管理", "工单管理", "销售分析", "客户旅程", "工程项目", "项目报价", "AI助手", "任务管理"],
            'support': ["仪表盘", "工单管理", "客户管理", "AI助手", "任务管理"],
            'user': ["仪表盘", "客户管理", "工单管理", "销售分析", "客户旅程", "工程项目", "项目报价", "AI助手", "任务管理"]
        }
        available = role_menus.get(self.role, role_menus['user'])
        pages = {
            "仪表盘": DashboardPage,
            "客户管理": CustomerPage,
            "工单管理": TicketPage,
            "销售分析": SalesAnalysisPage,
            "客户旅程": CustomerJourneyPage,
            "工程项目": ProjectPage,
            "项目报价": QuotationPage,
            "产品管理": ProductPage,
            "数据管理": DataManagePage,
            "AI助手": AIAssistantPage,
            "操作日志": LogPage,
            "任务管理": TaskPage,
            "系统设置": SettingsPage
        }
        for name in available:
            if name in pages:
                page = pages[name](self)
                self.pages[name] = page
                self.stacked_widget.addWidget(page)
                self.menu_list.addItem(name)
        self.menu_list.currentRowChanged.connect(self.on_menu_changed)

    def on_menu_changed(self, index):
        if index >= 0:
            item_text = self.menu_list.item(index).text()
            self.stacked_widget.setCurrentWidget(self.pages[item_text])

    def closeEvent(self, event):
        event.accept()


class DashboardPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.figure, self.ax = plt.subplots(figsize=(10, 5))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.update_dashboard)
        layout.addWidget(self.refresh_btn)
        self.update_dashboard()

    def update_dashboard(self):
        df = get_customers()
        if df.empty:
            self.ax.clear()
            self.ax.text(0.5, 0.5, "暂无数据", ha='center', va='center')
            self.canvas.draw()
            return
        counts = df['stage'].value_counts()
        self.ax.clear()
        counts.plot(kind='bar', ax=self.ax, color='#4AA3C2')
        self.ax.set_title('客户阶段分布')
        self.ax.set_xlabel('阶段')
        self.ax.set_ylabel('客户数')
        self.canvas.draw()


class CustomerPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("客户名称")
        self.stage_combo = QComboBox()
        self.stage_combo.addItems(["全部", "潜在", "意向", "谈判", "成交", "流失"])
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("全部标签")
        self.tag_combo.addItems(get_all_tags()['name'].tolist())
        self.search_btn = QPushButton("查询")
        self.search_btn.clicked.connect(self.load_customers)
        search_layout.addWidget(QLabel("搜索:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(QLabel("阶段:"))
        search_layout.addWidget(self.stage_combo)
        search_layout.addWidget(QLabel("标签:"))
        search_layout.addWidget(self.tag_combo)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["ID", "公司名称", "行业", "规模", "阶段", "预计年收入", "标签"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.show_customer_360)
        layout.addWidget(self.table)

        pagination_layout = QHBoxLayout()
        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")
        self.page_label = QLabel("第1页")
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        layout.addLayout(pagination_layout)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加客户")
        self.add_btn.clicked.connect(self.add_customer_dialog)
        self.delete_btn = QPushButton("删除选中客户")
        self.delete_btn.clicked.connect(self.delete_customer)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.delete_btn)
        layout.addLayout(btn_layout)

        self.current_page = 1
        self.total_pages = 1
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.load_customers()

    def load_customers(self):
        search_name = self.search_input.text().strip()
        stage = self.stage_combo.currentText()
        tag_name = self.tag_combo.currentText()
        filters = {}
        if search_name:
            filters['search_name'] = search_name
        if stage != "全部":
            filters['stage'] = stage
        if tag_name != "全部标签":
            tags_df = get_all_tags()
            tag_id = tags_df[tags_df['name'] == tag_name]['id'].values[0]
            filters['tag_ids'] = [tag_id]
        df = get_customers(filters)
        total = len(df)
        self.total_pages = max(1, (total - 1) // PAGE_SIZE + 1)
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        start = (self.current_page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        df_page = df.iloc[start:end]
        self.table.setRowCount(len(df_page))
        tags_dict = get_all_tags().set_index('id')['name'].to_dict()
        for i, row in df_page.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(row['name']))
            self.table.setItem(i, 2, QTableWidgetItem(row['industry'] or ''))
            self.table.setItem(i, 3, QTableWidgetItem(row['size'] or ''))
            self.table.setItem(i, 4, QTableWidgetItem(row['stage'] or ''))
            self.table.setItem(i, 5, QTableWidgetItem(f"¥{row['estimated_revenue']:,.0f}"))
            tags = get_customer_tags(row['id'])
            tag_names = [tags_dict[t] for t in tags if t in tags_dict]
            self.table.setItem(i, 6, QTableWidgetItem(", ".join(tag_names)))
        self.page_label.setText(f"第{self.current_page}页/共{self.total_pages}页")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_customers()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_customers()

    def add_customer_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加客户")
        layout = QFormLayout(dialog)
        name_edit = QLineEdit()
        industry_edit = QLineEdit()
        size_combo = QComboBox()
        size_combo.addItems(["小型", "中型", "大型"])
        stage_combo = QComboBox()
        stage_combo.addItems(["潜在", "意向", "谈判", "成交", "流失"])
        revenue_edit = QDoubleSpinBox()
        revenue_edit.setRange(0, 1e9)
        revenue_edit.setPrefix("¥")
        owner_edit = QLineEdit()
        layout.addRow("公司名称:", name_edit)
        layout.addRow("行业:", industry_edit)
        layout.addRow("规模:", size_combo)
        layout.addRow("阶段:", stage_combo)
        layout.addRow("预计年收入:", revenue_edit)
        layout.addRow("客户经理:", owner_edit)
        # 标签选择
        tags_df = get_all_tags()
        tag_widgets = []
        tag_layout = QHBoxLayout()
        for _, row in tags_df.iterrows():
            cb = QCheckBox(row['name'])
            tag_widgets.append((row['id'], cb))
            tag_layout.addWidget(cb)
        layout.addRow("标签:", tag_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "错误", "公司名称不能为空")
                return
            success, msg = add_customer(name, industry_edit.text(), size_combo.currentText(),
                                        stage_combo.currentText(), revenue_edit.value(), owner_edit.text())
            if success:
                # 获取新客户ID
                conn = get_db_connection()
                cid = conn.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()[0]
                conn.close()
                selected_tags = [tid for tid, cb in tag_widgets if cb.isChecked()]
                set_customer_tags(cid, selected_tags)
                QMessageBox.information(self, "成功", msg)
                self.load_customers()
            else:
                QMessageBox.critical(self, "错误", msg)

    def delete_customer(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的客户")
            return
        cid = int(self.table.item(current_row, 0).text())
        name = self.table.item(current_row, 1).text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除客户“{name}”及其所有关联数据吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                delete_customer(cid)
                QMessageBox.information(self, "成功", "客户已删除")
                self.load_customers()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")

    def show_customer_360(self, index):
        row = index.row()
        cid = int(self.table.item(row, 0).text())
        role = self.parent().role
        dialog = Customer360Dialog(cid, role, self)
        dialog.exec_()


class Customer360Dialog(QDialog):
    def __init__(self, customer_id, role, parent=None):
        super().__init__(parent)
        self.customer_id = customer_id
        self.role = role
        self.setWindowTitle("客户360视图")
        self.setMinimumSize(800, 600)
        layout = QVBoxLayout(self)

        customer = get_customer_by_id(customer_id)
        if not customer:
            QMessageBox.critical(self, "错误", "客户不存在")
            self.reject()
            return

        score = calculate_customer_score(customer_id)
        contacts = get_contacts(customer_id)
        tickets = get_tickets_by_customer(customer_id)
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"<b>{customer['name']}</b>"))
        header_layout.addWidget(QLabel(f"价值评分: {score}/100"))
        header_layout.addWidget(QLabel(f"联系人: {len(contacts)}"))
        header_layout.addWidget(QLabel(f"工单: {len(tickets)}"))
        layout.addLayout(header_layout)

        tab_widget = QTabWidget()
        # 基本信息
        basic_widget = QWidget()
        basic_layout = QFormLayout(basic_widget)
        basic_layout.addRow("公司名称:", QLabel(customer['name']))
        basic_layout.addRow("行业:", QLabel(customer['industry'] or ''))
        basic_layout.addRow("规模:", QLabel(customer['size'] or ''))
        basic_layout.addRow("阶段:", QLabel(customer['stage'] or ''))
        basic_layout.addRow("预计年收入:", QLabel(f"¥{customer['estimated_revenue']:,.0f}"))
        basic_layout.addRow("客户经理:", QLabel(customer['owner'] or '未分配'))
        basic_layout.addRow("创建时间:", QLabel(customer['created_at'] or ''))
        # 标签
        tags_df = get_all_tags()
        tags_dict = tags_df.set_index('id')['name'].to_dict()
        current_tags = get_customer_tags(customer_id)
        tag_names = [tags_dict[t] for t in current_tags if t in tags_dict]
        basic_layout.addRow("标签:", QLabel(", ".join(tag_names)))
        if self.role == 'admin':
            edit_btn = QPushButton("编辑客户")
            edit_btn.clicked.connect(lambda: self.edit_customer(customer))
            basic_layout.addRow(edit_btn)
        tab_widget.addTab(basic_widget, "基本信息")

        # 联系人
        contacts_widget = QWidget()
        contacts_layout = QVBoxLayout(contacts_widget)
        contacts_table = QTableWidget()
        contacts_table.setColumnCount(4)
        contacts_table.setHorizontalHeaderLabels(["姓名", "职位", "电话", "邮箱"])
        contacts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        contacts_df = get_contacts(customer_id)
        contacts_table.setRowCount(len(contacts_df))
        for i, row in contacts_df.iterrows():
            contacts_table.setItem(i, 0, QTableWidgetItem(row['name']))
            contacts_table.setItem(i, 1, QTableWidgetItem(row['title'] or ''))
            contacts_table.setItem(i, 2, QTableWidgetItem(row['phone'] or ''))
            contacts_table.setItem(i, 3, QTableWidgetItem(row['email'] or ''))
        contacts_layout.addWidget(contacts_table)
        if self.role == 'admin':
            add_contact_btn = QPushButton("添加联系人")
            add_contact_btn.clicked.connect(self.add_contact_dialog)
            contacts_layout.addWidget(add_contact_btn)
        tab_widget.addTab(contacts_widget, "联系人")

        # 交互历史
        interactions_widget = QWidget()
        interactions_layout = QVBoxLayout(interactions_widget)
        interactions_text = QTextEdit()
        interactions_text.setReadOnly(True)
        interactions_df = get_interactions(customer_id)
        text = ""
        for _, row in interactions_df.iterrows():
            text += f"**{row['type']}** · {row['happened_at']}\n{row['content']}\n\n"
        interactions_text.setPlainText(text)
        interactions_layout.addWidget(interactions_text)
        if self.role == 'admin':
            add_interaction_btn = QPushButton("添加交互记录")
            add_interaction_btn.clicked.connect(self.add_interaction_dialog)
            interactions_layout.addWidget(add_interaction_btn)
        tab_widget.addTab(interactions_widget, "交互历史")

        # 工单
        tickets_widget = QWidget()
        tickets_layout = QVBoxLayout(tickets_widget)
        tickets_table = QTableWidget()
        tickets_table.setColumnCount(5)
        tickets_table.setHorizontalHeaderLabels(["标题", "状态", "优先级", "类型", "创建时间"])
        tickets_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tickets_df = get_tickets_by_customer(customer_id)
        tickets_table.setRowCount(len(tickets_df))
        for i, row in tickets_df.iterrows():
            tickets_table.setItem(i, 0, QTableWidgetItem(row['title']))
            tickets_table.setItem(i, 1, QTableWidgetItem(row['status']))
            tickets_table.setItem(i, 2, QTableWidgetItem(row['priority']))
            tickets_table.setItem(i, 3, QTableWidgetItem(row['ticket_type'] or ''))
            tickets_table.setItem(i, 4, QTableWidgetItem(row['created_at']))
        tickets_layout.addWidget(tickets_table)
        if self.role == 'admin':
            add_ticket_btn = QPushButton("添加工单")
            add_ticket_btn.clicked.connect(self.add_ticket_dialog)
            tickets_layout.addWidget(add_ticket_btn)
        tab_widget.addTab(tickets_widget, "工单")

        layout.addWidget(tab_widget)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def edit_customer(self, customer):
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑客户")
        layout = QFormLayout(dialog)
        name_edit = QLineEdit(customer['name'])
        industry_edit = QLineEdit(customer['industry'] or '')
        size_combo = QComboBox()
        size_combo.addItems(["小型", "中型", "大型"])
        size_combo.setCurrentText(customer['size'] or '小型')
        stage_combo = QComboBox()
        stage_combo.addItems(["潜在", "意向", "谈判", "成交", "流失"])
        stage_combo.setCurrentText(customer['stage'] or '潜在')
        revenue_edit = QDoubleSpinBox()
        revenue_edit.setRange(0, 1e9)
        revenue_edit.setValue(customer['estimated_revenue'] or 0)
        revenue_edit.setPrefix("¥")
        owner_edit = QLineEdit(customer['owner'] or '')
        # 标签
        tags_df = get_all_tags()
        tag_widgets = []
        tag_layout = QHBoxLayout()
        current_tags = get_customer_tags(self.customer_id)
        for _, row in tags_df.iterrows():
            cb = QCheckBox(row['name'])
            cb.setChecked(row['id'] in current_tags)
            tag_widgets.append((row['id'], cb))
            tag_layout.addWidget(cb)
        layout.addRow("公司名称:", name_edit)
        layout.addRow("行业:", industry_edit)
        layout.addRow("规模:", size_combo)
        layout.addRow("阶段:", stage_combo)
        layout.addRow("预计年收入:", revenue_edit)
        layout.addRow("客户经理:", owner_edit)
        layout.addRow("标签:", tag_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            new_name = name_edit.text().strip()
            if not new_name:
                QMessageBox.warning(self, "错误", "公司名称不能为空")
                return
            success, msg = update_customer(self.customer_id, new_name, industry_edit.text(),
                                           size_combo.currentText(), stage_combo.currentText(),
                                           revenue_edit.value(), owner_edit.text())
            if success:
                # 更新标签
                selected_tags = [tid for tid, cb in tag_widgets if cb.isChecked()]
                set_customer_tags(self.customer_id, selected_tags)
                QMessageBox.information(self, "成功", msg)
                self.accept()
            else:
                QMessageBox.critical(self, "错误", msg)

    def add_contact_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加联系人")
        layout = QFormLayout(dialog)
        name_edit = QLineEdit()
        title_edit = QLineEdit()
        phone_edit = QLineEdit()
        email_edit = QLineEdit()
        layout.addRow("姓名:", name_edit)
        layout.addRow("职位:", title_edit)
        layout.addRow("电话:", phone_edit)
        layout.addRow("邮箱:", email_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "错误", "姓名不能为空")
                return
            success, msg = add_contact(self.customer_id, name, title_edit.text(), phone_edit.text(), email_edit.text())
            if success:
                QMessageBox.information(self, "成功", msg)
                self.accept()
            else:
                QMessageBox.critical(self, "错误", msg)

    def add_interaction_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加交互记录")
        layout = QFormLayout(dialog)
        type_combo = QComboBox()
        type_combo.addItems(["电话", "邮件", "会议"])
        content_edit = QTextEdit()
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(QDate.currentDate())
        layout.addRow("类型:", type_combo)
        layout.addRow("内容:", content_edit)
        layout.addRow("日期:", date_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            content = content_edit.toPlainText().strip()
            if not content:
                QMessageBox.warning(self, "错误", "内容不能为空")
                return
            happened_at = datetime(date_edit.date().year(), date_edit.date().month(), date_edit.date().day())
            add_interaction(self.customer_id, type_combo.currentText(), content, happened_at)
            QMessageBox.information(self, "成功", "交互记录已添加")
            self.accept()

    def add_ticket_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加工单")
        layout = QFormLayout(dialog)
        title_edit = QLineEdit()
        desc_edit = QTextEdit()
        priority_combo = QComboBox()
        priority_combo.addItems(["低", "中", "高", "紧急"])
        type_combo = QComboBox()
        type_combo.addItems(["技术支持", "售后服务", "投诉建议", "其他"])
        assigned_edit = QLineEdit()
        layout.addRow("标题:", title_edit)
        layout.addRow("描述:", desc_edit)
        layout.addRow("优先级:", priority_combo)
        layout.addRow("类型:", type_combo)
        layout.addRow("负责人:", assigned_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            title = title_edit.text().strip()
            if not title:
                QMessageBox.warning(self, "错误", "标题不能为空")
                return
            add_ticket(self.customer_id, title, desc_edit.toPlainText(),
                       priority_combo.currentText(), type_combo.currentText(), assigned_edit.text())
            QMessageBox.information(self, "成功", "工单已创建")
            self.accept()


class TicketPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        filter_layout = QHBoxLayout()
        self.status_combo = QComboBox()
        self.status_combo.addItems(["全部", "待分配", "处理中", "待验收", "已完成", "已关闭"])
        self.filter_btn = QPushButton("筛选")
        self.filter_btn.clicked.connect(self.load_tickets)
        filter_layout.addWidget(QLabel("工单状态:"))
        filter_layout.addWidget(self.status_combo)
        filter_layout.addWidget(self.filter_btn)
        layout.addLayout(filter_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["ID", "客户", "标题", "状态", "优先级", "类型", "创建时间"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.edit_ticket)  # 双击编辑
        layout.addWidget(self.table)

        if parent.role == 'admin':
            add_btn = QPushButton("新建工单")
            add_btn.clicked.connect(self.add_ticket_dialog)
            layout.addWidget(add_btn)

        self.load_tickets()

    def load_tickets(self):
        status = self.status_combo.currentText()
        df = get_all_tickets(status if status != "全部" else None)
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(row['customer_name']))
            self.table.setItem(i, 2, QTableWidgetItem(row['title']))
            self.table.setItem(i, 3, QTableWidgetItem(row['status']))
            self.table.setItem(i, 4, QTableWidgetItem(row['priority']))
            self.table.setItem(i, 5, QTableWidgetItem(row['ticket_type']))
            self.table.setItem(i, 6, QTableWidgetItem(row['created_at']))

    def add_ticket_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新建工单")
        layout = QFormLayout(dialog)
        customer_combo = QComboBox()
        customers_df = get_customers()
        customer_combo.addItems(customers_df['name'].tolist())
        title_edit = QLineEdit()
        desc_edit = QTextEdit()
        priority_combo = QComboBox()
        priority_combo.addItems(["低", "中", "高", "紧急"])
        type_combo = QComboBox()
        type_combo.addItems(["技术支持", "售后服务", "投诉建议", "其他"])
        assigned_edit = QLineEdit()
        layout.addRow("客户:", customer_combo)
        layout.addRow("标题:", title_edit)
        layout.addRow("描述:", desc_edit)
        layout.addRow("优先级:", priority_combo)
        layout.addRow("类型:", type_combo)
        layout.addRow("负责人:", assigned_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            title = title_edit.text().strip()
            if not title:
                QMessageBox.warning(self, "错误", "标题不能为空")
                return
            customer_name = customer_combo.currentText()
            cid = customers_df[customers_df['name'] == customer_name].iloc[0]['id']
            add_ticket(cid, title, desc_edit.toPlainText(),
                       priority_combo.currentText(), type_combo.currentText(), assigned_edit.text())
            QMessageBox.information(self, "成功", "工单已创建")
            self.load_tickets()

    def edit_ticket(self, index):
        if self.parent().role != 'admin':
            QMessageBox.warning(self, "权限不足", "只有管理员可以编辑工单")
            return
        row = index.row()
        ticket_id = int(self.table.item(row, 0).text())
        customer_name = self.table.item(row, 1).text()
        title = self.table.item(row, 2).text()
        status = self.table.item(row, 3).text()
        priority = self.table.item(row, 4).text()
        ticket_type = self.table.item(row, 5).text()

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑工单")
        layout = QFormLayout(dialog)
        title_edit = QLineEdit(title)
        desc_edit = QTextEdit()
        # 获取原有描述（需要从数据库获取完整描述）
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT description FROM tickets WHERE id=?", (ticket_id,))
        desc = c.fetchone()[0]
        conn.close()
        desc_edit.setPlainText(desc)
        status_combo = QComboBox()
        status_combo.addItems(["待分配", "处理中", "待验收", "已完成", "已关闭"])
        status_combo.setCurrentText(status)
        priority_combo = QComboBox()
        priority_combo.addItems(["低", "中", "高", "紧急"])
        priority_combo.setCurrentText(priority)
        type_combo = QComboBox()
        type_combo.addItems(["技术支持", "售后服务", "投诉建议", "其他"])
        type_combo.setCurrentText(ticket_type)
        assigned_edit = QLineEdit()
        layout.addRow("标题:", title_edit)
        layout.addRow("描述:", desc_edit)
        layout.addRow("状态:", status_combo)
        layout.addRow("优先级:", priority_combo)
        layout.addRow("类型:", type_combo)
        layout.addRow("负责人:", assigned_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            new_title = title_edit.text().strip()
            if not new_title:
                QMessageBox.warning(self, "错误", "标题不能为空")
                return
            update_ticket(ticket_id, new_title, desc_edit.toPlainText(),
                          status_combo.currentText(), priority_combo.currentText(),
                          assigned_edit.text(), type_combo.currentText())
            QMessageBox.information(self, "成功", "工单已更新")
            self.load_tickets()


class SalesAnalysisPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.funnel_fig, self.funnel_ax = plt.subplots(figsize=(8, 5))
        self.funnel_canvas = FigureCanvas(self.funnel_fig)
        self.trend_fig, self.trend_ax = plt.subplots(figsize=(8, 4))
        self.trend_canvas = FigureCanvas(self.trend_fig)
        self.pred_fig, self.pred_ax = plt.subplots(figsize=(8, 4))
        self.pred_canvas = FigureCanvas(self.pred_fig)
        layout.addWidget(QLabel("销售漏斗分析"))
        layout.addWidget(self.funnel_canvas)
        layout.addWidget(QLabel("月度新增客户趋势"))
        layout.addWidget(self.trend_canvas)
        layout.addWidget(QLabel("销售预测"))
        layout.addWidget(self.pred_canvas)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.update_analysis)
        layout.addWidget(self.refresh_btn)

        self.update_analysis()

    def update_analysis(self):
        df = get_customers()
        if not df.empty:
            funnel_fig = sales_funnel_analysis(df)
            if funnel_fig:
                self.funnel_canvas.setParent(None)
                self.funnel_canvas = FigureCanvas(funnel_fig)
                self.layout().insertWidget(1, self.funnel_canvas)
            trend_fig = monthly_trend(df)
            if trend_fig:
                self.trend_canvas.setParent(None)
                self.trend_canvas = FigureCanvas(trend_fig)
                self.layout().insertWidget(3, self.trend_canvas)
        pred_fig = sales_prediction()
        if pred_fig:
            self.pred_canvas.setParent(None)
            self.pred_canvas = FigureCanvas(pred_fig)
            self.layout().insertWidget(5, self.pred_canvas)


class CustomerJourneyPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("客户旅程可视化（简化版）"))
        steps = ["认知阶段", "考虑阶段", "决策阶段", "成交/流失"]
        for i, step in enumerate(steps):
            progress = QProgressBar()
            progress.setValue(int(100 * (i+1) / len(steps)))
            progress.setFormat(step)
            layout.addWidget(progress)
        layout.addWidget(QLabel("当前客户阶段分布"))
        self.df = get_customers()
        if not self.df.empty:
            stage_order = ["潜在", "意向", "谈判", "成交", "流失"]
            stage_count = self.df['stage'].value_counts()
            for stage in stage_order:
                count = stage_count.get(stage, 0)
                prog = QProgressBar()
                prog.setValue(int(count / max(stage_count.max(), 1) * 100))
                prog.setFormat(f"{stage}: {count}家客户")
                layout.addWidget(prog)


class ProjectPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("项目编号")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("项目名称")
        self.search_btn = QPushButton("查询")
        self.search_btn.clicked.connect(self.load_projects)
        search_layout.addWidget(QLabel("编号:"))
        search_layout.addWidget(self.code_input)
        search_layout.addWidget(QLabel("名称:"))
        search_layout.addWidget(self.name_input)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "项目编号", "项目名称", "地址", "跟踪人", "进度"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.edit_project)  # 双击编辑
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("新建项目")
        self.add_btn.clicked.connect(self.add_project_dialog)
        self.edit_btn = QPushButton("编辑项目")
        self.edit_btn.clicked.connect(self.edit_project)
        self.del_btn = QPushButton("删除项目")
        self.del_btn.clicked.connect(self.delete_project)
        if parent.role == 'admin':
            btn_layout.addWidget(self.add_btn)
            btn_layout.addWidget(self.edit_btn)
            btn_layout.addWidget(self.del_btn)
        layout.addLayout(btn_layout)

        self.load_projects()

    def load_projects(self):
        filters = {}
        if self.code_input.text().strip():
            filters['search_code'] = self.code_input.text().strip()
        if self.name_input.text().strip():
            filters['search_name'] = self.name_input.text().strip()
        df = get_all_projects(filters)
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(row['project_code']))
            self.table.setItem(i, 2, QTableWidgetItem(row['project_name']))
            self.table.setItem(i, 3, QTableWidgetItem(row['address'] or ''))
            self.table.setItem(i, 4, QTableWidgetItem(row['tracker'] or ''))
            self.table.setItem(i, 5, QTableWidgetItem(row['progress'] or ''))

    def add_project_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新建工程项目")
        layout = QFormLayout(dialog)

        code_edit = QLineEdit()
        name_edit = QLineEdit()
        address_edit = QLineEdit()
        tracker_edit = QLineEdit()
        city_edit = QLineEdit()
        usage_edit = QLineEdit()
        progress_edit = QLineEdit()
        last_followup = QDateEdit()
        last_followup.setDate(QDate.currentDate())
        products_edit = QLineEdit()
        equipment_edit = QLineEdit()
        const_unit = QLineEdit()
        const_dept = QLineEdit()
        const_contact = QLineEdit()
        const_phone = QLineEdit()
        design_unit = QLineEdit()
        design_dept = QLineEdit()
        design_contact = QLineEdit()
        design_phone = QLineEdit()
        general_unit = QLineEdit()
        general_dept = QLineEdit()
        general_contact = QLineEdit()
        general_phone = QLineEdit()
        estimated_amount = QDoubleSpinBox()
        estimated_amount.setRange(0, 1e9)
        estimated_amount.setSuffix(" 万")
        remarks_edit = QTextEdit()

        layout.addRow("项目编号*:", code_edit)
        layout.addRow("项目名称*:", name_edit)
        layout.addRow("地址:", address_edit)
        layout.addRow("跟踪人:", tracker_edit)
        layout.addRow("城市:", city_edit)
        layout.addRow("使用区域:", usage_edit)
        layout.addRow("进度:", progress_edit)
        layout.addRow("最近跟进:", last_followup)
        layout.addRow("产品:", products_edit)
        layout.addRow("设备量单:", equipment_edit)
        layout.addRow("建设单位单位:", const_unit)
        layout.addRow("建设单位部门:", const_dept)
        layout.addRow("建设单位联系人:", const_contact)
        layout.addRow("建设单位电话:", const_phone)
        layout.addRow("设计院单位:", design_unit)
        layout.addRow("设计院部门:", design_dept)
        layout.addRow("设计院联系人:", design_contact)
        layout.addRow("设计院电话:", design_phone)
        layout.addRow("总包单位:", general_unit)
        layout.addRow("总包部门:", general_dept)
        layout.addRow("总包联系人:", general_contact)
        layout.addRow("总包电话:", general_phone)
        layout.addRow("预计金额(万):", estimated_amount)
        layout.addRow("备注:", remarks_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            code = code_edit.text().strip()
            name = name_edit.text().strip()
            if not code or not name:
                QMessageBox.warning(self, "错误", "项目编号和名称不能为空")
                return
            data = {
                'project_code': code,
                'project_name': name,
                'address': address_edit.text(),
                'tracker': tracker_edit.text(),
                'city': city_edit.text(),
                'usage_area': usage_edit.text(),
                'progress': progress_edit.text(),
                'last_followup': last_followup.date().toString(Qt.ISODate),
                'products': products_edit.text(),
                'equipment_list': equipment_edit.text(),
                'construction_unit': const_unit.text(),
                'construction_dept': const_dept.text(),
                'construction_contact': const_contact.text(),
                'construction_phone': const_phone.text(),
                'design_unit': design_unit.text(),
                'design_dept': design_dept.text(),
                'design_contact': design_contact.text(),
                'design_phone': design_phone.text(),
                'general_unit': general_unit.text(),
                'general_dept': general_dept.text(),
                'general_contact': general_contact.text(),
                'general_phone': general_phone.text(),
                'estimated_amount': estimated_amount.value(),
                'remarks': remarks_edit.toPlainText()
            }
            success, msg = add_project(data)
            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_projects()
            else:
                QMessageBox.critical(self, "错误", msg)

    def edit_project(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要编辑的项目")
            return
        pid = int(self.table.item(current_row, 0).text())
        project = get_project_by_id(pid)
        if not project:
            QMessageBox.critical(self, "错误", "项目不存在")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑工程项目")
        layout = QFormLayout(dialog)

        code_edit = QLineEdit(project['project_code'])
        name_edit = QLineEdit(project['project_name'])
        address_edit = QLineEdit(project['address'] or '')
        tracker_edit = QLineEdit(project['tracker'] or '')
        city_edit = QLineEdit(project['city'] or '')
        usage_edit = QLineEdit(project['usage_area'] or '')
        progress_edit = QLineEdit(project['progress'] or '')
        last_followup = QDateEdit()
        if project['last_followup']:
            try:
                last_followup.setDate(QDate.fromString(project['last_followup'], Qt.ISODate))
            except:
                last_followup.setDate(QDate.currentDate())
        else:
            last_followup.setDate(QDate.currentDate())
        products_edit = QLineEdit(project['products'] or '')
        equipment_edit = QLineEdit(project['equipment_list'] or '')
        const_unit = QLineEdit(project['construction_unit'] or '')
        const_dept = QLineEdit(project['construction_dept'] or '')
        const_contact = QLineEdit(project['construction_contact'] or '')
        const_phone = QLineEdit(project['construction_phone'] or '')
        design_unit = QLineEdit(project['design_unit'] or '')
        design_dept = QLineEdit(project['design_dept'] or '')
        design_contact = QLineEdit(project['design_contact'] or '')
        design_phone = QLineEdit(project['design_phone'] or '')
        general_unit = QLineEdit(project['general_unit'] or '')
        general_dept = QLineEdit(project['general_dept'] or '')
        general_contact = QLineEdit(project['general_contact'] or '')
        general_phone = QLineEdit(project['general_phone'] or '')
        estimated_amount = QDoubleSpinBox()
        estimated_amount.setRange(0, 1e9)
        estimated_amount.setValue(project['estimated_amount'] or 0)
        estimated_amount.setSuffix(" 万")
        remarks_edit = QTextEdit(project['remarks'] or '')

        layout.addRow("项目编号*:", code_edit)
        layout.addRow("项目名称*:", name_edit)
        layout.addRow("地址:", address_edit)
        layout.addRow("跟踪人:", tracker_edit)
        layout.addRow("城市:", city_edit)
        layout.addRow("使用区域:", usage_edit)
        layout.addRow("进度:", progress_edit)
        layout.addRow("最近跟进:", last_followup)
        layout.addRow("产品:", products_edit)
        layout.addRow("设备量单:", equipment_edit)
        layout.addRow("建设单位单位:", const_unit)
        layout.addRow("建设单位部门:", const_dept)
        layout.addRow("建设单位联系人:", const_contact)
        layout.addRow("建设单位电话:", const_phone)
        layout.addRow("设计院单位:", design_unit)
        layout.addRow("设计院部门:", design_dept)
        layout.addRow("设计院联系人:", design_contact)
        layout.addRow("设计院电话:", design_phone)
        layout.addRow("总包单位:", general_unit)
        layout.addRow("总包部门:", general_dept)
        layout.addRow("总包联系人:", general_contact)
        layout.addRow("总包电话:", general_phone)
        layout.addRow("预计金额(万):", estimated_amount)
        layout.addRow("备注:", remarks_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            code = code_edit.text().strip()
            name = name_edit.text().strip()
            if not code or not name:
                QMessageBox.warning(self, "错误", "项目编号和名称不能为空")
                return
            data = {
                'project_code': code,
                'project_name': name,
                'address': address_edit.text(),
                'tracker': tracker_edit.text(),
                'city': city_edit.text(),
                'usage_area': usage_edit.text(),
                'progress': progress_edit.text(),
                'last_followup': last_followup.date().toString(Qt.ISODate),
                'products': products_edit.text(),
                'equipment_list': equipment_edit.text(),
                'construction_unit': const_unit.text(),
                'construction_dept': const_dept.text(),
                'construction_contact': const_contact.text(),
                'construction_phone': const_phone.text(),
                'design_unit': design_unit.text(),
                'design_dept': design_dept.text(),
                'design_contact': design_contact.text(),
                'design_phone': design_phone.text(),
                'general_unit': general_unit.text(),
                'general_dept': general_dept.text(),
                'general_contact': general_contact.text(),
                'general_phone': general_phone.text(),
                'estimated_amount': estimated_amount.value(),
                'remarks': remarks_edit.toPlainText()
            }
            success, msg = update_project(pid, data)
            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_projects()
            else:
                QMessageBox.critical(self, "错误", msg)

    def delete_project(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的项目")
            return
        pid = int(self.table.item(current_row, 0).text())
        name = self.table.item(current_row, 2).text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除项目“{name}”吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            delete_project(pid)
            QMessageBox.information(self, "成功", "项目已删除")
            self.load_projects()


class QuotationPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        self.no_input = QLineEdit()
        self.no_input.setPlaceholderText("报价单号")
        self.proj_input = QLineEdit()
        self.proj_input.setPlaceholderText("项目名称")
        self.search_btn = QPushButton("查询")
        self.search_btn.clicked.connect(self.load_quotations)
        search_layout.addWidget(QLabel("单号:"))
        search_layout.addWidget(self.no_input)
        search_layout.addWidget(QLabel("项目:"))
        search_layout.addWidget(self.proj_input)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "报价单号", "项目名称", "客户名称", "报价日期"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.edit_quotation)  # 双击编辑基本信息
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("新建报价单")
        self.add_btn.clicked.connect(self.add_quotation_dialog)
        self.del_btn = QPushButton("删除报价单")
        self.del_btn.clicked.connect(self.delete_quotation)
        self.pdf_btn = QPushButton("导出PDF")
        self.pdf_btn.clicked.connect(self.export_pdf)
        if parent.role == 'admin':
            btn_layout.addWidget(self.add_btn)
            btn_layout.addWidget(self.del_btn)
            btn_layout.addWidget(self.pdf_btn)
        layout.addLayout(btn_layout)

        self.load_quotations()

    def load_quotations(self):
        filters = {}
        if self.no_input.text().strip():
            filters['search_no'] = self.no_input.text().strip()
        if self.proj_input.text().strip():
            filters['project_name'] = self.proj_input.text().strip()
        df = get_all_quotations(filters)
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(row['quotation_no']))
            self.table.setItem(i, 2, QTableWidgetItem(row['project_name']))
            self.table.setItem(i, 3, QTableWidgetItem(row['customer_name']))
            self.table.setItem(i, 4, QTableWidgetItem(row['quotation_date']))

    def add_quotation_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新建报价单")
        layout = QFormLayout(dialog)

        no_edit = QLineEdit()
        proj_combo = QComboBox()
        projects_df = get_all_projects()
        proj_combo.addItems(projects_df['project_name'].tolist() if not projects_df.empty else [])
        customer_edit = QLineEdit()
        contact_edit = QLineEdit()
        phone_edit = QLineEdit()
        date_edit = QDateEdit()
        date_edit.setDate(QDate.currentDate())
        layout.addRow("报价单号*:", no_edit)
        layout.addRow("项目名称:", proj_combo)
        layout.addRow("客户名称:", customer_edit)
        layout.addRow("联系人:", contact_edit)
        layout.addRow("电话:", phone_edit)
        layout.addRow("报价日期:", date_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            no = no_edit.text().strip()
            if not no:
                QMessageBox.warning(self, "错误", "报价单号不能为空")
                return
            data = {
                'quotation_no': no,
                'project_name': proj_combo.currentText(),
                'customer_name': customer_edit.text(),
                'contact_person': contact_edit.text(),
                'contact_phone': phone_edit.text(),
                'quotation_date': date_edit.date().toString(Qt.ISODate)
            }
            success, result = add_quotation(data)
            if success:
                QMessageBox.information(self, "成功", f"报价单创建成功，ID: {result}")
                self.load_quotations()
                self.show_quotation_detail_by_id(result)
            else:
                QMessageBox.critical(self, "错误", result)

    def edit_quotation(self, index):
        if self.parent().role != 'admin':
            QMessageBox.warning(self, "权限不足", "只有管理员可以编辑报价单")
            return
        row = index.row()
        qid = int(self.table.item(row, 0).text())
        quote = get_quotation_by_id(qid)
        if not quote:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑报价单基本信息")
        layout = QFormLayout(dialog)
        no_edit = QLineEdit(quote['quotation_no'])
        proj_combo = QComboBox()
        projects_df = get_all_projects()
        proj_combo.addItems(projects_df['project_name'].tolist() if not projects_df.empty else [])
        proj_combo.setCurrentText(quote['project_name'])
        customer_edit = QLineEdit(quote['customer_name'])
        contact_edit = QLineEdit(quote['contact_person'])
        phone_edit = QLineEdit(quote['contact_phone'])
        date_edit = QDateEdit()
        date_edit.setDate(QDate.fromString(quote['quotation_date'], Qt.ISODate))
        layout.addRow("报价单号*:", no_edit)
        layout.addRow("项目名称:", proj_combo)
        layout.addRow("客户名称:", customer_edit)
        layout.addRow("联系人:", contact_edit)
        layout.addRow("电话:", phone_edit)
        layout.addRow("报价日期:", date_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            no = no_edit.text().strip()
            if not no:
                QMessageBox.warning(self, "错误", "报价单号不能为空")
                return
            data = {
                'quotation_no': no,
                'project_name': proj_combo.currentText(),
                'customer_name': customer_edit.text(),
                'contact_person': contact_edit.text(),
                'contact_phone': phone_edit.text(),
                'quotation_date': date_edit.date().toString(Qt.ISODate)
            }
            success, msg = update_quotation(qid, data)
            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_quotations()
            else:
                QMessageBox.critical(self, "错误", msg)

    def delete_quotation(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的报价单")
            return
        qid = int(self.table.item(current_row, 0).text())
        no = self.table.item(current_row, 1).text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除报价单“{no}”吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            delete_quotation(qid)
            QMessageBox.information(self, "成功", "报价单已删除")
            self.load_quotations()

    def export_pdf(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要导出的报价单")
            return
        qid = int(self.table.item(current_row, 0).text())
        no = self.table.item(current_row, 1).text()
        filename, _ = QFileDialog.getSaveFileName(self, "保存PDF文件", f"{no}.pdf", "PDF文件 (*.pdf)")
        if filename:
            if export_quotation_pdf(qid, filename):
                QMessageBox.information(self, "成功", f"报价单已导出至 {filename}")
            else:
                QMessageBox.critical(self, "错误", "导出失败")

    def show_quotation_detail(self, index):
        row = index.row()
        qid = int(self.table.item(row, 0).text())
        self.show_quotation_detail_by_id(qid)

    def show_quotation_detail_by_id(self, qid):
        dialog = QuotationDetailDialog(qid, self)
        dialog.exec_()


class QuotationDetailDialog(QDialog):
    def __init__(self, quotation_id, parent=None):
        super().__init__(parent)
        self.quotation_id = quotation_id
        self.setWindowTitle("报价单明细")
        self.setMinimumSize(800, 600)
        layout = QVBoxLayout(self)

        quote = get_quotation_by_id(quotation_id)
        if not quote:
            QMessageBox.critical(self, "错误", "报价单不存在")
            self.reject()
            return

        info = f"报价单号: {quote['quotation_no']}  项目: {quote['project_name']}  客户: {quote['customer_name']}  联系人: {quote['contact_person']}  电话: {quote['contact_phone']}  日期: {quote['quotation_date']}"
        layout.addWidget(QLabel(info))

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(10)
        self.items_table.setHorizontalHeaderLabels(["序号", "产品名称", "规格", "单位", "数量", "下浮(%)", "面价", "单价", "金额", "使用区域"])
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.doubleClicked.connect(self.edit_item)  # 双击编辑明细
        layout.addWidget(self.items_table)

        self.total_label = QLabel()
        layout.addWidget(self.total_label)

        btn_layout = QHBoxLayout()
        if parent.parent().role == 'admin':
            add_item_btn = QPushButton("添加明细")
            add_item_btn.clicked.connect(self.add_item)
            btn_layout.addWidget(add_item_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_items)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.load_items()

    def load_items(self):
        df = get_quotation_items(self.quotation_id)
        self.items_table.setRowCount(len(df))
        total = 0
        self.items_data = df  # 存储以便编辑时使用
        for i, row in df.iterrows():
            self.items_table.setItem(i, 0, QTableWidgetItem(str(row['seq'])))
            self.items_table.setItem(i, 1, QTableWidgetItem(row['product_name']))
            self.items_table.setItem(i, 2, QTableWidgetItem(row['specification'] or ''))
            self.items_table.setItem(i, 3, QTableWidgetItem(row['unit'] or ''))
            self.items_table.setItem(i, 4, QTableWidgetItem(str(row['quantity'])))
            self.items_table.setItem(i, 5, QTableWidgetItem(str(row['discount'])))
            self.items_table.setItem(i, 6, QTableWidgetItem(f"¥{row['list_price']:.2f}"))
            self.items_table.setItem(i, 7, QTableWidgetItem(f"¥{row['unit_price']:.2f}"))
            self.items_table.setItem(i, 8, QTableWidgetItem(f"¥{row['amount']:.2f}"))
            self.items_table.setItem(i, 9, QTableWidgetItem(row['usage_area'] or ''))
            total += row['amount']
        self.total_label.setText(f"报价总额: ¥{total:,.2f}")

    def add_item(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加报价明细")
        layout = QFormLayout(dialog)

        products_df = get_all_products()
        product_combo = QComboBox()
        product_combo.addItem("")
        for _, row in products_df.iterrows():
            text = f"{row['product_name']} [{row['category_major']} - {row['category_minor']}]" if row['category_major'] else row['product_name']
            product_combo.addItem(text, row['id'])
        product_combo.currentIndexChanged.connect(lambda: self.on_product_selected(product_combo, product_name_edit, spec_edit, unit_edit, price_edit))
        layout.addRow("产品:", product_combo)

        seq_spin = QSpinBox()
        seq_spin.setMinimum(1)
        layout.addRow("序号:", seq_spin)
        product_name_edit = QLineEdit()
        layout.addRow("产品名称:", product_name_edit)
        spec_edit = QLineEdit()
        layout.addRow("规格:", spec_edit)
        unit_edit = QLineEdit()
        layout.addRow("单位:", unit_edit)
        quantity_spin = QDoubleSpinBox()
        quantity_spin.setRange(0, 1e6)
        quantity_spin.setValue(1)
        layout.addRow("数量:", quantity_spin)
        discount_spin = QDoubleSpinBox()
        discount_spin.setRange(0, 100)
        discount_spin.setSuffix("%")
        layout.addRow("下浮点数:", discount_spin)
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0, 1e9)
        price_spin.setPrefix("¥")
        layout.addRow("面价:", price_spin)
        usage_edit = QLineEdit()
        layout.addRow("使用区域:", usage_edit)
        remark_edit = QLineEdit()
        layout.addRow("备注:", remark_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            product_id = product_combo.currentData()
            if product_id:
                prod = products_df[products_df['id'] == product_id].iloc[0]
                product_name = prod['product_name']
                spec = prod['specification'] or ''
                unit = prod['unit'] or ''
                list_price = prod['list_price']
            else:
                product_name = product_name_edit.text().strip()
                if not product_name:
                    QMessageBox.warning(self, "错误", "产品名称不能为空")
                    return
                spec = spec_edit.text()
                unit = unit_edit.text()
                list_price = price_spin.value()
            quantity = quantity_spin.value()
            discount = discount_spin.value()
            unit_price = list_price * (100 - discount) / 100
            amount = quantity * unit_price
            item = {
                'seq': seq_spin.value(),
                'product_id': product_id,
                'product_name': product_name,
                'specification': spec,
                'unit': unit,
                'quantity': quantity,
                'discount': discount,
                'list_price': list_price,
                'unit_price': unit_price,
                'amount': amount,
                'usage_area': usage_edit.text(),
                'remarks': remark_edit.text()
            }
            ok, msg = add_quotation_item(self.quotation_id, item)
            if ok:
                self.load_items()
            else:
                QMessageBox.warning(self, "警告", msg)

    def edit_item(self, index):
        if self.parent().parent().role != 'admin':
            QMessageBox.warning(self, "权限不足", "只有管理员可以编辑明细")
            return
        row = index.row()
        item_id = self.items_data.iloc[row]['id']
        item = self.items_data.iloc[row].to_dict()

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑报价明细")
        layout = QFormLayout(dialog)

        products_df = get_all_products()
        product_combo = QComboBox()
        product_combo.addItem("")
        for _, row in products_df.iterrows():
            text = f"{row['product_name']} [{row['category_major']} - {row['category_minor']}]" if row['category_major'] else row['product_name']
            product_combo.addItem(text, row['id'])
        # 设置当前产品
        current_idx = product_combo.findData(item['product_id']) if item['product_id'] else 0
        product_combo.setCurrentIndex(current_idx)
        product_combo.currentIndexChanged.connect(lambda: self.on_product_selected(product_combo, product_name_edit, spec_edit, unit_edit, price_edit))
        layout.addRow("产品:", product_combo)

        seq_spin = QSpinBox()
        seq_spin.setMinimum(1)
        seq_spin.setValue(item['seq'])
        layout.addRow("序号:", seq_spin)
        product_name_edit = QLineEdit(item['product_name'])
        layout.addRow("产品名称:", product_name_edit)
        spec_edit = QLineEdit(item['specification'] or '')
        layout.addRow("规格:", spec_edit)
        unit_edit = QLineEdit(item['unit'] or '')
        layout.addRow("单位:", unit_edit)
        quantity_spin = QDoubleSpinBox()
        quantity_spin.setRange(0, 1e6)
        quantity_spin.setValue(item['quantity'])
        layout.addRow("数量:", quantity_spin)
        discount_spin = QDoubleSpinBox()
        discount_spin.setRange(0, 100)
        discount_spin.setValue(item['discount'])
        discount_spin.setSuffix("%")
        layout.addRow("下浮点数:", discount_spin)
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0, 1e9)
        price_spin.setValue(item['list_price'])
        price_spin.setPrefix("¥")
        layout.addRow("面价:", price_spin)
        usage_edit = QLineEdit(item['usage_area'] or '')
        layout.addRow("使用区域:", usage_edit)
        remark_edit = QLineEdit(item['remarks'] or '')
        layout.addRow("备注:", remark_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            product_id = product_combo.currentData()
            if product_id:
                prod = products_df[products_df['id'] == product_id].iloc[0]
                product_name = prod['product_name']
                spec = prod['specification'] or ''
                unit = prod['unit'] or ''
                list_price = prod['list_price']
            else:
                product_name = product_name_edit.text().strip()
                if not product_name:
                    QMessageBox.warning(self, "错误", "产品名称不能为空")
                    return
                spec = spec_edit.text()
                unit = unit_edit.text()
                list_price = price_spin.value()
            quantity = quantity_spin.value()
            discount = discount_spin.value()
            unit_price = list_price * (100 - discount) / 100
            amount = quantity * unit_price
            new_item = {
                'seq': seq_spin.value(),
                'product_id': product_id,
                'product_name': product_name,
                'specification': spec,
                'unit': unit,
                'quantity': quantity,
                'discount': discount,
                'list_price': list_price,
                'unit_price': unit_price,
                'amount': amount,
                'usage_area': usage_edit.text(),
                'remarks': remark_edit.text()
            }
            update_quotation_item(item_id, new_item)
            self.load_items()

    def on_product_selected(self, combo, name_edit, spec_edit, unit_edit, price_edit):
        idx = combo.currentIndex()
        if idx <= 0:
            name_edit.clear()
            spec_edit.clear()
            unit_edit.clear()
            price_edit.setValue(0)
            return
        product_id = combo.itemData(idx)
        products_df = get_all_products()
        prod = products_df[products_df['id'] == product_id].iloc[0]
        name_edit.setText(prod['product_name'])
        spec_edit.setText(prod['specification'] or '')
        unit_edit.setText(prod['unit'] or '')
        price_edit.setValue(prod['list_price'])


class ProductPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["ID", "产品编号", "产品名称", "规格", "单位", "面价", "大类/类别", "库存"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.edit_product)  # 双击编辑
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("新增产品")
        self.add_btn.clicked.connect(self.add_product)
        self.edit_btn = QPushButton("编辑产品")
        self.edit_btn.clicked.connect(self.edit_product)
        self.del_btn = QPushButton("删除产品")
        self.del_btn.clicked.connect(self.delete_product)
        self.stock_btn = QPushButton("库存调整")
        self.stock_btn.clicked.connect(self.stock_adjustment)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addWidget(self.stock_btn)
        layout.addLayout(btn_layout)

        self.load_products()

    def load_products(self):
        df = get_all_products()
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(row['product_code']))
            self.table.setItem(i, 2, QTableWidgetItem(row['product_name']))
            self.table.setItem(i, 3, QTableWidgetItem(row['specification'] or ''))
            self.table.setItem(i, 4, QTableWidgetItem(row['unit'] or ''))
            self.table.setItem(i, 5, QTableWidgetItem(f"¥{row['list_price']:.2f}"))
            category = f"{row['category_major']} / {row['category_minor']}" if row['category_major'] else ''
            self.table.setItem(i, 6, QTableWidgetItem(category))
            self.table.setItem(i, 7, QTableWidgetItem(str(row['stock_quantity'])))

    def add_product(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新增产品")
        layout = QFormLayout(dialog)
        code_edit = QLineEdit()
        name_edit = QLineEdit()
        spec_edit = QLineEdit()
        unit_edit = QLineEdit()
        price_edit = QDoubleSpinBox()
        price_edit.setRange(0, 1e9)
        price_edit.setPrefix("¥")
        major_edit = QLineEdit()
        minor_edit = QLineEdit()
        stock_edit = QDoubleSpinBox()
        stock_edit.setRange(0, 1e6)
        layout.addRow("产品编号*:", code_edit)
        layout.addRow("产品名称*:", name_edit)
        layout.addRow("规格:", spec_edit)
        layout.addRow("单位:", unit_edit)
        layout.addRow("面价:", price_edit)
        layout.addRow("产品大类:", major_edit)
        layout.addRow("产品类别:", minor_edit)
        layout.addRow("初始库存:", stock_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            code = code_edit.text().strip()
            name = name_edit.text().strip()
            if not code or not name:
                QMessageBox.warning(self, "错误", "产品编号和名称不能为空")
                return
            success, msg = add_product(code, name, spec_edit.text(), unit_edit.text(),
                                       price_edit.value(), major_edit.text(), minor_edit.text(),
                                       stock_edit.value())
            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_products()
            else:
                QMessageBox.critical(self, "错误", msg)

    def edit_product(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要编辑的产品")
            return
        pid = int(self.table.item(current_row, 0).text())
        product = get_product_by_id(pid)
        if not product:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑产品")
        layout = QFormLayout(dialog)
        code_edit = QLineEdit(product['product_code'])
        name_edit = QLineEdit(product['product_name'])
        spec_edit = QLineEdit(product['specification'] or '')
        unit_edit = QLineEdit(product['unit'] or '')
        price_edit = QDoubleSpinBox()
        price_edit.setRange(0, 1e9)
        price_edit.setValue(product['list_price'])
        price_edit.setPrefix("¥")
        major_edit = QLineEdit(product['category_major'] or '')
        minor_edit = QLineEdit(product['category_minor'] or '')
        stock_edit = QDoubleSpinBox()
        stock_edit.setRange(0, 1e6)
        stock_edit.setValue(product['stock_quantity'])
        layout.addRow("产品编号*:", code_edit)
        layout.addRow("产品名称*:", name_edit)
        layout.addRow("规格:", spec_edit)
        layout.addRow("单位:", unit_edit)
        layout.addRow("面价:", price_edit)
        layout.addRow("产品大类:", major_edit)
        layout.addRow("产品类别:", minor_edit)
        layout.addRow("库存:", stock_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            code = code_edit.text().strip()
            name = name_edit.text().strip()
            if not code or not name:
                QMessageBox.warning(self, "错误", "产品编号和名称不能为空")
                return
            success, msg = update_product(pid, code, name, spec_edit.text(), unit_edit.text(),
                                          price_edit.value(), major_edit.text(), minor_edit.text(),
                                          stock_edit.value())
            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_products()
            else:
                QMessageBox.critical(self, "错误", msg)

    def delete_product(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的产品")
            return
        pid = int(self.table.item(current_row, 0).text())
        name = self.table.item(current_row, 2).text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除产品“{name}”吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            delete_product(pid)
            QMessageBox.information(self, "成功", "产品已删除")
            self.load_products()

    def stock_adjustment(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要调整库存的产品")
            return
        pid = int(self.table.item(current_row, 0).text())
        product = get_product_by_id(pid)
        if not product:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("库存调整")
        layout = QFormLayout(dialog)
        type_combo = QComboBox()
        type_combo.addItems(["入库", "出库"])
        quantity_edit = QDoubleSpinBox()
        quantity_edit.setRange(0, 1e6)
        reason_edit = QLineEdit()
        layout.addRow("类型:", type_combo)
        layout.addRow("数量:", quantity_edit)
        layout.addRow("原因:", reason_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            type_str = type_combo.currentText()
            qty = quantity_edit.value()
            if qty <= 0:
                QMessageBox.warning(self, "错误", "数量必须大于0")
                return
            reason = reason_edit.text()
            db_type = 'in' if type_str == '入库' else 'out'
            success, msg = update_product_stock(pid, qty, reason, db_type)
            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_products()
            else:
                QMessageBox.critical(self, "错误", msg)


class DataManagePage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        tables = {
            "customers": "客户表",
            "contacts": "联系人表",
            "interactions": "交互记录表",
            "tickets": "工单表",
            "projects": "工程项目表",
            "quotations": "报价主表",
            "quotation_items": "报价明细表",
            "products": "产品表",
            "logs": "操作日志表",
            "tags": "标签表",
            "customer_tags": "客户标签关联表",
            "tasks": "任务表",
            "inventory_transactions": "库存流水表"
        }

        export_group = QGroupBox("导出数据")
        export_layout = QHBoxLayout()
        self.export_combo = QComboBox()
        for key, val in tables.items():
            self.export_combo.addItem(val, key)
        export_btn = QPushButton("导出为CSV")
        export_btn.clicked.connect(self.export_data)
        export_layout.addWidget(QLabel("选择表:"))
        export_layout.addWidget(self.export_combo)
        export_layout.addWidget(export_btn)
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)

        import_group = QGroupBox("导入数据（将覆盖现有数据）")
        import_layout = QVBoxLayout()
        self.import_combo = QComboBox()
        for key, val in tables.items():
            self.import_combo.addItem(val, key)
        self.import_file_edit = QLineEdit()
        browse_btn = QPushButton("选择文件")
        browse_btn.clicked.connect(self.browse_file)
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.import_file_edit)
        file_layout.addWidget(browse_btn)
        import_layout.addWidget(QLabel("选择表:"))
        import_layout.addWidget(self.import_combo)
        import_layout.addWidget(QLabel("CSV文件:"))
        import_layout.addLayout(file_layout)
        self.confirm_check = QCheckBox("我确认已备份数据，并同意覆盖当前表内容")
        import_layout.addWidget(self.confirm_check)
        import_btn = QPushButton("开始导入")
        import_btn.clicked.connect(self.import_data)
        import_layout.addWidget(import_btn)
        import_group.setLayout(import_layout)
        layout.addWidget(import_group)

        backup_group = QGroupBox("数据库备份与恢复")
        backup_layout = QHBoxLayout()
        backup_btn = QPushButton("备份数据库")
        backup_btn.clicked.connect(self.backup_db)
        restore_btn = QPushButton("恢复数据库")
        restore_btn.clicked.connect(self.restore_db)
        backup_layout.addWidget(backup_btn)
        backup_layout.addWidget(restore_btn)
        backup_group.setLayout(backup_layout)
        layout.addWidget(backup_group)

        layout.addStretch()

    def export_data(self):
        table_key = self.export_combo.currentData()
        csv_data = export_table_to_csv(table_key)
        if not csv_data:
            QMessageBox.warning(self, "警告", "导出数据为空")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "保存CSV文件", f"{table_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "CSV文件 (*.csv)")
        if filename:
            with open(filename, 'w', encoding='utf-8-sig') as f:
                f.write(csv_data)
            QMessageBox.information(self, "成功", f"已导出到 {filename}")

    def browse_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "选择CSV文件", "", "CSV文件 (*.csv)")
        if filename:
            self.import_file_edit.setText(filename)

    def import_data(self):
        if not self.confirm_check.isChecked():
            QMessageBox.warning(self, "警告", "请勾选确认框后再导入")
            return
        filename = self.import_file_edit.text().strip()
        if not filename:
            QMessageBox.warning(self, "警告", "请选择CSV文件")
            return
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取文件失败: {e}")
            return
        table_key = self.import_combo.currentData()
        success, errors = safe_import(table_key, content)
        if errors:
            QMessageBox.warning(self, "导入完成", f"成功 {success} 条，错误 {len(errors)} 条。\n详情请查看控制台。")
            print("导入错误:", errors)
        else:
            QMessageBox.information(self, "成功", f"成功导入 {success} 条记录")
        QMessageBox.information(self, "提示", "请手动刷新其他页面以查看最新数据")

    def backup_db(self):
        try:
            path = backup_database()
            QMessageBox.information(self, "成功", f"数据库已备份至 {path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"备份失败: {e}")

    def restore_db(self):
        filename, _ = QFileDialog.getOpenFileName(self, "选择备份文件", "", "数据库文件 (*.db)")
        if filename:
            try:
                restore_database(filename)
                QMessageBox.information(self, "成功", "数据库已恢复，请重启应用。")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"恢复失败: {e}")


class AIAssistantPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("AI智能助手 (模拟模式)"))
        self.email_input = QPlainTextEdit()
        self.email_input.setPlaceholderText("粘贴客户邮件内容...")
        self.analyze_btn = QPushButton("智能分析")
        self.analyze_btn.clicked.connect(self.analyze)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.email_input)
        layout.addWidget(self.analyze_btn)
        layout.addWidget(self.result_text)

    def analyze(self):
        content = self.email_input.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "提示", "请输入邮件内容")
            return
        result = ai_email_assistant(content)
        self.result_text.setPlainText(result)


class LogPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "用户", "操作", "目标", "时间"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_logs)
        layout.addWidget(refresh_btn)
        self.load_logs()

    def load_logs(self):
        df = get_logs(limit=100)
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(row['user']))
            self.table.setItem(i, 2, QTableWidgetItem(row['action']))
            self.table.setItem(i, 3, QTableWidgetItem(row['target']))
            self.table.setItem(i, 4, QTableWidgetItem(row['created_at']))


class TaskPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        filter_layout = QHBoxLayout()
        self.status_combo = QComboBox()
        self.status_combo.addItems(["全部", "待处理", "进行中", "已完成"])
        self.filter_btn = QPushButton("筛选")
        self.filter_btn.clicked.connect(self.load_tasks)
        filter_layout.addWidget(QLabel("状态:"))
        filter_layout.addWidget(self.status_combo)
        filter_layout.addWidget(self.filter_btn)
        layout.addLayout(filter_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "标题", "描述", "负责人", "截止日期", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.edit_task)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("新建任务")
        self.add_btn.clicked.connect(self.add_task)
        self.edit_btn = QPushButton("编辑任务")
        self.edit_btn.clicked.connect(self.edit_task)
        self.del_btn = QPushButton("删除任务")
        self.del_btn.clicked.connect(self.delete_task)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.del_btn)
        layout.addLayout(btn_layout)

        self.load_tasks()

    def load_tasks(self):
        status = self.status_combo.currentText()
        filters = {}
        if status != "全部":
            filters['status'] = status
        # 如果非管理员，只显示自己的任务
        if self.parent().role not in ['admin', 'manager']:
            filters['assigned_to'] = self.parent().username
        df = get_tasks(filters)
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(row['title']))
            self.table.setItem(i, 2, QTableWidgetItem(row['description'] or ''))
            self.table.setItem(i, 3, QTableWidgetItem(row['assigned_to'] or ''))
            self.table.setItem(i, 4, QTableWidgetItem(row['due_date'] or ''))
            self.table.setItem(i, 5, QTableWidgetItem(row['status']))
        self.parent().update_task_count()

    def add_task(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新建任务")
        layout = QFormLayout(dialog)
        title_edit = QLineEdit()
        desc_edit = QTextEdit()
        assigned_edit = QComboBox()
        users = get_users()
        assigned_edit.addItems(users['username'].tolist())
        due_date = QDateEdit()
        due_date.setCalendarPopup(True)
        due_date.setDate(QDate.currentDate().addDays(7))
        layout.addRow("标题:", title_edit)
        layout.addRow("描述:", desc_edit)
        layout.addRow("负责人:", assigned_edit)
        layout.addRow("截止日期:", due_date)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            title = title_edit.text().strip()
            if not title:
                QMessageBox.warning(self, "错误", "标题不能为空")
                return
            due = datetime(due_date.date().year(), due_date.date().month(), due_date.date().day())
            add_task(title, desc_edit.toPlainText(), assigned_edit.currentText(), due)
            self.load_tasks()

    def edit_task(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要编辑的任务")
            return
        tid = int(self.table.item(current_row, 0).text())
        title = self.table.item(current_row, 1).text()
        desc = self.table.item(current_row, 2).text()
        assigned = self.table.item(current_row, 3).text()
        due_str = self.table.item(current_row, 4).text()
        status = self.table.item(current_row, 5).text()

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑任务")
        layout = QFormLayout(dialog)
        title_edit = QLineEdit(title)
        desc_edit = QTextEdit(desc)
        assigned_edit = QComboBox()
        users = get_users()
        assigned_edit.addItems(users['username'].tolist())
        assigned_edit.setCurrentText(assigned)
        due_date = QDateEdit()
        due_date.setCalendarPopup(True)
        if due_str:
            due_date.setDate(QDate.fromString(due_str, Qt.ISODate))
        else:
            due_date.setDate(QDate.currentDate())
        status_combo = QComboBox()
        status_combo.addItems(["待处理", "进行中", "已完成"])
        status_combo.setCurrentText(status)
        layout.addRow("标题:", title_edit)
        layout.addRow("描述:", desc_edit)
        layout.addRow("负责人:", assigned_edit)
        layout.addRow("截止日期:", due_date)
        layout.addRow("状态:", status_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            new_title = title_edit.text().strip()
            if not new_title:
                QMessageBox.warning(self, "错误", "标题不能为空")
                return
            due = datetime(due_date.date().year(), due_date.date().month(), due_date.date().day())
            update_task(tid, new_title, desc_edit.toPlainText(), assigned_edit.currentText(), due, status_combo.currentText())
            self.load_tasks()

    def delete_task(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的任务")
            return
        tid = int(self.table.item(current_row, 0).text())
        title = self.table.item(current_row, 1).text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除任务“{title}”吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            delete_task(tid)
            self.load_tasks()


class SettingsPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # 公司设置
        company_group = QGroupBox("公司信息")
        company_layout = QFormLayout()
        self.company_name = QLineEdit()
        self.company_name.setText(get_setting('company_name'))
        company_layout.addRow("公司名称:", self.company_name)
        company_group.setLayout(company_layout)
        layout.addWidget(company_group)

        # 邮件设置
        email_group = QGroupBox("邮件服务器设置")
        email_layout = QFormLayout()
        self.smtp_server = QLineEdit()
        self.smtp_server.setText(get_setting('smtp_server'))
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(int(get_setting('smtp_port') or 25))
        self.smtp_user = QLineEdit()
        self.smtp_user.setText(get_setting('smtp_user'))
        self.smtp_password = QLineEdit()
        self.smtp_password.setEchoMode(QLineEdit.Password)
        self.smtp_password.setText(get_setting('smtp_password'))
        self.email_from = QLineEdit()
        self.email_from.setText(get_setting('email_from'))
        email_layout.addRow("SMTP服务器:", self.smtp_server)
        email_layout.addRow("端口:", self.smtp_port)
        email_layout.addRow("用户名:", self.smtp_user)
        email_layout.addRow("密码:", self.smtp_password)
        email_layout.addRow("发件邮箱:", self.email_from)
        email_group.setLayout(email_layout)
        layout.addWidget(email_group)

        # 主题设置
        theme_group = QGroupBox("界面主题")
        theme_layout = QHBoxLayout()
        self.theme_light = QRadioButton("浅色")
        self.theme_dark = QRadioButton("深色")
        current_theme = get_setting('theme', 'light')
        if current_theme == 'light':
            self.theme_light.setChecked(True)
        else:
            self.theme_dark.setChecked(True)
        theme_layout.addWidget(self.theme_light)
        theme_layout.addWidget(self.theme_dark)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        # 保存按钮
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

        # 用户管理（仅管理员可见）
        if parent.role == 'admin':
            user_group = QGroupBox("用户管理")
            user_layout = QVBoxLayout()
            self.user_table = QTableWidget()
            self.user_table.setColumnCount(3)
            self.user_table.setHorizontalHeaderLabels(["ID", "用户名", "角色"])
            user_layout.addWidget(self.user_table)
            self.load_users()
            role_btn = QPushButton("修改角色")
            role_btn.clicked.connect(self.change_role)
            user_layout.addWidget(role_btn)
            user_group.setLayout(user_layout)
            layout.addWidget(user_group)

        layout.addStretch()

    def load_users(self):
        df = get_users()
        self.user_table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.user_table.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.user_table.setItem(i, 1, QTableWidgetItem(row['username']))
            self.user_table.setItem(i, 2, QTableWidgetItem(row['role']))

    def change_role(self):
        current_row = self.user_table.currentRow()
        if current_row < 0:
            return
        user_id = int(self.user_table.item(current_row, 0).text())
        current_role = self.user_table.item(current_row, 2).text()
        roles = ["admin", "manager", "sales", "support", "user"]
        new_role, ok = QInputDialog.getItem(self, "修改角色", "选择新角色", roles, roles.index(current_role), False)
        if ok and new_role != current_role:
            if update_user_role(user_id, new_role):
                QMessageBox.information(self, "成功", "角色已更新")
                self.load_users()
            else:
                QMessageBox.critical(self, "错误", "更新失败")

    def save_settings(self):
        set_setting('company_name', self.company_name.text())
        set_setting('smtp_server', self.smtp_server.text())
        set_setting('smtp_port', str(self.smtp_port.value()))
        set_setting('smtp_user', self.smtp_user.text())
        set_setting('smtp_password', self.smtp_password.text())
        set_setting('email_from', self.email_from.text())
        if self.theme_light.isChecked():
            set_setting('theme', 'light')
        else:
            set_setting('theme', 'dark')
        QMessageBox.information(self, "成功", "设置已保存，部分设置需重启生效。")
        # 主题立即应用
        self.parent().apply_theme()


# 全局 session_state 模拟
class SessionState:
    def __init__(self):
        self.username = 'system'
st_session_state = SessionState()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(248, 250, 254))
    palette.setColor(QPalette.WindowText, QColor(30, 47, 62))
    app.setPalette(palette)

    login = LoginDialog()
    if login.exec_() == QDialog.Accepted:
        st_session_state.username = login.user_info[1]
        main_win = MainWindow(login.user_info)
        main_win.show()
        sys.exit(app.exec_())
    else:
        sys.exit()

if __name__ == "__main__":
    main()