import streamlit as st
import os
import json
import time
import sqlite3
from google import genai
from google.genai import types

# ==========================================
# 1. إعداد قاعدة البيانات (SQLite)
# ==========================================
DB_NAME = "debrah.db"
st.info("👈 اضغط على السهم (>>) أعلى اليسار لتحديد لغتك وحالتك الصحية قبل ابتكار الوصفة")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            diet TEXT,
            health_conditions TEXT,
            calories INTEGER,
            full_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_recipe(recipe_dict, diet, health_conditions):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    title = recipe_dict.get("title", "وصفة بدون اسم")
    calories = recipe_dict.get("nutritional_facts", {}).get("calories_per_serving", 0)
    full_json = json.dumps(recipe_dict, ensure_ascii=False)
    
    cursor.execute('''
        INSERT INTO saved_recipes (title, diet, health_conditions, calories, full_json)
        VALUES (?, ?, ?, ?, ?)
    ''', (title, diet, health_conditions, calories, full_json))
    conn.commit()
    conn.close()

def get_saved_recipes():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, calories, full_json FROM saved_recipes ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

init_db()

# ==========================================
# 2. إعدادات الواجهة والذاكرة المؤقتة
# ==========================================
st.set_page_config(page_title="دبْرة - شيفك الذكي", page_icon="🍳", layout="wide", initial_sidebar_state="expanded")

if 'current_response' not in st.session_state:
    st.session_state.current_response = None
if 'override_mode' not in st.session_state:
    st.session_state.override_mode = False
if 'view_recipe' not in st.session_state:
    st.session_state.view_recipe = None

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    st.error("⚠️ مفتاح GEMINI_API_KEY غير موجود في النظام.")
    st.stop()

client = genai.Client(api_key=api_key)

SYSTEM_PROMPT = """أنت "دبْرة" (Debrah)، شيف ذكي ومساعد تغذية سريرية متقدم.
مهمتك ابتكار وصفات طعام بناءً على المعطيات، ويجب أن تكون نصوص الوصفة (الاسم، الوصف، النصائح، المقادير، والخطوات) باللغة المحددة في الطلب (العربية أو الإنجليزية).
يجب أن يكون مخرجك بصيغة JSON صالحة (Valid JSON) فقط.

المدخلات التي ستتلقاها:
- المكونات المتاحة.
- النظام الغذائي والمشاكل الصحية.
- لغة الرد المطلوبة.
- أمر تجاوز اختياري.

قواعد الاستجابة الصارمة (حارس البوابة):
1. فحص التعارض: إذا طلب المستخدم مكونات تتعارض بشدة مع حالته الصحية (مثل سكري + سكر عالي، أو حساسية لاكتوز + حليب بقري)، يجب أن توقف توليد الوصفة وتجعل الـ status تساوي "health_conflict"، وتملأ حقل conflict_details.
2. التجاوز (Override): إذا احتوت المدخلات على أمر "تأكيد_تجاوز_التحذير"، قم بتوليد الوصفة باستخدام المكونات المطلوبة، واجعل حقل health_and_diet_advice يحتوي على تحذير طبي شديد اللهجة.

الهيكل الإلزامي (تأكد من ترجمة القيم النصية للغة المطلوبة، لكن احتفظ بمفاتيح الـ JSON بالإنجليزية كما هي):
{
  "status": "success | health_conflict | error",
  "conflict_details": {
    "warning_message": "رسالة تنبيه ودية",
    "problematic_ingredients": ["المكونات المتعارضة"],
    "suggested_alternatives": ["البدائل الصحية"]
  },
  "recipe": {
    "title": "اسم الوصفة",
    "description": "وصف قصير للوجبة",
    "servings": 2,
    "prep_time_minutes": 10,
    "cook_time_minutes": 20,
    "difficulty": "سهل | متوسط | صعب",
    "nutritional_facts": {
      "calories_per_serving": 0,
      "carbs_grams": 0,
      "protein_grams": 0,
      "fat_grams": 0
    },
    "health_and_diet_advice": "الشرح الطبي",
    "ingredients": [
      {"item": "المكون", "quantity": "الكمية", "unit": "الوحدة"}
    ],
    "instructions": [
      "الخطوة الأولى..."
    ]
  },
  "error_message": null
}
"""

def call_debrah_api(user_prompt, retries=3):
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.7
    )
    for attempt in range(retries):
        try:
            response = client.chats.create(
                model='gemini-3.8-flash',
                config=config
            ).send_message(user_prompt)
            return json.loads(response.text)
        except Exception as e:
            err_str = str(e)
            if "503" in err_str or "429" in err_str:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            raise e

def render_recipe_ui(recipe):
    st.success(f"🎉 {recipe.get('title')}")
    st.write(f"**الوصف / Description:** {recipe.get('description', '')}")
    st.info(f"💡 **نصيحة صحية / Health Advice:** {recipe.get('health_and_diet_advice', 'لا توجد ملاحظات')}")
        
    col1, col2, col3 = st.columns(3)
    nutritional = recipe.get('nutritional_facts', {})
    col1.metric("السعرات / Calories", f"{nutritional.get('calories_per_serving', 0)} kcal")
    col2.metric("الحصص / Servings", recipe.get('servings', 1))
    col3.metric("الوقت / Time", f"{recipe.get('prep_time_minutes', 0) + recipe.get('cook_time_minutes', 0)} min")
    
    st.write("### 🛒 المكونات / Ingredients")
    for ing in recipe.get("ingredients", []):
        st.write(f"- {ing.get('quantity', '')} {ing.get('unit', '')} **{ing.get('item', '')}**")
        
    st.write("### 👨‍🍳 التحضير / Instructions")
    for step in recipe.get("instructions", []):
        st.write(f"- {step}")

# ==========================================
# 3. واجهة المستخدم الجانبية
# ==========================================
# ==========================================
# 3. واجهة المستخدم الجانبية
# ==========================================
with st.sidebar:
    st.header("🌐 إعدادات اللغة / Language")
    output_lang = st.selectbox("لغة الوصفة / Recipe Language:", ["العربية", "English"])
    
    st.markdown("---")
    st.header("⚙️ الفلاتر الصحية / Filters")
    diet = st.selectbox("النظام الغذائي / Diet:", 
                       ["بدون نظام محدد / No specific diet", 
                        "كيتو / Keto", 
                        "قليل الكربوهيدرات / Low Carb", 
                        "نباتي / Vegetarian", 
                        "عالي البروتين / High Protein"])
                        
    health = st.multiselect("المشاكل الصحية / Health Conditions:", 
                           ["السكري / Diabetes", 
                            "ارتفاع ضغط الدم / Hypertension", 
                            "الكوليسترول / High Cholesterol", 
                            "حساسية الجلوتين / Gluten Intolerance", 
                            "حساسية اللاكتوز / Lactose Intolerance"])
    
    st.markdown("---")
    st.header("📚 وصفاتي / My Recipes")
    saved_rows = get_saved_recipes()
    if saved_rows:
        for row in saved_rows:
            recipe_id, title, calories, full_json = row
            if st.button(f"🍽️ {title} ({calories} kcal)", key=f"btn_{recipe_id}"):
                st.session_state.view_recipe = json.loads(full_json)
                st.session_state.current_response = None
                st.rerun()
    else:
        st.info("لا توجد وصفات محفوظة بعد. / No saved recipes yet.")

# ==========================================
# 4. الواجهة الرئيسية
# ==========================================
if st.session_state.view_recipe:
    st.title("📖 عرض الوصفة / View Recipe")
    if st.button("🔙 عودة لابتكار وصفة جديدة / Back"):
        st.session_state.view_recipe = None
        st.rerun()
    render_recipe_ui(st.session_state.view_recipe)

else:
    st.title("🍳 تطبيق دبْرة (Debrah AI Chef)")
    ingredients = st.text_area("🛒 ماذا يوجد في مطبخك؟ / What's in your kitchen?")

    health_str = ", ".join(health) if health else 'لا يوجد'
    full_prompt = f"""
    المكونات: {ingredients}
    النظام الغذائي: {diet}
    المشاكل الصحية: {health_str}
    لغة الإجابة المطلوبة للوصفة (Output Language): {output_lang}
    """

    if st.button("✨ ابتكر الوصفة / Generate Recipe"):
        if ingredients:
            with st.spinner("دبْرة تحلل مكوناتك صحياً... / Analyzing..."):
                try:
                    st.session_state.current_response = call_debrah_api(full_prompt)
                    st.session_state.override_mode = False
                except Exception as e:
                    st.error("⚠️ فشل الاتصال بالسيرفر. / Server Error.")

    if st.session_state.current_response:
        res = st.session_state.current_response
        
        if res.get("status") == "health_conflict" and not st.session_state.override_mode:
            conflict = res.get("conflict_details", {})
            st.warning(f"⚠️ **تنبيه طبي / Medical Alert:** {conflict.get('warning_message')}")
            st.write("**المكونات المتعارضة:**", ", ".join(conflict.get("problematic_ingredients", [])))
            st.write("**البدائل المقترحة:**", ", ".join(conflict.get("suggested_alternatives", [])))
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ أريد البديل الصحي / Give me alternatives"):
                    with st.spinner("جاري التعديل..."):
                        safe_prompt = full_prompt + "\n اعتمد البدائل الصحية المقترحة."
                        st.session_state.current_response = call_debrah_api(safe_prompt)
                        st.rerun()
            with col2:
                if st.button("🚨 استمر على مسؤوليتي / Ignore alert"):
                    with st.spinner("جاري الإعداد..."):
                        override_prompt = full_prompt + "\n [تأكيد_تجاوز_التحذير] استخدم المكونات الأصلية."
                        st.session_state.current_response = call_debrah_api(override_prompt)
                        st.session_state.override_mode = True
                        st.rerun()

        elif res.get("status") == "success":
            recipe = res.get("recipe", {})
            render_recipe_ui(recipe)
                
            st.markdown("---")
            if st.button("💾 حفظ الوصفة / Save Recipe"):
                save_recipe(recipe, diet, health_str)
                st.success("✅ تم الحفظ بنجاح! / Saved successfully!")
                time.sleep(1)
                st.rerun()
                
        elif res.get("status") == "error":
            st.error(res.get("error_message"))
