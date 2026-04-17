st.set_page_config(page_title="轻量 CRM", layout="wide")
st.sidebar.title("导航")
menu = st.sidebar.radio("选择功能", ["客户列表", "添加客户", "仪表盘"])

if menu == "客户列表":
    st.header("所有客户")
    df_customers = get_customers()
    if df_customers.empty:
        st.info("暂无客户，请先添加")
    else:
        # 展示客户列表，每行一个可展开的详情
        for _, row in df_customers.iterrows():
            with st.expander(f"{row['name']} - {row['stage']}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**行业**: {row['industry']}  |  **规模**: {row['size']}")
                    st.write(f"**创建时间**: {row['created_at']}")

                    # 联系人管理
                    st.subheader("联系人")
                    contacts = get_contacts(row['id'])
                    if not contacts.empty:
                        st.dataframe(contacts[['name', 'title', 'phone', 'email']])
                    else:
                        st.write("暂无联系人")
                    # 添加联系人表单
                    with st.form(key=f"add_contact_{row['id']}"):
                        c_name = st.text_input("姓名", key=f"cname_{row['id']}")
                        c_title = st.text_input("职位", key=f"ctitle_{row['id']}")
                        c_phone = st.text_input("电话", key=f"cphone_{row['id']}")
                        c_email = st.text_input("邮箱", key=f"cemail_{row['id']}")
                        submitted = st.form_submit_button("添加联系人")
                        if submitted and c_name:
                            add_contact(row['id'], c_name, c_title, c_phone, c_email)
                            st.success("联系人已添加")
                            st.rerun()

                    # 交互记录
                    st.subheader("沟通记录")
                    interactions = get_interactions(row['id'])
                    if not interactions.empty:
                        for _, irow in interactions.iterrows():
                            st.write(f"**{irow['type']}** - {irow['happened_at']}")
                            st.write(irow['content'])
                            st.divider()
                    # 添加交互记录
                    with st.form(key=f"add_interaction_{row['id']}"):
                        i_type = st.selectbox("类型", ["电话", "邮件", "会议"], key=f"itype_{row['id']}")
                        i_content = st.text_area("内容", key=f"icontent_{row['id']}")
                        i_date = st.date_input("日期", datetime.now(), key=f"idate_{row['id']}")
                        submitted_i = st.form_submit_button("添加记录")
                        if submitted_i and i_content:
                            add_interaction(row['id'], i_type, i_content, i_date)
                            st.success("记录已添加")
                            st.rerun()

                with col2:
                    # 编辑和删除按钮
                    with st.popover("编辑客户"):
                        new_name = st.text_input("公司名称", value=row['name'], key=f"ename_{row['id']}")
                        new_industry = st.text_input("行业", value=row['industry'], key=f"eind_{row['id']}")
                        new_size = st.selectbox("规模", ["小型", "中型", "大型"],
                                                index=["小型", "中型", "大型"].index(row['size']) if row['size'] in [
                                                    "小型", "中型", "大型"] else 0, key=f"esize_{row['id']}")
                        new_stage = st.selectbox("销售阶段", ["潜在", "意向", "谈判", "成交", "流失"],
                                                 index=["潜在", "意向", "谈判", "成交", "流失"].index(row['stage']),
                                                 key=f"estage_{row['id']}")
                        if st.button("保存修改", key=f"save_{row['id']}"):
                            update_customer(row['id'], new_name, new_industry, new_size, new_stage)
                            st.success("已更新")
                            st.rerun()
                    if st.button("删除客户", key=f"del_{row['id']}"):
                        delete_customer(row['id'])
                        st.success("已删除")
                        st.rerun()

elif menu == "添加客户":
    st.header("新增客户")
    with st.form("add_customer_form"):
        name = st.text_input("公司名称*")
        industry = st.text_input("行业")
        size = st.selectbox("规模", ["小型", "中型", "大型"])
        stage = st.selectbox("销售阶段", ["潜在", "意向", "谈判", "成交", "流失"])
        submitted = st.form_submit_button("添加")
        if submitted:
            if name:
                add_customer(name, industry, size, stage)
                st.success("客户已添加")
                st.rerun()
            else:
                st.error("请填写公司名称")

elif menu == "仪表盘":
    st.header("销售仪表盘")
    df = get_customers()
    if not df.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("客户阶段分布")
            stage_counts = df['stage'].value_counts().reset_index()
            stage_counts.columns = ['阶段', '数量']
            st.bar_chart(stage_counts.set_index('阶段'))
        with col2:
            st.subheader("总客户数")
            st.metric("客户总数", len(df))
            st.subheader("最近新增")
            # 显示最近5条
            st.dataframe(df[['name', 'stage', 'created_at']].head(5))
    else:
        st.info("暂无数据")