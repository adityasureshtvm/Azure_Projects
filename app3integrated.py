import streamlit as st
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd
import os
from datetime import datetime
import tempfile
from supabase import create_client, Client

# --- Initialize Azure Client ---
endpoint = "https://idp-recognizer.cognitiveservices.azure.com/"
key = "9206ec731aff4d21864f3e98e57e3af7"
client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))

# --- Initialize Supabase Client ---
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Page Configuration ---
st.set_page_config(
    page_title="BizCardX | Business Card Processor",
    page_icon="📇",
    layout="wide"
)

# --- Custom CSS ---
st.markdown("""
<style>
    .st-emotion-cache-1y4p8pa {
        padding: 2rem;
    }
    .uploadedFile {
        border-left: 4px solid #4e8cff;
        padding: 12px;
        margin: 8px 0;
        background: #f8f9fa;
        border-radius: 4px;
    }
    .success-box {
        background-color: #e6f7e6;
        border-left: 4px solid #2e7d32;
        padding: 16px;
        border-radius: 4px;
        margin: 12px 0;
    }
</style>
""", unsafe_allow_html=True)

# --- Header Section ---
st.title("📇 BizCardX - Business Card Processor")
st.markdown("Extract contact details from business cards with AI")

# --- Sidebar ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3713/3713765.png", width=80)
    st.title("Settings")
    st.markdown("""
    **How it works:**
    1. Upload business card images
    2. AI extracts contact details
    3. Data is stored in Supabase
    4. Download as CSV
    """)
    st.divider()
    st.caption("Powered by Azure Form Recognizer & Supabase")

# --- Main Content ---
uploaded_files = st.file_uploader(
    "Upload business card files (JPG/PNG/PDF)",
    type=['jpg', 'jpeg', 'png', 'pdf'],
    accept_multiple_files=True
)

if uploaded_files:
    data = {
        'card_number': [],
        'file_name': [],
        'field_name': [],
        'value': [],
        'confidence': [],
        'extracted_at': []
    }
    
    card_counter = 1
    
    # Metrics row
    col1, col2, col3 = st.columns(3)
    
    with st.status("🔄 Processing files...", expanded=True) as status:
        for uploaded_file in uploaded_files:
            try:
                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as temp_file:
                    temp_file.write(uploaded_file.getbuffer())
                    temp_path = temp_file.name
                
                # Process with Azure
                with open(temp_path, "rb") as f:
                    poller = client.begin_analyze_document(
                        model_id="prebuilt-businessCard",
                        document=f
                    )
                    result = poller.result()
                
                # Extraction Logic
                for doc in result.documents:
                    for field_name, field in doc.fields.items():
                        if field.value:
                            if field_name == "ContactNames":
                                for person in field.value:
                                    first = person.value.get("FirstName").value if "FirstName" in person.value else ""
                                    last = person.value.get("LastName").value if "LastName" in person.value else ""
                                    value = f"{first} {last}".strip()
                                    data['card_number'].append(card_counter)
                                    data['file_name'].append(uploaded_file.name)
                                    data['field_name'].append("Name")
                                    data['value'].append(value)
                                    data['confidence'].append(round(person.confidence, 2))
                                    data['extracted_at'].append(datetime.now().isoformat())
                            
                            elif field_name == "Addresses":
                                for addr in field.value:
                                    addr_val = addr.value
                                    parts = [addr_val.road, addr_val.city, addr_val.state]
                                    value = ", ".join([p for p in parts if p])
                                    data['card_number'].append(card_counter)
                                    data['file_name'].append(uploaded_file.name)
                                    data['field_name'].append("Address")
                                    data['value'].append(value)
                                    data['confidence'].append(round(addr.confidence, 2))
                                    data['extracted_at'].append(datetime.now().isoformat())
                            
                            else:
                                items = field.value if isinstance(field.value, list) else [field]
                                for item in items:
                                    value = item.value if hasattr(item, "value") else item
                                    confidence = item.confidence if hasattr(item, "confidence") else field.confidence
                                    data['card_number'].append(card_counter)
                                    data['file_name'].append(uploaded_file.name)
                                    data['field_name'].append(field_name)
                                    data['value'].append(value)
                                    data['confidence'].append(round(confidence, 2))
                                    data['extracted_at'].append(datetime.now().isoformat())
                    
                    card_counter += 1
                
                os.unlink(temp_path)
                st.markdown(f"""
                <div class="uploadedFile">
                    ✅ <strong>{uploaded_file.name}</strong> processed successfully
                </div>
                """, unsafe_allow_html=True)
            
            except Exception as e:
                st.markdown(f"""
                <div style="color: #d32f2f;">
                    ❌ Failed to process {uploaded_file.name}: {str(e)}
                </div>
                """, unsafe_allow_html=True)
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.unlink(temp_path)
                continue
        
        status.update(label="✅ Processing complete!", state="complete", expanded=False)
    
    # Update metrics
    with col1:
        st.metric("Total Files", len(uploaded_files))
    with col2:
        st.metric("Cards Processed", card_counter-1)
    with col3:
        st.metric("Success Rate", f"{round((card_counter-1)/len(uploaded_files)*100)}%")
    
    # Results section
    st.subheader("📊 Extraction Results")
    df = pd.DataFrame(data)
    
    # Show dataframe with custom styling
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "confidence": st.column_config.ProgressColumn(
                "Confidence",
                format="%.2f",
                min_value=0,
                max_value=1
            )
        }
    )
    
    # Store data in Supabase
    if st.button("💾 Save to Supabase", use_container_width=True):
        try:
            # Convert DataFrame to list of dictionaries for Supabase
            records = df.to_dict('records')
            
            # Insert records in batches
            batch_size = 50
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                response = supabase.table('business_cards').insert(batch).execute()
            
            st.success(f"Successfully saved {len(records)} records to Supabase!")
        except Exception as e:
            st.error(f"Error saving to Supabase: {str(e)}")
    
    # Download button with icon
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Download CSV Report",
        data=csv,
        file_name=f"business_cards_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
        type="primary"
    )

# View stored data
if st.checkbox("🔍 View Stored Data"):
    try:
        stored_data = supabase.table('business_cards').select("*").execute()
        stored_df = pd.DataFrame(stored_data.data)
        
        if not stored_df.empty:
            st.subheader("📁 Data Stored in Supabase")
            st.dataframe(stored_df, use_container_width=True)
            
            # Add delete functionality
            if st.button("🗑️ Delete All Records", type="secondary"):
                supabase.table('business_cards').delete().neq('id', 0).execute()
                st.success("All records deleted successfully!")
                st.experimental_rerun()
        else:
            st.info("No data found in Supabase.")
    except Exception as e:
        st.error(f"Error retrieving data from Supabase: {str(e)}")