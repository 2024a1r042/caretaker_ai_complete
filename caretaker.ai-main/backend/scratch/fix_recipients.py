import sys

path = r'e:\model_test\caretaker\backend\routes\recipients.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
for i, line in enumerate(lines):
    if 'async def update_allergy' in line:
        start_idx = i
        break

end_idx = -1
for i, line in enumerate(lines):
    if 'priority = {"critical": 4' in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_content = lines[:start_idx + 2]
    new_content.append('    allg = db.query(Allergy).filter(Allergy.allergy_id == all_id, Allergy.care_recipient_id == recipient_id).first()\n')
    new_content.append('    if not allg: raise HTTPException(404, "Allergy not found")\n')
    new_content.append('    \n')
    new_content.append('    allg.allergen = data.allergen\n')
    new_content.append('    allg.allergy_type = AllergyType(data.allergy_type)\n')
    new_content.append('    allg.reaction = data.reaction\n')
    new_content.append('    allg.severity = data.severity\n')
    new_content.append('    allg.status = AllergyStatus(data.status)\n')
    new_content.append('    db.commit()\n')
    new_content.append('    return {"code": 200, "status": "success", "message": "Allergy updated"}\n')
    new_content.append('\n')
    new_content.append('# Recommendations\n')
    new_content.append('@router.get("/care-recipients/{recipient_id}/recommendations", response_model=ResponseSchema)\n')
    new_content.append('@router.get("/recipients/{recipient_id}/recommendations", response_model=ResponseSchema)\n')
    new_content.append('async def get_recommendations(recipient_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):\n')
    new_content.append('    from tables.medical_recommendations import MedicalRecommendation\n')
    new_content.append('    recs = db.query(MedicalRecommendation).filter(\n')
    new_content.append('        MedicalRecommendation.care_recipient_id == recipient_id\n')
    new_content.append('    ).order_by(MedicalRecommendation.created_at.desc()).limit(15).all()\n')
    new_content.append('\n')
    new_content.append('    latest_recs = {}\n')
    new_content.append('    for r in recs:\n')
    new_content.append('        if r.metric not in latest_recs:\n')
    new_content.append('            latest_recs[r.metric] = r\n')
    new_content.append('    \n')
    new_content.append('    results = []\n')
    new_content.append('    for r in latest_recs.values():\n')
    
    new_content.extend(lines[end_idx - 1:]) # end_idx - 1 because we want the results.append line which was merged
    
    # Wait, end_idx was searching for priority.
    # Looking at view_file result:
    # 1102: from tables.allergies import Allergy, AllergyType, AllergyStatus
    # 1103: results.append({
    
    # So end_idx 1103 is results.append. 
    # Let me re-read exactly.
    
    # Actually, I'll just find where "results.append({" starts
    append_idx = -1
    for i, line in enumerate(lines):
        if 'results.append({' in line:
            append_idx = i
            break
            
    if append_idx != -1:
         new_content = lines[:start_idx + 2]
         new_content.append('    allg = db.query(Allergy).filter(Allergy.allergy_id == all_id, Allergy.care_recipient_id == recipient_id).first()\n')
         new_content.append('    if not allg: raise HTTPException(404, "Allergy not found")\n')
         new_content.append('    \n')
         new_content.append('    allg.allergen = data.allergen\n')
         new_content.append('    allg.allergy_type = AllergyType(data.allergy_type)\n')
         new_content.append('    allg.reaction = data.reaction\n')
         new_content.append('    allg.severity = data.severity\n')
         new_content.append('    allg.status = AllergyStatus(data.status)\n')
         new_content.append('    db.commit()\n')
         new_content.append('    return {"code": 200, "status": "success", "message": "Allergy updated"}\n')
         new_content.append('\n')
         new_content.append('# Recommendations\n')
         new_content.append('@router.get("/care-recipients/{recipient_id}/recommendations", response_model=ResponseSchema)\n')
         new_content.append('@router.get("/recipients/{recipient_id}/recommendations", response_model=ResponseSchema)\n')
         new_content.append('async def get_recommendations(recipient_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):\n')
         new_content.append('    from tables.medical_recommendations import MedicalRecommendation\n')
         new_content.append('    recs = db.query(MedicalRecommendation).filter(\n')
         new_content.append('        MedicalRecommendation.care_recipient_id == recipient_id\n')
         new_content.append('    ).order_by(MedicalRecommendation.created_at.desc()).limit(15).all()\n')
         new_content.append('\n')
         new_content.append('    latest_recs = {}\n')
         new_content.append('    for r in recs:\n')
         new_content.append('        if r.metric not in latest_recs:\n')
         new_content.append('            latest_recs[r.metric] = r\n')
         new_content.append('    \n')
         new_content.append('    results = []\n')
         new_content.append('    for r in latest_recs.values():\n')
         new_content.extend(lines[append_idx:])
         
         with open(path, 'w', encoding='utf-8') as f:
             f.writelines(new_content)
         print("File restored successfully.")
    else:
         print("Could not find results.append index.")
else:
    print(f"Could not find indices: {start_idx}, {end_idx}")
