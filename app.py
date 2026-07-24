import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from streamlit_gsheets import GSheetsConnection

# ========== НАСТРОЙКИ (правь под себя) ==========
USERS = ["Димка", "Юлька"]  # кто вносит траты
CATEGORIES = [
    "Продукты", "Кафе и рестораны", "Транспорт", "Жильё и коммуналка",
    "Здоровье", "Одежда", "Развлечения", "Подарки", "Прочее", "Собаки", "Кредиты", "Для дома", "Косметика"
]
# каждой категории — свой постоянный цвет (берутся из палитры по порядку)
PALETTE = px.colors.qualitative.Set2 + px.colors.qualitative.Pastel
COLOR_MAP = {cat: PALETTE[i % len(PALETTE)] for i, cat in enumerate(CATEGORIES)}
CURRENCY = "руб"  # поменяй на "₽", если нужно
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


st.title("💸 Куда пропадают деньги")

tab_add, tab_stats, tab_edit = st.tabs(["➕ Внести", "📊 Аналитика", "✏️ Редактировать"])

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
        # фильтр по периоду (две даты: начало и конец)
        min_d, max_d = df["дата"].min(), df["дата"].max()
        # по умолчанию — текущий месяц, но не раньше самой первой траты
        start_default = max(min_d, max_d.replace(day=1))
        period = st.date_input(
            "Период",
            value=(start_default, max_d),
            min_value=min_d, max_value=max_d,
        )
        if len(period) == 2:
            start, end = period
        else:
            start = end = period[0]  # пока выбрана только первая дата
        dfm = df[(df["дата"] >= start) & (df["дата"] <= end)]

        # ключевые цифры
        total = dfm["сумма"].sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Всего за период", f"{total:,.0f} {CURRENCY}")
        for col, u in zip([col2, col3], USERS):
            u_sum = dfm.loc[dfm["кто"] == u, "сумма"].sum()
            col.metric(u, f"{u_sum:,.0f} {CURRENCY}")

        # расходы по категориям
        by_cat = dfm.groupby("категория", as_index=False)["сумма"].sum()
        fig_cat = px.bar(
            by_cat.sort_values("сумма"),
            x="сумма", y="категория", orientation="h",
            color="категория", color_discrete_map=COLOR_MAP,
            title="По категориям",
        )
        fig_cat.update_layout(showlegend=False)  # легенда не нужна, названия и так слева
        st.plotly_chart(fig_cat, use_container_width=True)
        # динамика по дням
        by_day = dfm.groupby("дата", as_index=False)["сумма"].sum()
        fig_day = px.line(by_day, x="дата", y="сумма", markers=True,
                          title="По дням")
        st.plotly_chart(fig_day, use_container_width=True)

        # последние записи
        st.subheader("Последние траты")
        def color_category(val):
            # красим ячейку категории в её цвет
            return f"background-color: {COLOR_MAP.get(val, '')}; color: black"

        st.dataframe(
            dfm.sort_values("дата", ascending=False)
               .head(20)
               .style.map(color_category, subset=["категория"]),
            use_container_width=True, hide_index=True,
        )

        # разбор одной категории: все траты по ней с комментариями
        st.subheader("Разбор категории")
        sel_cat = st.selectbox("Выбери категорию", sorted(dfm["категория"].unique()))
        dfc = dfm[dfm["категория"] == sel_cat]
        st.metric(f"Итого за период: {sel_cat}", f"{dfc['сумма'].sum():,.0f} {CURRENCY}")
        st.dataframe(
            dfc.sort_values("дата", ascending=False)[["дата", "кто", "сумма", "комментарий"]],
            use_container_width=True, hide_index=True,
        )

# ================= ВКЛАДКА: РЕДАКТИРОВАТЬ =================
with tab_edit:
    df_edit = load_data()
    if df_edit.empty:
        st.info("Пока нечего редактировать")
    else:
        st.caption("Меняй ячейки прямо в таблице. Удалить трату: выдели строку галочкой слева и нажми Delete. Изменения применятся после кнопки «Сохранить».")
        edited = st.data_editor(
            df_edit,
            num_rows="dynamic",  # разрешает удалять и добавлять строки
            use_container_width=True,
            hide_index=True,
            column_config={
                "дата": st.column_config.DateColumn("дата"),
                "кто": st.column_config.SelectboxColumn("кто", options=USERS),
                "категория": st.column_config.SelectboxColumn("категория", options=CATEGORIES),
                "сумма": st.column_config.NumberColumn("сумма", min_value=0.0),
                "комментарий": st.column_config.TextColumn("комментарий"),
            },
        )
        if st.button("💾 Сохранить изменения", use_container_width=True):
            out = edited.copy()
            out["дата"] = out["дата"].astype(str)  # даты обратно в текст для таблицы
            conn.update(worksheet=WORKSHEET, data=out.astype(str))
            st.success("Сохранено! Обнови вкладку аналитики.")
