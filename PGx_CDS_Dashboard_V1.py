"""
===============================================================================
PGx-Guided Behavioral Health CDS Dashboard – Prototype

AUTHOR: Barry Ohearn, RN, MN-Informatics Candidate (WGU, 2025)
DATE: 5/27/25
-------------------------------------------------------------------------------
DISCLAIMER:
This software is a prototype for educational and demonstration purposes only.
It is NOT validated for clinical use and should NOT be used to guide actual
medical decisions or patient care. Outputs are based on sample logic and
reference data, and do not constitute medical advice.

PROJECT DESCRIPTION:
This Streamlit app demonstrates a nurse-facing clinical decision support (CDS)
dashboard that integrates pharmacogenomic (PGx) panel results with psychiatric
medication management. Users can upload a PDF or text PGx report, select
active psychiatric/behavioral health medications, and receive:
    - Automated gene/phenotype extraction
    - Bayesian-style risk estimates for drug-gene interactions
    - Polypharmacy and phenoconversion alerts
    - Flowsheet documentation prompts and provider smart notes
    - One-click PDF/JSON report exports

HOW TO USE:
1. Install Python 3.9+ and required packages (see requirements.txt).
2. Launch the app using: streamlit run <this_script.py>
3. Upload a sample PGx report (PDF or TXT).
4. Select medications using the autocomplete field.
5. Review the dashboard outputs for clinical insights and export options.

For questions, suggestions, or collaboration, contact Barry Ohearn.

===============================================================================
"""

import streamlit as st
from PyPDF2 import PdfReader
import pandas as pd
from fpdf import FPDF
import tempfile

# ----------------------- Brand/Generic Synonym Mapping -----------------------
# Add new pairs as needed
MED_SYNONYMS = {
    # SSRIs / SNRIs
    "lexapro": "escitalopram",
    "celexa": "citalopram",
    "paxil": "paroxetine",
    "prozac": "fluoxetine",
    "zoloft": "sertraline",
    "effexor": "venlafaxine",
    "cymbalta": "duloxetine",
    # Antipsychotics
    "abilify": "aripiprazole",
    "risperdal": "risperidone",
    "zyprexa": "olanzapine",
    "seroquel": "quetiapine",
    "geodon": "ziprasidone",
    "haldol": "haloperidol",
    # Mood stabilizers
    "lamictal": "lamotrigine",
    "tegretol": "carbamazepine",
    "depakote": "valproate",
    # Other psych
    "wellbutrin": "bupropion",
    "ativan": "lorazepam",
    "klonopin": "clonazepam",
    "ambien": "zolpidem",
    "buspar": "buspirone"
}
# Include reverse mappings
for brand, generic in list(MED_SYNONYMS.items()):
    MED_SYNONYMS[generic] = generic

# For display: brand/generic pretty mapping
DISPLAY_NAME = {
    "escitalopram": "escitalopram (Lexapro)",
    "citalopram": "citalopram (Celexa)",
    "paroxetine": "paroxetine (Paxil)",
    "fluoxetine": "fluoxetine (Prozac)",
    "sertraline": "sertraline (Zoloft)",
    "venlafaxine": "venlafaxine (Effexor)",
    "duloxetine": "duloxetine (Cymbalta)",
    "aripiprazole": "aripiprazole (Abilify)",
    "risperidone": "risperidone (Risperdal)",
    "olanzapine": "olanzapine (Zyprexa)",
    "quetiapine": "quetiapine (Seroquel)",
    "ziprasidone": "ziprasidone (Geodon)",
    "haloperidol": "haloperidol (Haldol)",
    "lamotrigine": "lamotrigine (Lamictal)",
    "carbamazepine": "carbamazepine (Tegretol)",
    "valproate": "valproate (Depakote)",
    "bupropion": "bupropion (Wellbutrin)",
    "lorazepam": "lorazepam (Ativan)",
    "clonazepam": "clonazepam (Klonopin)",
    "zolpidem": "zolpidem (Ambien)",
    "buspirone": "buspirone (Buspar)",
}
def normalize_med_name(med):
    """Returns canonical generic med name, and display string with brand."""
    key = med.strip().lower()
    generic = MED_SYNONYMS.get(key, key)
    display = DISPLAY_NAME.get(generic, generic.capitalize())
    return generic, display
# ---- Combined list of all unique med names for autocomplete ----
ALL_MEDS = sorted(set(list(MED_SYNONYMS.keys()) + list(MED_SYNONYMS.values())))
# Show both brand and generic in dropdown options
ALL_MEDS_DISPLAY = []
for med in ALL_MEDS:
    disp: object
    gen, disp = normalize_med_name(med)
    if disp not in ALL_MEDS_DISPLAY:
        ALL_MEDS_DISPLAY.append(disp)
# ----------------------- Phenoconversion Inhibitors/Inducers -----------------------
PHENOCONVERT = {
    "CYP2D6": {
        "strong_inhibitors": ["paroxetine", "fluoxetine", "bupropion"],
        "moderate_inhibitors": [],
        "inducers": []
    },
    "CYP2C19": {
        "strong_inhibitors": ["fluvoxamine", "fluoxetine"],
        "moderate_inhibitors": [],
        "inducers": ["carbamazepine"]
    },
    "CYP3A4": {
        "strong_inhibitors": ["ritonavir", "ketoconazole"],
        "moderate_inhibitors": ["fluvoxamine"],
        "inducers": ["carbamazepine"]
    },
    "CYP1A2": {
        "strong_inhibitors": ["fluvoxamine"],
        "moderate_inhibitors": [],
        "inducers": ["carbamazepine", "smoking"]
    }
}

# --------------- Example PGX_FACTORS, FLOWSHEET_PROMPTS, CLINICAL_COMMENTS, PRIOR_RISKS ---------------
# Use your latest/expanded dictionaries here (truncated for brevity in this sample)
PGX_FACTORS = {
    # --- Antipsychotics ---
    ("CYP2D6", "Poor Metabolizer", "risperidone"): 3,
    ("CYP2D6", "Poor Metabolizer", "aripiprazole"): 2.5,
    ("CYP2D6", "Poor Metabolizer", "haloperidol"): 2.5,
    ("CYP3A4", "Decreased Function", "quetiapine"): 2,
    ("CYP1A2", "Ultra-rapid Metabolizer", "olanzapine"): 0.5,
    ("CYP1A2", "Ultra-rapid Metabolizer", "clozapine"): 0.5,

    # --- SSRIs/SNRIs ---
    ("CYP2C19", "Ultra-rapid Metabolizer", "citalopram"): 0.4,
    ("CYP2C19", "Poor Metabolizer", "citalopram"): 2,
    ("CYP2C19", "Ultra-rapid Metabolizer", "escitalopram"): 0.5,
    ("CYP2C19", "Poor Metabolizer", "escitalopram"): 1.8,
    ("CYP2D6", "Poor Metabolizer", "paroxetine"): 2,
    ("CYP2D6", "Poor Metabolizer", "fluoxetine"): 1.5,
    ("CYP2D6", "Poor Metabolizer", "venlafaxine"): 2,
    ("CYP2D6", "Poor Metabolizer", "duloxetine"): 1.5,

    # --- Mood stabilizers ---
    ("CYP2C19", "Poor Metabolizer", "lamotrigine"): 1.2,
    ("CYP2C9", "Poor Metabolizer", "valproate"): 1.4,

    # --- Anxiolytics/Sleep ---
    ("CYP3A4", "Decreased Function", "alprazolam"): 1.7,
    ("CYP2C19", "Poor Metabolizer", "diazepam"): 1.6,
    ("CYP3A4", "Decreased Function", "zolpidem"): 1.5,

    # --- Pharmacodynamic/Transporters ---
    ("HTR2A", "A/A", "sertraline"): 0.7,
    ("SLC6A4", "S/S", "sertraline"): 0.7,
    ("COMT", "Val/Val", "bupropion"): 0.8,
}
FLOWSHEET_PROMPTS = {
    # --- Antipsychotics ---
    ("CYP2D6", "Poor Metabolizer", "risperidone"): ["Monitor for tremor", "Assess for EPS", "Check for sedation"],
    ("CYP2D6", "Poor Metabolizer", "aripiprazole"): ["Monitor for akathisia", "Check for restlessness"],
    ("CYP2D6", "Poor Metabolizer", "haloperidol"): ["Assess for rigidity", "Monitor for neurotoxicity"],
    ("CYP3A4", "Decreased Function", "quetiapine"): ["Check for sedation", "Monitor blood pressure (orthostasis)"],
    ("CYP1A2", "Ultra-rapid Metabolizer", "olanzapine"): ["Assess for decreased efficacy", "Monitor weight/appetite"],

    # --- SSRIs/SNRIs ---
    ("CYP2C19", "Ultra-rapid Metabolizer", "citalopram"): ["Assess for lack of effect", "Monitor mood symptoms"],
    ("CYP2C19", "Poor Metabolizer", "citalopram"): ["Monitor for QT prolongation", "Check for GI upset"],
    ("CYP2D6", "Poor Metabolizer", "paroxetine"): ["Assess for anticholinergic effects", "Monitor for sedation"],
    ("CYP2D6", "Poor Metabolizer", "fluoxetine"): ["Check for insomnia", "Monitor for GI side effects"],

    # --- Mood stabilizers ---
    ("CYP2C19", "Poor Metabolizer", "lamotrigine"): ["Monitor for rash", "Assess for dizziness"],
    ("CYP2C9", "Poor Metabolizer", "valproate"): ["Monitor LFTs", "Check for thrombocytopenia"],

    # --- Anxiolytics/Sleep ---
    ("CYP3A4", "Decreased Function", "alprazolam"): ["Monitor for sedation", "Assess fall risk"],
    ("CYP2C19", "Poor Metabolizer", "diazepam"): ["Check for prolonged sedation", "Assess confusion"],
    ("CYP3A4", "Decreased Function", "zolpidem"): ["Monitor for next-day drowsiness"],

    # --- Pharmacodynamic/Transporters ---
    ("HTR2A", "A/A", "sertraline"): ["Monitor for lack of SSRI effect"],
    ("SLC6A4", "S/S", "sertraline"): ["Assess for SSRI intolerance"],
    ("COMT", "Val/Val", "bupropion"): ["Monitor for low response", "Check for irritability"],
}

CLINICAL_COMMENTS = {
    # --- Antipsychotics ---
    ("CYP2D6", "Poor Metabolizer", "risperidone"):
        "CYP2D6 Poor Metabolizer status reduces risperidone clearance, causing the drug to accumulate in the bloodstream. This increases the risk of extrapyramidal side effects (EPS), sedation, and toxicity. Consider lowering the dose or switching to a medication less dependent on CYP2D6 metabolism. [CPIC]",
    ("CYP2D6", "Poor Metabolizer", "aripiprazole"):
        "Poor CYP2D6 metabolism slows aripiprazole clearance, raising blood concentrations and increasing risk of side effects such as akathisia, sedation, and QT prolongation. A dose reduction or alternative therapy may be appropriate.",
    ("CYP2D6", "Poor Metabolizer", "haloperidol"):
        "Reduced CYP2D6 function decreases haloperidol metabolism, which can lead to higher blood levels and increased risk of EPS, neurotoxicity, or cardiac adverse events. Careful monitoring or dose adjustment is recommended.",
    ("CYP3A4", "Decreased Function", "quetiapine"):
        "Quetiapine is primarily metabolized by CYP3A4. Decreased function can lead to elevated quetiapine concentrations, increasing sedation, orthostatic hypotension, and risk of toxicity. Dose reduction may be needed.",
    ("CYP1A2", "Ultra-rapid Metabolizer", "olanzapine"):
        "Ultra-rapid CYP1A2 metabolism increases olanzapine clearance, potentially resulting in subtherapeutic levels and decreased efficacy, especially in smokers. Consider higher doses or alternate agents.",
    ("CYP1A2", "Ultra-rapid Metabolizer", "clozapine"):
        "Ultra-rapid metabolism leads to low clozapine levels, risking therapeutic failure. Monitor response and consider dose adjustment.",

    # --- SSRIs/SNRIs ---
    ("CYP2C19", "Ultra-rapid Metabolizer", "citalopram"):
        "CYP2C19 ultra-rapid metabolism clears citalopram more quickly, which can result in subtherapeutic plasma concentrations and poor antidepressant response. Consider an SSRI less affected by CYP2C19 or increase the dose if clinically appropriate.",
    ("CYP2C19", "Poor Metabolizer", "citalopram"):
        "Poor CYP2C19 metabolism raises citalopram levels, increasing the risk of QT prolongation and other side effects. Dose reduction or close monitoring is recommended.",
    ("CYP2C19", "Ultra-rapid Metabolizer", "escitalopram"):
        "Faster metabolism of escitalopram may cause lower drug levels and reduced antidepressant effect. Monitor for lack of response.",
    ("CYP2C19", "Poor Metabolizer", "escitalopram"):
        "Reduced metabolism raises escitalopram blood levels, increasing the risk of side effects, including QT prolongation. Consider lower doses or more frequent monitoring.",
    ("CYP2D6", "Poor Metabolizer", "paroxetine"):
        "CYP2D6 Poor Metabolizer status leads to slow paroxetine clearance, resulting in drug accumulation and a higher risk of anticholinergic effects, sedation, and sexual dysfunction. Dose reduction or switching medications may be needed.",
    ("CYP2D6", "Poor Metabolizer", "fluoxetine"):
        "Reduced CYP2D6 activity increases fluoxetine levels, elevating risk of side effects such as insomnia, GI upset, and serotonin syndrome. Monitor and consider dose reduction.",
    ("CYP2D6", "Poor Metabolizer", "venlafaxine"):
        "Venlafaxine is metabolized to its active metabolite by CYP2D6. Poor metabolism may cause higher venlafaxine and lower active metabolite levels, leading to reduced efficacy and increased side effects. Adjust therapy as needed.",
    ("CYP2D6", "Poor Metabolizer", "duloxetine"):
        "Slow CYP2D6 metabolism raises duloxetine concentrations, increasing the risk of side effects such as nausea, hypertension, and liver toxicity. Lower doses or alternative therapy may be appropriate.",

    # --- Mood Stabilizers/Other Psych ---
    ("CYP2C19", "Poor Metabolizer", "lamotrigine"):
        "Poor CYP2C19 metabolism may result in higher lamotrigine levels, which can increase the risk of rash and other adverse effects. Monitor closely.",
    ("CYP2C9", "Poor Metabolizer", "valproate"):
        "Valproate clearance is reduced in CYP2C9 poor metabolizers, raising blood levels and risk of toxicity, including liver damage and thrombocytopenia. Dose adjustment and monitoring recommended.",
    ("CYP2C19", "Ultra-rapid Metabolizer", "clobazam"):
        "Faster metabolism may result in lower clobazam levels, possibly reducing efficacy in seizure control or anxiety treatment.",

    # --- Anxiety/Sleep ---
    ("CYP3A4", "Decreased Function", "alprazolam"):
        "Decreased CYP3A4 activity leads to slower alprazolam metabolism, increasing sedation, confusion, and fall risk, especially in older adults.",
    ("CYP2C19", "Poor Metabolizer", "diazepam"):
        "Poor metabolism of diazepam leads to drug accumulation, prolonging sedation and increasing risk of adverse effects.",
    ("CYP3A4", "Decreased Function", "zolpidem"):
        "Zolpidem is cleared by CYP3A4. Decreased function can result in prolonged sedation and next-day drowsiness. Lower doses or alternate sleep aids may be needed.",

    # --- Transporter/Pharmacodynamic Markers ---
    ("HTR2A", "A/A", "sertraline"):
        "HTR2A A/A genotype may reduce SSRI efficacy, possibly requiring dose escalation or alternative antidepressants.",
    ("SLC6A4", "S/S", "sertraline"):
        "S/S genotype of SLC6A4 (5-HTTLPR) is associated with poorer SSRI tolerance and reduced likelihood of response. Consider alternative therapy if ineffective or poorly tolerated.",
    ("COMT", "Val/Val", "bupropion"):
        "COMT Val/Val may increase dopamine breakdown, possibly reducing bupropion efficacy in treating depression or ADHD. Clinical significance varies.",
}
PRIOR_RISKS = {
    "risperidone": 0.1,
    "aripiprazole": 0.07,
    "haloperidol": 0.12,
    "quetiapine": 0.07,
    "olanzapine": 0.05,
    "clozapine": 0.04,
    "citalopram": 0.08,
    "escitalopram": 0.07,
    "paroxetine": 0.09,
    "fluoxetine": 0.06,
    "sertraline": 0.05,
    "venlafaxine": 0.09,
    "duloxetine": 0.06,
    "lamotrigine": 0.03,
    "valproate": 0.1,
    "clobazam": 0.03,
    "alprazolam": 0.05,
    "diazepam": 0.04,
    "zolpidem": 0.03,
    "bupropion": 0.05,
}


# ----------------------- Utility Functions -----------------------


def parse_pdf(file):
    pdf = PdfReader(file)
    text = ''
    for page in pdf.pages:
        if page.extract_text():
            text += page.extract_text()
    return text

def extract_genes_from_text(text):
    genes = []
    lines = text.splitlines()
    for line in lines:
        if 'CYP2D6' in line and 'Poor Metabolizer' in line:
            genes.append(('CYP2D6', 'Poor Metabolizer'))
        if 'CYP2C19' in line and 'Ultra-rapid Metabolizer' in line:
            genes.append(('CYP2C19', 'Ultra-rapid Metabolizer'))
        if 'CYP2C19' in line and 'Poor Metabolizer' in line:
            genes.append(('CYP2C19', 'Poor Metabolizer'))
        if 'CYP3A4' in line and 'Decreased Function' in line:
            genes.append(('CYP3A4', 'Decreased Function'))
        if 'CYP1A2' in line and 'Ultra-rapid Metabolizer' in line:
            genes.append(('CYP1A2', 'Ultra-rapid Metabolizer'))
        if 'HTR2A' in line and 'A/A' in line:
            genes.append(('HTR2A', 'A/A'))
        if 'SLC6A4' in line and 'S/S' in line:
            genes.append(('SLC6A4', 'S/S'))
        if 'COMT' in line and 'Val/Val' in line:
            genes.append(('COMT', 'Val/Val'))
        if 'CYP2C9' in line and 'Poor Metabolizer' in line:
            genes.append(('CYP2C9', 'Poor Metabolizer'))
    return genes

def phenoconvert_genes(genes, meds, log):
    # Make a copy so original isn't mutated
    functional_genes = []
    gene_set = set(g for g, _ in genes)
    # Dict to allow updates (key: gene, value: (original, functional, caused_by))
    gene_state = {}
    for gene, phenotype in genes:
        gene_state[gene] = {"genotype": phenotype, "functional": phenotype, "caused_by": []}
    # Scan for inhibitors/inducers
    for gene in gene_set:
        inhibitors = PHENOCONVERT.get(gene, {})
        for strength in ["strong_inhibitors", "moderate_inhibitors"]:
            found = [m for m in meds if m in inhibitors.get(strength, [])]
            if found:
                if strength == "strong_inhibitors":
                    gene_state[gene]["functional"] = "Poor Metabolizer"
                    gene_state[gene]["caused_by"].extend(found)
                    log.append(f"{gene}: Genotype = {gene_state[gene]['genotype']}, adjusted to Poor Metabolizer due to {', '.join(found)} (strong inhibitor).")
                elif strength == "moderate_inhibitors" and gene_state[gene]["functional"] != "Poor Metabolizer":
                    gene_state[gene]["functional"] = "Intermediate Metabolizer"
                    gene_state[gene]["caused_by"].extend(found)
                    log.append(f"{gene}: Genotype = {gene_state[gene]['genotype']}, adjusted to Intermediate Metabolizer due to {', '.join(found)} (moderate inhibitor).")
        found_inducers = [m for m in meds if m in inhibitors.get("inducers", [])]
        if found_inducers:
            gene_state[gene]["functional"] = "Ultra-rapid Metabolizer"
            gene_state[gene]["caused_by"].extend(found_inducers)
            log.append(f"{gene}: Genotype = {gene_state[gene]['genotype']}, adjusted to Ultra-rapid Metabolizer due to {', '.join(found_inducers)} (inducer).")
    # Reconstruct gene/phenotype pairs
    for gene, info in gene_state.items():
        functional_genes.append((gene, info["functional"]))
    return functional_genes, gene_state

def create_pdf_report(filename, genes, functional_genes, gene_state, active_meds, recommendations, polypharmacy_warnings, flowsheet_all, phenolog, smartnote_lines):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, "PGx-Guided Behavioral Health CDS Report", ln=1, align='C')
    pdf.set_font("Arial", style="I", size=9)
    pdf.set_font("Arial", size=12)

    pdf.ln(5)
    pdf.cell(0, 10, "Medications Assessed:", ln=1)
    for med in active_meds:
        pdf.cell(0, 8, f"- {med}", ln=1)
    pdf.ln(3)
    pdf.cell(0, 10, "Gene Metabolism Table:", ln=1)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 8, "Gene    Genotype Phenotype   Functional Phenotype   Caused by", ln=1)
    for gene in gene_state:
        genotype = gene_state[gene]["genotype"]
        func = gene_state[gene]["functional"]
        caused_by = ", ".join(gene_state[gene]["caused_by"])
        line = f"{gene:8} {genotype:18} {func:20} {caused_by}"
        pdf.cell(0, 8, line, ln=1)
    pdf.set_font("Arial", size=12)
    pdf.ln(2)
    pdf.cell(0, 10, "Recommendations & Risks:", ln=1)
    for _, rec_string, rec in recommendations:
        pdf.multi_cell(0, 8, f"{rec_string}: {rec}")
    if polypharmacy_warnings:
        pdf.cell(0, 10, "Polypharmacy Warnings:", ln=1)
        for warning in polypharmacy_warnings:
            pdf.multi_cell(0, 8, warning)
    pdf.cell(0, 10, "Flowsheet Prompts:", ln=1)
    for prompt in flowsheet_all:
        pdf.multi_cell(0, 8, prompt)
    pdf.cell(0, 10, "Phenoconversion Log:", ln=1)
    for log in phenolog:
        pdf.multi_cell(0, 8, log)
    pdf.cell(0, 10, "Provider Smart Note:", ln=1)
    for line in smartnote_lines:
        pdf.multi_cell(0, 8, line)
    pdf.output(filename)

# ----------------------- Streamlit UI -----------------------
st.set_page_config(page_title="PGx CDS Dashboard", layout="wide")
st.markdown(
    """
    <div style="background-color:#fff3cd;padding:16px;border-radius:8px;border:1px solid #ffeeba;margin-bottom:16px;">
    <strong>DISCLAIMER:</strong> <br>
    This dashboard is a prototype for demonstration and educational purposes only.
    <br>
    It is <span style="color:#dc3545;"><strong>NOT validated for clinical use</strong></span> and should NOT be used to guide actual medical decisions or patient care.
    </div>
    """,
    unsafe_allow_html=True
)

with st.sidebar:
    st.title("🩺 PGx CDS Dashboard")
    st.markdown(
        "Upload a **PGx panel report** and enter psychiatric/anti-anxiety medications for clinical decision support. Powered by Nursing Informatics.")
    uploaded_file = st.file_uploader("PGx Report (PDF or TXT)", type=["pdf", "txt"])

    selected_meds = st.multiselect(
        "Select Medications (type to search, select multiple):",
        options=ALL_MEDS_DISPLAY,
        default=[]
    )

    if st.button("Clear All Medications"):
        selected_meds.clear()
        st.experimental_rerun()

    # <-- Put the symptom selector OUTSIDE the clear button logic! -->
    symptom = st.selectbox(
        "Observed Symptom",
        ["None", "tremor", "agitation", "sedation", "QT prolongation", "toxicity", "orthostatic hypotension"]
    )

    st.markdown("---")
    st.markdown("**Work in Process by Barry Ohearn, RN, MSN-Informatics Candidate (WGU, 2025).**")
    st.markdown("_Precision support for behavioral health medication management_")

st.markdown("# 🧬 PGx-Informed CDS Clinical Dashboard")
st.markdown("#### A dynamic clinical tool for nurse/provider medication safety and personalized care.")

if uploaded_file and selected_meds:
    # Parse and process
    if uploaded_file.type == "application/pdf":
        raw_text = parse_pdf(uploaded_file)
    else:
        raw_text = uploaded_file.read().decode('utf-8')
    genes = extract_genes_from_text(raw_text)

    # Normalize selected meds for CDS logic
    meds_mapped = {}
    for disp in selected_meds:
        generic = disp.split(' ')[0].lower()
        meds_mapped[generic] = disp
    active_meds_norm = list(meds_mapped.keys())
    active_meds_disp = list(meds_mapped.values())

    # ----- Phenoconversion -----
    phenolog = []
    functional_genes, gene_state = phenoconvert_genes(genes, active_meds_norm, phenolog)

    # Metrics
    high_risk_count = 0
    polypharmacy_count = 0
    recommendations = []
    smartnote_lines = []
    polypharmacy_warnings = []
    gene_med_tracker = {}

    # ----- CDS Logic -----
    shown_recs = set()
    for gene, phenotype in functional_genes:
        for med in active_meds_norm:
            key = (gene, phenotype, med)
            rec_string = f"{gene} ({phenotype}) + {DISPLAY_NAME.get(med, med.capitalize())}"
            if key in PGX_FACTORS and rec_string not in shown_recs:
                prior_risk = PRIOR_RISKS.get(med, 0.05)
                pgx_factor = PGX_FACTORS.get(key, 1)
                symptom_factor = 2 if symptom in ["tremor", "agitation", "QT prolongation", "toxicity", "orthostatic hypotension"] else 1
                risk = min(prior_risk * pgx_factor * symptom_factor, 1.0)
                comment = CLINICAL_COMMENTS.get(key, "")
                rec = f"Estimated risk: {int(risk*100)}%. [{gene} metabolism: {phenotype}]. {comment}"
                smartnote_lines.append(f"- {rec_string}: {rec}")
                shown_recs.add(rec_string)
                # Polypharmacy
                enzyme = (gene, phenotype)
                gene_med_tracker.setdefault(enzyme, set()).add(med)
                # For metrics
                if risk > 0.2:
                    high_risk_count += 1
                recommendations.append((risk, rec_string, rec))

    for enzyme, meds in gene_med_tracker.items():
        meds_set = list(set(meds))
        if len(meds_set) > 1:
            polypharmacy_count += 1
            polypharmacy_warnings.append(
                f"⚠️ Polypharmacy alert: {', '.join([DISPLAY_NAME.get(m, m.capitalize()) for m in meds_set])} all metabolized by {enzyme[0]}. ↑ risk of drug-drug interaction and toxicity."
            )

    # ----- Dashboard Metrics -----
    colA, colB, colC = st.columns(3)
    colA.metric("🔴 High-Risk Findings", high_risk_count)
    colB.metric("🟡 Polypharmacy Alerts", polypharmacy_count)
    colC.metric("🧬 Markers Detected", len(set(genes)))

    st.markdown("---")

    # ----- Main Layout -----
    left_col, right_col = st.columns([1.2, 2])

    with left_col:
        st.subheader("🧬 Gene Metabolism Table")
        if genes:
            df = pd.DataFrame([
                {
                    "Gene": gene,
                    "Genotype Phenotype": gene_state[gene]["genotype"],
                    "Functional Phenotype": gene_state[gene]["functional"],
                    "Caused by Drugs": ", ".join(gene_state[gene]["caused_by"])
                } for gene in gene_state
            ])
            st.dataframe(df, hide_index=True)
        else:
            st.info("No recognized gene/phenotype pairs found.")
        st.subheader("💊 Medication List")
        for med in active_meds_disp:
            st.markdown(f"- **{med}**")

    with right_col:
        st.subheader("🔎 Recommendations & Risks")
        if recommendations:
            for risk, rec_string, rec in sorted(recommendations, key=lambda x: -x[0]):
                if risk > 0.2:
                    st.error(f"⚠️ {rec_string}: {rec}")
                else:
                    st.info(f"{rec_string}: {rec}")
        else:
            st.info("No specific recommendations based on current rules.")
        if polypharmacy_warnings:
            for warning in polypharmacy_warnings:
                st.warning(warning)
        with st.expander("📋 Dynamic Flowsheet Prompts"):
            flowsheet_all = set()
            for gene, phenotype in functional_genes:
                for med in active_meds_norm:
                    prompts = FLOWSHEET_PROMPTS.get((gene, phenotype, med), [])
                    for prompt in prompts:
                        flowsheet_all.add(f"{DISPLAY_NAME.get(med, med.capitalize())}: {prompt}")
            if flowsheet_all:
                for prompt in sorted(flowsheet_all):
                    st.write(f"- {prompt}")
            else:
                st.write("No special prompts for these combinations.")
        with st.expander("🧪 Phenoconversion Log"):
            if phenolog:
                for log in phenolog:
                    st.write(f"- {log}")
            else:
                st.write("No phenotype adjustments by inhibitors/inducers.")

    st.markdown("---")

    st.subheader("📝 Provider Smart Note (Copy to Chart)")
    if smartnote_lines:
        st.code('\n'.join(smartnote_lines), language="markdown")
    else:
        st.info("No CDS findings to summarize.")

    # ----- PDF Export -----
    if st.button("Download PDF Summary Report"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            create_pdf_report(
                tmp_pdf.name,
                genes, functional_genes, gene_state, active_meds_disp,
                recommendations, polypharmacy_warnings, flowsheet_all, phenolog, smartnote_lines
            )
            with open(tmp_pdf.name, "rb") as f:
                st.download_button(
                    label="Click to Download PDF",
                    data=f,
                    file_name="PGx_CDS_Report.pdf",
                    mime="application/pdf"
                )

    # ----- CDS Logic JSON -----
    with st.expander("Show CDS Logic Snapshot (JSON)"):
        st.json({
            "genes": genes,
            "medications": active_meds_disp,
            "symptom": symptom,
            "recommendations": [x[1] + ": " + x[2] for x in recommendations],
            "polypharmacy_warnings": polypharmacy_warnings,
            "flowsheet_prompts": list(flowsheet_all),
            "phenoconversion_log": phenolog
        })

else:
    st.info("Upload a PGx result and enter one or more active medications to begin.")

