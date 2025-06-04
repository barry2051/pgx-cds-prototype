# pgx-cds-prototype
PGx-Guided Behavioral Health CDS Dashboard
Created by Barry Ohearn, RN, MSN-Informatics Candidate (WGU, 2025)

Overview
This project is a working prototype for a nurse-facing clinical decision support (CDS) dashboard that integrates pharmacogenomic (PGx) results into behavioral health medication management. Built with Streamlit, the tool helps nurses and providers identify high-risk gene-drug interactions, estimate individualized risk, and document findings directly in their workflow.

The goal is to move beyond generic alerts and actually provide nuanced, actionable guidance—helping nurses act as early-warning sensors for medication safety, especially in psychiatry where trial-and-error prescribing is still common.

Key Features
PGx Panel Parsing
Upload a PDF or text pharmacogenetic panel report; the app extracts gene-phenotype results automatically.

Medication Synonym Handling
Supports both brand and generic drug names (autocomplete), normalizes inputs for robust CDS logic.

Dynamic CDS Engine
Calculates Bayesian-style risk estimates for adverse drug reactions, factoring in genotype, active meds, and reported symptoms. Outputs include expanded clinical explanations based on current guidelines.

Phenoconversion Detection
Adjusts gene function in real-time when medications act as inhibitors or inducers (e.g., paroxetine as a CYP2D6 inhibitor).

Nursing Flowsheet Prompts
Generates dynamic documentation prompts based on risk factors, so frontline nurses know what to watch for.

Polypharmacy Alerts
Flags overlapping metabolism and possible drug-drug interactions, with clear warnings.

Provider Smart Note
Creates a structured summary for easy EHR charting or escalation.

PDF and JSON Export
One-click export of reports and all calculated logic for sharing or record-keeping.

Why I Built This
Informatics in behavioral health needs tools that actually work for nurses—simple to use, clinically meaningful, and transparent. Too often, CDS is either too rigid or too vague.
This dashboard is my attempt to bridge that gap: blending real-world nursing needs with the power of PGx and AI-driven logic.

How to Run
Clone this repo

Install Python 3.9+ and the requirements (pip install -r requirements.txt)

Run the app:

arduino
Copy
Edit
streamlit run <your_script_name.py>
Upload a PGx report (PDF or TXT) and select medications to get started.

Next Steps
Tying risk calculations to published clinical evidence (CPIC, PharmGKB, cohort studies)

Expanding FHIR/EHR interoperability for deployment in real-world systems

Usability feedback from nurses and behavioral health clinicians

Feedback, collaboration, and suggestions are welcome.
Let’s build clinical tools that actually make a difference.

Built in partnership with advanced AI (GPT-4/4.1), but every line and logic choice reflects a nursing lens.

Barry Ohearn
RN, MSN-Informatics Candidate, WGU (2025)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for more information.
