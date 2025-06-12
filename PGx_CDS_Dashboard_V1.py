"""
===============================================================================
PGx-Guided Behavioral Health CDS Dashboard – Prototype

AUTHOR: Barry Ohearn, RN, MSN-Informatics Candidate (WGU, 2025)
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
2. Launch the app using: streamlit run PGx_CDS_Dashboard_V1.py
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
    gen, disp = normalize_med_name(med)
    if disp not in ALL_MEDS_DISPLAY:
        ALL_MEDS_DISPLAY.append(disp)
# ----------------------- Drug Class Mapping -----------------------
DRUG_CLASSES = {
    # Antipsychotics
    "aripiprazole": "Antipsychotic",
    "risperidone": "Antipsychotic",
    "olanzapine": "Antipsychotic",
    "quetiapine": "Antipsychotic",
    "ziprasidone": "Antipsychotic",
    "haloperidol": "Antipsychotic",
    # SSRIs
    "escitalopram": "SSRI",
    "citalopram": "SSRI",
    "paroxetine": "SSRI",
    "fluoxetine": "SSRI",
    "sertraline": "SSRI",
    # SNRIs
    "venlafaxine": "SNRI",
    "duloxetine": "SNRI",
    # Mood stabilizers
    "lamotrigine": "Mood stabilizer",
    "carbamazepine": "Mood stabilizer",
    "valproate": "Mood stabilizer",
    # Anxiolytics/Sedatives
    "clonazepam": "Benzodiazepine",
    "lorazepam": "Benzodiazepine",
    "zolpidem": "Sedative/Hypnotic",
    "buspirone": "Anxiolytic",
    # Add others as needed
}
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
    ("CYP3A5", "Poor Metabolizer", "quetiapine"): 0.5,
    ("CYP3A5", "Intermediate Metabolizer", "quetiapine"): 0.8,
    
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
    ("CYP2C9", "Poor Metabolizer", "phenytoin"): 2.2,
    ("CYP2C9", "Intermediate Metabolizer", "phenytoin"): 1.4,
    ("CYP2C9", "Poor Metabolizer", "valproate"): 1.4,
    ("UGT1A4", "Poor Metabolizer", "lamotrigine"): 1.3,
    ("HLA-A*31:01", "Positive", "carbamazepine"): 5,  # strong contraindication
    ("HLA-A*31:01", "Positive", "oxcarbazepine"): 5,
    ("HLA-B*15:02", "Positive", "carbamazepine"): 5,  # strong contraindication
    ("HLA-B*15:02", "Positive", "oxcarbazepine"): 5,
    
    # --- Anxiolytics/Sleep ---
    ("CYP3A4", "Decreased Function", "alprazolam"): 1.7,
    ("CYP2C19", "Poor Metabolizer", "diazepam"): 1.6,
    ("CYP3A4", "Decreased Function", "zolpidem"): 1.5,
    ("UGT2B15", "Poor Metabolizer", "lorazepam"): 2.2,
    ("UGT2B15", "Poor Metabolizer", "oxazepam"): 2.2,
    
    # --- Pharmacodynamic/Transporters/Other ---
    ("HTR2A", "A/A", "sertraline"): 0.7,
    ("SLC6A4", "S/S", "sertraline"): 0.7,
    ("COMT", "Val/Val", "bupropion"): 0.8,
    ("CYP2B6", "Poor Metabolizer", "bupropion"): 2,
    ("CYP2B6", "Intermediate Metabolizer", "bupropion"): 1.2,
    ("MTHFR", "C/T", "any"): 0.2,  # placeholder
    ("MTHFR", "A/C", "any"): 0.2,
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

    # --- Expanded Tempus Panel Genes ---

    # CYP2B6 - relevant for bupropion
    ("CYP2B6", "Poor Metabolizer", "bupropion"): ["Monitor for agitation or insomnia", "Assess for bupropion toxicity (e.g., seizures)"],
    ("CYP2B6", "Intermediate Metabolizer", "bupropion"): ["Monitor for bupropion side effects","Assess efficacy at usual dose"],

    # CYP2C9 - impacts phenytoin/valproate
    ("CYP2C9", "Poor Metabolizer", "phenytoin"): ["Monitor phenytoin levels closely","Assess for ataxia or nystagmus"],
    ("CYP2C9", "Poor Metabolizer", "valproate"): ["Monitor LFTs","Check for GI side effects"],

    # CYP3A5 - less common, but can impact clearance
    ("CYP3A5", "Poor Metabolizer", "quetiapine"): ["Monitor for sedation","Assess for excessive drowsiness"],
    ("CYP3A5", "Intermediate Metabolizer", "quetiapine"): ["Monitor for quetiapine side effects","Check for dizziness"],

    # UGT1A4 - impacts lamotrigine
    ("UGT1A4", "Poor Metabolizer", "lamotrigine"): ["Monitor for increased lamotrigine side effects","Assess for dizziness or diplopia"],

    # UGT2B15 - impacts lorazepam, oxazepam
    ("UGT2B15", "Poor Metabolizer", "lorazepam"): ["Monitor for excessive sedation","Assess for respiratory depression"],
    ("UGT2B15", "Poor Metabolizer", "oxazepam"): ["Monitor for prolonged sedation","Check for confusion"],

    # HLA-A*31:01 - SJS/TEN risk
    ("HLA-A*31:01", "Positive", "carbamazepine"): ["Do NOT administer—risk of severe skin reaction (SJS/TEN)","Alert provider immediately"],
    ("HLA-A*31:01", "Positive", "oxcarbazepine"): ["Do NOT administer—risk of severe skin reaction (SJS/TEN)","Alert provider immediately"],

    # HLA-B*15:02 - SJS/TEN risk
    ("HLA-B*15:02", "Positive", "carbamazepine"): ["Do NOT administer—risk of Stevens-Johnson Syndrome","Alert provider immediately"],
    ("HLA-B*15:02", "Positive", "oxcarbazepine"): ["Do NOT administer—risk of Stevens-Johnson Syndrome","Alert provider immediately"],

    # MTHFR - not directly actionable, but can document
    ("MTHFR", "C/T", "any"): ["Document folate metabolism variant","Consider folate supplementation if clinically indicated"],
    ("MTHFR", "A/C", "any"): ["Document folate metabolism variant","Monitor for neuropsychiatric symptoms if relevant"],

}

CLINICAL_COMMENTS = {
    # --- Antipsychotics ---
    ("CYP2D6", "Poor Metabolizer", "risperidone"):
        "CYP2D6 Poor Metabolizer status reduces risperidone clearance, causing the drug to accumulate in the bloodstream. "
        "This increases the risk of extrapyramidal side effects (EPS), sedation, and toxicity. "
        "Consider lowering the dose or switching to a medication less dependent on CYP2D6 metabolism. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/) | [PharmGKB Risperidone](https://www.pharmgkb.org/chemical/PA451257).",

    ("CYP2D6", "Poor Metabolizer", "aripiprazole"):
        "Poor CYP2D6 metabolism slows aripiprazole clearance, raising blood concentrations and increasing risk of side effects such as akathisia, sedation, and QT prolongation. "
        "A dose reduction or alternative therapy may be appropriate. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/) | [PharmGKB Aripiprazole](https://www.pharmgkb.org/chemical/PA10026).",

    ("CYP2D6", "Poor Metabolizer", "haloperidol"):
        "Reduced CYP2D6 function decreases haloperidol metabolism, which can lead to higher blood levels and increased risk of EPS, neurotoxicity, or cardiac adverse events. Careful monitoring or dose adjustment is recommended. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/) | [PharmGKB Haloperidol](https://www.pharmgkb.org/chemical/PA449841).",

    ("CYP3A4", "Decreased Function", "quetiapine"):
        "Quetiapine is primarily metabolized by CYP3A4. Decreased function can lead to elevated quetiapine concentrations, increasing sedation, orthostatic hypotension, and risk of toxicity. Dose reduction may be needed. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/) | [PharmGKB Quetiapine](https://www.pharmgkb.org/chemical/PA451201).",

    ("CYP1A2", "Ultra-rapid Metabolizer", "olanzapine"):
        "Ultra-rapid CYP1A2 metabolism increases olanzapine clearance, potentially resulting in subtherapeutic levels and decreased efficacy, especially in smokers. Consider higher doses or alternate agents. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/) | [PharmGKB Olanzapine](https://www.pharmgkb.org/chemical/PA450688).",

    ("CYP1A2", "Ultra-rapid Metabolizer", "clozapine"):
        "Ultra-rapid metabolism leads to low clozapine levels, risking therapeutic failure. Monitor response and consider dose adjustment. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/) | [PharmGKB Clozapine](https://www.pharmgkb.org/chemical/PA449061).",
    
    ("CYP3A4", "Decreased Function", "ziprasidone"):
        "Ziprasidone is primarily metabolized by CYP3A4, but there are currently no actionable pharmacogenomic recommendations. Standard care applies. "
        "[PharmGKB Ziprasidone](https://www.pharmgkb.org/chemical/PA451974).",

    # --- SSRIs/SNRIs ---
    ("CYP2C19", "Ultra-rapid Metabolizer", "citalopram"):
        "CYP2C19 ultra-rapid metabolism clears citalopram more quickly, which can result in subtherapeutic plasma concentrations and poor antidepressant response. "
        "Consider an SSRI less affected by CYP2C19 or increase the dose if clinically appropriate. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Citalopram](https://www.pharmgkb.org/chemical/PA449015).",

    ("CYP2C19", "Poor Metabolizer", "citalopram"):
        "Poor CYP2C19 metabolism raises citalopram levels, increasing the risk of QT prolongation and other side effects. Dose reduction or close monitoring is recommended. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Citalopram](https://www.pharmgkb.org/chemical/PA449015).",

    ("CYP2C19", "Ultra-rapid Metabolizer", "escitalopram"):
        "Faster metabolism of escitalopram may cause lower drug levels and reduced antidepressant effect. Monitor for lack of response. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Escitalopram](https://www.pharmgkb.org/chemical/PA10074).",

    ("CYP2C19", "Poor Metabolizer", "escitalopram"):
        "Reduced metabolism raises escitalopram blood levels, increasing the risk of side effects, including QT prolongation. Consider lower doses or more frequent monitoring. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Escitalopram](https://www.pharmgkb.org/chemical/PA10074).",

    ("CYP2D6", "Poor Metabolizer", "paroxetine"):
        "CYP2D6 Poor Metabolizer status leads to slow paroxetine clearance, resulting in drug accumulation and a higher risk of anticholinergic effects, sedation, and sexual dysfunction. Dose reduction or switching medications may be needed. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Paroxetine](https://www.pharmgkb.org/chemical/PA450801).",

    ("CYP2D6", "Poor Metabolizer", "fluoxetine"):
        "Reduced CYP2D6 activity increases fluoxetine levels, elevating risk of side effects such as insomnia, GI upset, and serotonin syndrome. Monitor and consider dose reduction. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Fluoxetine](https://www.pharmgkb.org/chemical/PA449673).",

    ("CYP2D6", "Poor Metabolizer", "venlafaxine"):
        "Venlafaxine is metabolized to its active metabolite by CYP2D6. Poor metabolism may cause higher venlafaxine and lower active metabolite levels, leading to reduced efficacy and increased side effects. Adjust therapy as needed. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Venlafaxine](https://www.pharmgkb.org/chemical/PA451866).",

    ("CYP2D6", "Poor Metabolizer", "duloxetine"):
        "Slow CYP2D6 metabolism raises duloxetine concentrations, increasing the risk of side effects such as nausea, hypertension, and liver toxicity. Lower doses or alternative therapy may be appropriate. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/cpic-guideline-for-ssri-and-snri-antidepressants/) | [PharmGKB Duloxetine](https://www.pharmgkb.org/chemical/PA10066).",

    # --- Mood Stabilizers/Other Psych ---
     ("CYP2C19", "Poor Metabolizer", "lamotrigine"):
        "Poor CYP2C19 metabolism may result in higher lamotrigine levels, which can increase the risk of rash and other adverse effects. Monitor closely. "
        "[PharmGKB Lamotrigine](https://www.pharmgkb.org/chemical/PA450164).",

    ("CYP2C9", "Poor Metabolizer", "valproate"):
        "Valproate clearance is reduced in CYP2C9 poor metabolizers, raising blood levels and risk of toxicity, including liver damage and thrombocytopenia. Dose adjustment and monitoring recommended. "
        "[PharmGKB Valproic Acid](https://www.pharmgkb.org/chemical/PA451846).",

    ("CYP2C19", "Ultra-rapid Metabolizer", "clobazam"):
        "Faster metabolism may result in lower clobazam levels, possibly reducing efficacy in seizure control or anxiety treatment. "
        "[PharmGKB Clobazam](https://www.pharmgkb.org/chemical/PA10888).",

    # --- Anxiety/Sleep ---
    ("CYP3A4", "Decreased Function", "alprazolam"):
        "Decreased CYP3A4 activity leads to slower alprazolam metabolism, increasing sedation, confusion, and fall risk, especially in older adults. "
        "[PharmGKB Alprazolam](https://www.pharmgkb.org/chemical/PA448333).",

    ("CYP2C19", "Poor Metabolizer", "diazepam"):
        "Poor metabolism of diazepam leads to drug accumulation, prolonging sedation and increasing risk of adverse effects. "
        "[CPIC Guideline](https://cpicpgx.org/guidelines/) | [PharmGKB Diazepam](https://www.pharmgkb.org/chemical/PA449283).",

    ("CYP3A4", "Decreased Function", "zolpidem"):
        "Zolpidem is cleared by CYP3A4. Decreased function can result in prolonged sedation and next-day drowsiness. Lower doses or alternate sleep aids may be needed. "
        "[PharmGKB Zolpidem](https://www.pharmgkb.org/chemical/PA451976).",
    ("CYP2D6", "Poor Metabolizer", "buspirone"):
        "Buspirone: No clinically significant pharmacogenomic drug-gene interactions have been established. Standard dosing and monitoring apply. "
        "[PharmGKB Buspirone](https://www.pharmgkb.org/chemical/PA448689).",
    ("CYP3A4", "Decreased Function", "buspirone"):
        "Buspirone: While metabolized by CYP3A4, no actionable gene-drug interactions are established in clinical guidelines. "
        "[PharmGKB Buspirone](https://www.pharmgkb.org/chemical/PA448689).",
    ("CYP3A4", "Decreased Function", "clonazepam"):
        "Clonazepam: CYP3A4 plays a role in metabolism, but no clinically actionable PGx recommendations are currently available. "
        "[PharmGKB Clonazepam](https://www.pharmgkb.org/chemical/PA449050).",

    ("UGT1A4", "Poor Metabolizer", "clonazepam"):
        "Clonazepam: Glucuronidation is the major metabolic pathway, but current evidence does not support actionable pharmacogenomic guidance. "
        "[PharmGKB Clonazepam](https://www.pharmgkb.org/chemical/PA449050).",

    ("UGT2B7", "Poor Metabolizer", "lorazepam"):
        "Lorazepam is metabolized by glucuronidation (UGT2B7). No clinically significant pharmacogenomic effects have been reported. Use standard dosing and monitoring. "
        "[PharmGKB Lorazepam](https://www.pharmgkb.org/chemical/PA450267).",
    # --- Transporter/Pharmacodynamic Markers ---
    ("HTR2A", "A/A", "sertraline"):
        "HTR2A A/A genotype may reduce SSRI efficacy, possibly requiring dose escalation or alternative antidepressants. "
        "[PharmGKB Sertraline](https://www.pharmgkb.org/chemical/PA451333).",

    ("SLC6A4", "S/S", "sertraline"):
        "S/S genotype of SLC6A4 (5-HTTLPR) is associated with poorer SSRI tolerance and reduced likelihood of response. Consider alternative therapy if ineffective or poorly tolerated. "
        "[PharmGKB Sertraline](https://www.pharmgkb.org/chemical/PA451333).",

    ("COMT", "Val/Val", "bupropion"):
        "COMT Val/Val may increase dopamine breakdown, possibly reducing bupropion efficacy in treating depression or ADHD. Clinical significance varies. "
        "[PharmGKB Bupropion](https://www.pharmgkb.org/chemical/PA448687).",
    # --- Expanded Tempus Panel Clinical Comments ---

    ("CYP2B6", "Poor Metabolizer", "bupropion"):
        "CYP2B6 Poor Metabolizer status impairs bupropion clearance, increasing plasma concentrations and risk of adverse effects such as agitation, insomnia, or, rarely, seizures. Dose reduction or alternative therapy may be needed. "
        "[FDA Label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=4956af38-182a-4015-a945-67e40bd38772) | [PharmGKB Bupropion](https://www.pharmgkb.org/chemical/PA448687).",

    ("CYP2B6", "Intermediate Metabolizer", "bupropion"):
        "Intermediate CYP2B6 activity can moderately reduce bupropion clearance, raising exposure and side effect risk. Monitor for adverse reactions and adjust dose if clinically warranted. "
        "[FDA Label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=4956af38-182a-4015-a945-67e40bd38772) | [PharmGKB Bupropion](https://www.pharmgkb.org/chemical/PA448687).",

    ("CYP2C9", "Poor Metabolizer", "phenytoin"):
        "CYP2C9 Poor Metabolizer status leads to significantly reduced phenytoin clearance, increasing toxicity risk (e.g., ataxia, nystagmus, CNS effects). Consider alternative therapy or substantial dose reduction with frequent monitoring. "
        "[CPIC Phenytoin Guideline](https://cpicpgx.org/guidelines/guideline-for-phenytoin/) | [PharmGKB Phenytoin](https://www.pharmgkb.org/chemical/PA451094).",

    ("CYP2C9", "Poor Metabolizer", "valproate"):
        "Poor CYP2C9 metabolism can elevate valproate concentrations, increasing risk for hepatotoxicity, thrombocytopenia, and other adverse effects. Dose adjustment and regular monitoring are recommended. "
        "[FDA Label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=82d29262-c72b-48d1-8471-5d582b3496ea) | [PharmGKB Valproic Acid](https://www.pharmgkb.org/chemical/PA451846).",

    ("CYP3A5", "Poor Metabolizer", "quetiapine"):
        "Reduced CYP3A5 activity may contribute to higher quetiapine concentrations, especially in patients with decreased CYP3A4. Monitor for increased sedation and adverse effects. "
        "[FDA Label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=0584dda8-bc3c-48fe-1a90-79608f78e8a0) | [PharmGKB Quetiapine](https://www.pharmgkb.org/chemical/PA451201).",

    ("CYP3A5", "Intermediate Metabolizer", "quetiapine"):
        "Intermediate CYP3A5 activity can result in modestly increased quetiapine exposure. Monitor for sedation and titrate dose if needed. "
        "[FDA Label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=0584dda8-bc3c-48fe-1a90-79608f78e8a0) | [PharmGKB Quetiapine](https://www.pharmgkb.org/chemical/PA451201).",

    ("UGT1A4", "Poor Metabolizer", "lamotrigine"):
        "Poor UGT1A4 metabolism can slow lamotrigine clearance, increasing plasma levels and risk for adverse effects (e.g., dizziness, rash). Consider slower titration and close monitoring. "
        "[FDA Label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=0b0f0209-edbd-46f3-9bed-762cbea0d737) | [PharmGKB Lamotrigine](https://www.pharmgkb.org/chemical/PA450164).",

    ("UGT2B15", "Poor Metabolizer", "lorazepam"):
        "UGT2B15 Poor Metabolizer status reduces lorazepam clearance, increasing risk for prolonged sedation and CNS depression. Consider lower initial dosing and monitor closely, especially in older adults. "
        "[PMID: 15961980](https://pubmed.ncbi.nlm.nih.gov/15961980/) | [PharmGKB Lorazepam](https://www.pharmgkb.org/chemical/PA450267).",

    ("UGT2B15", "Poor Metabolizer", "oxazepam"):
        "Reduced UGT2B15 activity impairs oxazepam clearance, raising exposure and risk of sedation. Start with lower doses and monitor response. "
        "[PMID: 15044558](https://pubmed.ncbi.nlm.nih.gov/15044558/) | [PharmGKB Oxazepam](https://www.pharmgkb.org/chemical/PA450731).",

    ("HLA-A*31:01", "Positive", "carbamazepine"):
        "HLA-A*31:01 positivity is strongly associated with increased risk of carbamazepine-induced hypersensitivity reactions, including SJS/TEN. Do NOT initiate carbamazepine; choose alternatives. "
        "[PharmGKB Carbamazepine](https://www.pharmgkb.org/chemical/PA448785).",

    ("HLA-A*31:01", "Positive", "oxcarbazepine"):
        "Patients positive for HLA-A*31:01 have higher risk for severe cutaneous adverse reactions with oxcarbazepine. Avoid use and select non-aromatic anticonvulsants. "
        "[PharmGKB Oxcarbazepine](https://www.pharmgkb.org/chemical/PA450083).",

    ("HLA-B*15:02", "Positive", "carbamazepine"):
        "HLA-B*15:02 is associated with life-threatening SJS/TEN after carbamazepine exposure, especially in patients of Asian ancestry. **Contraindicated**—do not prescribe. "
        "[PharmGKB Carbamazepine](https://www.pharmgkb.org/chemical/PA448785).",

    ("HLA-B*15:02", "Positive", "oxcarbazepine"):
        "HLA-B*15:02 carriers are at high risk for Stevens-Johnson Syndrome and toxic epidermal necrolysis with oxcarbazepine. Avoid use—select an alternative agent. "
        "[PharmGKB Oxcarbazepine](https://www.pharmgkb.org/chemical/PA450083).",

    ("MTHFR", "C/T", "any"):
        "MTHFR variants may impact folate metabolism, but routine clinical action in psychiatric care is not established. Consider folate supplementation only if deficiency suspected or clinically indicated. "
        "[PharmGKB MTHFR](https://www.pharmgkb.org/gene/PA162373209).",

    ("MTHFR", "A/C", "any"):
        "A/C variant in MTHFR may affect folate pathways; direct pharmacogenomic action for psychiatric medication selection is not currently recommended. "
        "[PharmGKB MTHFR](https://www.pharmgkb.org/gene/PA162373209).",
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
    "buspirone": 0.02,
    "ziprasidone": 0.06,
    "clonazepam": 0.05,
    "lorazepam": 0.04,
}


# ----------------------- Utility Functions -----------------------


def parse_pdf(file):
    pdf = PdfReader(file)
    text = ''
    for page in pdf.pages:
        if page.extract_text():
            text += page.extract_text()
    return text

import re

def extract_genes_from_text(text):
    gene_panel = [
        "CYP1A2", "CYP2B6", "CYP2C19", "CYP2C9", "CYP2D6",
        "CYP3A4", "CYP3A5", "UGT1A4", "UGT2B15",
        "HTR2A", "SLC6A4", "HLA-A*31:01", "HLA-B*15:02",
        "MTHFR", "COMT"
    ]
    phenotype_keywords = [
        "Normal Metabolizer", "Poor Metabolizer", "Intermediate Metabolizer",
        "Ultra-rapid Metabolizer", "Decreased Function", "Increased Risk",
        "Positive", "Negative", "Val/Val", "A/C", "C/T", "Short/Short", "Short", "Long"
    ]
    genes = []
    found_genes = set()
    for gene in gene_panel:
        gene_stripped = gene.replace("*", "")
        for line in text.splitlines():
            line_stripped = line.replace("*", "")
            if gene_stripped in line_stripped or (
                gene.startswith("HLA-A") and "HLA-A" in line and "31:01" in line
            ) or (
                gene.startswith("HLA-B") and "HLA-B" in line and "15:02" in line
            ):
                for keyword in phenotype_keywords:
                    if keyword in line:
                        genes.append((gene, keyword))
                        found_genes.add(gene)
                        break
    for gene in gene_panel:
        if gene not in found_genes:
            genes.append((gene, "Not Reported"))
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

from fpdf import FPDF

def clean_text(text):
    # Convert any text to a latin-1-safe string for FPDF.
    # Non-latin1 characters become '?'
    return str(text).encode("latin-1", "replace").decode("latin-1")

def create_pdf_report(
    filename,
    genes,
    functional_genes,
    gene_state,
    active_meds,
    recommendations,
    polypharmacy_warnings,
    flowsheet_all,
    phenolog,
    smartnote_lines
):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, clean_text("PGx-Guided Behavioral Health CDS Report"), ln=1, align='C')
    pdf.set_font("Arial", style="I", size=9)
    pdf.set_font("Arial", size=12)

    pdf.ln(5)
    pdf.cell(0, 10, clean_text("Medications Assessed:"), ln=1)
    for med in active_meds:
        pdf.cell(0, 8, clean_text(f"- {med}"), ln=1)
    pdf.ln(3)

    # --- Gene Metabolism Table ---
    pdf.cell(0, 10, clean_text("Gene Metabolism Table:"), ln=1)
    pdf.set_font("Courier", size=10)

    # Table Header
    col_widths = [28, 36, 40, 60]  # Adjust these as needed for your data
    headers = ["Gene", "Genotype Phenotype", "Functional Phenotype", "Caused by"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, clean_text(h), border=1, align='C')
    pdf.ln()

    # Table Rows
    for gene in gene_state:
        genotype = gene_state[gene]["genotype"]
        func = gene_state[gene]["functional"]
        caused_by = ", ".join(gene_state[gene]["caused_by"])
        row = [gene, genotype, func, caused_by]
        for i, val in enumerate(row):
            pdf.cell(col_widths[i], 8, clean_text(val), border=1)
        pdf.ln()
    pdf.set_font("Arial", size=12)  # Reset font for rest of the report

    # --- Recommendations & Risks ---
    pdf.ln(2)
    pdf.cell(0, 10, clean_text("Recommendations & Risks:"), ln=1)
    for _, rec_string, rec in recommendations:
        pdf.multi_cell(0, 8, clean_text(f"{rec_string}: {rec}"), align='L')

    # --- Polypharmacy Warnings ---
    if polypharmacy_warnings:
        pdf.cell(0, 10, clean_text("Polypharmacy Warnings:"), ln=1)
        for warning in polypharmacy_warnings:
            pdf.multi_cell(0, 8, clean_text(warning), align='L')

    # --- Flowsheet Prompts ---
    pdf.cell(0, 10, clean_text("Flowsheet Prompts:"), ln=1)
    for prompt in flowsheet_all:
        pdf.multi_cell(0, 8, clean_text(prompt), align='L')

    # --- Phenoconversion Log ---
    pdf.cell(0, 10, clean_text("Phenoconversion Log:"), ln=1)
    for log in phenolog:
        pdf.multi_cell(0, 8, clean_text(log), align='L')

    # --- Provider Smart Note ---
    pdf.cell(0, 10, clean_text("Provider Smart Note:"), ln=1)
    for line in smartnote_lines:
        pdf.multi_cell(0, 8, clean_text(line), align='L')

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
  
    if st.button("Clear All Medications"):
        st.session_state.selected_meds = []
    
    selected_meds = st.multiselect(
        "Select Medications (type to search, select multiple):",
        options=ALL_MEDS_DISPLAY,
        key="selected_meds"
    )
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

    from collections import defaultdict

    # --- Class-based Polypharmacy Logic ---
    class_counter = defaultdict(list)
    for med in active_meds_norm:
        drug_class = DRUG_CLASSES.get(med)
        if drug_class:
            class_counter[drug_class].append(med)

    class_polypharmacy = {cls: meds for cls, meds in class_counter.items() if len(meds) > 1}

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
                    st.error(f"⚠️ {rec_string}:")
                    st.markdown(rec, unsafe_allow_html=True)
                else:
                    st.info(f"{rec_string}:")
                    st.markdown(rec, unsafe_allow_html=True)
        else:
            st.info("No specific recommendations based on current rules.")
        if polypharmacy_warnings:
            for warning in polypharmacy_warnings:
                st.warning(warning)
       
        # --- Class-based polypharmacy alerts ---
        if class_polypharmacy:
            for cls, meds in class_polypharmacy.items():
                med_names = [DISPLAY_NAME.get(m, m.capitalize()) for m in meds]
                st.warning(
                    f"⚠️ Multiple {cls}s selected: {', '.join(med_names)}. "
                    "Increased risk of additive side effects, interactions, and toxicity. "
                    "Review the combination carefully."
            )        
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

