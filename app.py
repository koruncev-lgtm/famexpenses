import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from streamlit_gsheets import GSheetsConnection

# ========== НАСТРОЙКИ (правь под себя) ==========
USERS = ["Дмитрий", "Жена"]  # кто вносит траты
CATEGORIES = [
    "Продукты", "Кафе и рестораны", "Транспорт", "Жильё и коммуналка",
    "Здоровье", "Одежда", "Развлечения", "Подарки", "Прочее",
]
CURRENCY = "€"  # поменяй на "₽", если нужно
WORKSHEET = "траты"  # название листа в гугл-таблице
COLUMNS = ["дата", "кто", "категория", "сумма", "комментарий"]
# ================================================

st.set_page_config(page_title="Семейные расходы", page_icon="💸")

# --- простая защита паролем, чтобы чужие не заходили ---
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    pwd = st.text_input("Пароль", type="password")
    if pwd:
        if pwd == st.secrets["app_password"]:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Неверный пароль")
    st.stop()

# --- подключение к гугл-таблице ---
conn = st.connection("gsheets", type=GSheetsConnection)


def load_data():
    # ttl=0 — всегда читаем свежие данные, без кэша
    df = conn.read(worksheet=WORKSHEET, ttl=0)
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df = df.dropna(how="all")  # убираем пустые строки
    df["дата"] = pd.to_datetime(df["дата"]).dt.date
    df["сумма"] = pd.to_numeric(df["сумма"])
    return df


st.title("💸 Семейные расходы")

tab_add, tab_stats = st.tabs(["➕ Внести трату", "📊 Аналитика"])

# ================= ВКЛАДКА: ВНЕСТИ ТРАТУ =================
with tab_add:
    with st.form("add_expense", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            d = st.date_input("Дата", value=date.today())
            user = st.selectbox("Кто потратил", USERS)
        with col2:
            category = st.selectbox("Категория", CATEGORIES)
            amount = st.number_input(f"Сумма, {CURRENCY}", min_value=0.0, step=0.5)
        comment = st.text_input("Комментарий (необязательно)")
        submitted = st.form_submit_button("Сохранить", use_container_width=True)

    if submitted:
        if amount <= 0:
            st.warning("Введи сумму больше нуля")
        else:
            df = load_data()
            new_row = pd.DataFrame(
                [[d.isoformat(), user, category, amount, comment]],
                columns=COLUMNS,
            )
            # добавляем строку и перезаписываем лист целиком
            updated = pd.concat([df.astype(str), new_row], ignore_index=True)
            conn.update(worksheet=WORKSHEET, data=updated)
            st.success(f"Записано: {user} — {category} — {amount} {CURRENCY}")

# ================= ВКЛАДКА: АНАЛИТИКА =================
with tab_stats:
    df = load_data()

    if df.empty:
        st.info("Пока нет ни одной траты — внеси первую на соседней вкладке")
    else:
        # фильтр по месяцу
        df["месяц"] = pd.to_datetime(df["дата"]).dt.strftime("%Y-%m")
        months = sorted(df["месяц"].unique(), reverse=True)
        month = st.selectbox("Месяц", months)
        dfm = df[df["месяц"] == month]

        # ключевые цифры
        total = dfm["сумма"].sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Всего за месяц", f"{total:,.0f} {CURRENCY}")
        for col, u in zip([col2, col3], USERS):
            u_sum = dfm.loc[dfm["кто"] == u, "сумма"].sum()
            col.metric(u, f"{u_sum:,.0f} {CURRENCY}")

        # расходы по категориям
        by_cat = dfm.groupby("категория", as_index=False)["сумма"].sum()
        fig_cat = px.bar(
            by_cat.sort_values("сумма"),
            x="сумма", y="категория", orientation="h",
            title="По категориям",
        )
        st.plotly_chart(fig_cat, use_container_width=True)

        # динамика по дням
        by_day = dfm.groupby("дата", as_index=False)["сумма"].sum()
        fig_day = px.line(by_day, x="дата", y="сумма", markers=True,
                          title="По дням")
        st.plotly_chart(fig_day, use_container_width=True)

        # последние записи
        st.subheader("Последние траты")
        st.dataframe(
            dfm.sort_values("дата", ascending=False)
               .drop(columns="месяц")
               .head(20),
            use_container_width=True, hide_index=True,
        )
