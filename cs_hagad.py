#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CS HAGAD v2 - Gestion scolaire graphique pour Debian."""
import os, sqlite3, hashlib, secrets, shutil, csv
from pathlib import Path
from datetime import datetime, date
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

HOME = Path.home()
DATA = HOME / ".cs_hagad"
BACKUPS = DATA / "sauvegardes"
DATA.mkdir(exist_ok=True); BACKUPS.mkdir(exist_ok=True)
DB = DATA / "cs_hagad.db"
SCHOOL = "CS HAGAD"
ROLES = ["Directeur", "Comptable", "Secrétaire", "Surveillant", "Enseignant"]

SCHEMAS = {
"eleves": [("matricule","TEXT","Matricule"),("classe","TEXT","Classe"),("nom","TEXT","Nom"),("prenom","TEXT","Prénom"),("date_naissance","TEXT","Date naissance"),("sexe","TEXT","Sexe"),("adresse","TEXT","Adresse"),("telephone_parent","TEXT","Téléphone parent")],
"classes": [("nom","TEXT","Nom classe"),("enseignant_principal","TEXT","Professeur principal"),("type","TEXT","Type")],
"matieres": [("nom","TEXT","Matière"),("classe","TEXT","Classe"),("coefficient","REAL","Coefficient")],
"notes": [("matricule_eleve","TEXT","Matricule élève"),("classe","TEXT","Classe"),("matiere","TEXT","Matière"),("periode","TEXT","Période"),("annee_scolaire","TEXT","Année scolaire"),("note","REAL","Note /20"),("coefficient","REAL","Coefficient")],
"inscriptions": [("matricule_eleve","TEXT","Matricule élève"),("annee_scolaire","TEXT","Année scolaire"),("date_inscription","TEXT","Date"),("type_inscription","TEXT","Inscription/réinscription"),("frais","REAL","Frais GNF")],
"paiements": [("matricule_eleve","TEXT","Matricule élève"),("date_paiement","TEXT","Date"),("motif","TEXT","Motif"),("mois","TEXT","Mois"),("montant","REAL","Montant GNF"),("mode","TEXT","Mode paiement"),("reference","TEXT","Référence")],
"depenses": [("date_operation","TEXT","Date"),("categorie","TEXT","Catégorie"),("libelle","TEXT","Libellé"),("montant","REAL","Montant GNF"),("caisse","TEXT","Caisse"),("reference","TEXT","Référence")],
"stocks": [("numero","TEXT","Numéro"),("designation","TEXT","Désignation"),("quantite","REAL","Quantité"),("service_demandeur","TEXT","Service demandeur"),("motif","TEXT","Motif"),("type_mouvement","TEXT","Entrée/Sortie")],
"fournisseurs": [("nom","TEXT","Nom"),("prenom","TEXT","Prénom"),("adresse","TEXT","Adresse"),("numero","TEXT","Numéro"),("quantite_demandee","REAL","Qté demandée"),("quantite_recue","REAL","Qté reçue"),("montant_total","REAL","Montant total"),("paye","REAL","Payé")],
"personnel": [("matricule","TEXT","Matricule"),("nom","TEXT","Nom"),("prenom","TEXT","Prénom"),("adresse","TEXT","Adresse"),("service","TEXT","Service"),("fonction","TEXT","Fonction"),("salaire","REAL","Salaire base")],
"paie": [("matricule_personnel","TEXT","Matricule personnel"),("mois","TEXT","Mois"),("salaire_base","REAL","Salaire base"),("primes","REAL","Primes"),("retenues","REAL","Retenues"),("avance","REAL","Avance"),("salaire_net","REAL","Salaire net")],
}
LABELS = {
"eleves":"Élèves","classes":"Classes","matieres":"Matières","notes":"Notes et évaluations",
"inscriptions":"Inscriptions / réinscriptions","paiements":"Paiements / scolarité",
"depenses":"Dépenses","stocks":"Stocks","fournisseurs":"Fournisseurs","personnel":"Personnel","paie":"Paie"
}
# permissions par rôle : onglets métier autorisés
ACCESS = {
"Directeur": set(SCHEMAS)|{"dashboard","documents","utilisateurs","audit","finance"},
"Comptable": {"dashboard","paiements","depenses","fournisseurs","paie","finance","documents","audit"},
"Secrétaire": {"dashboard","eleves","classes","inscriptions","paiements","documents"},
"Surveillant": {"dashboard","eleves","classes","notes","documents"},
"Enseignant": {"dashboard","eleves","classes","notes","documents"},
}

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    return c

def pw_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),180000).hex()
    return salt, digest

def audit(user, action, detail=""):
    with conn() as c:
        c.execute("INSERT INTO audit(date_action,utilisateur,action,detail) VALUES(?,?,?,?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),user,action,detail))

def init_db():
    with conn() as c:
        for table, fields in SCHEMAS.items():
            defs=["id INTEGER PRIMARY KEY AUTOINCREMENT"]+[f'"{n}" {t}' for n,t,_ in fields]
            c.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({",".join(defs)})')
        c.execute("""CREATE TABLE IF NOT EXISTS utilisateurs(
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, nom TEXT,
          role TEXT, salt TEXT, password_hash TEXT, actif INTEGER DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,date_action TEXT,utilisateur TEXT,action TEXT,detail TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS sequence_recu(id INTEGER PRIMARY KEY CHECK(id=1), dernier INTEGER)""")
        c.execute("INSERT OR IGNORE INTO sequence_recu VALUES(1,0)")
        c.execute("""CREATE TABLE IF NOT EXISTS parametres(cle TEXT PRIMARY KEY,valeur TEXT)""")
        c.execute("INSERT OR IGNORE INTO parametres VALUES('annee_scolaire','2026-2027')")
        if c.execute("SELECT COUNT(*) n FROM utilisateurs").fetchone()["n"] == 0:
            salt,digest=pw_hash("Admin@123")
            c.execute("INSERT INTO utilisateurs(username,nom,role,salt,password_hash) VALUES(?,?,?,?,?)",
                      ("admin","Administrateur","Directeur",salt,digest))

def backup():
    if DB.exists():
        target=BACKUPS/f"cs_hagad_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.copy2(DB,target)
        # Conserver les 30 sauvegardes les plus récentes
        old=sorted(BACKUPS.glob("cs_hagad_*.db"),key=lambda p:p.stat().st_mtime,reverse=True)
        for p in old[30:]:
            try:p.unlink()
            except OSError:pass


def rank_for_class(class_name, period, year):
    """Retourne les matricules triés par moyenne pondérée décroissante."""
    with conn() as c:
        rows = c.execute("""
            SELECT matricule_eleve,
                   CASE WHEN SUM(COALESCE(coefficient,1))=0 THEN 0
                        ELSE SUM(COALESCE(note,0)*COALESCE(coefficient,1))/SUM(COALESCE(coefficient,1)) END AS moyenne
            FROM notes
            WHERE classe=? AND (?='' OR periode=?) AND (?='' OR annee_scolaire=?)
            GROUP BY matricule_eleve
            ORDER BY moyenne DESC, matricule_eleve
        """, (class_name, period, period, year, year)).fetchall()
    return [(r["matricule_eleve"], r["moyenne"]) for r in rows]

def login_check(username,password):
    with conn() as c:
        u=c.execute("SELECT * FROM utilisateurs WHERE username=? AND actif=1",(username,)).fetchone()
    if not u:return None
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),u["salt"].encode(),180000).hex()
    return dict(u) if secrets.compare_digest(digest,u["password_hash"]) else None

def create_pdf(title, lines, path, subtitle=""):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c=canvas.Canvas(str(path),pagesize=A4); w,h=A4
    c.setFillColor(colors.HexColor("#17365D")); c.rect(0,h-92,w,92,fill=1,stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold",20); c.drawString(42,h-48,SCHOOL)
    c.setFont("Helvetica",10); c.drawString(42,h-67,"Établissement scolaire")
    c.setFillColor(colors.HexColor("#17365D")); c.setFont("Helvetica-Bold",16); c.drawString(42,h-125,title)
    if subtitle:
        c.setFont("Helvetica",9); c.setFillColor(colors.grey); c.drawString(42,h-143,subtitle)
    y=h-175
    c.setFillColor(colors.black); c.setFont("Helvetica",10)
    for line in lines:
        if y<105:
            c.showPage(); y=h-55; c.setFont("Helvetica",10)
        # Wrap long text to page width
        words=str(line).split(); current=""
        for word in words:
            candidate=(current+" "+word).strip()
            if stringWidth(candidate,"Helvetica",10)>w-84:
                c.drawString(42,y,current); y-=16; current=word
            else: current=candidate
        if current:c.drawString(42,y,current); y-=18
    c.setStrokeColor(colors.HexColor("#17365D")); c.line(42,75,230,75)
    c.setFont("Helvetica",9); c.drawString(42,60,"Signature et cachet de la direction")
    c.drawRightString(w-42,35,f"Édité le {datetime.now():%d/%m/%Y à %H:%M}")
    c.save()

class Login:
    def __init__(self, root):
        self.root=root; self.user=None
        root.title("Connexion | CS HAGAD"); root.geometry("430x500"); root.resizable(False,False)
        root.configure(bg="#eef2f7")
        panel=tk.Frame(root,bg="white",padx=34,pady=28); panel.pack(fill="both",expand=True,padx=22,pady=22)
        logo=tk.Canvas(panel,width=110,height=110,bg="white",highlightthickness=0); logo.pack(pady=(0,8))
        logo.create_oval(8,8,102,102,fill="#17365D",outline="#D9A441",width=5)
        logo.create_text(55,43,text="CS",fill="white",font=("DejaVu Sans",25,"bold"))
        logo.create_text(55,72,text="HAGAD",fill="white",font=("DejaVu Sans",12,"bold"))
        tk.Label(panel,text="CS HAGAD",font=("DejaVu Sans",20,"bold"),fg="#17365D",bg="white").pack()
        tk.Label(panel,text="Gestion intégrée de l'établissement",fg="#667085",bg="white").pack(pady=(3,20))
        tk.Label(panel,text="Nom d'utilisateur",bg="white",anchor="w").pack(fill="x")
        self.username=ttk.Entry(panel); self.username.pack(fill="x",ipady=6,pady=(4,12))
        tk.Label(panel,text="Mot de passe",bg="white",anchor="w").pack(fill="x")
        self.password=ttk.Entry(panel,show="●"); self.password.pack(fill="x",ipady=6,pady=(4,18))
        ttk.Button(panel,text="Se connecter",command=self.login).pack(fill="x",ipady=5)
        tk.Label(panel,text="Première connexion : admin / Admin@123\nChangez ce mot de passe immédiatement.",
                 fg="#9A6700",bg="white",font=("DejaVu Sans",8),justify="center").pack(pady=15)
        self.password.bind("<Return>",lambda e:self.login())
        self.username.focus_set()
    def login(self):
        u=login_check(self.username.get().strip(),self.password.get())
        if not u:
            messagebox.showerror("Connexion refusée","Identifiants incorrects ou compte désactivé."); return
        self.user=u; audit(u["username"],"Connexion","Ouverture de session")
        self.root.destroy()

class App:
    def __init__(self,root,user):
        self.root=root; self.user=user; self.role=user["role"]
        root.title("CS HAGAD | Gestion scolaire"); root.geometry("1450x850"); root.minsize(1100,680)
        self.style=ttk.Style()
        try:self.style.theme_use("clam")
        except:pass
        self.style.configure("Treeview",rowheight=25)
        self.build()

    def build(self):
        header=ttk.Frame(self.root,padding=12); header.pack(fill="x")
        ttk.Label(header,text="CS HAGAD",font=("DejaVu Sans",20,"bold"),foreground="#17365D").pack(side="left")
        ttk.Label(header,text="Gestion scolaire intégrée",font=("DejaVu Sans",11)).pack(side="left",padx=18)
        ttk.Label(header,text=f"{self.user['nom']}  |  {self.role}").pack(side="right")
        ttk.Separator(self.root).pack(fill="x")
        self.nb=ttk.Notebook(self.root); self.nb.pack(fill="both",expand=True,padx=9,pady=9)
        self.add_dashboard()
        for table,fields in SCHEMAS.items():
            if table in ACCESS[self.role]: self.add_crud(table,fields)
        if "documents" in ACCESS[self.role]: self.add_documents()
        if "finance" in ACCESS[self.role]: self.add_finance()
        if "utilisateurs" in ACCESS[self.role]: self.add_users()
        if "audit" in ACCESS[self.role]: self.add_audit()
        ttk.Label(self.root,text="CS HAGAD • Sauvegarde locale • Debian / Python / SQLite",anchor="center").pack(fill="x",pady=4)
        self.root.protocol("WM_DELETE_WINDOW",self.close)

    def add_dashboard(self):
        f=ttk.Frame(self.nb,padding=18); self.nb.add(f,text="Tableau de bord")
        ttk.Label(f,text="TABLEAU DE BORD GÉNÉRAL",font=("DejaVu Sans",16,"bold"),foreground="#17365D").pack(anchor="w")
        ttk.Label(f,text=f"Bienvenue {self.user['nom']} — {datetime.now():%d/%m/%Y}",foreground="#667085").pack(anchor="w",pady=5)
        cards=ttk.Frame(f); cards.pack(fill="x",pady=18)
        metrics=[("Élèves","SELECT COUNT(*) FROM eleves"),("Classes","SELECT COUNT(*) FROM classes"),
                 ("Personnel","SELECT COUNT(*) FROM personnel"),("Paiements GNF","SELECT COALESCE(SUM(montant),0) FROM paiements"),
                 ("Dépenses GNF","SELECT COALESCE(SUM(montant),0) FROM depenses")]
        for i,(label,sql) in enumerate(metrics):
            with conn() as c: val=c.execute(sql).fetchone()[0]
            card=ttk.LabelFrame(cards,text=label,padding=16); card.grid(row=0,column=i,sticky="nsew",padx=5)
            cards.columnconfigure(i,weight=1)
            ttk.Label(card,text=f"{val:,.0f}" if isinstance(val,(float,int)) else str(val),
                      font=("DejaVu Sans",15,"bold"),foreground="#17365D").pack()
        ttk.Label(f,text="Raccourcis",font=("DejaVu Sans",12,"bold")).pack(anchor="w",pady=(22,8))
        row=ttk.Frame(f); row.pack(anchor="w")
        if "eleves" in ACCESS[self.role]: ttk.Button(row,text="Gérer les élèves",command=lambda:self.select_tab("Élèves")).pack(side="left",padx=4)
        if "notes" in ACCESS[self.role]: ttk.Button(row,text="Saisir les notes",command=lambda:self.select_tab("Notes et évaluations")).pack(side="left",padx=4)
        if "documents" in ACCESS[self.role]: ttk.Button(row,text="Générer les documents",command=lambda:self.select_tab("Documents PDF / Excel")).pack(side="left",padx=4)
        ttk.Label(f,text="Les indicateurs sont calculés à partir des données actuellement enregistrées.",foreground="#667085").pack(anchor="w",pady=20)

    def select_tab(self,name):
        for i in range(self.nb.index("end")):
            if self.nb.tab(i,"text")==name:self.nb.select(i);break

    def add_crud(self,table,fields):
        f=ttk.Frame(self.nb,padding=8); self.nb.add(f,text=LABELS[table])
        form=ttk.LabelFrame(f,text="Saisie / modification",padding=8); form.pack(fill="x")
        entries={}
        for i,(name,typ,label) in enumerate(fields):
            r,c=divmod(i,4)
            ttk.Label(form,text=label).grid(row=r*2,column=c,sticky="w",padx=4)
            e=ttk.Entry(form,width=24); e.grid(row=r*2+1,column=c,sticky="ew",padx=4,pady=(0,5))
            entries[name]=e; form.columnconfigure(c,weight=1)
        bar=ttk.Frame(f);bar.pack(fill="x",pady=5)
        cols=["id"]+[x[0] for x in fields]
        tree=ttk.Treeview(f,columns=cols,show="headings")
        for col in cols:
            label="ID" if col=="id" else next(x[2] for x in fields if x[0]==col)
            tree.heading(col,text=label);tree.column(col,width=125)
        tree.pack(fill="both",expand=True)
        selected={"id":None}
        def refresh():
            tree.delete(*tree.get_children())
            with conn() as c: rows=c.execute(f'SELECT * FROM "{table}" ORDER BY id DESC LIMIT 1000').fetchall()
            for r in rows:tree.insert("","end",values=[r[x] for x in ["id"]+[x[0] for x in fields]])
        def clear():
            for e in entries.values():e.delete(0,"end")
            selected["id"]=None
        def save():
            vals=[]
            try:
                for n,t,_ in fields:
                    raw=entries[n].get().strip()
                    if raw and t=="REAL":raw=float(raw.replace(",","."))
                    elif not raw:raw=None
                    vals.append(raw)
            except ValueError:
                messagebox.showerror("Erreur","Une valeur numérique est invalide.");return
            d={fields[i][0]:vals[i] for i in range(len(fields))}
            if table=="notes":
                # Les notes pondérées sont calculées au moment des relevés.
                if d["note"] is not None and not 0<=d["note"]<=20:
                    messagebox.showerror("Note invalide","La note doit être comprise entre 0 et 20.");return
            if table=="paiements" and (d["montant"] or 0)<=0:
                messagebox.showerror("Montant invalide","Le paiement doit être supérieur à zéro.");return
            with conn() as c:
                if selected["id"]:
                    c.execute(f'UPDATE "{table}" SET '+",".join(f'"{x[0]}"=?' for x in fields)+" WHERE id=?",vals+[selected["id"]])
                    action="Modification"
                else:
                    c.execute(f'INSERT INTO "{table}" ('+",".join(f'"{x[0]}"' for x in fields)+") VALUES ("+",".join("?" for _ in fields)+")",vals)
                    action="Ajout"
            audit(self.user["username"],action,LABELS[table])
            refresh();clear()
        def delete():
            if not selected["id"]:messagebox.showinfo("Suppression","Sélectionnez une ligne.");return
            if messagebox.askyesno("Confirmation","Supprimer cet enregistrement ?"):
                with conn() as c:c.execute(f'DELETE FROM "{table}" WHERE id=?',(selected["id"],))
                audit(self.user["username"],"Suppression",LABELS[table]);refresh();clear()
        def pick(event=None):
            sel=tree.selection()
            if not sel:return
            row=tree.item(sel[0],"values");selected["id"]=int(row[0])
            for i,(n,_,_) in enumerate(fields):
                entries[n].delete(0,"end")
                if row[i+1] not in ("","None"):entries[n].insert(0,row[i+1])
        def export():
            path=filedialog.asksaveasfilename(defaultextension=".csv",initialfile=f"{table}.csv",filetypes=[("CSV","*.csv")])
            if not path:return
            with conn() as c:rows=c.execute(f'SELECT * FROM "{table}"').fetchall()
            with open(path,"w",newline="",encoding="utf-8-sig") as out:
                w=csv.writer(out,delimiter=";");w.writerow(["id"]+[x[2] for x in fields])
                for r in rows:w.writerow([r["id"]]+[r[x[0]] for x in fields])
            messagebox.showinfo("Export",f"Export terminé : {path}")
        for label,cmd in [("Enregistrer",save),("Nouveau",clear),("Supprimer",delete),("Actualiser",refresh),("Exporter CSV",export)]:
            ttk.Button(bar,text=label,command=cmd).pack(side="left",padx=3)
        tree.bind("<<TreeviewSelect>>",pick);refresh()

    def add_documents(self):
        f=ttk.Frame(self.nb,padding=16);self.nb.add(f,text="Documents PDF / Excel")
        ttk.Label(f,text="ÉDITIONS SCOLAIRES ET ADMINISTRATIVES",font=("DejaVu Sans",15,"bold"),foreground="#17365D").pack(anchor="w")
        form=ttk.LabelFrame(f,text="Paramètres du document",padding=12);form.pack(fill="x",pady=12)
        fields={}
        for i,(lab,key) in enumerate([("Matricule élève","matricule"),("Période (mois/T1/S1/Année)","periode"),("Année scolaire","annee")]):
            ttk.Label(form,text=lab).grid(row=0,column=i,sticky="w",padx=5)
            e=ttk.Entry(form,width=28);e.grid(row=1,column=i,sticky="ew",padx=5,pady=4);fields[key]=e
        fields["annee"].insert(0,"2026-2027")
        ttk.Label(f,text="Les documents PDF affichent l'identité CS HAGAD et un emplacement de signature/cachet. Le logo graphique est intégré à l'en-tête.",
                  wraplength=1000).pack(anchor="w",pady=4)
        def student(matricule):
            with conn() as c:return c.execute("SELECT * FROM eleves WHERE matricule=?",(matricule,)).fetchone()
        def notes_data(matricule,period,year):
            with conn() as c:
                return c.execute("""SELECT matiere, AVG(note) note, MAX(coefficient) coeff
                    FROM notes WHERE matricule_eleve=? AND (?='' OR periode=?)
                    AND (?='' OR annee_scolaire=?) GROUP BY matiere ORDER BY matiere""",
                    (matricule,period,period,year,year)).fetchall()
        def pdf_bulletin():
            m=fields["matricule"].get().strip();p=fields["periode"].get().strip();y=fields["annee"].get().strip()
            s=student(m)
            if not s:messagebox.showerror("Élève introuvable","Vérifiez le matricule.");return
            data=notes_data(m,p,y)
            if not data:messagebox.showwarning("Aucune note","Aucune note trouvée pour cette période.");return
            weighted=sum((r["note"] or 0)*(r["coeff"] or 1) for r in data)
            coeff=sum((r["coeff"] or 1) for r in data);avg=weighted/coeff if coeff else 0
            ranking=rank_for_class(s["classe"],p,y)
            rank=next((i+1 for i,x in enumerate(ranking) if x[0]==m),"—")
            lines=[f"Élève : {s['nom']} {s['prenom']}  | Matricule : {m}",f"Classe : {s['classe']}  | Année scolaire : {y}",f"Période : {p}",
                   "","MATIÈRES — NOTES — COEFFICIENTS — NOTES PONDÉRÉES"]
            for r in data:lines.append(f"{r['matiere']} : {r['note']:.2f}/20 | Coeff. {r['coeff'] or 1} | {(r['note'] or 0)*(r['coeff'] or 1):.2f}")
            lines += ["",f"Moyenne générale : {avg:.2f}/20",f"Rang dans la classe : {rank}/{len(ranking)}","Décision / appréciation : ................................................................"]
            path=filedialog.asksaveasfilename(defaultextension=".pdf",initialfile=f"bulletin_{m}_{p}.pdf")
            if path:create_pdf("BULLETIN SCOLAIRE",lines,path,f"{SCHOOL} • Document scolaire");audit(self.user["username"],"PDF","Bulletin "+m);messagebox.showinfo("PDF créé",path)
        def pdf_releve():
            m=fields["matricule"].get().strip();p=fields["periode"].get().strip();y=fields["annee"].get().strip()
            s=student(m)
            if not s:messagebox.showerror("Élève introuvable","Matricule non trouvé.");return
            data=notes_data(m,p,y);lines=[f"Élève : {s['nom']} {s['prenom']} ({m})",f"Classe : {s['classe']}",f"Période : {p} • Année : {y}"]
            for r in data:lines.append(f"{r['matiere']} : {r['note']:.2f}/20 (coefficient {r['coeff'] or 1})")
            path=filedialog.asksaveasfilename(defaultextension=".pdf",initialfile=f"releve_{m}_{p}.pdf")
            if path:create_pdf("RELEVÉ DE NOTES",lines,path);audit(self.user["username"],"PDF","Relevé "+m);messagebox.showinfo("PDF créé",path)
        def receipt():
            m=fields["matricule"].get().strip();s=student(m)
            if not s:messagebox.showerror("Élève introuvable","Matricule non trouvé.");return
            with conn() as c:
                pays=c.execute("SELECT * FROM paiements WHERE matricule_eleve=? ORDER BY id DESC LIMIT 1",(m,)).fetchone()
                if not pays:messagebox.showwarning("Paiement absent","Aucun paiement enregistré pour cet élève.");return
                c.execute("UPDATE sequence_recu SET dernier=dernier+1 WHERE id=1")
                num=c.execute("SELECT dernier FROM sequence_recu WHERE id=1").fetchone()[0]
            lines=[f"Reçu N° : CH-{datetime.now():%Y}-{num:06d}",f"Reçu de : {s['nom']} {s['prenom']}",f"Matricule : {m}",f"Date : {pays['date_paiement']}",
                   f"Motif : {pays['motif']} / {pays['mois']}",f"Montant reçu : {pays['montant']:,.0f} GNF",f"Mode : {pays['mode']}",f"Référence : {pays['reference'] or ''}","Arrêté le présent reçu à la somme indiquée ci-dessus."]
            path=filedialog.asksaveasfilename(defaultextension=".pdf",initialfile=f"recu_CH_{num:06d}.pdf")
            if path:create_pdf("REÇU DE PAIEMENT",lines,path);audit(self.user["username"],"PDF",f"Reçu CH-{num:06d}");messagebox.showinfo("Reçu créé",path)
        def export_excel():
            try:from openpyxl import Workbook
            except ImportError:messagebox.showerror("Dépendance absente","Installez openpyxl : sudo apt install python3-openpyxl");return
            path=filedialog.asksaveasfilename(defaultextension=".xlsx",initialfile="rapport_cs_hagad.xlsx")
            if not path:return
            wb=Workbook();ws=wb.active;ws.title="Élèves"
            with conn() as c:
                rows=c.execute("SELECT matricule,classe,nom,prenom FROM eleves ORDER BY classe,nom").fetchall()
                pays=c.execute("SELECT COALESCE(SUM(montant),0) FROM paiements").fetchone()[0]
                dep=c.execute("SELECT COALESCE(SUM(montant),0) FROM depenses").fetchone()[0]
            ws.append(["Matricule","Classe","Nom","Prénom"])
            for r in rows:ws.append(list(r))
            wf=wb.create_sheet("Synthèse financière");wf.append(["Indicateur","Montant GNF"]);wf.append(["Recettes encaissées",pays]);wf.append(["Dépenses",dep]);wf.append(["Solde",pays-dep])
            wb.save(path);audit(self.user["username"],"Excel","Rapport financier et élèves");messagebox.showinfo("Excel créé",path)
        for text,cmd in [("Bulletin scolaire PDF",pdf_bulletin),("Relevé de notes PDF",pdf_releve),("Reçu de paiement PDF",receipt),("Rapport financier / élèves Excel",export_excel)]:
            ttk.Button(f,text=text,command=cmd).pack(anchor="w",pady=6,ipadx=8,ipady=5)

    def add_finance(self):
        f=ttk.Frame(self.nb,padding=16);self.nb.add(f,text="États financiers")
        ttk.Label(f,text="SYNTHÈSE FINANCIÈRE",font=("DejaVu Sans",15,"bold")).pack(anchor="w")
        tree=ttk.Treeview(f,columns=("type","montant"),show="headings",height=8)
        tree.heading("type",text="Indicateur");tree.heading("montant",text="Montant GNF")
        tree.pack(fill="x",pady=12)
        def refresh():
            tree.delete(*tree.get_children())
            with conn() as c:
                rec=c.execute("SELECT COALESCE(SUM(montant),0) FROM paiements").fetchone()[0]
                dep=c.execute("SELECT COALESCE(SUM(montant),0) FROM depenses").fetchone()[0]
                imp=c.execute("SELECT COALESCE(SUM(montant_total-paye),0) FROM fournisseurs").fetchone()[0]
            for k,v in [("Recettes encaissées",rec),("Dépenses",dep),("Solde de trésorerie",rec-dep),("Dettes fournisseurs estimées",imp)]:
                tree.insert("","end",values=(k,f"{v:,.0f}"))
        def pdf():
            rows=[f"{tree.item(i,'values')[0]} : {tree.item(i,'values')[1]} GNF" for i in tree.get_children()]
            p=filedialog.asksaveasfilename(defaultextension=".pdf",initialfile="etat_financier.pdf")
            if p:create_pdf("ÉTAT FINANCIER",rows,p);audit(self.user["username"],"PDF","État financier");messagebox.showinfo("PDF créé",p)
        ttk.Button(f,text="Actualiser",command=refresh).pack(side="left",padx=4)
        ttk.Button(f,text="Exporter l'état financier PDF",command=pdf).pack(side="left",padx=4)
        refresh()

    def add_users(self):
        f=ttk.Frame(self.nb,padding=12);self.nb.add(f,text="Utilisateurs")
        form=ttk.LabelFrame(f,text="Créer un compte utilisateur",padding=10);form.pack(fill="x")
        fields={}
        for i,(lab,key) in enumerate([("Identifiant","username"),("Nom complet","nom"),("Mot de passe","password")]):
            ttk.Label(form,text=lab).grid(row=0,column=i,sticky="w",padx=4)
            e=ttk.Entry(form,width=25,show="*" if key=="password" else "");e.grid(row=1,column=i,padx=4,pady=5);fields[key]=e
        ttk.Label(form,text="Rôle").grid(row=0,column=3,sticky="w")
        role=ttk.Combobox(form,values=ROLES,state="readonly",width=20);role.grid(row=1,column=3,padx=4);role.set("Secrétaire")
        tree=ttk.Treeview(f,columns=("id","username","nom","role","actif"),show="headings")
        for c in tree["columns"]:tree.heading(c,text=c.title());tree.column(c,width=160)
        tree.pack(fill="both",expand=True,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            with conn() as c:rows=c.execute("SELECT id,username,nom,role,actif FROM utilisateurs").fetchall()
            for r in rows:tree.insert("","end",values=tuple(r))
        def add():
            username=fields["username"].get().strip();password=fields["password"].get()
            if not username or len(password)<8:
                messagebox.showerror("Données invalides","Identifiant requis et mot de passe de 8 caractères minimum.");return
            salt,digest=pw_hash(password)
            try:
                with conn() as c:c.execute("INSERT INTO utilisateurs(username,nom,role,salt,password_hash) VALUES(?,?,?,?,?)",
                    (username,fields["nom"].get().strip(),role.get(),salt,digest))
                audit(self.user["username"],"Création utilisateur",username);refresh()
                for e in fields.values():e.delete(0,"end")
            except sqlite3.IntegrityError:messagebox.showerror("Erreur","Cet identifiant existe déjà.")
        def disable():
            sel=tree.selection()
            if not sel:return
            row=tree.item(sel[0],"values")
            if row[1]=="admin":messagebox.showwarning("Protection","Le compte admin initial ne peut pas être désactivé ici.");return
            with conn() as c:c.execute("UPDATE utilisateurs SET actif=0 WHERE id=?",(row[0],))
            audit(self.user["username"],"Désactivation utilisateur",row[1]);refresh()
        ttk.Button(form,text="Créer le compte",command=add).grid(row=1,column=4,padx=8)
        ttk.Button(f,text="Désactiver le compte sélectionné",command=disable).pack(anchor="w")
        refresh()

    def add_audit(self):
        f=ttk.Frame(self.nb,padding=12);self.nb.add(f,text="Journal d'audit")
        tree=ttk.Treeview(f,columns=("date","user","action","detail"),show="headings")
        for c,h in zip(tree["columns"],["Date / heure","Utilisateur","Action","Détail"]):
            tree.heading(c,text=h);tree.column(c,width=180)
        tree.pack(fill="both",expand=True)
        def refresh():
            tree.delete(*tree.get_children())
            with conn() as c:rows=c.execute("SELECT date_action,utilisateur,action,detail FROM audit ORDER BY id DESC LIMIT 2000").fetchall()
            for r in rows:tree.insert("","end",values=tuple(r))
        ttk.Button(f,text="Actualiser",command=refresh).pack(anchor="e",pady=5);refresh()

    def close(self):
        backup();audit(self.user["username"],"Déconnexion","Sauvegarde effectuée")
        self.root.destroy()

def main():
    init_db()
    # Sauvegarde de démarrage si une base existante est présente.
    backup()
    login_root=tk.Tk(); login=Login(login_root); login_root.mainloop()
    if login.user:
        root=tk.Tk();App(root,login.user);root.mainloop()

if __name__=="__main__":main()
