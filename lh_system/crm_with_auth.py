import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import re
import io
import warnings
from functools import wraps

# 密码哈希依赖
try:
    from werkzeug.security import generate_password_hash, check_password_hash
    HAS_WERKZEUG = True
except ImportError:
    HAS_WERKZEUG = False
    import hashlib
    def generate_password_hash(password):
        return hashlib.sha256(password.encode()).hexdigest()
    def check_password_hash(hash, password):
        return hash == hashlib.sha256(password.encode()).hexdigest()

warnings.filterwarnings('ignore')

# ---------- 配置 ----------
DB_PATH = "crm_ultimate.db"
PAGE_SIZE = 10
APP_TITLE = "智云CRM | 企业级客户关系管理系统"

# 尝试导入可选依赖
try:
    from st_customer_journey import st_customer_journey
    HAS_JOURNEY_LIB = True
except ImportError:
    HAS_JOURNEY_LIB = False

try:
    from transformers import pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


# ---------- 数据库连接与事务辅助 ----------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def execute_sql(conn, sql, params=None, commit=True):
    try:
        c = conn.cursor()
        c.execute(sql, params or ())
        if commit:
            conn.commit()
        return c
    except Exception as e:
        conn.rollback()
        raise e


# ---------- 数据库初始化（增加产品大类、类别） ----------
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # 原有表（客户、联系人、交互、日志、工单）
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

    # 工程项目表
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

    # 报价主表
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

    # 报价明细表
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

    # 用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT
                )''')

    # 产品表 - 增加产品大类、产品类别字段
    c.execute('''CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_code TEXT UNIQUE NOT NULL,
                    product_name TEXT NOT NULL,
                    specification TEXT,
                    unit TEXT,
                    list_price REAL DEFAULT 0,
                    category_major TEXT,   -- 产品大类
                    category_minor TEXT,   -- 产品类别
                    created_at TEXT,
                    updated_at TEXT
                )''')

    # 检查并添加新字段（兼容已有数据库）
    c.execute("PRAGMA table_info(products)")
    existing_columns = [col[1] for col in c.fetchall()]
    if 'category_major' not in existing_columns:
        c.execute("ALTER TABLE products ADD COLUMN category_major TEXT")
    if 'category_minor' not in existing_columns:
        c.execute("ALTER TABLE products ADD COLUMN category_minor TEXT")

    # 添加索引
    c.execute('CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_customers_stage ON customers(stage)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_projects_code ON projects(project_code)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(project_name)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_quotations_no ON quotations(quotation_no)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_quotations_project ON quotations(project_name)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_products_code ON products(product_code)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name)')

    # 创建默认管理员用户（若不存在）
    admin_exists = c.execute("SELECT id FROM users WHERE username=?", ('admin',)).fetchone()
    if not admin_exists:
        password_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
                  ('admin', password_hash, 'admin', datetime.now().isoformat()))

    conn.commit()
    conn.close()


init_db()


# ---------- 辅助函数 ----------
def add_log(user, action, target, details=""):
    conn = get_db_connection()
    try:
        execute_sql(conn, "INSERT INTO logs (user, action, target, details, created_at) VALUES (?,?,?,?,?)",
                    (user, action, target, details, datetime.now().isoformat()))
    except Exception as e:
        st.error(f"日志记录失败: {e}")
    finally:
        conn.close()


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def check_customer_exists(name):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM customers WHERE name=?", (name,))
        exists = c.fetchone() is not None
    finally:
        conn.close()
    return exists


def check_username_exists(username):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        exists = c.fetchone() is not None
    finally:
        conn.close()
    return exists


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


# ---------- 原有客户操作 ----------
@st.cache_data(ttl=60)
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
        add_log(st.session_state.username, "添加客户", name, f"行业:{industry}, 规模:{size}, 阶段:{stage}")
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
        add_log(st.session_state.username, "编辑客户", name, f"ID:{cid}")
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
        conn.commit()
        add_log(st.session_state.username, "删除客户", name, f"ID:{cid}")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ---------- 原有联系人操作 ----------
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
        add_log(st.session_state.username, "添加联系人", f"客户ID:{customer_id}", f"姓名:{name}, 邮箱:{email}")
        return True, "添加成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def delete_contact(contact_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM contacts WHERE id=?", (contact_id,))
        add_log(st.session_state.username, "删除联系人", f"联系人ID:{contact_id}", "")
    except Exception as e:
        st.error(f"删除失败: {e}")
    finally:
        conn.close()


# ---------- 原有交互记录操作 ----------
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
        add_log(st.session_state.username, "添加交互记录", f"客户ID:{customer_id}", f"类型:{type}, 内容:{content[:50]}")
    except Exception as e:
        st.error(f"添加失败: {e}")
    finally:
        conn.close()


# ---------- 原有工单操作 ----------
def get_tickets_by_customer(customer_id):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM tickets WHERE customer_id=? ORDER BY created_at DESC", conn,
                           params=(customer_id,))
    conn.close()
    return df


@st.cache_data(ttl=30)
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
        add_log(st.session_state.username, "创建工单", f"客户ID:{customer_id}", f"标题:{title}")
    except Exception as e:
        st.error(f"创建失败: {e}")
    finally:
        conn.close()


def update_ticket_status(ticket_id, status, completed_at=None):
    conn = get_db_connection()
    try:
        execute_sql(conn, "UPDATE tickets SET status=?, completed_at=? WHERE id=?", (status, completed_at, ticket_id))
    except Exception as e:
        st.error(f"更新失败: {e}")
    finally:
        conn.close()


def delete_ticket(ticket_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM tickets WHERE id=?", (ticket_id,))
        add_log(st.session_state.username, "删除工单", f"工单ID:{ticket_id}", "")
    except Exception as e:
        st.error(f"删除失败: {e}")
    finally:
        conn.close()


# ---------- 原有日志操作 ----------
def get_logs(limit=50):
    conn = get_db_connection()
    df = pd.read_sql_query(f"SELECT * FROM logs ORDER BY created_at DESC LIMIT {limit}", conn)
    conn.close()
    return df


# ---------- 原有客户价值评分 ----------
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


# ---------- 原有AI辅助 ----------
def ai_email_assistant(email_content):
    if HAS_TRANSFORMERS and st.session_state.get('use_real_ai', False):
        try:
            summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
            summary = summarizer(email_content, max_length=50, min_length=20, do_sample=False)[0]['summary_text']
            return f"**摘要**: {summary}\n\n**建议**: 请及时回复客户，关注核心诉求。"
        except Exception as e:
            return f"AI模型运行出错，使用模拟模式：{e}\n\n**摘要**: 客户询问产品功能\n**建议**: 安排销售跟进。"
    else:
        return f"""**📝 邮件摘要**  
客户在邮件中提到了关键需求，建议优先处理。

**💡 回复建议**  
1. 感谢客户的耐心等待，确认收到邮件。  
2. 针对客户提出的问题，提供详细解答。  
3. 主动邀约下一步沟通时间。"""


# ---------- 原有销售漏斗分析 ----------
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
    fig = go.Figure(go.Funnel(
        y=[d['阶段'] for d in funnel_data],
        x=[d['客户数'] for d in funnel_data],
        textinfo="value+percent initial",
        marker={"color": ["#2E86AB", "#4AA3C2", "#6BB8D9", "#A23B72", "#F18F01"]}
    ))
    fig.update_layout(title="销售漏斗分析", height=500)
    return fig


def monthly_trend(df):
    if df.empty:
        return None
    df['created_at'] = pd.to_datetime(df['created_at'])
    df['month'] = df['created_at'].dt.to_period('M').astype(str)
    monthly = df.groupby('month').size().reset_index(name='新增客户数')
    fig = px.line(monthly, x='month', y='新增客户数', title="月度新增客户趋势")
    return fig


def stage_distribution(df):
    if df.empty:
        return None
    counts = df['stage'].value_counts().reset_index()
    counts.columns = ['阶段', '数量']
    fig = px.bar(counts, x='阶段', y='数量', title="客户阶段分布", color='阶段')
    return fig


# ---------- 原有客户旅程可视化 ----------
def customer_journey_view():
    if HAS_JOURNEY_LIB:
        journey_nodes = [
            {
                "id": 1,
                "name": "awareness",
                "label": "认知阶段",
                "color": "#2E86AB",
                "icon": "fa fa-eye",
                "children": [
                    {"id": 2, "name": "website", "label": "访问官网", "color": "#4AA3C2"},
                    {"id": 3, "name": "ad", "label": "广告触达", "color": "#4AA3C2"}
                ]
            },
            {
                "id": 4,
                "name": "consideration",
                "label": "考虑阶段",
                "color": "#A23B72",
                "icon": "fa fa-brain",
                "children": [
                    {"id": 5, "name": "demo", "label": "产品演示", "color": "#6BB8D9"},
                    {"id": 6, "name": "proposal", "label": "方案评估", "color": "#6BB8D9"}
                ]
            },
            {
                "id": 7,
                "name": "decision",
                "label": "决策阶段",
                "color": "#F18F01",
                "icon": "fa fa-check-circle",
                "children": [
                    {"id": 8, "name": "negotiation", "label": "商务谈判", "color": "#F4A261"},
                    {"id": 9, "name": "contract", "label": "签约", "color": "#E76F51"}
                ]
            }
        ]
        clicked = st_customer_journey(journey_nodes, key="journey")
        if clicked:
            st.info(f"当前点击节点: {clicked}")
    else:
        st.info("💡 如需使用交互式客户旅程图，请安装 st-customer-journey 库：`pip install st-customer-journey`")
        steps = ["认知阶段", "考虑阶段", "决策阶段", "成交/流失"]
        cols = st.columns(len(steps))
        for i, step in enumerate(steps):
            with cols[i]:
                st.markdown(f"**{i + 1}. {step}**")
                st.progress(0.3 * (i + 1))


# ==================== 工程项目管理模块 ====================
@st.cache_data(ttl=60)
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
        if filters.get('tracker'):
            query += " AND tracker = ?"
            params.append(filters['tracker'])
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
        add_log(st.session_state.username, "添加工程项目", data['project_name'], f"编号:{data['project_code']}")
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
        add_log(st.session_state.username, "编辑工程项目", data['project_name'], f"ID:{pid}")
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
        add_log(st.session_state.username, "删除工程项目", name, f"ID:{pid}")
    except Exception as e:
        st.error(f"删除失败: {e}")
    finally:
        conn.close()


# ==================== 产品管理模块（包含大类、类别） ====================
@st.cache_data(ttl=60)
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


def add_product(product_code, product_name, specification, unit, list_price, category_major, category_minor):
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO products
                     (product_code, product_name, specification, unit, list_price, category_major, category_minor, created_at, updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                    (product_code, product_name, specification, unit, list_price,
                     category_major, category_minor,
                     datetime.now().isoformat(), datetime.now().isoformat()))
        add_log(st.session_state.username, "添加产品", product_name, f"编号:{product_code}")
        return True, "添加成功"
    except sqlite3.IntegrityError:
        return False, "产品编号已存在"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def update_product(pid, product_code, product_name, specification, unit, list_price, category_major, category_minor):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM products WHERE product_code=? AND id!=?", (product_code, pid))
        if c.fetchone():
            return False, "产品编号已存在"
        execute_sql(conn, """UPDATE products SET
                     product_code=?, product_name=?, specification=?, unit=?, list_price=?,
                     category_major=?, category_minor=?, updated_at=?
                     WHERE id=?""",
                    (product_code, product_name, specification, unit, list_price,
                     category_major, category_minor,
                     datetime.now().isoformat(), pid))
        add_log(st.session_state.username, "编辑产品", product_name, f"ID:{pid}")
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
        add_log(st.session_state.username, "删除产品", name, f"ID:{pid}")
    except Exception as e:
        st.error(f"删除失败: {e}")
    finally:
        conn.close()


# ==================== 报价管理模块（集成产品大类类别） ====================
@st.cache_data(ttl=60)
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
    """获取报价明细，并关联产品表获取大类、类别信息"""
    conn = get_db_connection()
    query = """
        SELECT qi.*, p.category_major, p.category_minor
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
        add_log(st.session_state.username, "创建报价单", data['quotation_no'], f"项目:{data['project_name']}")
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
        add_log(st.session_state.username, "编辑报价单", data['quotation_no'], f"ID:{qid}")
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
        add_log(st.session_state.username, "删除报价单", no, f"ID:{qid}")
    except Exception as e:
        st.error(f"删除失败: {e}")
    finally:
        conn.close()


def add_quotation_item(qid, item):
    conn = get_db_connection()
    try:
        execute_sql(conn, """INSERT INTO quotation_items
                     (quotation_id, seq, product_id, product_name, specification, unit, quantity, discount,
                      list_price, unit_price, amount, usage_area, remarks)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (qid, item['seq'], item.get('product_id'), item['product_name'], item['specification'],
                     item['unit'], item['quantity'], item['discount'], item['list_price'],
                     item['unit_price'], item['amount'], item['usage_area'], item['remarks']))
    except Exception as e:
        st.error(f"添加明细失败: {e}")
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
        st.error(f"更新明细失败: {e}")
    finally:
        conn.close()


def delete_quotation_item(item_id):
    conn = get_db_connection()
    try:
        execute_sql(conn, "DELETE FROM quotation_items WHERE id=?", (item_id,))
    except Exception as e:
        st.error(f"删除明细失败: {e}")
    finally:
        conn.close()


# ==================== 导入导出模块 ====================
def export_table_to_csv(table_name):
    conn = get_db_connection()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    return csv_buffer.getvalue()


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


# ---------- 登录页面 ----------
def login_page():
    st.title("🔐 智云CRM · 企业级客户关系管理系统")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 登录您的账户")
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="请输入用户名", key="login_username")
            password = st.text_input("密码", type="password", placeholder="请输入密码", key="login_password")
            submitted = st.form_submit_button("登录", use_container_width=True)
            if submitted:
                user = authenticate_user(username, password)
                if user:
                    user_id, user_name, role = user
                    st.session_state.logged_in = True
                    st.session_state.user_id = user_id
                    st.session_state.username = user_name
                    st.session_state.role = role
                    st.rerun()
                else:
                    st.error("用户名或密码错误")
        with st.expander("还没有账号？注册新用户"):
            with st.form("register_form"):
                new_user = st.text_input("用户名", key="reg_username")
                new_pass = st.text_input("密码", type="password", key="reg_password")
                confirm_pass = st.text_input("确认密码", type="password", key="reg_confirm")
                reg_submit = st.form_submit_button("注册")
                if reg_submit:
                    if not new_user or not new_pass:
                        st.error("用户名和密码不能为空")
                    elif new_pass != confirm_pass:
                        st.error("两次输入的密码不一致")
                    else:
                        ok, msg = register_user(new_user, new_pass, role='user')
                        if ok:
                            st.success("注册成功，请登录")
                        else:
                            st.error(msg)


# ---------- 客户360°视图 ----------
def customer_360_view(customer_id):
    customer = get_customer_by_id(customer_id)
    if customer is None:
        st.error("客户不存在")
        return
    contacts = get_contacts(customer_id)
    interactions = get_interactions(customer_id)
    tickets = get_tickets_by_customer(customer_id)
    score = calculate_customer_score(customer_id)
    is_admin = st.session_state.role == 'admin'

    st.subheader(f"客户全景视图 · {customer['name']}")
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("客户价值评分", f"{score}/100")
    with col2:
        revenue_val = customer['estimated_revenue'] if customer['estimated_revenue'] is not None else 0
        st.metric("预计年收入", f"¥{revenue_val:,.0f}")
    with col3:
        st.metric("联系人数量", len(contacts))
    with col4:
        st.metric("工单数量", len(tickets))

    tab1, tab2, tab3, tab4 = st.tabs(["📋 基本信息", "👥 联系人", "📞 交互历史", "🔧 服务工单"])
    with tab1:
        col_a, col_b = st.columns(2)
        with col_a:
            st.write(f"**公司名称**：{customer['name']}")
            st.write(f"**行业**：{customer['industry']}")
            st.write(f"**规模**：{customer['size']}")
        with col_b:
            st.write(f"**当前阶段**：{customer['stage']}")
            st.write(f"**客户经理**：{customer['owner'] or '未分配'}")
            st.write(f"**创建时间**：{customer['created_at']}")
        if is_admin:
            with st.expander("✏️ 编辑客户信息"):
                with st.form("edit_customer_form"):
                    new_name = st.text_input("公司名称", value=customer['name'], key="edit_cust_name")
                    new_industry = st.text_input("行业", value=customer['industry'] or "", key="edit_cust_industry")
                    size_options = ["小型", "中型", "大型"]
                    size_default = size_options.index(customer['size']) if customer['size'] in size_options else 0
                    new_size = st.selectbox("规模", size_options, index=size_default, key="edit_cust_size")
                    stage_options = ["潜在", "意向", "谈判", "成交", "流失"]
                    try:
                        stage_index = stage_options.index(customer['stage'])
                    except ValueError:
                        stage_index = 0
                    new_stage = st.selectbox("销售阶段", stage_options, index=stage_index, key="edit_cust_stage")
                    new_revenue = st.number_input("预计年收入(元)", value=float(customer['estimated_revenue']),
                                                  key="edit_cust_revenue")
                    new_owner = st.text_input("客户经理", value=customer['owner'] or "", key="edit_cust_owner")
                    if st.form_submit_button("保存"):
                        success, msg = update_customer(customer_id, new_name, new_industry, new_size, new_stage,
                                                       new_revenue, new_owner)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
    with tab2:
        if not contacts.empty:
            for _, row in contacts.iterrows():
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.write(f"**{row['name']}** · {row['title']} | {row['phone']} | {row['email']}")
                with col_b:
                    if is_admin and st.button("删除", key=f"del_contact_{row['id']}"):
                        delete_contact(row['id'])
                        st.rerun()
        else:
            st.info("暂无联系人")
        if is_admin:
            with st.form("add_contact_form"):
                st.write("➕ 添加新联系人")
                c_name = st.text_input("姓名", key="add_contact_name")
                c_title = st.text_input("职位", key="add_contact_title")
                c_phone = st.text_input("电话", key="add_contact_phone")
                c_email = st.text_input("邮箱", key="add_contact_email")
                if st.form_submit_button("添加"):
                    if c_name:
                        success, msg = add_contact(customer_id, c_name, c_title, c_phone, c_email)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
    with tab3:
        if not interactions.empty:
            for _, row in interactions.iterrows():
                st.markdown(f"**{row['type']}** · {row['happened_at']}")
                st.write(row['content'])
                st.divider()
        else:
            st.info("暂无交互记录")
        with st.form("add_interaction_form"):
            i_type = st.selectbox("类型", ["电话", "邮件", "会议"], key="interaction_type")
            i_content = st.text_area("内容", key="interaction_content")
            i_date = st.date_input("日期", datetime.now(), key="interaction_date")
            if st.form_submit_button("添加"):
                if i_content:
                    happened_at = datetime.combine(i_date, datetime.min.time())
                    add_interaction(customer_id, i_type, i_content, happened_at)
                    st.success("记录已添加")
                    st.rerun()
    with tab4:
        if not tickets.empty:
            for _, row in tickets.iterrows():
                with st.expander(f"#{row['id']} · {row['title']} ({row['status']})"):
                    st.write(f"**优先级**: {row['priority']}  |  **类型**: {row['ticket_type']}")
                    st.write(f"**描述**: {row['description']}")
                    st.write(f"**创建时间**: {row['created_at']}")
                    if row['status'] != "已完成" and is_admin:
                        if st.button("标记为已完成", key=f"complete_{row['id']}"):
                            update_ticket_status(row['id'], "已完成", datetime.now().isoformat())
                            st.rerun()
        else:
            st.info("暂无工单")
        if is_admin:
            with st.form("add_ticket_form"):
                st.write("➕ 创建新工单")
                title = st.text_input("工单标题", key="ticket_title")
                desc = st.text_area("描述", key="ticket_desc")
                priority = st.selectbox("优先级", ["低", "中", "高", "紧急"], key="ticket_priority")
                ticket_type = st.selectbox("类型", ["技术支持", "售后服务", "投诉建议", "其他"], key="ticket_type")
                assigned_to = st.text_input("负责人", key="ticket_assigned")
                if st.form_submit_button("创建"):
                    if title:
                        add_ticket(customer_id, title, desc, priority, ticket_type, assigned_to)
                        st.success("工单已创建")
                        st.rerun()


# ---------- 主页面 ----------
def crm_page():
    with st.sidebar:
        st.markdown(f"### 👋 欢迎，{st.session_state.username} ({'管理员' if st.session_state.role=='admin' else '普通用户'})")
        st.markdown("---")
        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.logged_in = False
            for k in ['user_id', 'username', 'role']:
                st.session_state.pop(k, None)
            st.rerun()
        st.markdown("---")

        if st.session_state.role == 'admin':
            menu_options = [
                "📊 仪表盘", "👥 客户管理", "🔧 工单管理", "📈 销售分析",
                "🗺️ 客户旅程", "🏗️ 工程项目", "💰 项目报价", "📦 产品管理", "📁 数据管理", "🤖 AI助手", "📜 操作日志"
            ]
        else:
            menu_options = [
                "📊 仪表盘", "👥 客户管理", "🔧 工单管理", "🏗️ 工程项目", "💰 项目报价", "🤖 AI助手"
            ]
        menu = st.radio("导航", menu_options, index=0)

    # 筛选状态（客户管理用）
    if 'search_name' not in st.session_state:
        st.session_state.search_name = ""
    if 'stage_filter' not in st.session_state:
        st.session_state.stage_filter = "全部"
    if 'page_num' not in st.session_state:
        st.session_state.page_num = 1

    is_admin = st.session_state.role == 'admin'

    # ---------- 仪表盘 ----------
    if menu == "📊 仪表盘":
        st.header("📊 数据仪表盘")
        st.markdown("---")
        df_all = get_customers()
        if df_all.empty:
            st.info("暂无客户数据")
        else:
            col1, col2 = st.columns(2)
            with col1:
                fig1 = stage_distribution(df_all)
                if fig1:
                    st.plotly_chart(fig1, use_container_width=True)
            with col2:
                fig2 = monthly_trend(df_all)
                if fig2:
                    st.plotly_chart(fig2, use_container_width=True)
            col3, col4 = st.columns(2)
            with col3:
                funnel_fig = sales_funnel_analysis(df_all)
                if funnel_fig:
                    st.plotly_chart(funnel_fig, use_container_width=True)
            with col4:
                st.subheader("最近活跃客户")
                recent = df_all.sort_values('created_at', ascending=False).head(5)
                st.dataframe(recent[['name', 'stage', 'created_at']], use_container_width=True)
                total_pipeline = df_all[df_all['stage'] != '流失']['estimated_revenue'].sum()
                st.metric("商机池总额", f"¥{total_pipeline:,.0f}")

    # ---------- 客户管理 ----------
    elif menu == "👥 客户管理":
        st.header("👥 客户管理")
        st.markdown("---")
        col_search, col_filter = st.columns([2, 1])
        with col_search:
            search_name = st.text_input("🔍 搜索客户名称", value=st.session_state.search_name,
                                        placeholder="输入客户名称...", key="cust_search_name")
        with col_filter:
            stages = ["全部"] + ["潜在", "意向", "谈判", "成交", "流失"]
            stage_filter = st.selectbox("📌 按阶段筛选", stages, index=stages.index(st.session_state.stage_filter),
                                        key="cust_stage_filter")
        if search_name != st.session_state.search_name or stage_filter != st.session_state.stage_filter:
            st.session_state.search_name = search_name
            st.session_state.stage_filter = stage_filter
            st.session_state.page_num = 1

        filters = {"search_name": st.session_state.search_name}
        if st.session_state.stage_filter != "全部":
            filters["stage"] = st.session_state.stage_filter
        df_customers = get_customers(filters)

        total_rows = len(df_customers)
        total_pages = (total_rows - 1) // PAGE_SIZE + 1 if total_rows > 0 else 1
        start = (st.session_state.page_num - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        df_page = df_customers.iloc[start:end]

        if df_page.empty:
            st.info("没有找到客户")
        else:
            for _, row in df_page.iterrows():
                with st.expander(f"🏢 {row['name']} · {row['stage']}"):
                    if st.button("🔍 查看360°视图", key=f"view360_{row['id']}"):
                        st.session_state.viewing_customer = row['id']
                        st.rerun()
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(
                            f"**行业**: {row['industry']}  |  **规模**: {row['size']}  |  **负责人**: {row['owner'] or '未分配'}")
                        st.write(f"**预计年收入**: ¥{row['estimated_revenue']:,.0f}")
                    with col2:
                        if is_admin and st.button("删除", key=f"del_{row['id']}"):
                            delete_customer(row['id'])
                            st.rerun()
            if total_pages > 1:
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    if st.button("上一页") and st.session_state.page_num > 1:
                        st.session_state.page_num -= 1
                        st.rerun()
                with col2:
                    st.write(f"第 {st.session_state.page_num} / {total_pages} 页")
                with col3:
                    if st.button("下一页") and st.session_state.page_num < total_pages:
                        st.session_state.page_num += 1
                        st.rerun()
            if st.button("📎 导出当前筛选客户为 CSV"):
                csv = df_customers.to_csv(index=False).encode('utf-8')
                st.download_button("点击下载", csv, f"customers_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

        if is_admin:
            with st.sidebar.expander("➕ 快速添加客户", expanded=False):
                with st.form("quick_add"):
                    name = st.text_input("公司名称*", key="quick_cust_name")
                    industry = st.text_input("行业", key="quick_cust_industry")
                    size = st.selectbox("规模", ["小型", "中型", "大型"], key="quick_cust_size")
                    stage = st.selectbox("阶段", ["潜在", "意向", "谈判", "成交", "流失"], key="quick_cust_stage")
                    revenue = st.number_input("预计年收入(元)", value=0, key="quick_cust_revenue")
                    owner = st.text_input("客户经理", key="quick_cust_owner")
                    if st.form_submit_button("添加", use_container_width=True):
                        if name:
                            success, msg = add_customer(name, industry, size, stage, revenue, owner)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

    # ---------- 工单管理 ----------
    elif menu == "🔧 工单管理":
        st.header("🔧 工单管理")
        st.markdown("---")
        status_filter = st.selectbox("工单状态", ["全部", "待分配", "处理中", "待验收", "已完成", "已关闭"],
                                     key="ticket_status_filter")
        tickets_df = get_all_tickets(status_filter if status_filter != "全部" else None)
        if tickets_df.empty:
            st.info("暂无工单")
        else:
            statuses = ["待分配", "处理中", "待验收", "已完成", "已关闭"]
            cols = st.columns(len(statuses))
            for idx, status in enumerate(statuses):
                with cols[idx]:
                    st.subheader(status)
                    status_tickets = tickets_df[tickets_df['status'] == status]
                    for _, t in status_tickets.iterrows():
                        with st.container():
                            st.markdown(f"**#{t['id']}** {t['title']}")
                            st.caption(f"客户: {t['customer_name']} | 优先级: {t['priority']}")
                            if status != "已完成" and is_admin:
                                if st.button("完成", key=f"complete_{t['id']}", use_container_width=True):
                                    update_ticket_status(t['id'], "已完成", datetime.now().isoformat())
                                    st.rerun()
                            st.divider()

    # ---------- 销售分析 ----------
    elif menu == "📈 销售分析":
        st.header("📈 销售漏斗与预测")
        st.markdown("---")
        df_all = get_customers()
        if df_all.empty:
            st.info("暂无数据")
        else:
            funnel_fig = sales_funnel_analysis(df_all)
            if funnel_fig:
                st.plotly_chart(funnel_fig, use_container_width=True)
            col1, col2 = st.columns(2)
            with col1:
                stage_counts = df_all['stage'].value_counts().reset_index()
                stage_counts.columns = ['阶段', '数量']
                st.bar_chart(stage_counts.set_index('阶段'))
            with col2:
                total_pipeline = df_all[df_all['stage'] != '流失']['estimated_revenue'].sum()
                st.metric("当前商机池总额", f"¥{total_pipeline:,.0f}")
                win_rate = len(df_all[df_all['stage'] == '成交']) / len(df_all) * 100 if len(df_all) > 0 else 0
                st.metric("赢单率", f"{win_rate:.1f}%")

    # ---------- 客户旅程 ----------
    elif menu == "🗺️ 客户旅程":
        st.header("🗺️ 客户旅程可视化")
        st.markdown("---")
        st.info("客户旅程帮助您理解客户从认知到成交的完整过程")
        customer_journey_view()
        df_all = get_customers()
        if not df_all.empty:
            stage_order = ["潜在", "意向", "谈判", "成交", "流失"]
            stage_count = df_all['stage'].value_counts()
            st.subheader("当前客户分布")
            for stage in stage_order:
                count = stage_count.get(stage, 0)
                st.progress(min(1.0, count / max(stage_count.max(), 1)), text=f"{stage}: {count}家客户")

    # ---------- 工程项目管理 ----------
    elif menu == "🏗️ 工程项目":
        st.header("🏗️ 工程项目管理")
        st.markdown("---")
        tab1, tab2 = st.tabs(["📋 项目列表", "➕ 新建项目"])
        with tab1:
            col_search1, col_search2 = st.columns(2)
            with col_search1:
                search_code = st.text_input("项目编号", placeholder="输入项目编号", key="proj_search_code")
            with col_search2:
                search_name = st.text_input("项目名称", placeholder="输入项目名称", key="proj_search_name")
            filters = {}
            if search_code:
                filters['search_code'] = search_code
            if search_name:
                filters['search_name'] = search_name
            projects_df = get_all_projects(filters)
            if projects_df.empty:
                st.info("暂无工程项目")
            else:
                project_page = st.number_input("页码", min_value=1,
                                               max_value=max(1, (len(projects_df) - 1) // PAGE_SIZE + 1),
                                               value=1, step=1, key="proj_page")
                start = (project_page - 1) * PAGE_SIZE
                end = start + PAGE_SIZE
                df_page = projects_df.iloc[start:end]
                for _, row in df_page.iterrows():
                    with st.expander(f"🏗️ {row['project_code']} · {row['project_name']}"):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**地址**: {row['address']}")
                            st.write(f"**跟踪人**: {row['tracker']} | **城市**: {row['city']} | **使用区域**: {row['usage_area']}")
                            st.write(f"**进度**: {row['progress']} | **最近跟进**: {row['last_followup']}")
                            st.write(f"**预计金额**: ¥{row['estimated_amount']:,.0f} 万")
                            st.write(f"**备注**: {row['remarks']}")
                        with col2:
                            if is_admin:
                                if st.button("编辑", key=f"edit_proj_{row['id']}"):
                                    st.session_state.editing_project = row['id']
                                    st.rerun()
                                if st.button("删除", key=f"del_proj_{row['id']}"):
                                    delete_project(row['id'])
                                    st.rerun()
                total_pages = (len(projects_df) - 1) // PAGE_SIZE + 1
                if total_pages > 1:
                    st.write(f"第 {project_page} / {total_pages} 页")
        if is_admin:
            with tab2:
                with st.form("add_project_form"):
                    st.markdown("### 基本信息")
                    col1, col2 = st.columns(2)
                    with col1:
                        proj_code = st.text_input("项目编号 *", key="proj_code_new")
                        proj_name = st.text_input("项目名称 *", key="proj_name_new")
                        address = st.text_input("项目地址", key="proj_address")
                        tracker = st.text_input("项目跟踪人", key="proj_tracker")
                        city = st.text_input("区域/城市", key="proj_city")
                        usage_area = st.text_input("使用区域/部位", key="proj_usage")
                    with col2:
                        progress = st.text_input("项目进度明细", key="proj_progress")
                        last_followup = st.date_input("最近跟进时间", value=datetime.now(), key="proj_followup")
                        products = st.text_input("产品", key="proj_products")
                        equipment_list = st.text_input("设备量单", key="proj_equipment")
                        estimated_amount = st.number_input("预计金额(万)", value=0.0, key="proj_amount")

                    st.markdown("### 建设单位")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        const_unit = st.text_input("单位", key="const_unit")
                        const_dept = st.text_input("部门", key="const_dept")
                    with col_b:
                        const_contact = st.text_input("联系人", key="const_contact")
                        const_phone = st.text_input("电话", key="const_phone")

                    st.markdown("### 设计院")
                    col_c, col_d = st.columns(2)
                    with col_c:
                        design_unit = st.text_input("单位", key="design_unit")
                        design_dept = st.text_input("部门", key="design_dept")
                    with col_d:
                        design_contact = st.text_input("联系人", key="design_contact")
                        design_phone = st.text_input("电话", key="design_phone")

                    st.markdown("### 总包方")
                    col_e, col_f = st.columns(2)
                    with col_e:
                        general_unit = st.text_input("单位", key="general_unit")
                        general_dept = st.text_input("部门", key="general_dept")
                    with col_f:
                        general_contact = st.text_input("联系人", key="general_contact")
                        general_phone = st.text_input("电话", key="general_phone")

                    remarks = st.text_area("备注", key="proj_remarks")

                    if st.form_submit_button("创建项目"):
                        if not proj_code or not proj_name:
                            st.error("项目编号和项目名称不能为空")
                        else:
                            data = {
                                'project_code': proj_code,
                                'project_name': proj_name,
                                'address': address,
                                'tracker': tracker,
                                'city': city,
                                'usage_area': usage_area,
                                'progress': progress,
                                'last_followup': last_followup.isoformat(),
                                'products': products,
                                'equipment_list': equipment_list,
                                'construction_unit': const_unit,
                                'construction_dept': const_dept,
                                'construction_contact': const_contact,
                                'construction_phone': const_phone,
                                'design_unit': design_unit,
                                'design_dept': design_dept,
                                'design_contact': design_contact,
                                'design_phone': design_phone,
                                'general_unit': general_unit,
                                'general_dept': general_dept,
                                'general_contact': general_contact,
                                'general_phone': general_phone,
                                'estimated_amount': estimated_amount,
                                'remarks': remarks
                            }
                            success, msg = add_project(data)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

        if 'editing_project' in st.session_state and is_admin:
            pid = st.session_state.editing_project
            proj = get_project_by_id(pid)
            if proj is not None:
                with st.form("edit_project_form"):
                    st.markdown(f"### 编辑项目：{proj['project_code']} · {proj['project_name']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        e_proj_code = st.text_input("项目编号 *", value=proj['project_code'], key="edit_proj_code")
                        e_proj_name = st.text_input("项目名称 *", value=proj['project_name'], key="edit_proj_name")
                        e_address = st.text_input("项目地址", value=proj['address'] or "", key="edit_address")
                        e_tracker = st.text_input("项目跟踪人", value=proj['tracker'] or "", key="edit_tracker")
                        e_city = st.text_input("区域/城市", value=proj['city'] or "", key="edit_city")
                        e_usage_area = st.text_input("使用区域/部位", value=proj['usage_area'] or "", key="edit_usage")
                    with col2:
                        e_progress = st.text_input("项目进度明细", value=proj['progress'] or "", key="edit_progress")
                        last_followup_val = proj['last_followup']
                        if last_followup_val:
                            try:
                                last_followup_date = datetime.fromisoformat(last_followup_val).date()
                            except:
                                last_followup_date = datetime.now().date()
                        else:
                            last_followup_date = datetime.now().date()
                        e_last_followup = st.date_input("最近跟进时间", value=last_followup_date, key="edit_followup")
                        e_products = st.text_input("产品", value=proj['products'] or "", key="edit_products")
                        e_equipment_list = st.text_input("设备量单", value=proj['equipment_list'] or "",
                                                         key="edit_equipment")
                        e_estimated_amount = st.number_input("预计金额(万)", value=proj['estimated_amount'] or 0.0,
                                                             key="edit_amount")

                    st.markdown("### 建设单位")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        e_const_unit = st.text_input("单位", value=proj['construction_unit'] or "", key="edit_const_unit")
                        e_const_dept = st.text_input("部门", value=proj['construction_dept'] or "", key="edit_const_dept")
                    with col_b:
                        e_const_contact = st.text_input("联系人", value=proj['construction_contact'] or "",
                                                        key="edit_const_contact")
                        e_const_phone = st.text_input("电话", value=proj['construction_phone'] or "", key="edit_const_phone")

                    st.markdown("### 设计院")
                    col_c, col_d = st.columns(2)
                    with col_c:
                        e_design_unit = st.text_input("单位", value=proj['design_unit'] or "", key="edit_design_unit")
                        e_design_dept = st.text_input("部门", value=proj['design_dept'] or "", key="edit_design_dept")
                    with col_d:
                        e_design_contact = st.text_input("联系人", value=proj['design_contact'] or "",
                                                         key="edit_design_contact")
                        e_design_phone = st.text_input("电话", value=proj['design_phone'] or "", key="edit_design_phone")

                    st.markdown("### 总包方")
                    col_e, col_f = st.columns(2)
                    with col_e:
                        e_general_unit = st.text_input("单位", value=proj['general_unit'] or "", key="edit_general_unit")
                        e_general_dept = st.text_input("部门", value=proj['general_dept'] or "", key="edit_general_dept")
                    with col_f:
                        e_general_contact = st.text_input("联系人", value=proj['general_contact'] or "",
                                                          key="edit_general_contact")
                        e_general_phone = st.text_input("电话", value=proj['general_phone'] or "", key="edit_general_phone")

                    e_remarks = st.text_area("备注", value=proj['remarks'] or "", key="edit_remarks")

                    if st.form_submit_button("保存修改"):
                        data = {
                            'project_code': e_proj_code,
                            'project_name': e_proj_name,
                            'address': e_address,
                            'tracker': e_tracker,
                            'city': e_city,
                            'usage_area': e_usage_area,
                            'progress': e_progress,
                            'last_followup': e_last_followup.isoformat(),
                            'products': e_products,
                            'equipment_list': e_equipment_list,
                            'construction_unit': e_const_unit,
                            'construction_dept': e_const_dept,
                            'construction_contact': e_const_contact,
                            'construction_phone': e_const_phone,
                            'design_unit': e_design_unit,
                            'design_dept': e_design_dept,
                            'design_contact': e_design_contact,
                            'design_phone': e_design_phone,
                            'general_unit': e_general_unit,
                            'general_dept': e_general_dept,
                            'general_contact': e_general_contact,
                            'general_phone': e_general_phone,
                            'estimated_amount': e_estimated_amount,
                            'remarks': e_remarks
                        }
                        success, msg = update_project(pid, data)
                        if success:
                            st.success(msg)
                            del st.session_state.editing_project
                            st.rerun()
                        else:
                            st.error(msg)
                if st.button("取消编辑"):
                    del st.session_state.editing_project
                    st.rerun()

    # ---------- 项目报价管理（集成产品选择，展示大类类别） ----------
    elif menu == "💰 项目报价":
        st.header("💰 项目报价管理")
        st.markdown("---")
        tab1, tab2 = st.tabs(["📋 报价列表", "➕ 新建报价"])
        with tab1:
            col_search1, col_search2 = st.columns(2)
            with col_search1:
                search_no = st.text_input("报价单号", placeholder="输入报价单号", key="quote_search_no")
            with col_search2:
                search_proj = st.text_input("项目名称", placeholder="输入项目名称", key="quote_search_proj")
            filters = {}
            if search_no:
                filters['search_no'] = search_no
            if search_proj:
                filters['project_name'] = search_proj
            quotations_df = get_all_quotations(filters)
            if quotations_df.empty:
                st.info("暂无报价单")
            else:
                for _, row in quotations_df.iterrows():
                    with st.expander(f"💰 {row['quotation_no']} · {row['project_name']} (报价日期: {row['quotation_date']})"):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**客户名称**: {row['customer_name']}")
                            st.write(f"**联系人**: {row['contact_person']} | **电话**: {row['contact_phone']}")
                        with col2:
                            if st.button("查看明细", key=f"view_quote_{row['id']}"):
                                st.session_state.viewing_quotation = row['id']
                                st.rerun()
                            if is_admin and st.button("删除报价单", key=f"del_quote_{row['id']}"):
                                delete_quotation(row['id'])
                                st.rerun()
        if is_admin:
            with tab2:
                with st.form("add_quotation_form"):
                    st.markdown("### 报价单基本信息")
                    col1, col2 = st.columns(2)
                    with col1:
                        quote_no = st.text_input("报价单号 *", key="quote_no_new")
                        projects_df = get_all_projects()
                        project_names = [""] + list(projects_df['project_name'].unique()) if not projects_df.empty else [""]
                        project_name = st.selectbox("项目名称", project_names, key="quote_project_name")
                    with col2:
                        customer_name = st.text_input("客户名称", key="quote_customer_name")
                        contact_person = st.text_input("联系人", key="quote_contact_person")
                        contact_phone = st.text_input("电话", key="quote_contact_phone")
                        quote_date = st.date_input("报价日期", value=datetime.now(), key="quote_date")
                    if st.form_submit_button("创建报价单"):
                        if not quote_no:
                            st.error("报价单号不能为空")
                        else:
                            data = {
                                'quotation_no': quote_no,
                                'project_name': project_name,
                                'customer_name': customer_name,
                                'contact_person': contact_person,
                                'contact_phone': contact_phone,
                                'quotation_date': quote_date.isoformat()
                            }
                            success, result = add_quotation(data)
                            if success:
                                st.success(f"报价单创建成功，ID: {result}")
                                st.session_state.viewing_quotation = result
                                st.rerun()
                            else:
                                st.error(result)

        if 'viewing_quotation' in st.session_state:
            qid = st.session_state.viewing_quotation
            quote = get_quotation_by_id(qid)
            if quote is None:
                del st.session_state.viewing_quotation
                st.rerun()
            st.subheader(f"报价单明细：{quote['quotation_no']} - {quote['project_name']}")
            st.write(
                f"客户：{quote['customer_name']} | 联系人：{quote['contact_person']} | 电话：{quote['contact_phone']} | 报价日期：{quote['quotation_date']}")
            st.markdown("---")

            items_df = get_quotation_items(qid)
            if not items_df.empty:
                # 显示明细表格，增加产品大类、类别列
                display_cols = ['seq', 'product_name', 'specification', 'unit', 'quantity', 'discount',
                                'list_price', 'unit_price', 'amount', 'usage_area', 'remarks',
                                'category_major', 'category_minor']
                # 确保列存在
                available_cols = [col for col in display_cols if col in items_df.columns]
                st.dataframe(items_df[available_cols], use_container_width=True)
                total_amount = items_df['amount'].sum()
                st.metric("报价总额", f"¥{total_amount:,.2f}")
            else:
                st.info("暂无明细，请添加")

            # 添加明细（集成产品选择）
            with st.expander("➕ 添加报价明细"):
                if is_admin:
                    products_df = get_all_products()
                    if products_df.empty:
                        st.warning("暂无产品数据，请先在产品管理中录入产品")
                        product_options = [("", "")]
                    else:
                        # 在下拉选项中显示产品名称、大类、类别
                        product_options = [("", "请选择产品")] + [(row['id'], f"{row['product_name']} [{row['category_major']} - {row['category_minor']}]" if row['category_major'] else row['product_name']) for _, row in products_df.iterrows()]

                    col1, col2 = st.columns(2)
                    with col1:
                        selected_product = st.selectbox("选择产品", product_options, format_func=lambda x: x[1] if x[0] else x[1], key="selected_product")
                        if selected_product[0]:
                            product_id = selected_product[0]
                            product_info = products_df[products_df['id'] == product_id].iloc[0]
                            product_name = product_info['product_name']
                            specification = product_info['specification'] or ""
                            unit = product_info['unit'] or ""
                            list_price = product_info['list_price']
                        else:
                            product_id = None
                            product_name = ""
                            specification = ""
                            unit = ""
                            list_price = 0.0

                        seq = st.number_input("序号", min_value=1, value=1, step=1, key="item_seq")
                        quantity = st.number_input("数量", min_value=0.0, value=1.0, step=0.1, key="item_qty")
                        discount = st.number_input("下浮点数 (%)", min_value=0.0, value=0.0, step=0.1, key="item_discount")
                    with col2:
                        usage_area = st.text_input("使用区域", key="item_usage")
                        remarks = st.text_input("备注", key="item_remarks")

                    if not selected_product[0]:
                        product_name = st.text_input("产品名称 *", key="item_product")
                        specification = st.text_input("规格", key="item_spec")
                        unit = st.text_input("单位", key="item_unit")
                        list_price = st.number_input("面价", min_value=0.0, value=0.0, step=0.1, key="item_list")

                    unit_price = list_price * (100 - discount) / 100
                    amount = quantity * unit_price
                    st.write(f"**单价**: ¥{unit_price:.2f} | **金额**: ¥{amount:.2f}")

                    if st.button("添加明细", key="add_item_btn"):
                        if not product_name:
                            st.error("产品名称不能为空")
                        else:
                            item = {
                                'seq': seq,
                                'product_id': product_id,
                                'product_name': product_name,
                                'specification': specification,
                                'unit': unit,
                                'quantity': quantity,
                                'discount': discount,
                                'list_price': list_price,
                                'unit_price': unit_price,
                                'amount': amount,
                                'usage_area': usage_area,
                                'remarks': remarks
                            }
                            add_quotation_item(qid, item)
                            st.success("明细已添加")
                            st.rerun()
                else:
                    st.info("您没有权限添加报价明细，请联系管理员。")

            if not items_df.empty and is_admin:
                st.markdown("### 管理明细")
                for idx, row in items_df.iterrows():
                    with st.expander(f"序号 {row['seq']}: {row['product_name']}"):
                        products_df = get_all_products()
                        if products_df.empty:
                            product_options_edit = [("", "")]
                        else:
                            product_options_edit = [("", "请选择产品")] + [(row['product_id'], f"{row['product_name']} [{row['category_major']} - {row['category_minor']}]" if row['category_major'] else row['product_name']) for _, row in products_df.iterrows()] if row['product_id'] else [("", "请选择产品")]

                        col1, col2 = st.columns(2)
                        with col1:
                            selected_product_edit = st.selectbox("选择产品", product_options_edit, index=0, format_func=lambda x: x[1] if x[0] else x[1], key=f"edit_product_{row['id']}")
                            if selected_product_edit[0]:
                                product_id_edit = selected_product_edit[0]
                                product_info_edit = products_df[products_df['id'] == product_id_edit].iloc[0]
                                e_product_name = product_info_edit['product_name']
                                e_spec = product_info_edit['specification'] or ""
                                e_unit = product_info_edit['unit'] or ""
                                e_list = product_info_edit['list_price']
                            else:
                                product_id_edit = row['product_id']
                                e_product_name = row['product_name']
                                e_spec = row['specification'] or ""
                                e_unit = row['unit'] or ""
                                e_list = row['list_price']

                            e_seq = st.number_input("序号", value=row['seq'], key=f"seq_{row['id']}")
                            e_qty = st.number_input("数量", value=row['quantity'], key=f"qty_{row['id']}")
                            e_discount = st.number_input("下浮点数 (%)", value=row['discount'], key=f"disc_{row['id']}")
                        with col2:
                            e_usage = st.text_input("使用区域", value=row['usage_area'] or "", key=f"usage_{row['id']}")
                            e_remarks = st.text_input("备注", value=row['remarks'] or "", key=f"rem_{row['id']}")

                        if not selected_product_edit[0]:
                            e_product_name = st.text_input("产品名称", value=e_product_name, key=f"prod_{row['id']}")
                            e_spec = st.text_input("规格", value=e_spec, key=f"spec_{row['id']}")
                            e_unit = st.text_input("单位", value=e_unit, key=f"unit_{row['id']}")
                            e_list = st.number_input("面价", value=e_list, key=f"list_{row['id']}")

                        new_unit_price = e_list * (100 - e_discount) / 100
                        new_amount = e_qty * new_unit_price
                        st.write(f"**单价**: ¥{new_unit_price:.2f} | **金额**: ¥{new_amount:.2f}")

                        col_save, col_del = st.columns(2)
                        with col_save:
                            if st.button("保存修改", key=f"save_item_{row['id']}"):
                                item_data = {
                                    'seq': e_seq,
                                    'product_id': product_id_edit,
                                    'product_name': e_product_name,
                                    'specification': e_spec,
                                    'unit': e_unit,
                                    'quantity': e_qty,
                                    'discount': e_discount,
                                    'list_price': e_list,
                                    'unit_price': new_unit_price,
                                    'amount': new_amount,
                                    'usage_area': e_usage,
                                    'remarks': e_remarks
                                }
                                update_quotation_item(row['id'], item_data)
                                st.success("更新成功")
                                st.rerun()
                        with col_del:
                            if st.button("删除明细", key=f"del_item_{row['id']}"):
                                delete_quotation_item(row['id'])
                                st.success("删除成功")
                                st.rerun()
            if st.button("返回报价列表"):
                del st.session_state.viewing_quotation
                st.rerun()

    # ---------- 产品管理（仅管理员） ----------
    elif menu == "📦 产品管理" and is_admin:
        st.header("📦 产品管理")
        st.markdown("---")
        tab1, tab2 = st.tabs(["📋 产品列表", "➕ 新增产品"])
        with tab1:
            products_df = get_all_products()
            if products_df.empty:
                st.info("暂无产品数据")
            else:
                st.dataframe(products_df[['product_code', 'product_name', 'specification', 'unit', 'list_price', 'category_major', 'category_minor']],
                             use_container_width=True)
                for _, row in products_df.iterrows():
                    with st.expander(f"✏️ 编辑 {row['product_code']} - {row['product_name']}"):
                        with st.form(f"edit_product_{row['id']}"):
                            new_code = st.text_input("产品编号", value=row['product_code'], key=f"code_{row['id']}")
                            new_name = st.text_input("产品名称", value=row['product_name'], key=f"name_{row['id']}")
                            new_spec = st.text_input("规格", value=row['specification'] or "", key=f"spec_{row['id']}")
                            new_unit = st.text_input("单位", value=row['unit'] or "", key=f"unit_{row['id']}")
                            new_price = st.number_input("面价", value=row['list_price'], key=f"price_{row['id']}")
                            new_major = st.text_input("产品大类", value=row['category_major'] or "", key=f"major_{row['id']}")
                            new_minor = st.text_input("产品类别", value=row['category_minor'] or "", key=f"minor_{row['id']}")
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.form_submit_button("保存"):
                                    success, msg = update_product(row['id'], new_code, new_name, new_spec, new_unit, new_price, new_major, new_minor)
                                    if success:
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                            with col2:
                                if st.form_submit_button("删除"):
                                    delete_product(row['id'])
                                    st.success("删除成功")
                                    st.rerun()
        with tab2:
            with st.form("add_product_form"):
                product_code = st.text_input("产品编号 *")
                product_name = st.text_input("产品名称 *")
                specification = st.text_input("规格")
                unit = st.text_input("单位")
                list_price = st.number_input("面价", min_value=0.0, value=0.0)
                category_major = st.text_input("产品大类")
                category_minor = st.text_input("产品类别")
                if st.form_submit_button("添加产品"):
                    if not product_code or not product_name:
                        st.error("产品编号和产品名称不能为空")
                    else:
                        success, msg = add_product(product_code, product_name, specification, unit, list_price, category_major, category_minor)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

    # ---------- 数据管理（仅管理员） ----------
    elif menu == "📁 数据管理" and is_admin:
        st.header("📁 数据导入导出")
        st.markdown("---")

        tables = {
            "customers": "客户表",
            "contacts": "联系人表",
            "interactions": "交互记录表",
            "tickets": "工单表",
            "projects": "工程项目表",
            "quotations": "报价主表",
            "quotation_items": "报价明细表",
            "products": "产品表",
            "logs": "操作日志表"
        }

        st.subheader("📤 导出数据")
        col1, col2 = st.columns(2)
        with col1:
            export_table = st.selectbox("选择要导出的表", list(tables.keys()), format_func=lambda x: tables[x], key="export_table")
        with col2:
            if st.button("导出为 CSV", key="export_btn"):
                csv_data = export_table_to_csv(export_table)
                st.download_button(
                    label="点击下载",
                    data=csv_data,
                    file_name=f"{export_table}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

        st.markdown("---")
        st.subheader("📥 导入数据")
        st.warning("注意：导入将**覆盖**现有数据，请确保备份或确认无误！")
        import_table = st.selectbox("选择要导入的表", list(tables.keys()), format_func=lambda x: tables[x], key="import_table")
        uploaded_file = st.file_uploader("选择 CSV 文件", type=["csv"], key="import_file")
        if uploaded_file is not None:
            confirm = st.checkbox("我确认已备份数据，并同意覆盖当前表内容")
            if st.button("开始导入", key="import_btn"):
                if not confirm:
                    st.error("请勾选确认框后再导入")
                else:
                    raw_content = uploaded_file.read()
                    encodings = ['utf-8-sig', 'gbk', 'gb2312', 'utf-8', 'latin1']
                    csv_content = None
                    for enc in encodings:
                        try:
                            csv_content = raw_content.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    if csv_content is None:
                        st.error("无法解码文件，请确保文件为UTF-8或GBK编码")
                    else:
                        success, errors = safe_import(import_table, csv_content)
                        if errors:
                            st.error(f"导入完成，成功 {success} 条，错误 {len(errors)} 条")
                            with st.expander("查看错误详情"):
                                for err in errors:
                                    st.write(err)
                        else:
                            st.success(f"导入完成，成功 {success} 条记录")
                        st.cache_data.clear()

    # ---------- AI助手 ----------
    elif menu == "🤖 AI助手":
        st.header("🤖 AI智能助手")
        st.markdown("---")
        st.info("AI助手可以帮助您快速分析邮件内容，生成回复建议")
        if not HAS_TRANSFORMERS:
            st.warning("当前使用模拟AI模式。如需更强大的AI能力，请安装 transformers 和 torch。")
        st.checkbox("启用真实AI模型（需GPU/内存充足）", value=st.session_state.get('use_real_ai', False),
                    key="use_real_ai")
        email_text = st.text_area("粘贴客户邮件内容", height=200, key="ai_email")
        if st.button("智能分析", use_container_width=True):
            if email_text:
                with st.spinner("AI正在分析..."):
                    result = ai_email_assistant(email_text)
                st.markdown(result)
            else:
                st.warning("请输入邮件内容")

    # ---------- 操作日志（仅管理员） ----------
    elif menu == "📜 操作日志" and is_admin:
        st.header("📜 操作日志")
        st.markdown("---")
        logs = get_logs(limit=100)
        if logs.empty:
            st.info("暂无操作记录")
        else:
            st.dataframe(logs, use_container_width=True)

    # 处理360视图跳转
    if 'viewing_customer' in st.session_state:
        customer_360_view(st.session_state.viewing_customer)
        if st.button("返回客户列表", use_container_width=True):
            del st.session_state.viewing_customer
            st.rerun()


# ---------- 主入口 ----------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700&display=swap');
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; box-sizing: border-box; }
    .main { background-color: #F8FAFE; }
    [data-testid="stSidebar"] {
        background: linear-gradient(135deg, #1A2C3E 0%, #0F1A2A 100%);
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    [data-testid="stSidebar"] * { color: #EFF3F8 !important; }
    [data-testid="stSidebar"] .stMarkdown { color: #EFF3F8; }
    [data-testid="stSidebar"] .stRadio label {
        font-weight: 500; padding: 8px 12px; border-radius: 10px; transition: all 0.2s ease;
        background: rgba(255,255,255,0.02); margin: 2px 0;
    }
    [data-testid="stSidebar"] .stRadio label:hover { background: rgba(255,255,255,0.12); transform: translateX(2px); }
    [data-testid="stSidebar"] .stRadio label[data-testid="stRadioLabelSelected"] {
        background: rgba(46,134,171,0.3); border-left: 3px solid #2E86AB;
    }
    h1 { color: #1E2F3E; font-weight: 700; font-size: 1.9rem; letter-spacing: -0.02em; margin-bottom: 0.75rem; border-left: 4px solid #2E86AB; padding-left: 1rem; }
    h2, h3 { color: #2C3E50; font-weight: 600; letter-spacing: -0.01em; }
    .stExpander, .stForm, [data-testid="stMetric"] {
        background: white; border-radius: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.03), 0 1px 2px rgba(0,0,0,0.05);
        border: 1px solid #EDF2F7; transition: box-shadow 0.2s ease, transform 0.1s ease;
    }
    .stExpander:hover { box-shadow: 0 8px 20px rgba(0,0,0,0.08); border-color: #E2E8F0; }
    .stButton > button {
        background: linear-gradient(95deg, #2E86AB 0%, #2C6E8F 100%); color: white; border: none;
        border-radius: 12px; padding: 0.5rem 1.2rem; font-weight: 600; font-size: 0.9rem;
        transition: all 0.2s cubic-bezier(0.2, 0.9, 0.4, 1.1); box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .stButton > button:hover { background: linear-gradient(95deg, #3B9AC1 0%, #2E86AB 100%); transform: translateY(-1px); box-shadow: 0 6px 12px rgba(46,134,171,0.2); }
    .stButton > button:active { transform: translateY(1px); }
    .stButton > button[data-testid*="del_"] { background: linear-gradient(95deg, #DC3545 0%, #B02A37 100%); }
    .stButton > button[data-testid*="del_"]:hover { background: linear-gradient(95deg, #E4606F 0%, #DC3545 100%); box-shadow: 0 6px 12px rgba(220,53,69,0.2); }
    [data-testid="stDataFrame"] { border-radius: 16px; overflow: hidden; border: 1px solid #EDF2F7; }
    [data-testid="stDataFrameHeader"] { background: #F8FAFE !important; }
    [data-testid="stDataFrameHeader"] th { color: #1E2F3E !important; font-weight: 600 !important; font-size: 0.85rem !important; padding: 12px 16px !important; }
    [data-testid="stDataFrameRow"]:hover { background-color: #F8F9FC !important; }
    input, textarea, select {
        border-radius: 12px !important; border: 1px solid #E2E8F0 !important; padding: 10px 14px !important;
        background: white !important; transition: all 0.2s;
    }
    input:focus, textarea:focus, select:focus { border-color: #2E86AB !important; box-shadow: 0 0 0 3px rgba(46,134,171,0.1) !important; outline: none; }
    [data-testid="stMetric"] {
        background: white; border-radius: 20px; padding: 1.2rem; border-left: 4px solid #2E86AB; box-shadow: 0 2px 6px rgba(0,0,0,0.02);
    }
    [data-testid="stMetric"] label { color: #5A6E7E; font-weight: 500; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { color: #1E2F3E; font-size: 2rem; font-weight: 700; }
    hr { margin: 1rem 0; border: none; height: 1px; background: linear-gradient(90deg, #E2E8F0, transparent); }
    .stProgress > div > div { background-color: #2E86AB; border-radius: 20px; }
    @media (max-width: 768px) { h1 { font-size: 1.5rem; } .stButton > button { width: 100%; } [data-testid="stMetric"] { padding: 0.8rem; } }
    /* 界面缩小至0.6倍 */
    .block-container {
        max-width: 60% !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    [data-testid="stSidebar"] {
        width: 12.6rem !important;
        min-width: 12.6rem !important;
    }
    html, body, .stMarkdown, .stText, .stSelectbox, .stMultiSelect, 
    .stTextInput, .stTextArea, .stNumberInput, .stDateInput, 
    .stButton, .stDataFrame {
        font-size: 0.9rem !important;
    }
    .stButton > button {
        padding: 0.3rem 0.8rem !important;
        font-size: 0.8rem !important;
    }
    [data-testid="stDataFrame"] th,
    [data-testid="stDataFrame"] td {
        font-size: 0.75rem !important;
        padding: 4px 8px !important;
    }
    [data-testid="stMetric"] {
        padding: 0.8rem !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
    div[data-testid="stExpander"] {
        margin-bottom: 0.5rem !important;
    }
    .stRadio > div {
        gap: 0.2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if st.session_state.logged_in:
        crm_page()
    else:
        login_page()


if __name__ == "__main__":
    main()