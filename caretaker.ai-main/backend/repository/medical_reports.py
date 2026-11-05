from tables.medical_reports import MedicalReport
import config


def create_medical_report(db, care_recipient_id: int, filename: str, mime_type: str, data: bytes):
    report = MedicalReport(
        care_recipient_id=care_recipient_id,
        filename=filename,
        mime_type=mime_type,
        data=data,
    )
    try:
        print(f"[repo.medical_reports] DB URL: {getattr(config, 'DATABASE_URL', 'unknown')}")
        db.add(report)
        db.commit()
        db.refresh(report)
        # confirm count for this recipient
        try:
            cnt = db.query(MedicalReport).filter(MedicalReport.care_recipient_id == care_recipient_id).count()
            print(f"[repo.medical_reports] After insert, count for recipient {care_recipient_id} = {cnt}")
        except Exception as qex:
            print("[repo.medical_reports] Could not query count after insert:", qex)
        return report
    except Exception as e:
        print("[repo.medical_reports] Exception while creating report:", e)
        try:
            db.rollback()
        except Exception:
            pass
        raise


def list_reports_for_recipient(db, care_recipient_id: int):
    return db.query(MedicalReport).filter(MedicalReport.care_recipient_id == care_recipient_id).all()


def delete_medical_report(db, report_id: int):
    report = db.query(MedicalReport).filter(MedicalReport.id == report_id).first()
    if report:
        # Delete associated lab values linked to this report
        try:
            from tables.medical_conditions import LabValue, ConditionHistory, MedicalAlert
            deleted_labs = db.query(LabValue).filter(LabValue.report_id == report_id).delete(synchronize_session='fetch')
            deleted_history = db.query(ConditionHistory).filter(ConditionHistory.report_id == report_id).delete(synchronize_session='fetch')
            print(f"[repo.medical_reports] Cleaned up {deleted_labs} lab values, {deleted_history} condition history entries for report {report_id}")
        except Exception as e:
            print(f"[repo.medical_reports] Cleanup warning: {e}")
        db.delete(report)
        db.commit()
        return True
    return False
