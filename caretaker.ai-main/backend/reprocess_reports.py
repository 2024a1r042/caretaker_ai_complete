# Reprocess all pending medical reports for recipient 45
import sys, datetime, traceback
sys.path.insert(0, '.')

from config import SessionLocal
from tables.medical_reports import MedicalReport, ReportProcessingStatus
from tables.medical_conditions import PatientCondition, ConditionStatus, ConditionSeverity, SourceType
from tables.users import CareRecipient
from utils.summarizer import extract_text_from_bytes
from services.report_ingestion import extract_structured_report
from services.disease_detection import detect_diseases_from_report
from services.disease_progression import analyze_progression
from services.alert_engine import generate_alerts, check_monitoring_gaps
from services.medical_history_ai import calculate_risk_score
from repository import medical_history as repo

db = SessionLocal()
try:
    reports = db.query(MedicalReport).filter(
        MedicalReport.care_recipient_id == 45
    ).all()

    print("Found %d reports for recipient 45" % len(reports))
    for report in reports:
        recipient_id = report.care_recipient_id
        report_id = report.id
        print("\n" + "="*60)
        print("Processing report id=%d filename=%s" % (report_id, report.filename))
        print("  Current status: %s" % report.processing_status)

        try:
            report.processing_status = ReportProcessingStatus.processing
            db.flush()

            # 1. Extract text
            text = ""
            if report.data:
                text = extract_text_from_bytes(report.data, report.filename)
            print("  1. Text extraction: %d chars" % len(text))

            if not text:
                print("  SKIP: No text extracted")
                report.processing_status = ReportProcessingStatus.failed
                db.commit()
                continue

            # 2. Structured extraction via Gemini
            extracted = extract_structured_report(text)
            report.extracted_data = extracted
            if extracted.get("report_date"):
                try:
                    report.report_date = datetime.date.fromisoformat(extracted["report_date"])
                except (ValueError, TypeError):
                    pass
            print("  2. Structured extraction: %d diagnoses, %d labs" % (
                len(extracted.get('diagnoses', [])), len(extracted.get('lab_values', {}))))

            # 3. Disease detection
            existing = repo.get_all_conditions(db, recipient_id)
            new_diseases = detect_diseases_from_report(
                extracted, existing, db, report_id, extracted.get("report_date")
            )
            print("  3. Disease detection: %d new diseases" % len(new_diseases))

            for disease in new_diseases:
                cond = PatientCondition(
                    care_recipient_id=recipient_id,
                    disease_code=disease["disease_code"],
                    disease_name=disease["disease_name"],
                    status=ConditionStatus.active,
                    severity=ConditionSeverity.moderate,
                    first_detected=disease.get("first_detected", datetime.date.today()),
                    last_updated=disease.get("first_detected", datetime.date.today()),
                    baseline_value=disease.get("baseline_value"),
                    baseline_date=disease.get("baseline_date"),
                    confidence_score=disease.get("confidence_score", 0.5),
                    source_type=SourceType(disease.get("source_type", "lab_inferred")),
                    source_report_id=report_id,
                )
                db.add(cond)
            db.flush()

            # 4. Progression analysis
            progression = analyze_progression(
                recipient_id, extracted, report_id,
                extracted.get("report_date", ""), db
            )
            print("  4. Progression analysis done")

            # 5. Generate alerts
            generate_alerts(recipient_id, progression, db)
            print("  5. Alert generation done")

            # 6. Check monitoring gaps
            check_monitoring_gaps(recipient_id, db)

            # 7. Update risk score
            calculate_risk_score(recipient_id, db)

            # 8. Update last_report_date
            recipient = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
            if recipient:
                recipient.last_report_date = datetime.datetime.utcnow()

            report.processing_status = ReportProcessingStatus.completed
            db.commit()
            print("  Report %d processed successfully!" % report_id)

        except Exception as e:
            print("  Error processing report %d: %s" % (report_id, e))
            traceback.print_exc()
            db.rollback()
            try:
                report = db.query(MedicalReport).filter(MedicalReport.id == report_id).first()
                if report:
                    report.processing_status = ReportProcessingStatus.failed
                    db.commit()
            except:
                pass
finally:
    db.close()

print("\nAll done!")
