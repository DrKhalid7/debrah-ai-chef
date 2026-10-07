import streamlit as st
import os
import json
from google import genai
from google.genai import types

# ==========================================
# إعدادات الواجهة والذاكرة المؤقتة (Session State)
# ==========================================
st.set_page_config(page_title="دبْرة - شيفك الذكي", page_icon="🍳")

# ذاكرة التطبيق لحفظ الحالة عند النقر على الأزرار
if 'current_response' not in st.session_state:
    st.session_state.current_response = None
if 'override_mode' not in st.session_state:
    st.session_state.override_mode = False

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    st.error("⚠️ مفتاح GEMINI_API_KEY غير موجود في النظام.")
    st.stop()

client = genai.Client(api_key=api_key)

# برومبت النظام المحدث (نفس الذي وضعته في استوديو جوجل)
SYSTEM_PROMPT = """أنت "دبْرة" (Debrah)، شيف ذكي ومساعد تغذية سريرية متقدم.
(طبق نفس البرومبت الشامل الذي اتفقنا عليه سابقاً الخاص بحارس البوابة الطبية والـ JSON)
"""

def call_debrah_api(user_prompt):
    """دالة الاتصال بالنموذج"""
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.7
    )
    response = client.chats.create(
        model='gemini-2.5-flash',
        config=config
    ).send_message(user_prompt)
    return json.loads(response.text)

# ==========================================
# واجهة المستخدم الجانبية (الفلاتر)
# ==========================================
with st.sidebar:
    st.header("⚙️ الفلاتر الصحية")
    diet = st.selectbox("النظام الغذائي:", ["بدون نظام محدد", "كيتو", "قليل الكربوهيدرات", "نباتي", "عالي البروتين"])
    health = st.multiselect("المشاكل الصحية (إن وجدت):", ["السكري", "ارتفاع ضغط الدم", "الكوليسترول", "حساسية الجلوتين"])

# ==========================================
# الواجهة الرئيسية
# ==========================================
st.title("🍳 تطبيق دبْرة (MVP)")
ingredients = st.text_area("🛒 ماذا يوجد في مطبخك؟ (اكتب المكونات والكميات):")

# تجهيز النص المُرسل للنموذج
full_prompt = f"""
المكونات: {ingredients}
النظام الغذائي: {diet}
المشاكل الصحية: {', '.join(health) if health else 'لا يوجد'}
"""

if st.button("✨ ابتكر الوصفة"):
    if ingredients:
        with st.spinner("دبْرة تحلل مكوناتك صحياً..."):
            st.session_state.current_response = call_debrah_api(full_prompt)
            st.session_state.override_mode = False # إعادة ضبط وضع التجاوز

# ==========================================
# منطق معالجة الاستجابة (حارس البوابة)
# ==========================================
if st.session_state.current_response:
    res = st.session_state.current_response
    
    # حالة التعارض الصحي
    if res.get("status") == "health_conflict" and not st.session_state.override_mode:
        conflict = res.get("conflict_details", {})
        st.warning(f"⚠️ **تنبيه طبي:** {conflict.get('warning_message')}")
        
        st.write("**المكونات المتعارضة:**", ", ".join(conflict.get("problematic_ingredients", [])))
        st.write("**البدائل المقترحة:**", ", ".join(conflict.get("suggested_alternatives", [])))
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ أريد البديل الصحي"):
                with st.spinner("جاري تعديل الوصفة بالبدائل..."):
                    safe_prompt = full_prompt + "\n اعتمد البدائل الصحية المقترحة وتجاهل المكونات المضرة."
                    st.session_state.current_response = call_debrah_api(safe_prompt)
                    st.rerun() # تحديث الصفحة لعرض الوصفة
                    
        with col2:
            if st.button("🚨 استمر على مسؤوليتي"):
                with st.spinner("جاري إعداد الوصفة الأصلية..."):
                    override_prompt = full_prompt + "\n [تأكيد_تجاوز_التحذير] استخدم المكونات الأصلية."
                    st.session_state.current_response = call_debrah_api(override_prompt)
                    st.session_state.override_mode = True
                    st.rerun()

    # حالة النجاح أو التجاوز
    elif res.get("status") == "success":
        recipe = res.get("recipe", {})
        st.success(f"🎉 {recipe.get('title')}")
        
        # عرض التحذير الطبي إذا كان هناك تجاوز
        if st.session_state.override_mode:
            st.error(f"🚨 **إخلاء مسؤولية طبي:** {recipe.get('health_and_diet_advice')}")
        else:
            st.info(f"💡 **نصيحة دبرة:** {recipe.get('health_and_diet_advice')}")
            
        col1, col2, col3 = st.columns(3)
        col1.metric("السعرات", f"{recipe.get('nutritional_facts', {}).get('calories_per_serving')} kcal")
        col2.metric("الحصص", recipe.get('servings'))
        col3.metric("الوقت", f"{recipe.get('prep_time_minutes') + recipe.get('cook_time_minutes')} دقيقة")
        
        st.write("### المكونات")
        for ing in recipe.get("ingredients", []):
            st.write(f"- {ing['quantity']} {ing['unit']} **{ing['item']}**")
            
        st.write("### التحضير")
        for step in recipe.get("instructions", []):
            st.write(f"- {step}")
            
    elif res.get("status") == "error":
        st.error(res.get("error_message"))
