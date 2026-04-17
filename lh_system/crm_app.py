import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
import json
import warnings

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


# ---------- 数据库初始化（扩展工程项目、报价表） ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
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

    # ---------- 新增：工程项目表 ----------
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

    # ---------- 新增：报价主表 ----------
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

    # ---------- 新增：报价明细表 ----------
    c.execute('''CREATE TABLE IF NOT EXISTS quotation_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quotation_id INTEGER,
                    seq INTEGER,
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
                    FOREIGN KEY(quotation_id) REFERENCES quotations(id) ON DELETE CASCADE
                )''')

    conn.commit()
    conn.close()


init_db()


# ---------- 辅助函数 ----------
def add_log(user, action, target, details=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO logs (user, action, target, details, created_at) VALUES (?,?,?,?,?)",
              (user, action, target, details, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def check_customer_exists(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM customers WHERE name=?", (name,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


# ---------- 原有客户操作 ----------
def get_customers(filters=None):
    conn = sqlite3.connect(DB_PATH)
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
    return df


def get_customer_by_id(cid):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM customers WHERE id=?", conn, params=(cid,))
    conn.close()
    return df.iloc[0] if not df.empty else None


def add_customer(name, industry, size, stage, estimated_revenue=0, owner=""):
    if check_customer_exists(name):
        return False, "客户名称已存在"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO customers
                     (name, industry, size, stage, estimated_revenue, owner, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (name, industry, size, stage, estimated_revenue, owner, datetime.now().isoformat()))
        conn.commit()
        add_log(st.session_state.username, "添加客户", name, f"行业:{industry}, 规模:{size}, 阶段:{stage}")
        return True, "添加成功"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def update_customer(cid, name, industry, size, stage, estimated_revenue, owner):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM customers WHERE name=? AND id!=?", (name, cid))
    if c.fetchone():
        conn.close()
        return False, "客户名称已存在"
    c.execute("""UPDATE customers
                 SET name=?, industry=?, size=?, stage=?, estimated_revenue=?, owner=?
                 WHERE id=?""",
              (name, industry, size, stage, estimated_revenue, owner, cid))
    conn.commit()
    add_log(st.session_state.username, "编辑客户", name, f"ID:{cid}")
    conn.close()
    return True, "更新成功"


def delete_customer(cid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM customers WHERE id=?", (cid,))
    name = c.fetchone()[0]
    c.execute("DELETE FROM customers WHERE id=?", (cid,))
    c.execute("DELETE FROM contacts WHERE customer_id=?", (cid,))
    c.execute("DELETE FROM interactions WHERE customer_id=?", (cid,))
    c.execute("DELETE FROM tickets WHERE customer_id=?", (cid,))
    conn.commit()
    add_log(st.session_state.username, "删除客户", name, f"ID:{cid}")
    conn.close()


# ---------- 原有联系人操作 ----------
def get_contacts(customer_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM contacts WHERE customer_id=?", conn, params=(customer_id,))
    conn.close()
    return df


def add_contact(customer_id, name, title, phone, email):
    if email and not validate_email(email):
        return False, "邮箱格式不正确"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO contacts (customer_id, name, title, phone, email) VALUES (?,?,?,?,?)",
              (customer_id, name, title, phone, email))
    conn.commit()
    conn.close()
    add_log(st.session_state.username, "添加联系人", f"客户ID:{customer_id}", f"姓名:{name}, 邮箱:{email}")
    return True, "添加成功"


def delete_contact(contact_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
    conn.commit()
    conn.close()
    add_log(st.session_state.username, "删除联系人", f"联系人ID:{contact_id}", "")


# ---------- 原有交互记录操作 ----------
def get_interactions(customer_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM interactions WHERE customer_id=? ORDER BY happened_at DESC",
                           conn, params=(customer_id,))
    conn.close()
    return df


def add_interaction(customer_id, type, content, happened_at):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO interactions (customer_id, type, content, happened_at) VALUES (?,?,?,?)",
              (customer_id, type, content, happened_at.isoformat()))
    conn.commit()
    conn.close()
    add_log(st.session_state.username, "添加交互记录", f"客户ID:{customer_id}", f"类型:{type}, 内容:{content[:50]}")


# ---------- 原有工单操作 ----------
def get_tickets_by_customer(customer_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM tickets WHERE customer_id=? ORDER BY created_at DESC", conn,
                           params=(customer_id,))
    conn.close()
    return df


def get_all_tickets(status_filter=None):
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT t.*, c.name as customer_name FROM tickets t LEFT JOIN customers c ON t.customer_id = c.id"
    if status_filter and status_filter != "全部":
        query += " WHERE t.status = ?"
        df = pd.read_sql_query(query, conn, params=(status_filter,))
    else:
        df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def add_ticket(customer_id, title, description, priority, ticket_type, assigned_to):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO tickets
                 (customer_id, title, description, status, priority, assigned_to, ticket_type, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (customer_id, title, description, "待分配", priority, assigned_to, ticket_type,
               datetime.now().isoformat()))
    conn.commit()
    conn.close()
    add_log(st.session_state.username, "创建工单", f"客户ID:{customer_id}", f"标题:{title}")


def update_ticket_status(ticket_id, status, completed_at=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tickets SET status=?, completed_at=? WHERE id=?", (status, completed_at, ticket_id))
    conn.commit()
    conn.close()


def delete_ticket(ticket_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))
    conn.commit()
    conn.close()
    add_log(st.session_state.username, "删除工单", f"工单ID:{ticket_id}", "")


# ---------- 原有日志操作 ----------
def get_logs(limit=50):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM logs ORDER BY created_at DESC LIMIT {limit}", conn)
    conn.close()
    return df


# ---------- 原有客户价值评分 ----------
def calculate_customer_score(customer_id):
    conn = sqlite3.connect(DB_PATH)
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


# ==================== 新增：工程项目管理模块 ====================
def get_all_projects(filters=None):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM projects WHERE id=?", conn, params=(pid,))
    conn.close()
    return df.iloc[0] if not df.empty else None


def add_project(data):
    """data: dict with all fields"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO projects (
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
        conn.commit()
        add_log(st.session_state.username, "添加工程项目", data['project_name'], f"编号:{data['project_code']}")
        return True, "添加成功"
    except sqlite3.IntegrityError:
        return False, "项目编号已存在"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def update_project(pid, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 检查编号唯一性
    c.execute("SELECT id FROM projects WHERE project_code=? AND id!=?", (data['project_code'], pid))
    if c.fetchone():
        conn.close()
        return False, "项目编号已存在"
    c.execute("""UPDATE projects SET
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
    conn.commit()
    add_log(st.session_state.username, "编辑工程项目", data['project_name'], f"ID:{pid}")
    conn.close()
    return True, "更新成功"


def delete_project(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT project_name FROM projects WHERE id=?", (pid,))
    name = c.fetchone()[0]
    c.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()
    add_log(st.session_state.username, "删除工程项目", name, f"ID:{pid}")
    conn.close()


# ==================== 新增：报价管理模块 ====================
def get_all_quotations(filters=None):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM quotations WHERE id=?", conn, params=(qid,))
    conn.close()
    return df.iloc[0] if not df.empty else None


def get_quotation_items(qid):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY seq", conn, params=(qid,))
    conn.close()
    return df


def add_quotation(data):
    """data: dict for quotation master"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO quotations
                     (quotation_no, project_name, customer_name, contact_person, contact_phone,
                      quotation_date, created_at, updated_at)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (data['quotation_no'], data['project_name'], data['customer_name'],
                   data['contact_person'], data['contact_phone'],
                   data['quotation_date'], datetime.now().isoformat(), datetime.now().isoformat()))
        qid = c.lastrowid
        conn.commit()
        add_log(st.session_state.username, "创建报价单", data['quotation_no'], f"项目:{data['project_name']}")
        return True, qid
    except sqlite3.IntegrityError:
        return False, "报价单号已存在"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def update_quotation(qid, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM quotations WHERE quotation_no=? AND id!=?", (data['quotation_no'], qid))
    if c.fetchone():
        conn.close()
        return False, "报价单号已存在"
    c.execute("""UPDATE quotations SET
        quotation_no=?, project_name=?, customer_name=?, contact_person=?, contact_phone=?,
        quotation_date=?, updated_at=?
        WHERE id=?""",
              (data['quotation_no'], data['project_name'], data['customer_name'],
               data['contact_person'], data['contact_phone'], data['quotation_date'],
               datetime.now().isoformat(), qid))
    conn.commit()
    add_log(st.session_state.username, "编辑报价单", data['quotation_no'], f"ID:{qid}")
    conn.close()
    return True, "更新成功"


def delete_quotation(qid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT quotation_no FROM quotations WHERE id=?", (qid,))
    no = c.fetchone()[0]
    c.execute("DELETE FROM quotations WHERE id=?", (qid,))
    # 明细表自动级联删除
    conn.commit()
    add_log(st.session_state.username, "删除报价单", no, f"ID:{qid}")
    conn.close()


def add_quotation_item(qid, item):
    """item: dict with seq, product_name, specification, unit, quantity, discount, list_price, unit_price, amount, usage_area, remarks"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO quotation_items
                 (quotation_id, seq, product_name, specification, unit, quantity, discount,
                  list_price, unit_price, amount, usage_area, remarks)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
              (qid, item['seq'], item['product_name'], item['specification'], item['unit'],
               item['quantity'], item['discount'], item['list_price'], item['unit_price'],
               item['amount'], item['usage_area'], item['remarks']))
    conn.commit()
    conn.close()


def update_quotation_item(item_id, item):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE quotation_items SET
                 seq=?, product_name=?, specification=?, unit=?, quantity=?, discount=?,
                 list_price=?, unit_price=?, amount=?, usage_area=?, remarks=?
                 WHERE id=?""",
              (item['seq'], item['product_name'], item['specification'], item['unit'],
               item['quantity'], item['discount'], item['list_price'], item['unit_price'],
               item['amount'], item['usage_area'], item['remarks'], item_id))
    conn.commit()
    conn.close()


def delete_quotation_item(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM quotation_items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()


# ---------- 原有页面：登录 ----------
def login_page():
    st.title("🔐 智云CRM · 企业级客户关系管理系统")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 登录您的账户")
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submitted = st.form_submit_button("登录", use_container_width=True)
            if submitted:
                if username == "admin" and password == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("用户名或密码错误")


# ---------- 原有页面：客户360°视图 ----------
def customer_360_view(customer_id):
    customer = get_customer_by_id(customer_id)
    if customer is None:
        st.error("客户不存在")
        return
    contacts = get_contacts(customer_id)
    interactions = get_interactions(customer_id)
    tickets = get_tickets_by_customer(customer_id)
    score = calculate_customer_score(customer_id)

    st.subheader(f"客户全景视图 · {customer['name']}")
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("客户价值评分", f"{score}/100")
    with col2:
        st.metric("预计年收入", f"¥{customer['estimated_revenue']:,.0f}")
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
        with st.expander("✏️ 编辑客户信息"):
            with st.form("edit_customer_form"):
                new_name = st.text_input("公司名称", value=customer['name'])
                new_industry = st.text_input("行业", value=customer['industry'] or "")
                new_size = st.selectbox("规模", ["小型", "中型", "大型"],
                                        index=["小型", "中型", "大型"].index(customer['size']) if customer['size'] in [
                                            "小型", "中型", "大型"] else 0)
                new_stage = st.selectbox("销售阶段", ["潜在", "意向", "谈判", "成交", "流失"],
                                         index=["潜在", "意向", "谈判", "成交", "流失"].index(customer['stage']))
                new_revenue = st.number_input("预计年收入(元)", value=float(customer['estimated_revenue']))
                new_owner = st.text_input("客户经理", value=customer['owner'] or "")
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
                    if st.button("删除", key=f"del_contact_{row['id']}"):
                        delete_contact(row['id'])
                        st.rerun()
        else:
            st.info("暂无联系人")
        with st.form("add_contact_form"):
            st.write("➕ 添加新联系人")
            c_name = st.text_input("姓名")
            c_title = st.text_input("职位")
            c_phone = st.text_input("电话")
            c_email = st.text_input("邮箱")
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
            i_type = st.selectbox("类型", ["电话", "邮件", "会议"])
            i_content = st.text_area("内容")
            i_date = st.date_input("日期", datetime.now())
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
                    if row['status'] != "已完成":
                        if st.button("标记为已完成", key=f"complete_{row['id']}"):
                            update_ticket_status(row['id'], "已完成", datetime.now().isoformat())
                            st.rerun()
        else:
            st.info("暂无工单")
        with st.form("add_ticket_form"):
            st.write("➕ 创建新工单")
            title = st.text_input("工单标题")
            desc = st.text_area("描述")
            priority = st.selectbox("优先级", ["低", "中", "高", "紧急"])
            ticket_type = st.selectbox("类型", ["技术支持", "售后服务", "投诉建议", "其他"])
            assigned_to = st.text_input("负责人")
            if st.form_submit_button("创建"):
                if title:
                    add_ticket(customer_id, title, desc, priority, ticket_type, assigned_to)
                    st.success("工单已创建")
                    st.rerun()


# ---------- 原有页面：CRM主页 ----------
def crm_page():
    # 侧边栏
    with st.sidebar:
        st.markdown(f"### 👋 欢迎，{st.session_state.username}")
        st.markdown("---")
        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.pop("username", None)
            st.rerun()
        st.markdown("---")
        menu = st.radio("导航",
                        ["📊 仪表盘", "👥 客户管理", "🔧 工单管理", "📈 销售分析",
                         "🗺️ 客户旅程", "🏗️ 工程项目", "💰 项目报价", "🤖 AI助手", "📜 操作日志"],
                        index=0)

    # 筛选状态（客户管理用）
    if 'search_name' not in st.session_state:
        st.session_state.search_name = ""
    if 'stage_filter' not in st.session_state:
        st.session_state.stage_filter = "全部"
    if 'page_num' not in st.session_state:
        st.session_state.page_num = 1

    # ---------- 原有模块 ----------
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

    elif menu == "👥 客户管理":
        st.header("👥 客户管理")
        st.markdown("---")
        col_search, col_filter = st.columns([2, 1])
        with col_search:
            search_name = st.text_input("🔍 搜索客户名称", value=st.session_state.search_name,
                                        placeholder="输入客户名称...")
        with col_filter:
            stages = ["全部"] + ["潜在", "意向", "谈判", "成交", "流失"]
            stage_filter = st.selectbox("📌 按阶段筛选", stages, index=stages.index(st.session_state.stage_filter))
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
                        if st.button("删除", key=f"del_{row['id']}"):
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

        with st.sidebar.expander("➕ 快速添加客户", expanded=False):
            with st.form("quick_add"):
                name = st.text_input("公司名称*")
                industry = st.text_input("行业")
                size = st.selectbox("规模", ["小型", "中型", "大型"])
                stage = st.selectbox("阶段", ["潜在", "意向", "谈判", "成交", "流失"])
                revenue = st.number_input("预计年收入(元)", value=0)
                owner = st.text_input("客户经理")
                if st.form_submit_button("添加", use_container_width=True):
                    if name:
                        success, msg = add_customer(name, industry, size, stage, revenue, owner)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

    elif menu == "🔧 工单管理":
        st.header("🔧 工单管理")
        st.markdown("---")
        status_filter = st.selectbox("工单状态", ["全部", "待分配", "处理中", "待验收", "已完成", "已关闭"])
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
                            if status != "已完成":
                                if st.button("完成", key=f"complete_{t['id']}", use_container_width=True):
                                    update_ticket_status(t['id'], "已完成", datetime.now().isoformat())
                                    st.rerun()
                            st.divider()

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

    # ==================== 新增：工程项目管理 ====================
    elif menu == "🏗️ 工程项目":
        st.header("🏗️ 工程项目管理")
        st.markdown("---")
        tab1, tab2 = st.tabs(["📋 项目列表", "➕ 新建项目"])
        with tab1:
            # 搜索筛选
            col_search1, col_search2 = st.columns(2)
            with col_search1:
                search_code = st.text_input("项目编号", placeholder="输入项目编号")
            with col_search2:
                search_name = st.text_input("项目名称", placeholder="输入项目名称")
            # 获取筛选后数据
            filters = {}
            if search_code:
                filters['search_code'] = search_code
            if search_name:
                filters['search_name'] = search_name
            projects_df = get_all_projects(filters)
            if projects_df.empty:
                st.info("暂无工程项目")
            else:
                # 分页显示
                project_page = st.number_input("页码", min_value=1, max_value=max(1, (len(projects_df) - 1) // PAGE_SIZE + 1),
                                               value=1, step=1)
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
                            if st.button("编辑", key=f"edit_proj_{row['id']}"):
                                st.session_state.editing_project = row['id']
                                st.rerun()
                            if st.button("删除", key=f"del_proj_{row['id']}"):
                                delete_project(row['id'])
                                st.rerun()
                # 分页控件
                total_pages = (len(projects_df) - 1) // PAGE_SIZE + 1
                if total_pages > 1:
                    st.write(f"第 {project_page} / {total_pages} 页")
        with tab2:
            with st.form("add_project_form"):
                st.markdown("### 基本信息")
                col1, col2 = st.columns(2)
                with col1:
                    proj_code = st.text_input("项目编号 *")
                    proj_name = st.text_input("项目名称 *")
                    address = st.text_input("项目地址")
                    tracker = st.text_input("项目跟踪人")
                    city = st.text_input("区域/城市")
                    usage_area = st.text_input("使用区域/部位")
                with col2:
                    progress = st.text_input("项目进度明细")
                    last_followup = st.date_input("最近跟进时间", value=datetime.now())
                    products = st.text_input("产品")
                    equipment_list = st.text_input("设备量单")
                    estimated_amount = st.number_input("预计金额(万)", value=0.0)

                st.markdown("### 建设单位")
                col_a, col_b = st.columns(2)
                with col_a:
                    const_unit = st.text_input("单位")
                    const_dept = st.text_input("部门")
                with col_b:
                    const_contact = st.text_input("联系人")
                    const_phone = st.text_input("电话")

                st.markdown("### 设计院")
                col_c, col_d = st.columns(2)
                with col_c:
                    design_unit = st.text_input("单位")
                    design_dept = st.text_input("部门")
                with col_d:
                    design_contact = st.text_input("联系人")
                    design_phone = st.text_input("电话")

                st.markdown("### 总包方")
                col_e, col_f = st.columns(2)
                with col_e:
                    general_unit = st.text_input("单位")
                    general_dept = st.text_input("部门")
                with col_f:
                    general_contact = st.text_input("联系人")
                    general_phone = st.text_input("电话")

                remarks = st.text_area("备注")

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

        # 编辑项目模态框
        if 'editing_project' in st.session_state:
            pid = st.session_state.editing_project
            proj = get_project_by_id(pid)
            if proj is not None:
                with st.form("edit_project_form"):
                    st.markdown(f"### 编辑项目：{proj['project_code']} · {proj['project_name']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        e_proj_code = st.text_input("项目编号 *", value=proj['project_code'])
                        e_proj_name = st.text_input("项目名称 *", value=proj['project_name'])
                        e_address = st.text_input("项目地址", value=proj['address'] or "")
                        e_tracker = st.text_input("项目跟踪人", value=proj['tracker'] or "")
                        e_city = st.text_input("区域/城市", value=proj['city'] or "")
                        e_usage_area = st.text_input("使用区域/部位", value=proj['usage_area'] or "")
                    with col2:
                        e_progress = st.text_input("项目进度明细", value=proj['progress'] or "")
                        e_last_followup = st.date_input("最近跟进时间",
                                                         value=datetime.fromisoformat(proj['last_followup']) if proj[
                                                             'last_followup'] else datetime.now())
                        e_products = st.text_input("产品", value=proj['products'] or "")
                        e_equipment_list = st.text_input("设备量单", value=proj['equipment_list'] or "")
                        e_estimated_amount = st.number_input("预计金额(万)", value=proj['estimated_amount'] or 0.0)

                    st.markdown("### 建设单位")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        e_const_unit = st.text_input("单位", value=proj['construction_unit'] or "")
                        e_const_dept = st.text_input("部门", value=proj['construction_dept'] or "")
                    with col_b:
                        e_const_contact = st.text_input("联系人", value=proj['construction_contact'] or "")
                        e_const_phone = st.text_input("电话", value=proj['construction_phone'] or "")

                    st.markdown("### 设计院")
                    col_c, col_d = st.columns(2)
                    with col_c:
                        e_design_unit = st.text_input("单位", value=proj['design_unit'] or "")
                        e_design_dept = st.text_input("部门", value=proj['design_dept'] or "")
                    with col_d:
                        e_design_contact = st.text_input("联系人", value=proj['design_contact'] or "")
                        e_design_phone = st.text_input("电话", value=proj['design_phone'] or "")

                    st.markdown("### 总包方")
                    col_e, col_f = st.columns(2)
                    with col_e:
                        e_general_unit = st.text_input("单位", value=proj['general_unit'] or "")
                        e_general_dept = st.text_input("部门", value=proj['general_dept'] or "")
                    with col_f:
                        e_general_contact = st.text_input("联系人", value=proj['general_contact'] or "")
                        e_general_phone = st.text_input("电话", value=proj['general_phone'] or "")

                    e_remarks = st.text_area("备注", value=proj['remarks'] or "")

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

    # ==================== 新增：项目报价管理 ====================
    elif menu == "💰 项目报价":
        st.header("💰 项目报价管理")
        st.markdown("---")
        tab1, tab2 = st.tabs(["📋 报价列表", "➕ 新建报价"])
        with tab1:
            col_search1, col_search2 = st.columns(2)
            with col_search1:
                search_no = st.text_input("报价单号", placeholder="输入报价单号")
            with col_search2:
                search_proj = st.text_input("项目名称", placeholder="输入项目名称")
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
                            if st.button("删除报价单", key=f"del_quote_{row['id']}"):
                                delete_quotation(row['id'])
                                st.rerun()
        with tab2:
            with st.form("add_quotation_form"):
                st.markdown("### 报价单基本信息")
                col1, col2 = st.columns(2)
                with col1:
                    quote_no = st.text_input("报价单号 *")
                    # 项目名称可以从已有项目中选择
                    projects_df = get_all_projects()
                    project_names = [""] + list(projects_df['project_name'].unique()) if not projects_df.empty else [""]
                    project_name = st.selectbox("项目名称", project_names)
                with col2:
                    customer_name = st.text_input("客户名称")
                    contact_person = st.text_input("联系人")
                    contact_phone = st.text_input("电话")
                    quote_date = st.date_input("报价日期", value=datetime.now())
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
                        success, qid = add_quotation(data)
                        if success:
                            st.success(f"报价单创建成功，ID: {qid}")
                            st.session_state.viewing_quotation = qid
                            st.rerun()
                        else:
                            st.error(msg)

        # 报价单明细管理
        if 'viewing_quotation' in st.session_state:
            qid = st.session_state.viewing_quotation
            quote = get_quotation_by_id(qid)
            if quote is None:
                del st.session_state.viewing_quotation
                st.rerun()
            st.subheader(f"报价单明细：{quote['quotation_no']} - {quote['project_name']}")
            st.write(f"客户：{quote['customer_name']} | 联系人：{quote['contact_person']} | 电话：{quote['contact_phone']} | 报价日期：{quote['quotation_date']}")
            st.markdown("---")

            # 显示明细表
            items_df = get_quotation_items(qid)
            if not items_df.empty:
                st.dataframe(items_df[['seq', 'product_name', 'specification', 'unit', 'quantity', 'discount',
                                       'list_price', 'unit_price', 'amount', 'usage_area', 'remarks']],
                             use_container_width=True)
                total_amount = items_df['amount'].sum()
                st.metric("报价总额", f"¥{total_amount:,.2f}")
            else:
                st.info("暂无明细，请添加")

            # 添加明细表单
            with st.expander("➕ 添加报价明细"):
                with st.form("add_quotation_item_form"):
                    seq = st.number_input("序号", min_value=1, value=1, step=1)
                    product_name = st.text_input("产品名称 *")
                    specification = st.text_input("规格")
                    unit = st.text_input("单位")
                    quantity = st.number_input("数量", min_value=0.0, value=1.0, step=0.1)
                    discount = st.number_input("下浮点数 (%)", min_value=0.0, value=0.0, step=0.1)
                    list_price = st.number_input("面价", min_value=0.0, value=0.0, step=0.1)
                    usage_area = st.text_input("使用区域")
                    remarks = st.text_input("备注")
                    # 自动计算单价和金额：单价 = 面价 * (100-下浮点数)/100
                    unit_price = list_price * (100 - discount) / 100
                    amount = quantity * unit_price
                    st.write(f"**单价**: ¥{unit_price:.2f} | **金额**: ¥{amount:.2f}")
                    if st.form_submit_button("添加明细"):
                        if product_name:
                            item = {
                                'seq': seq,
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
                            st.error("产品名称不能为空")

            # 编辑/删除明细（简单起见，列表展示并提供操作）
            if not items_df.empty:
                st.markdown("### 管理明细")
                for idx, row in items_df.iterrows():
                    with st.expander(f"序号 {row['seq']}: {row['product_name']}"):
                        with st.form(f"edit_item_{row['id']}"):
                            e_seq = st.number_input("序号", value=row['seq'], key=f"seq_{row['id']}")
                            e_product = st.text_input("产品名称", value=row['product_name'], key=f"prod_{row['id']}")
                            e_spec = st.text_input("规格", value=row['specification'] or "", key=f"spec_{row['id']}")
                            e_unit = st.text_input("单位", value=row['unit'] or "", key=f"unit_{row['id']}")
                            e_qty = st.number_input("数量", value=row['quantity'], key=f"qty_{row['id']}")
                            e_discount = st.number_input("下浮点数 (%)", value=row['discount'], key=f"disc_{row['id']}")
                            e_list = st.number_input("面价", value=row['list_price'], key=f"list_{row['id']}")
                            e_usage = st.text_input("使用区域", value=row['usage_area'] or "", key=f"usage_{row['id']}")
                            e_remarks = st.text_input("备注", value=row['remarks'] or "", key=f"rem_{row['id']}")
                            # 重新计算
                            new_unit_price = e_list * (100 - e_discount) / 100
                            new_amount = e_qty * new_unit_price
                            st.write(f"**单价**: ¥{new_unit_price:.2f} | **金额**: ¥{new_amount:.2f}")
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.form_submit_button("保存修改"):
                                    item_data = {
                                        'seq': e_seq,
                                        'product_name': e_product,
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
                            with col2:
                                if st.form_submit_button("删除明细"):
                                    delete_quotation_item(row['id'])
                                    st.success("删除成功")
                                    st.rerun()
            if st.button("返回报价列表"):
                del st.session_state.viewing_quotation
                st.rerun()

    # ---------- 原有AI助手和操作日志 ----------
    elif menu == "🤖 AI助手":
        st.header("🤖 AI智能助手")
        st.markdown("---")
        st.info("AI助手可以帮助您快速分析邮件内容，生成回复建议")
        if not HAS_TRANSFORMERS:
            st.warning("当前使用模拟AI模式。如需更强大的AI能力，请安装 transformers 和 torch。")
        use_real = st.checkbox("启用真实AI模型（需GPU/内存充足）", value=st.session_state.get('use_real_ai', False))
        st.session_state.use_real_ai = use_real

        email_text = st.text_area("粘贴客户邮件内容", height=200)
        if st.button("智能分析", use_container_width=True):
            if email_text:
                with st.spinner("AI正在分析..."):
                    result = ai_email_assistant(email_text)
                st.markdown(result)
            else:
                st.warning("请输入邮件内容")

    elif menu == "📜 操作日志":
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
    # 页面配置
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")

    # 增强版 CSS 样式 —— 精致现代
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