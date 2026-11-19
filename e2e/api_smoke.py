import httpx, datetime as dt
B="http://localhost:5173/api"
def login(email):
    c=httpx.Client(base_url=B)
    r=c.post("/auth/login",json={"email":email,"password":"Undeclared!2026"}); r.raise_for_status()
    d=r.json(); m=d["me"]["memberships"][0]
    c.headers.update({"Authorization":"Bearer "+d["access_token"],"X-Organization-Id":m["organization_id"]})
    return c,m
bad=[]
def chk(c,path,**kw):
    r=c.get(path,**kw)
    if r.status_code>=500 or r.status_code in (404,422): bad.append((path,r.status_code,r.text[:200]))
    return r
now=dt.datetime.now(dt.timezone.utc)
for email in ["dr.chen@harborview.dev","frontdesk@harborview.dev","nurse.rivera@harborview.dev","clinicadmin@harborview.dev","billing@harborview.dev","admin@undeclared.dev"]:
    c,m=login(email)
    clinic=m["clinics"][0]["id"]
    chk(c,"/dashboard",params={"clinic_id":clinic}); chk(c,"/notifications"); chk(c,"/search",params={"q":"mor"})
    if "patients:read" in m["permissions"]:
        pid=chk(c,"/patients").json()["items"][0]["id"]
        for p in ["", "/summary","/appointments","/notes"]: chk(c,f"/patients/{pid}{p}")
        if "clinical:read" in m["permissions"]:
            for p in ["/allergies","/medications","/problems","/history","/vitals","/encounters","/timeline"]: chk(c,f"/patients/{pid}{p}")
            chk(c,"/encounters"); chk(c,"/templates"); chk(c,"/orders"); chk(c,"/orders-counts")
            chk(c,f"/patients/{pid}/orders"); chk(c,f"/patients/{pid}/results"); chk(c,"/codes/icd10",params={"q":"hyper"})
            if "orders:write" in m["permissions"]: chk(c,"/catalog/labs")
    if "schedule:read" in m["permissions"]:
        chk(c,"/providers"); chk(c,"/appointment-types"); chk(c,"/front-desk/queue",params={"clinic_id":clinic})
        chk(c,"/appointments",params={"start":(now-dt.timedelta(days=3)).isoformat(),"end":(now+dt.timedelta(days=30)).isoformat(),"clinic_id":clinic,"include_cancelled":True})
        prov=c.get("/providers").json()[0]["id"]
        chk(c,f"/providers/{prov}/slots",params={"clinic_id":clinic,"day":(now+dt.timedelta(days=7)).date().isoformat()})
    if "documents:read" in m["permissions"]:
        chk(c,"/documents"); chk(c,"/documents/counts")
        if "patients:read" in m["permissions"]: chk(c,f"/patients/{pid}/documents")
    if "users:manage" in m["permissions"]: chk(c,"/staff"); chk(c,"/invitations"); chk(c,"/outbox")
    if "audit:read" in m["permissions"]: chk(c,"/audit")
    if "clinic:manage" in m["permissions"]: chk(c,"/system/status"); chk(c,"/clinics",params={"include_inactive":True})
    chk(c,"/organizations"); chk(c,"/auth/sessions")
    print("ok", email)
c,m=login("patient@harborview.dev"); chk(c,f"/patients/{m['patient_id']}"); chk(c,f"/patients/{m['patient_id']}/summary"); print("ok patient")
print("BAD:",bad)
